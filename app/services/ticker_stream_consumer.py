"""
Ticker Stream Consumer for Signal Service
Consumes market data from ticker service's sharded Redis streams
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.signal_redis_manager import signal_redis_manager
from app.utils.logging_utils import log_error, log_info, log_warning

logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Represents a single tick from ticker service"""
    instrument_key: str
    ltp: float
    timestamp: datetime
    status: str
    source: str
    volume: int | None = None
    bid: float | None = None
    ask: float | None = None


class TickerStreamConsumer:
    """
    Consumes market data from ticker service's sharded streams
    Designed to work with worker affinity for optimal performance
    """

    # Match ticker service's shard configuration
    NUM_SHARDS = 10

    def __init__(self, worker_id: str, assigned_symbols: set[str]):
        self.worker_id = worker_id
        self.assigned_symbols = assigned_symbols
        self.redis_manager = signal_redis_manager
        self.consumer_group = f"signal_processors_{worker_id}"
        self.consumer_name = f"signal_worker_{worker_id}"

        # Calculate which shards this worker should consume from
        self.assigned_shards = self._calculate_assigned_shards()

        # Track processing state
        self.is_consuming = False
        self.processed_count = 0
        self.error_count = 0

        log_info(f"TickerStreamConsumer initialized for worker {worker_id} with {len(assigned_symbols)} symbols")
        log_info(f"Assigned shards: {self.assigned_shards}")

    def _calculate_assigned_shards(self) -> set[int]:
        """Calculate which shards contain our assigned symbols"""
        shards = set()
        for symbol in self.assigned_symbols:
            # Use same hashing logic as ticker service
            shard = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % self.NUM_SHARDS
            shards.add(shard)
        return shards

    def _get_symbol_shard(self, instrument_key: str) -> int:
        """Get shard number for an instrument key"""
        return int(hashlib.sha256(instrument_key.encode()).hexdigest(), 16) % self.NUM_SHARDS

    async def start_consuming(self):
        """Start consuming from assigned shards"""
        if self.is_consuming:
            log_warning(f"Consumer already running for worker {self.worker_id}")
            return

        self.is_consuming = True
        log_info(f"Starting ticker stream consumption for worker {self.worker_id}")

        # Create tasks for each assigned shard
        tasks = []
        for shard in self.assigned_shards:
            task = asyncio.create_task(self._consume_shard(shard))
            tasks.append(task)

        # Run all shard consumers concurrently
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log_error(f"Error in ticker stream consumption: {e}")
        finally:
            self.is_consuming = False

    async def _consume_shard(self, shard: int):
        """Consume from a specific shard stream"""
        stream_key = f"stream:shard:{shard}"
        log_info(f"Worker {self.worker_id} starting consumption from {stream_key}")

        # Create consumer group if it doesn't exist
        try:
            await self.redis_manager.redis_client.xgroup_create(
                stream_key, self.consumer_group, id="0"
            )
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                log_error(f"Failed to create consumer group: {e}")

        while self.is_consuming:
            try:
                # Read messages from stream
                messages = await self.redis_manager.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {stream_key: ">"},  # Read only new messages
                    count=100,  # Process up to 100 messages at a time
                    block=1000  # Block for 1 second if no messages
                )

                for stream, stream_messages in messages:
                    for msg_id, data in stream_messages:
                        try:
                            # Process the tick
                            await self._process_tick(data, msg_id.decode('utf-8'), stream_key)

                            # Acknowledge the message
                            await self.redis_manager.redis_client.xack(
                                stream_key, self.consumer_group, msg_id
                            )

                        except Exception as e:
                            self.error_count += 1
                            log_error(f"Error processing tick: {e}")

            except Exception as e:
                if "MOVED" in str(e):
                    # Redis cluster redirect - this is expected
                    continue
                log_error(f"Error consuming from shard {shard}: {e}")
                await asyncio.sleep(1)  # Back off on error

    async def _process_tick(self, data: dict[bytes, bytes], msg_id: str, stream_key: str):
        """Process a single tick from the stream"""
        try:
            # Decode tick data
            tick_data = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in data.items()
            }

            instrument_key = tick_data['instrument_key']

            # Check if this symbol is assigned to us
            if instrument_key not in self.assigned_symbols:
                # Skip symbols not assigned to this worker
                return

            # Parse tick
            tick = TickData(
                instrument_key=instrument_key,
                ltp=float(tick_data['ltp']),
                timestamp=datetime.fromisoformat(tick_data['timestamp']),
                status=tick_data.get('status', 'U'),
                source=tick_data.get('source', 'ticker_service'),
                volume=int(tick_data['volume']) if 'volume' in tick_data else None,
                bid=float(tick_data['bid']) if 'bid' in tick_data else None,
                ask=float(tick_data['ask']) if 'ask' in tick_data else None
            )

            self.processed_count += 1

            # Process the tick (implement your signal logic here)
            await self._calculate_signals(tick)

            # Log progress periodically
            if self.processed_count % 1000 == 0:
                log_info(f"Worker {self.worker_id} processed {self.processed_count} ticks")

        except Exception as e:
            log_error(f"Failed to process tick {msg_id}: {e}")
            raise

    async def _calculate_signals(self, tick: TickData):
        """Calculate signals based on the tick data"""
        # This is where you would:
        # 1. Update technical indicators
        # 2. Check for signal conditions
        # 3. Publish signals if triggered

        # For now, just cache the latest price
        cache_key = f"signal:cache:{tick.instrument_key}:latest"
        await self.redis_manager.set_with_retry(
            cache_key,
            json.dumps({
                "ltp": tick.ltp,
                "timestamp": tick.timestamp.isoformat(),
                "volume": tick.volume
            }),
            ex=300  # 5 minute TTL
        )

    async def update_assigned_symbols(self, new_symbols: set[str]):
        """Update the assigned symbols and recalculate shards"""
        self.assigned_symbols = new_symbols
        self.assigned_shards = self._calculate_assigned_shards()

        log_info(f"Updated assigned symbols for worker {self.worker_id}: {len(new_symbols)} symbols, {len(self.assigned_shards)} shards")

        # If consumer is running, it will pick up changes on next iteration

    async def stop_consuming(self):
        """Stop consuming from streams"""
        self.is_consuming = False
        log_info(f"Stopping ticker stream consumer for worker {self.worker_id}")

    def get_metrics(self) -> dict[str, Any]:
        """Get consumer metrics"""
        return {
            "worker_id": self.worker_id,
            "assigned_symbols": len(self.assigned_symbols),
            "assigned_shards": list(self.assigned_shards),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(1, self.processed_count),
            "is_consuming": self.is_consuming
        }


