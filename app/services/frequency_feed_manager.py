"""
Frequency-based Feed Manager for Signal Service
Manages computation and delivery based on subscription frequencies
"""
import asyncio
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import json

from app.utils.logging_utils import log_info, log_error, log_warning
from app.utils.redis import get_redis_client


class FeedFrequency(Enum):
    """Supported feed frequencies"""
    REALTIME = "realtime"      # Every tick
    SECOND_1 = "1s"            # Every second
    SECOND_5 = "5s"            # Every 5 seconds
    SECOND_10 = "10s"          # Every 10 seconds
    SECOND_30 = "30s"          # Every 30 seconds
    MINUTE_1 = "1m"            # Every minute
    MINUTE_5 = "5m"            # Every 5 minutes
    MINUTE_15 = "15m"          # Every 15 minutes
    MINUTE_30 = "30m"          # Every 30 minutes
    HOUR_1 = "1h"              # Every hour
    
    @property
    def seconds(self) -> float:
        """Get frequency in seconds"""
        if self == FeedFrequency.REALTIME:
            return 0
        
        value = self.value
        if value.endswith('s'):
            return int(value[:-1])
        elif value.endswith('m'):
            return int(value[:-1]) * 60
        elif value.endswith('h'):
            return int(value[:-1]) * 3600
        return 1


