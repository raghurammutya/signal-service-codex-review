"""Core SignalProcessor for processing tick data and computing signals"""
import asyncio
import json
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import psutil

from app.adapters import EnhancedTickerAdapter
from app.core.config import settings
from app.errors import ComputationError, handle_computation_error
from app.schemas.config_schema import ComputationResult, SignalConfigData, TickProcessingContext
from app.utils.logging_utils import log_error, log_exception, log_info, log_warning
from app.utils.redis import get_redis_client
from app.utils.resilience import CircuitBreaker, CircuitBreakerConfig


class SignalProcessor:
    """
    Core signal processor responsible for:
    - Consuming tick data from Redis Streams
    - Processing configurations from subscription_manager
    - Computing signals (Greeks, Technical Indicators, Custom Functions)
    - Publishing results to Redis Streams/Lists
    """

    def __init__(self):
        self.redis_client = None
        self.timescale_session_factory = None
        self.consumer_group = settings.CONSUMER_GROUP_NAME
        self.consumer_name = settings.CONSUMER_NAME

        # Component dependencies (will be injected)
        self.config_handler = None
        self.greeks_calculator = None
        self.realtime_greeks_calculator = None
        self.pandas_ta_executor = None
        self.external_function_executor = None
        self.ticker_adapter = None  # Enhanced ticker adapter

        # New components
        self.local_moneyness_calculator = None
        self.market_profile_calculator = None
        self.frequency_feed_manager = None

        # Processing state
        self.is_running = False
        self.active_streams = set()
        self.active_instruments = set()  # Track instruments we're monitoring
        self.processing_metrics = defaultdict(int)

        # Circuit breakers for external dependencies
        self.redis_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30.0,
                expected_exception=(Exception,),
                name="redis_circuit"
            )
        )
        self.timescale_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60.0,
                expected_exception=(Exception,),
                name="timescale_circuit"
            )
        )

        log_info("SignalProcessor initialized")

    async def initialize(self, app_state):
        """Initialize processor with shared connections and dependencies"""
        try:
            # Get shared connections
            self.redis_client = await get_redis_client()

            # Initialize component dependencies
            from app.repositories.signal_repository import SignalRepository
            from app.services.config_handler import ConfigHandler
            from app.services.external_function_executor import ExternalFunctionExecutor
            from app.services.flexible_timeframe_manager import FlexibleTimeframeManager
            from app.services.greeks_calculator import GreeksCalculator
            from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
            from app.services.moneyness_historical_processor import MoneynessHistoricalProcessor
            from app.services.pandas_ta_executor import PandasTAExecutor
            from app.services.realtime_greeks_calculator import RealTimeGreeksCalculator

            self.config_handler = ConfigHandler(self.redis_client)
            self.greeks_calculator = GreeksCalculator()
            self.realtime_greeks_calculator = RealTimeGreeksCalculator(self.redis_client)
            self.pandas_ta_executor = PandasTAExecutor(self.redis_client)
            self.external_function_executor = ExternalFunctionExecutor()

            # Initialize moneyness components - instrument_client will be set later in initialize()
            from app.clients.client_factory import get_client_manager
            manager = get_client_manager()
            self.instrument_client = await manager.get_client('instrument_service')

            self.moneyness_calculator = MoneynessAwareGreeksCalculator(self.instrument_client)
            self.signal_repository = SignalRepository()
            self.timeframe_manager = FlexibleTimeframeManager()
            self.moneyness_processor = MoneynessHistoricalProcessor(
                self.moneyness_calculator,
                self.signal_repository,
                self.timeframe_manager,
                self.instrument_client
            )

            # Initialize new components
            from app.services.broker_symbol_converter import BrokerSymbolConverter
            from app.services.frequency_feed_manager import FrequencyFeedManager
            from app.services.market_profile_calculator import MarketProfileCalculator
            from app.services.moneyness_calculator_local import LocalMoneynessCalculator

            self.local_moneyness_calculator = LocalMoneynessCalculator()
            self.market_profile_calculator = MarketProfileCalculator(self.signal_repository)
            self.frequency_feed_manager = FrequencyFeedManager(self)
            self.broker_symbol_converter = BrokerSymbolConverter()

            # Initialize local moneyness with rules from instrument service
            await self._initialize_local_moneyness()

            # Initialize frequency feed manager
            await self.frequency_feed_manager.initialize()

            # Initialize enhanced ticker adapter
            self.ticker_adapter = EnhancedTickerAdapter()

            # Store reference to subscription client (will be set later)
            self.subscription_client = None

            # Store reference in app state if provided
            if app_state:
                app_state.signal_processor = self

            log_info("SignalProcessor fully initialized with all dependencies")

        except Exception as e:
            log_exception(f"Failed to initialize SignalProcessor: {e}")
            raise

    async def _initialize_local_moneyness(self):
        """Initialize local moneyness calculator with rules from instrument service"""
        try:
            # Get moneyness configuration from instrument service
            config = await self.instrument_client.get_moneyness_configuration()

            if config:
                # Update local calculator with thresholds
                self.local_moneyness_calculator.thresholds = config.get('thresholds',
                    self.local_moneyness_calculator.thresholds)

                log_info("Local moneyness calculator initialized with instrument service rules")
            else:
                log_warning("Using default moneyness thresholds")

        except Exception as e:
            log_error(f"Error initializing local moneyness: {e}")
            # Continue with defaults

    async def compute_greeks_with_quota_check(self, user_id: str, symbols: list[str], context: dict = None) -> dict:
        """
        Compute Greeks with subscription quota validation

        Args:
            user_id: User requesting computation
            symbols: list of option symbols
            context: Additional context for computation

        Returns:
            dict with computation results or error
        """
        try:
            if not self.subscription_client:
                log_warning("No subscription client available, skipping quota check")
                return await self._compute_greeks_internal(symbols, context)

            # 1. Check feature access
            has_greeks_access = await self.subscription_client.check_feature_access(user_id, "greeks_calculation")
            if not has_greeks_access:
                raise ComputationError("Greeks calculation not available in user's subscription")

            # 2. Request resource allocation
            allocation_request = {
                "computation_type": "greeks_bulk",
                "symbols": symbols,
                "estimated_duration_ms": len(symbols) * 50,  # Estimate 50ms per symbol
                "data_sources": ["option_chain", "underlying_price", "volatility"]
            }

            allocation = await self.subscription_client.allocate_signal_resources(user_id, allocation_request)

            if not allocation.get("granted", False):
                raise ComputationError(f"Resource allocation denied: {allocation.get('reason')}")

            # 3. Perform computation with allocated resources
            start_time = time.time()
            log_info(f"🧮 Computing Greeks for {len(symbols)} symbols for user {user_id}")

            results = await self._compute_greeks_internal(symbols, context)

            computation_time_ms = (time.time() - start_time) * 1000

            # 4. Record usage
            usage_data = {
                "signal_type": "greeks",
                "computation_count": len(symbols),
                "symbols": symbols,
                "execution_time_ms": computation_time_ms,
                "memory_used_mb": self._get_current_memory_usage(),
                "data_points_consumed": len(results.get("results", [])),
                "worker_id": allocation.get("worker_id", "unknown"),
                "quality": "high" if results.get("error_count", 0) == 0 else "medium"
            }

            await self.subscription_client.update_signal_usage(user_id, usage_data)

            log_info(f"✅ Greeks computation completed for user {user_id}, time: {computation_time_ms:.1f}ms")

            return {
                "success": True,
                "results": results,
                "computation_metrics": {
                    "symbols_processed": len(symbols),
                    "execution_time_ms": computation_time_ms,
                    "allocation_id": allocation.get("allocation_id")
                }
            }

        except Exception as e:
            log_exception(f"Greeks computation failed for user {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def _compute_greeks_internal(self, symbols: list[str], context: dict = None) -> dict:
        """Internal Greeks computation without quota checks"""
        try:
            # Use existing Greeks calculation logic
            if self.greeks_calculator:
                return await self.greeks_calculator.calculate_historical_greeks_parallel(symbols)
            raise ComputationError("Greeks calculator not available")
        except Exception as e:
            log_exception(f"Internal Greeks computation failed: {e}")
            raise

    async def compute_technical_indicators_with_quota_check(self, user_id: str, symbols: list[str], indicators: list[dict]) -> dict:
        """
        Compute technical indicators with subscription quota validation

        Args:
            user_id: User requesting computation
            symbols: list of symbols
            indicators: list of indicator configurations

        Returns:
            dict with computation results or error
        """
        try:
            if not self.subscription_client:
                log_warning("No subscription client available, skipping quota check")
                return await self._compute_technical_indicators_internal(symbols, indicators)

            # 1. Request resource allocation
            allocation_request = {
                "computation_type": "technical_indicators",
                "symbols": symbols,
                "estimated_duration_ms": len(symbols) * len(indicators) * 20,  # Estimate 20ms per symbol/indicator
                "data_sources": ["market_data", "historical_data"]
            }

            allocation = await self.subscription_client.allocate_signal_resources(user_id, allocation_request)

            if not allocation.get("granted", False):
                raise ComputationError(f"Resource allocation denied: {allocation.get('reason')}")

            # 2. Perform computation
            start_time = time.time()
            log_info(f"📊 Computing {len(indicators)} indicators for {len(symbols)} symbols for user {user_id}")

            results = await self._compute_technical_indicators_internal(symbols, indicators)

            computation_time_ms = (time.time() - start_time) * 1000

            # 3. Record usage
            usage_data = {
                "signal_type": "technical_indicators",
                "computation_count": len(symbols) * len(indicators),
                "symbols": symbols,
                "execution_time_ms": computation_time_ms,
                "data_points_consumed": len(results.get("results", [])),
                "worker_id": allocation.get("worker_id", "unknown")
            }

            await self.subscription_client.update_signal_usage(user_id, usage_data)

            log_info(f"✅ Technical indicators completed for user {user_id}, time: {computation_time_ms:.1f}ms")

            return {
                "success": True,
                "results": results,
                "computation_metrics": {
                    "symbols_processed": len(symbols),
                    "indicators_computed": len(indicators),
                    "execution_time_ms": computation_time_ms
                }
            }

        except Exception as e:
            log_exception(f"Technical indicators computation failed for user {user_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _compute_technical_indicators_internal(self, symbols: list[str], indicators: list[dict]) -> dict:
        """Internal technical indicators computation without quota checks"""
        try:
            # Use existing TA executor logic
            if self.pandas_ta_executor:
                results = []
                computed_count = 0

                for symbol in symbols:
                    try:
                        # Get real market data - fail fast if unavailable (no synthetic fallback)
                        market_data = await self._get_latest_market_data(symbol)
                        if not market_data:
                            log_error(f"No market data available for technical indicators: {symbol}")
                            continue  # Skip this symbol

                        # Create processing context for the symbol using real market data
                        context = TickProcessingContext(
                            tick_data=market_data,  # Required field - only real data
                            instrument_key=symbol,
                            timestamp=datetime.utcnow()
                        )

                        # Create basic configuration for indicators
                        from app.schemas.config_schema import (
                            FrequencyType,
                            IntervalType,
                            SignalConfigData,
                            TechnicalIndicatorConfig,
                        )

                        # Convert indicators list to proper config format using correct schema fields
                        indicator_configs = []
                        for indicator_dict in indicators:
                            indicator_config = TechnicalIndicatorConfig(
                                name=indicator_dict.get('indicator', 'sma'),  # Correct field name
                                parameters=indicator_dict.get('parameters', {}),
                                output_key=indicator_dict.get('indicator', 'sma')  # Required field
                            )
                            indicator_configs.append(indicator_config)

                        config_data = SignalConfigData(
                            instrument_key=symbol,  # Required field
                            interval=IntervalType.FIVE_MINUTE,  # Required field
                            frequency=FrequencyType.EVERY_MINUTE,  # Required field
                            technical_indicators=indicator_configs
                        )

                        # Execute technical indicators
                        if config_data.technical_indicators:
                            for indicator_config in config_data.technical_indicators:
                                try:
                                    ta_result = await self.pandas_ta_executor.execute_indicators(
                                        config_data, context
                                    )
                                    if ta_result:
                                        results.append({
                                            "symbol": symbol,
                                            "indicator": indicator_config.name,
                                            "result": ta_result,
                                            "timestamp": datetime.utcnow().isoformat()
                                        })
                                        computed_count += 1
                                except Exception as e:
                                    log_warning(f"Failed to compute {indicator_config.name} for {symbol}: {e}")

                    except Exception as e:
                        log_warning(f"Failed to process symbol {symbol}: {e}")

                return {"results": results, "computed_count": computed_count}
            raise ComputationError("Technical indicators executor not available")
        except Exception as e:
            log_exception(f"Internal technical indicators computation failed: {e}")
            raise

    async def start_consuming_redis_streams(self):
        """Start consuming tick data from Redis Streams"""
        self.is_running = True
        log_info("Starting Redis Streams consumption")

        try:
            # Load initial configurations
            await self.load_initial_configurations()

            # Start configuration update consumer
            asyncio.create_task(self.consume_config_updates())

            # Start tick data consumer
            await self.consume_tick_streams()

        except Exception as e:
            log_exception(f"Error in Redis Streams consumption: {e}")
            self.is_running = False
            raise

    async def load_initial_configurations(self):
        """Load initial configurations from Redis cache"""
        try:
            log_info("Loading initial configurations from Redis")

            # Get all config keys
            config_pattern = "config:*"
            config_keys = []

            async for key in self.redis_client.scan_iter(match=config_pattern):
                config_keys.append(key.decode() if isinstance(key, bytes) else key)

            log_info(f"Found {len(config_keys)} cached configurations")

            # Load and process each configuration
            for key in config_keys:
                try:
                    config_data = await self.redis_client.get(key)
                    if config_data:
                        config_json = json.loads(config_data)
                        await self.config_handler.apply_config(config_json)
                except Exception as e:
                    log_exception(f"Failed to load config from {key}: {e}")

        except Exception as e:
            log_exception(f"Failed to load initial configurations: {e}")

    async def consume_config_updates(self):
        """Consume configuration updates from Redis Stream"""
        stream_name = settings.REDIS_CONFIG_STREAM

        try:
            # Create consumer group if not exists
            try:
                await self.redis_client.xgroup_create(
                    stream_name, self.consumer_group, id='0', mkstream=True
                )
            except Exception as e:
                # Only ignore BUSYGROUP error, log all others
                error_str = str(e).upper()
                if 'BUSYGROUP' not in error_str:
                    log_error(f"Failed to create consumer group for {stream_name}: {e}")
                # BUSYGROUP means group already exists, which is expected

            log_info(f"Starting configuration updates consumer for stream: {stream_name}")

            while self.is_running:
                try:
                    # Read from stream
                    messages = await self.redis_client.xreadgroup(
                        self.consumer_group,
                        f"{self.consumer_name}_config",
                        {stream_name: '>'},
                        count=1,
                        block=settings.STREAM_READ_TIMEOUT_MS
                    )

                    for _stream, msgs in messages:
                        for msg_id, fields in msgs:
                            await self.process_config_update_message(msg_id, fields)

                            # Acknowledge message
                            await self.redis_client.xack(stream_name, self.consumer_group, msg_id)

                except TimeoutError:
                    continue
                except Exception as e:
                    log_exception(f"Error consuming config updates: {e}")
                    await asyncio.sleep(5)

        except Exception as e:
            log_exception(f"Fatal error in config updates consumer: {e}")

    async def process_config_update_message(self, msg_id: str, fields: dict):
        """Process a configuration update message"""
        try:
            # Extract message data
            config_json = fields.get(b'config_json') or fields.get('config_json')
            action = fields.get(b'action') or fields.get('action')

            if isinstance(config_json, bytes):
                config_json = config_json.decode()
            if isinstance(action, bytes):
                action = action.decode()

            config_data = json.loads(config_json)

            log_info(f"Processing config update: action={action}, instrument={config_data.get('instrument_key')}")

            # Delegate to config handler
            await self.config_handler.process_config_update(config_data, action)

        except Exception as e:
            log_exception(f"Failed to process config update message {msg_id}: {e}")

    async def consume_tick_streams(self):
        """Consume tick data from multiple Redis Streams"""
        log_info("Starting tick data streams consumption")

        while self.is_running:
            try:
                # Get active configurations to determine which streams to monitor
                active_configs = await self.config_handler.get_active_configs()

                # Use sharded streams (same format as ticker_service)
                # This matches ticker_service's stream:shard:* format
                NUM_SHARDS = 10
                required_streams = {f"stream:shard:{i}" for i in range(NUM_SHARDS)}

                # Store active instrument keys for filtering
                self.active_instruments = set()
                for config in active_configs.values():
                    instrument_key = config.get('instrument_key')
                    if instrument_key:
                        self.active_instruments.add(instrument_key)

                # Only monitor shards if we have active configurations
                if not self.active_instruments:
                    required_streams = set()

                # Create consumer groups for new streams
                for stream_name in required_streams:
                    if stream_name not in self.active_streams:
                        try:
                            await self.redis_client.xgroup_create(
                                stream_name, self.consumer_group, id='0', mkstream=True
                            )
                            self.active_streams.add(stream_name)
                            log_info(f"Added stream to monitoring: {stream_name}")
                        except Exception as e:
                            # Only ignore BUSYGROUP error, log all others
                            error_str = str(e).upper()
                            if 'BUSYGROUP' not in error_str:
                                log_error(f"Failed to create consumer group for {stream_name}: {e}")
                            # BUSYGROUP means group already exists, which is expected

                # Read from all active streams
                if self.active_streams:
                    stream_dict = {stream: '>' for stream in self.active_streams}

                    messages = await self.redis_client.xreadgroup(
                        self.consumer_group,
                        self.consumer_name,
                        stream_dict,
                        count=settings.STREAM_READ_COUNT,
                        block=settings.STREAM_READ_TIMEOUT_MS
                    )

                    # Process messages in parallel, filtering for active instruments
                    tasks = []
                    for stream, msgs in messages:
                        for msg_id, fields in msgs:
                            # Decode fields to check instrument_key
                            decoded_fields = {
                                k.decode() if isinstance(k, bytes) else k:
                                v.decode() if isinstance(v, bytes) else v
                                for k, v in fields.items()
                            }

                            # Only process if instrument is in our active configurations
                            instrument_key = decoded_fields.get('instrument_key')
                            if instrument_key in self.active_instruments:
                                # Pass original fields since process_tick_message handles decoding
                                task = self.process_tick_message(stream.decode(), msg_id, fields)
                                tasks.append(task)

                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # No active streams, wait a bit
                    await asyncio.sleep(1)

            except TimeoutError:
                continue
            except Exception as e:
                log_exception(f"Error in tick streams consumption: {e}")
                await asyncio.sleep(5)

    async def process_tick_message(self, stream_name: str, msg_id: str, fields: dict):
        """Process a single tick message"""
        start_time = time.time()

        try:
            # Extract tick data
            tick_data = {}
            for key, value in fields.items():
                if isinstance(key, bytes):
                    key = key.decode()
                if isinstance(value, bytes):
                    value = value.decode()
                tick_data[key] = value

            # Check if tick is unprocessed
            state = tick_data.get('state', 'U')
            if state != 'U':
                # Already processed, just acknowledge
                await self.redis_client.xack(stream_name, self.consumer_group, msg_id)
                return

            # Extract instrument key from stream name
            instrument_key = stream_name.replace(settings.REDIS_TICK_STREAM_PREFIX, '')

            # Process the tick
            await self.process_tick_async(instrument_key, tick_data)

            # Mark as processed and republish
            tick_data['state'] = 'P'
            tick_data['processed_at'] = datetime.utcnow().isoformat()
            tick_data['processor_id'] = self.consumer_name

            await self.redis_client.xadd(stream_name, tick_data)

            # Acknowledge original message
            await self.redis_client.xack(stream_name, self.consumer_group, msg_id)

            # Update metrics
            processing_time = (time.time() - start_time) * 1000
            self.processing_metrics['total_processed'] += 1
            self.processing_metrics['total_time_ms'] += processing_time

            if processing_time > 1000:  # Log slow processing
                log_warning(f"Slow tick processing: {processing_time:.2f}ms for {instrument_key}")

        except Exception as e:
            log_exception(f"Failed to process tick message {msg_id}: {e}")
            self.processing_metrics['errors'] += 1

    async def process_tick_async(self, instrument_key: str, tick_data: dict):
        """Main tick processing logic"""
        try:
            # Get relevant configurations
            configs = await self.config_handler.get_configs_for_instrument(instrument_key)

            if not configs:
                return  # No configurations for this instrument

            # Process tick with enhanced adapter
            processed_tick = await self.ticker_adapter.process_tick(tick_data)

            # Validate tick data
            is_valid, error_msg = await self.ticker_adapter.validate_tick_data(tick_data)
            if not is_valid:
                log_warning(f"Invalid tick data for {instrument_key}: {error_msg}")
                return

            # Enrich with metadata
            processed_tick = await self.ticker_adapter.enrich_with_metadata(processed_tick)

            # Create processing context with enhanced tick data
            context = TickProcessingContext(
                tick_data=processed_tick,  # Use processed tick instead of raw
                instrument_key=instrument_key,
                timestamp=processed_tick["timestamp"]["utc"],
                configurations=configs
            )

            # Get aggregated data if needed
            context.aggregated_data = await self.get_aggregated_data(instrument_key, configs)

            # Process each configuration
            computation_tasks = []
            for config in configs:
                # Check if should execute based on frequency
                if await self.should_execute(config, context.timestamp):
                    task = self.execute_configuration(config, context)
                    computation_tasks.append(task)

            # Execute computations in parallel
            if computation_tasks:
                results = await asyncio.gather(*computation_tasks, return_exceptions=True)

                # Collect successful results
                for result in results:
                    if isinstance(result, ComputationResult):
                        context.computation_results.append(result)
                    elif isinstance(result, Exception):
                        log_exception(f"Computation failed: {result}")

            # Publish results
            if context.computation_results:
                await self.publish_results(context)

        except Exception as e:
            error = handle_computation_error(e, "tick_processing", instrument_key)
            log_exception(f"Error processing tick for {instrument_key}: {error}")
            raise error from e

    async def execute_configuration(self, config: SignalConfigData, context: TickProcessingContext) -> ComputationResult | None:
        """Execute a single configuration"""
        start_time = time.time()
        instrument_key = context.instrument_key

        try:
            # Parallel execution of different computation types
            tasks = []

            # Option Greeks
            if config.option_greeks and config.option_greeks.enabled:
                task = self.compute_greeks(config, context)
                tasks.append(('greeks', task))

            # Technical Indicators
            if config.technical_indicators:
                task = self.compute_technical_indicators(config, context)
                tasks.append(('technical_indicators', task))

            # Internal Functions
            if config.internal_functions:
                task = self.compute_internal_functions(config, context)
                tasks.append(('internal_functions', task))

            # External Functions
            if config.external_functions:
                task = self.compute_external_functions(config, context)
                tasks.append(('external_functions', task))

            # Execute all computations
            results = {}
            if tasks:
                if config.parallel_execution:
                    # Parallel execution
                    computation_results = await asyncio.gather(
                        *[task for _, task in tasks],
                        return_exceptions=True
                    )

                    for (comp_type, _), result in zip(tasks, computation_results, strict=False):
                        if isinstance(result, Exception):
                            log_exception(f"Computation {comp_type} failed: {result}")
                            results[comp_type] = {"error": str(result)}
                        else:
                            results[comp_type] = result
                else:
                    # Sequential execution
                    for comp_type, task in tasks:
                        try:
                            result = await task
                            results[comp_type] = result
                        except Exception as e:
                            log_exception(f"Computation {comp_type} failed: {e}")
                            results[comp_type] = {"error": str(e)}

            # Create result
            execution_time = (time.time() - start_time) * 1000

            return ComputationResult(
                computation_type="configuration",
                instrument_key=instrument_key,
                timestamp=context.timestamp,
                results=results,
                execution_time_ms=execution_time,
                success=len(results) > 0,
                error=None
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error = handle_computation_error(e, "configuration", instrument_key)

            return ComputationResult(
                computation_type="configuration",
                instrument_key=instrument_key,
                timestamp=context.timestamp,
                results={},
                execution_time_ms=execution_time,
                success=False,
                error=str(error)
            )

    async def get_aggregated_data(self, instrument_key: str, configs: list[SignalConfigData]) -> dict | None:
        """Get aggregated historical data for computations"""
        try:
            # Determine required intervals
            required_intervals = set()
            for config in configs:
                required_intervals.add(config.interval.value)

            # Get data for each interval
            aggregated_data = {}
            for interval in required_intervals:
                cache_key = settings.get_aggregated_data_cache_key(instrument_key, interval)

                # Try cache first
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    aggregated_data[interval] = json.loads(cached_data)
                else:
                    # CONSOLIDATED: Fetch from ticker_service instead of direct TimescaleDB
                    ticker_data = await self.fetch_from_ticker_service(instrument_key, interval)
                    if ticker_data:
                        aggregated_data[interval] = ticker_data
                        # Cache for future use
                        await self.redis_client.setex(
                            cache_key,
                            settings.CACHE_TTL_SECONDS,
                            json.dumps(ticker_data)
                        )

            return aggregated_data if aggregated_data else None

        except Exception as e:
            log_exception(f"Failed to get aggregated data for {instrument_key}: {e}")
            return None


    async def compute_greeks(self, config: SignalConfigData, context: TickProcessingContext) -> dict:
        """Compute option Greeks"""
        try:
            if context.aggregated_data:
                # Historical Greeks calculation
                return await self.greeks_calculator.calculate_historical_greeks(
                    config, context
                )
            # Real-time Greeks calculation
            return await self.realtime_greeks_calculator.calculate_realtime_greeks(
                config, context
            )
        except Exception as e:
            raise handle_computation_error(e, "greeks", context.instrument_key) from e

    async def compute_technical_indicators(self, config: SignalConfigData, context: TickProcessingContext) -> dict:
        """Compute technical indicators"""
        try:
            return await self.pandas_ta_executor.execute_indicators(config, context)
        except Exception as e:
            raise handle_computation_error(e, "technical_indicators", context.instrument_key) from e

    async def compute_internal_functions(self, config: SignalConfigData, context: TickProcessingContext) -> dict:
        """Compute internal functions"""
        try:
            # Placeholder for internal function execution
            results = {}
            for func_config in config.internal_functions:
                # Execute internal function
                result = await self.execute_internal_function(func_config, context)
                results[func_config.name] = result
            return results
        except Exception as e:
            raise handle_computation_error(e, "internal_functions", context.instrument_key) from e

    async def compute_external_functions(self, config: SignalConfigData, context: TickProcessingContext) -> dict:
        """Compute external functions"""
        try:
            return await self.external_function_executor.execute_functions(config, context)
        except Exception as e:
            raise handle_computation_error(e, "external_functions", context.instrument_key) from e

    async def execute_internal_function(self, func_config, context: TickProcessingContext) -> Any:
        """Execute a single internal function"""
        # Placeholder implementation
        return {"result": "internal_function_executed", "function": func_config.name}

    async def should_execute(self, config: SignalConfigData, timestamp: datetime) -> bool:
        """Determine if configuration should execute based on frequency"""
        try:
            frequency = config.frequency

            if frequency.value == "every_tick":
                return True
            if frequency.value == "every_second":
                return timestamp.second != getattr(self, '_last_second', -1)
            if frequency.value == "every_minute":
                return timestamp.minute != getattr(self, '_last_minute', -1)
            if frequency.value == "on_close":
                # Logic for market close detection
                return False  # Placeholder
            return True

        except Exception as e:
            log_exception(f"Error in should_execute: {e}")
            return False

    async def publish_results(self, context: TickProcessingContext):
        """Publish computation results with broker symbol information"""
        try:
            instrument_key = context.instrument_key

            # Prepare output data
            output_data = {
                "instrument_key": instrument_key,
                "timestamp": context.timestamp.isoformat(),
                "tick_data": context.tick_data,
                "computations": [result.dict() for result in context.computation_results]
            }

            # Enrich with broker symbol mappings
            if self.broker_symbol_converter:
                output_data = await self.broker_symbol_converter.enrich_with_broker_info(output_data)

            # Publish to Redis list (for backward compatibility)
            list_key = settings.get_computed_data_key(instrument_key)
            await self.redis_client.lpush(list_key, json.dumps(output_data))

            # Trim list to prevent memory issues
            await self.redis_client.ltrim(list_key, 0, 999)  # Keep last 1000 entries

            # Publish to Redis Stream (for new consumers)
            stream_key = f"{settings.REDIS_OUTPUT_STREAM_PREFIX}{instrument_key}"
            await self.redis_client.xadd(stream_key, output_data)

            log_info(f"Published results for {instrument_key}: {len(context.computation_results)} computations")

        except Exception as e:
            log_exception(f"Failed to publish results: {e}")

    async def stop(self):
        """Stop the signal processor"""
        self.is_running = False
        log_info("SignalProcessor stopped")

    def get_metrics(self) -> dict[str, Any]:
        """Get processing metrics"""
        total_processed = self.processing_metrics.get('total_processed', 0)
        total_time = self.processing_metrics.get('total_time_ms', 0)

        return {
            "total_processed": total_processed,
            "total_errors": self.processing_metrics.get('errors', 0),
            "average_processing_time_ms": total_time / total_processed if total_processed > 0 else 0,
            "active_streams": len(self.active_streams),
            "is_running": self.is_running
        }

    # New methods for frequency-based processing

    async def compute_greeks_for_instrument(self, instrument_key: str) -> dict | None:
        """Compute Greeks for a single instrument (used by frequency manager)"""
        try:
            # Check if moneyness-based
            if instrument_key.startswith("MONEYNESS@"):
                return await self._compute_moneyness_greeks_local(instrument_key)

            # Regular Greeks
            # Get market data - fail fast if unavailable (no synthetic fallback)
            market_data = await self._get_latest_market_data(instrument_key)
            if not market_data:
                log_error(f"No market data available for Greeks computation: {instrument_key}")
                return None

            context = TickProcessingContext(
                tick_data=market_data,  # Required field - only real data
                instrument_key=instrument_key,
                timestamp=datetime.utcnow()
            )

            # Import schema classes for proper construction
            from app.schemas.config_schema import (
                FrequencyType,
                IntervalType,
                OptionGreeksConfig,
                SignalConfigData,
            )

            result = await self.compute_greeks(
                SignalConfigData(
                    instrument_key=instrument_key,
                    interval=IntervalType.ONE_MINUTE,  # Required field
                    frequency=FrequencyType.EVERY_MINUTE,  # Required field
                    option_greeks=OptionGreeksConfig(enabled=True)  # Proper config object
                ),
                context
            )

            return result.results if result else None

        except Exception as e:
            log_error(f"Error computing Greeks for {instrument_key}: {e}")
            return None

    async def _compute_moneyness_greeks_local(self, moneyness_key: str) -> dict | None:
        """Compute moneyness Greeks using local calculator"""
        try:
            # Parse moneyness key
            parts = moneyness_key.split("@")
            if len(parts) != 4:
                return None

            _, underlying, moneyness_level, expiry_date = parts

            # Get spot price
            spot_data = await self._get_latest_market_data(f"{underlying}@equity_spot")
            if not spot_data:
                return None

            spot_price = spot_data.get('last_price', 0)

            # Get available strikes
            strikes = self.local_moneyness_calculator.get_strike_distribution(
                underlying, spot_price, expiry_date
            )

            # Find strikes at moneyness level
            matching_strikes = self.local_moneyness_calculator.find_strikes_by_moneyness(
                spot_price, strikes, moneyness_level, 'call'
            )

            if not matching_strikes:
                return None

            # Compute Greeks for matching strikes
            greeks_by_strike = {}
            for strike in matching_strikes:
                call_key = f"NSE@{underlying}@equity_options@{expiry_date}@call@{strike}"
                put_key = f"NSE@{underlying}@equity_options@{expiry_date}@put@{strike}"

                # Compute Greeks (simplified)
                call_greeks = await self.compute_greeks_for_instrument(call_key)
                put_greeks = await self.compute_greeks_for_instrument(put_key)

                if call_greeks and put_greeks:
                    # Average call and put Greeks
                    greeks_by_strike[strike] = {
                        'delta': (call_greeks.get('delta', 0) + abs(put_greeks.get('delta', 0))) / 2,
                        'gamma': (call_greeks.get('gamma', 0) + put_greeks.get('gamma', 0)) / 2,
                        'theta': (call_greeks.get('theta', 0) + put_greeks.get('theta', 0)) / 2,
                        'vega': (call_greeks.get('vega', 0) + put_greeks.get('vega', 0)) / 2,
                        'rho': (call_greeks.get('rho', 0) + put_greeks.get('rho', 0)) / 2,
                        'iv': (call_greeks.get('iv', 0) + put_greeks.get('iv', 0)) / 2
                    }

            # Aggregate using local calculator
            return self.local_moneyness_calculator.aggregate_greeks_by_moneyness(
                moneyness_level,
                matching_strikes,
                greeks_by_strike,
                spot_price,
                'call'
            )

        except Exception as e:
            log_error(f"Error computing local moneyness Greeks: {e}")
            return None

    async def compute_indicators_for_instrument(
        self,
        instrument_key: str,
        indicators: list[dict]
    ) -> dict | None:
        """Compute indicators for a single instrument"""
        try:
            # Get market data - fail fast if unavailable (no synthetic fallback)
            market_data = await self._get_latest_market_data(instrument_key)
            if not market_data:
                log_error(f"No market data available for indicators computation: {instrument_key}")
                return None

            context = TickProcessingContext(
                tick_data=market_data,  # Required field - only real data
                instrument_key=instrument_key,
                timestamp=datetime.utcnow()
            )

            # Import schema classes for proper construction
            from app.schemas.config_schema import (
                FrequencyType,
                IntervalType,
                SignalConfigData,
                TechnicalIndicatorConfig,
            )

            # Convert indicators to proper TechnicalIndicatorConfig objects
            indicator_configs = []
            for indicator in indicators:
                indicator_configs.append(TechnicalIndicatorConfig(
                    name=indicator["name"],
                    parameters=indicator.get("params", {}),
                    output_key=indicator.get("output_key", indicator["name"])
                ))

            result = await self.compute_technical_indicators(
                SignalConfigData(
                    instrument_key=instrument_key,
                    interval=IntervalType.ONE_MINUTE,  # Required field
                    frequency=FrequencyType.EVERY_MINUTE,  # Required field
                    technical_indicators=indicator_configs
                ),
                context
            )

            return result.results if result else None

        except Exception as e:
            log_error(f"Error computing indicators for {instrument_key}: {e}")
            return None

    async def _get_latest_market_data(self, instrument_key: str) -> dict | None:
        """Get latest market data for an instrument"""
        try:
            # Get from Redis
            key = f"market:latest:{instrument_key}"
            data = await self.redis_client.get(key)

            if data:
                return json.loads(data)

            return None

        except Exception as e:
            log_error(f"Error getting market data for {instrument_key}: {e}")
            return None

    async def enable_realtime_signal(
        self,
        user_id: str,
        instrument_key: str,
        signal_type: str
    ):
        """Enable real-time signal processing for a user"""
        # This would configure real-time processing
        # For now, just log
        log_info(f"Enabled real-time {signal_type} for {user_id}/{instrument_key}")

    def _get_current_memory_usage(self) -> float:
        """
        Get current memory usage in MB for the signal processor.

        Returns:
            Memory usage in megabytes
        """
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            # Return RSS (Resident set Size) in MB
            memory_mb = memory_info.rss / 1024 / 1024
            return round(memory_mb, 2)
        except Exception as e:
            log_warning(f"Failed to get memory usage: {e}")
            return 0.0


# Global singleton instance and lock
_signal_processor_instance = None
_signal_processor_lock = asyncio.Lock()


async def get_signal_processor() -> SignalProcessor:
    """Get global signal processor singleton instance with thread safety."""
    global _signal_processor_instance

    if _signal_processor_instance is None:
        async with _signal_processor_lock:
            # Double-check pattern to avoid race conditions
            if _signal_processor_instance is None:
                _signal_processor_instance = SignalProcessor()
                # Initialize with minimal state for shared usage
                await _signal_processor_instance.initialize(app_state=None)

    return _signal_processor_instance