class TickerChannelSubscriber:
    """
    Alternative consumer that subscribes to Redis pub/sub channels
    Used for real-time tick updates with lower latency
    """

    def __init__(self, worker_id: str, assigned_symbols: set[str]):
        self.worker_id = worker_id
        self.assigned_symbols = assigned_symbols
        self.redis_manager = signal_redis_manager
        self.pubsub = None
        self.is_subscribed = False

        log_info(f"TickerChannelSubscriber initialized for worker {worker_id}")

    async def start_subscribing(self):
        """Start subscribing to ticker channels"""
        if self.is_subscribed:
            return

        try:
            # Create pubsub instance
            self.pubsub = self.redis_manager.redis_client.pubsub()

            # Subscribe to channels for assigned symbols
            channels = [f"ticker:{symbol}" for symbol in self.assigned_symbols]
            if channels:
                await self.pubsub.subscribe(*channels)
                self.is_subscribed = True

                log_info(f"Subscribed to {len(channels)} ticker channels")

                # Start listening for messages
                asyncio.create_task(self._listen_for_ticks())

        except Exception as e:
            log_error(f"Failed to subscribe to ticker channels: {e}")
            raise

    async def _listen_for_ticks(self):
        """Listen for tick updates on subscribed channels"""
        while self.is_subscribed:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

                if message:
                    await self._process_channel_message(message)

            except Exception as e:
                if "pubsub connection not set" not in str(e):
                    log_error(f"Error listening for ticks: {e}")
                await asyncio.sleep(0.1)

    async def _process_channel_message(self, message: dict[str, Any]):
        """Process a message from ticker channel"""
        try:
            channel = message['channel'].decode('utf-8')
            instrument_key = channel.replace('ticker:', '')

            # Parse tick data
            tick_data = json.loads(message['data'])

            # Create tick object
            tick = TickData(
                instrument_key=instrument_key,
                ltp=tick_data['ltp'],
                timestamp=datetime.fromisoformat(tick_data['timestamp']),
                status=tick_data.get('status', 'U'),
                source='ticker_channel',
                volume=tick_data.get('volume'),
                bid=tick_data.get('bid'),
                ask=tick_data.get('ask')
            )

            # Process the tick
            await self._process_realtime_tick(tick)

        except Exception as e:
            log_error(f"Failed to process channel message: {e}")

    async def _process_realtime_tick(self, tick: TickData):
        """Process real-time tick for immediate signal generation"""
        try:
            # Process tick through signal processor service - use singleton with proper initialization
            from app.services.signal_processor import get_signal_processor

            processor = await get_signal_processor()  # Get properly initialized singleton
            # Submit tick for processing using correct method name
            await processor.process_tick_async(tick.instrument_key, tick.to_dict())
            logger.debug(f"Processed realtime tick for {tick.instrument_key}")

        except Exception as e:
            logger.error(f"Error processing realtime tick: {e}")
            # Don't raise - continue processing other ticks

    async def update_subscriptions(self, new_symbols: set[str]):
        """Update channel subscriptions"""
        if not self.pubsub:
            return

        # Calculate channels to add/remove
        old_channels = {f"ticker:{s}" for s in self.assigned_symbols}
        new_channels = {f"ticker:{s}" for s in new_symbols}

        to_unsubscribe = old_channels - new_channels
        to_subscribe = new_channels - old_channels

        # Update subscriptions
        if to_unsubscribe:
            await self.pubsub.unsubscribe(*to_unsubscribe)

        if to_subscribe:
            await self.pubsub.subscribe(*to_subscribe)

        self.assigned_symbols = new_symbols
        log_info(f"Updated subscriptions: +{len(to_subscribe)}, -{len(to_unsubscribe)}")

    async def stop_subscribing(self):
        """Stop subscribing to channels"""
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
            self.pubsub = None

        self.is_subscribed = False
        log_info(f"Stopped ticker channel subscriber for worker {self.worker_id}")