class FrequencyFeedManager:
    """
    Manages signal computations based on subscription frequencies
    Coordinates with ticker_service frequency_manager for aligned processing
    """
    
    def __init__(self, signal_processor):
        self.signal_processor = signal_processor
        self.redis_client = None
        
        # Subscription tracking
        self.frequency_subscriptions = defaultdict(set)  # frequency -> set of (user_id, instrument_key, signal_type)
        self.user_frequencies = defaultdict(dict)  # user_id -> {instrument_key: {signal_type: frequency}}
        
        # Processing state
        self.last_processed = defaultdict(datetime)  # (frequency, instrument_key, signal_type) -> timestamp
        self.processing_tasks = {}  # frequency -> asyncio.Task
        self.is_running = False
        
        # Batch processing
        self.computation_batches = defaultdict(list)  # frequency -> [(user_id, instrument_key, signal_type)]
        
        # Performance tracking
        self.metrics = defaultdict(int)
        
    async def initialize(self):
        """Initialize frequency feed manager"""
        self.redis_client = await get_redis_client()
        log_info("FrequencyFeedManager initialized")
        
    async def start(self):
        """Start frequency-based processing"""
        self.is_running = True
        
        # Start processing tasks for each frequency
        for frequency in FeedFrequency:
            if frequency != FeedFrequency.REALTIME:
                task = asyncio.create_task(self._process_frequency(frequency))
                self.processing_tasks[frequency] = task
                
        log_info("FrequencyFeedManager started with all frequency processors")
        
    async def stop(self):
        """Stop all frequency processors"""
        self.is_running = False
        
        # Cancel all processing tasks
        for task in self.processing_tasks.values():
            task.cancel()
            
        # Wait for tasks to complete
        await asyncio.gather(*self.processing_tasks.values(), return_exceptions=True)
        
        log_info("FrequencyFeedManager stopped")
        
    async def update_subscription_frequency(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str,
        frequency: str
    ):
        """
        Update subscription frequency for a user
        
        Args:
            user_id: User identifier
            instrument_key: Instrument to subscribe
            signal_type: Type of signal (greeks, indicators, moneyness, market_profile)
            frequency: Desired frequency
        """
        try:
            # Parse frequency
            freq = FeedFrequency(frequency)
            
            # Remove from old frequency if exists
            old_freq = self._get_current_frequency(user_id, instrument_key, signal_type)
            if old_freq:
                self.frequency_subscriptions[old_freq].discard((user_id, instrument_key, signal_type))
                
            # Add to new frequency
            self.frequency_subscriptions[freq].add((user_id, instrument_key, signal_type))
            
            # Update user mapping
            if instrument_key not in self.user_frequencies[user_id]:
                self.user_frequencies[user_id][instrument_key] = {}
            self.user_frequencies[user_id][instrument_key][signal_type] = freq
            
            # Store in Redis for persistence
            await self._store_subscription_redis(user_id, instrument_key, signal_type, frequency)
            
            log_info(f"Updated frequency for {user_id}/{instrument_key}/{signal_type} to {frequency}")
            
            # If realtime, enable immediate processing
            if freq == FeedFrequency.REALTIME:
                await self._enable_realtime_processing(user_id, instrument_key, signal_type)
                
        except Exception as e:
            log_error(f"Error updating subscription frequency: {e}")
            
    async def remove_subscription(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str
    ):
        """Remove a subscription"""
        freq = self._get_current_frequency(user_id, instrument_key, signal_type)
        if freq:
            self.frequency_subscriptions[freq].discard((user_id, instrument_key, signal_type))
            
            if instrument_key in self.user_frequencies[user_id]:
                self.user_frequencies[user_id][instrument_key].pop(signal_type, None)
                if not self.user_frequencies[user_id][instrument_key]:
                    del self.user_frequencies[user_id][instrument_key]
                    
        await self._remove_subscription_redis(user_id, instrument_key, signal_type)
        
    async def _process_frequency(self, frequency: FeedFrequency):
        """Process signals for a specific frequency"""
        interval_seconds = frequency.seconds
        
        while self.is_running:
            try:
                start_time = datetime.utcnow()
                
                # Get all subscriptions for this frequency
                subscriptions = list(self.frequency_subscriptions[frequency])
                
                if subscriptions:
                    # Group by instrument and signal type for batch processing
                    batches = self._group_subscriptions(subscriptions)
                    
                    # Process each batch
                    tasks = []
                    for (instrument_key, signal_type), users in batches.items():
                        task = self._process_batch(
                            instrument_key, signal_type, users, frequency
                        )
                        tasks.append(task)
                        
                    # Wait for all batches to complete
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Track metrics
                    self.metrics[f'{frequency.value}_processed'] += len(subscriptions)
                    
                # Calculate next run time
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                sleep_time = max(0, interval_seconds - processing_time)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    log_warning(f"Processing for {frequency.value} took longer than interval: {processing_time}s")
                    
            except Exception as e:
                log_error(f"Error in frequency processor {frequency.value}: {e}")
                await asyncio.sleep(1)  # Brief pause before retry
                
    async def _process_batch(
        self,
        instrument_key: str,
        signal_type: str,
        users: List[str],
        frequency: FeedFrequency
    ):
        """Process a batch of users for the same instrument/signal"""
        try:
            # Check if we need to compute
            cache_key = (frequency, instrument_key, signal_type)
            last_processed = self.last_processed.get(cache_key)
            
            if last_processed:
                elapsed = (datetime.utcnow() - last_processed).total_seconds()
                if elapsed < frequency.seconds * 0.9:  # 90% of interval
                    return  # Skip, too soon
                    
            # Compute signal based on type
            result = await self._compute_signal(instrument_key, signal_type)
            
            if result:
                # Update last processed time
                self.last_processed[cache_key] = datetime.utcnow()
                
                # Publish to users
                await self._publish_to_users(
                    users, instrument_key, signal_type, result, frequency
                )
                
        except Exception as e:
            log_error(f"Error processing batch for {instrument_key}/{signal_type}: {e}")
            
    async def _compute_signal(
        self,
        instrument_key: str,
        signal_type: str
    ) -> Optional[Dict[str, Any]]:
        """Compute signal based on type"""
        
        if signal_type == "greeks":
            return await self._compute_greeks(instrument_key)
        elif signal_type == "indicators":
            return await self._compute_indicators(instrument_key)
        elif signal_type == "moneyness":
            return await self._compute_moneyness(instrument_key)
        elif signal_type == "market_profile":
            return await self._compute_market_profile(instrument_key)
        else:
            log_warning(f"Unknown signal type: {signal_type}")
            return None
            
    async def _compute_greeks(self, instrument_key: str) -> Optional[Dict]:
        """Compute Greeks for instrument"""
        # Check if moneyness-based
        if instrument_key.startswith("MONEYNESS@"):
            return await self._compute_moneyness_greeks(instrument_key)
            
        # Regular Greeks computation
        return await self.signal_processor.compute_greeks_for_instrument(instrument_key)
        
    async def _compute_moneyness_greeks(self, moneyness_key: str) -> Optional[Dict]:
        """Compute moneyness-based Greeks"""
        # Parse moneyness key
        parts = moneyness_key.split("@")
        if len(parts) != 4:
            return None
            
        _, underlying, moneyness_level, expiry_date = parts
        
        # Use moneyness processor
        return await self.signal_processor.moneyness_processor.calculate_moneyness_greeks(
            underlying, moneyness_level, expiry_date
        )
        
    async def _compute_indicators(self, instrument_key: str) -> Optional[Dict]:
        """Compute technical indicators"""
        # Get configured indicators for this instrument
        indicators = await self._get_configured_indicators(instrument_key)
        
        if indicators:
            return await self.signal_processor.compute_indicators_for_instrument(
                instrument_key, indicators
            )
        return None
        
    async def _compute_market_profile(self, instrument_key: str) -> Optional[Dict]:
        """Compute market profile"""
        # Default to 30m interval, 1d lookback
        return await self.signal_processor.market_profile_calculator.calculate_market_profile(
            instrument_key,
            interval="30m",
            lookback_period="1d",
            profile_type="volume"
        )
        
    async def _publish_to_users(
        self,
        users: List[str],
        instrument_key: str,
        signal_type: str,
        result: Dict,
        frequency: FeedFrequency
    ):
        """Publish results to subscribed users"""
        
        # Create message
        message = {
            "timestamp": datetime.utcnow().isoformat(),
            "instrument_key": instrument_key,
            "signal_type": signal_type,
            "frequency": frequency.value,
            "data": result
        }
        
        # Publish to each user's channel
        for user_id in users:
            channel = f"signal:{user_id}:{instrument_key}:{signal_type}"
            await self.redis_client.publish(channel, json.dumps(message))
            
        # Also store latest value
        cache_key = f"signal:latest:{instrument_key}:{signal_type}"
        await self.redis_client.setex(
            cache_key,
            300,  # 5 minute TTL
            json.dumps(message)
        )
        
    def _group_subscriptions(
        self,
        subscriptions: List[Tuple[str, str, str]]
    ) -> Dict[Tuple[str, str], List[str]]:
        """Group subscriptions by instrument and signal type"""
        groups = defaultdict(list)
        
        for user_id, instrument_key, signal_type in subscriptions:
            groups[(instrument_key, signal_type)].append(user_id)
            
        return groups
        
    def _get_current_frequency(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str
    ) -> Optional[FeedFrequency]:
        """Get current frequency for a subscription"""
        if user_id in self.user_frequencies:
            if instrument_key in self.user_frequencies[user_id]:
                return self.user_frequencies[user_id][instrument_key].get(signal_type)
        return None
        
    async def _enable_realtime_processing(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str
    ):
        """Enable real-time processing for a subscription"""
        # Notify signal processor to enable real-time updates
        await self.signal_processor.enable_realtime_signal(
            user_id, instrument_key, signal_type
        )
        
    async def _store_subscription_redis(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str,
        frequency: str
    ):
        """Store subscription in Redis"""
        key = f"signal:subscription:{user_id}:{instrument_key}:{signal_type}"
        value = {
            "frequency": frequency,
            "created_at": datetime.utcnow().isoformat()
        }
        await self.redis_client.setex(key, 86400 * 7, json.dumps(value))  # 7 day TTL
        
    async def _remove_subscription_redis(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str
    ):
        """Remove subscription from Redis"""
        key = f"signal:subscription:{user_id}:{instrument_key}:{signal_type}"
        await self.redis_client.delete(key)
        
    async def _get_configured_indicators(self, instrument_key: str) -> List[Dict]:
        """Get configured indicators for an instrument"""
        # This would fetch from configuration
        # For now, return common indicators
        return [
            {"name": "rsi", "params": {"period": 14}},
            {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"name": "bbands", "params": {"period": 20, "std_dev": 2}}
        ]
        
    async def get_subscription_stats(self) -> Dict[str, Any]:
        """Get subscription statistics"""
        stats = {
            "total_subscriptions": sum(len(subs) for subs in self.frequency_subscriptions.values()),
            "by_frequency": {},
            "by_signal_type": defaultdict(int),
            "active_users": len(self.user_frequencies),
            "metrics": dict(self.metrics)
        }
        
        # Count by frequency
        for freq, subs in self.frequency_subscriptions.items():
            stats["by_frequency"][freq.value] = len(subs)
            
            # Count by signal type
            for _, _, signal_type in subs:
                stats["by_signal_type"][signal_type] += 1
                
        return stats
        
    async def sync_with_ticker_frequency(self, ticker_frequency_data: Dict):
        """
        Sync with ticker service frequency settings
        Ensures signal computations align with ticker data availability
        """
        # This would coordinate with ticker_service to ensure
        # we don't compute signals more frequently than data arrives
        logger.info("Frequency synchronization with ticker service - implementation would coordinate with ticker_service API")
        # Production implementation would call ticker_service configuration endpoints