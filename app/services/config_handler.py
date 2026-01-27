"""Configuration handler for managing signal configurations"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.core.config import settings
from app.errors import ConfigurationError, InvalidConfigurationError, MissingConfigurationError
from app.schemas.config_schema import ConfigurationMessage, SignalConfigData
from app.utils.logging_utils import log_error, log_exception, log_info, log_warning


class ConfigHandler:
    """
    Manages the lifecycle of signal service configurations:
    - Validates incoming configurations
    - Caches configurations in Redis
    - Manages scheduled tasks for configurations
    - Handles configuration updates and deletions
    """

    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.active_tasks = {}  # {config_key: asyncio.Task}
        self.current_configs = {}  # In-memory cache of active configs

        log_info("ConfigHandler initialized")

    async def process_config_update(self, config_data: dict, action: str):
        """Process a configuration update message"""
        try:
            # Validate action
            if action not in ['create', 'update', 'delete']:
                raise InvalidConfigurationError(f"Invalid action: {action}")

            if action == 'delete':
                await self.delete_config(config_data)
            else:
                # Validate configuration
                validated_config = await self.validate_config(config_data)

                if action == 'create':
                    await self.create_config(validated_config)
                elif action == 'update':
                    await self.update_config(validated_config)

            log_info(f"Successfully processed config {action}: {config_data.get('instrument_key')}")

        except Exception as e:
            log_exception(f"Failed to process config update: {e}")
            raise ConfigurationError(f"Configuration processing failed: {str(e)}") from e

    async def validate_config(self, config_data: dict) -> SignalConfigData:
        """Validate configuration data using Pydantic schema"""
        try:
            return SignalConfigData(**config_data)
        except Exception as e:
            raise InvalidConfigurationError(f"Configuration validation failed: {str(e)}") from e

    async def create_config(self, config: SignalConfigData):
        """Create a new configuration"""
        config_key = self.get_config_key(config)

        try:
            # Store in Redis
            await self.store_config(config_key, config)

            # Add to in-memory cache
            self.current_configs[config_key] = config.dict()

            # Apply configuration (start scheduled tasks if needed)
            await self.apply_config(config)

            log_info(f"Created configuration: {config_key}")

        except Exception as e:
            log_exception(f"Failed to create config {config_key}: {e}")
            raise

    async def update_config(self, config: SignalConfigData):
        """Update an existing configuration"""
        config_key = self.get_config_key(config)

        try:
            # Cancel existing tasks
            await self.cancel_config_tasks(config_key)

            # Store updated config in Redis
            await self.store_config(config_key, config)

            # Update in-memory cache
            self.current_configs[config_key] = config.dict()

            # Apply updated configuration
            await self.apply_config(config)

            # Invalidate related cache
            await self.invalidate_cache_for_config(config)

            log_info(f"Updated configuration: {config_key}")

        except Exception as e:
            log_exception(f"Failed to update config {config_key}: {e}")
            raise

    async def delete_config(self, config_data: dict):
        """Delete a configuration"""
        # Extract key info for deletion
        instrument_key = config_data.get('instrument_key')
        interval = config_data.get('interval')
        frequency = config_data.get('frequency')

        if not all([instrument_key, interval, frequency]):
            raise MissingConfigurationError("Missing required fields for config deletion")

        config_key = settings.get_config_cache_key(instrument_key, interval, frequency)

        try:
            # Cancel existing tasks
            await self.cancel_config_tasks(config_key)

            # Remove from Redis
            await self.redis_client.delete(config_key)

            # Remove from in-memory cache
            self.current_configs.pop(config_key, None)

            # Invalidate related cache
            await self.invalidate_cache_for_instrument(instrument_key, interval, frequency)

            log_info(f"Deleted configuration: {config_key}")

        except Exception as e:
            log_exception(f"Failed to delete config {config_key}: {e}")
            raise

    async def store_config(self, config_key: str, config: SignalConfigData):
        """Store configuration in Redis"""
        try:
            config_json = config.json()
            await self.redis_client.setex(
                config_key,
                settings.CONFIG_CACHE_TTL_SECONDS,
                config_json
            )
        except Exception as e:
            log_exception(f"Failed to store config in Redis: {e}")
            raise

    async def apply_config(self, config: SignalConfigData):
        """Apply configuration by setting up scheduled tasks"""
        config_key = self.get_config_key(config)

        try:
            # set up scheduled tasks based on frequency
            if config.frequency.value in ['every_interval', 'on_close']:
                await self.setup_scheduled_tasks(config_key, config)

            log_info(f"Applied configuration: {config_key}")

        except Exception as e:
            log_exception(f"Failed to apply config {config_key}: {e}")
            raise

    async def setup_scheduled_tasks(self, config_key: str, config: SignalConfigData):
        """set up scheduled tasks for configuration"""
        try:
            # Cancel existing task if any
            await self.cancel_config_tasks(config_key)

            # Create new task based on frequency
            if config.frequency.value == 'every_interval':
                # Determine interval in seconds
                interval_seconds = self.parse_interval_to_seconds(config.interval.value)

                if interval_seconds:
                    task = asyncio.create_task(
                        self.execute_periodic_computation(config, interval_seconds)
                    )
                    self.active_tasks[config_key] = task
                    log_info(f"Started periodic task for {config_key} (every {interval_seconds}s)")

            elif config.frequency.value == 'on_close':
                # set up market close detection task
                task = asyncio.create_task(
                    self.execute_on_close_computation(config)
                )
                self.active_tasks[config_key] = task
                log_info(f"Started on-close task for {config_key}")

        except Exception as e:
            log_exception(f"Failed to setup scheduled tasks for {config_key}: {e}")
            raise

    async def execute_periodic_computation(self, config: SignalConfigData, interval_seconds: int):
        """Execute computation periodically"""
        config_key = self.get_config_key(config)

        while config_key in self.active_tasks:
            try:
                # Wait for the interval
                await asyncio.sleep(interval_seconds)

                # Check if task is still active (config not deleted)
                if config_key not in self.active_tasks:
                    break

                log_info(f"Executing periodic computation for {config_key}")

                # Trigger actual computation via SignalProcessor
                await self._trigger_computation(config)

            except asyncio.CancelledError:
                log_info(f"Periodic task cancelled for {config_key}")
                break
            except Exception as e:
                log_exception(f"Error in periodic computation for {config_key}: {e}")
                # Continue running despite errors
                await asyncio.sleep(5)

    async def execute_on_close_computation(self, config: SignalConfigData):
        """Execute computation on market close"""
        config_key = self.get_config_key(config)

        while config_key in self.active_tasks:
            try:
                # Wait until market close (simplified logic)
                # In reality, this would integrate with market schedule
                await asyncio.sleep(3600)  # Check every hour

                current_time = datetime.now()
                if self.is_market_close_time(current_time):
                    log_info(f"Executing on-close computation for {config_key}")
                    # Trigger actual computation via SignalProcessor
                    await self._trigger_computation(config)

            except asyncio.CancelledError:
                log_info(f"On-close task cancelled for {config_key}")
                break
            except Exception as e:
                log_exception(f"Error in on-close computation for {config_key}: {e}")
                await asyncio.sleep(60)

    async def cancel_config_tasks(self, config_key: str):
        """Cancel all tasks for a configuration"""
        if config_key in self.active_tasks:
            task = self.active_tasks[config_key]
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                # Expected after explicit cancellation - task properly cancelled
                log_info(f"Task cancelled successfully for {config_key}")

            del self.active_tasks[config_key]
            log_info(f"Cancelled tasks for {config_key}")

    async def _trigger_computation(self, config: SignalConfigData):
        """Trigger actual signal computation for a configuration"""
        try:
            # Import here to avoid circular dependencies
            from app.services.signal_processor import get_signal_processor

            # Get signal processor instance
            processor = await get_signal_processor()

            # Trigger computation based on actual config fields (not signal_type which doesn't exist)
            if config.option_greeks:
                # Trigger Greeks calculation using actual method
                result = await processor.compute_greeks_for_instrument(
                    instrument_key=config.instrument_key
                )
                log_info(f"Triggered Greeks computation for {config.instrument_key}: {result is not None}")

            if config.technical_indicators:
                # Trigger indicator calculation using actual method
                # Convert TechnicalIndicatorConfig objects to dict format expected by processor
                indicators = []
                for indicator_config in config.technical_indicators:
                    indicators.append({
                        "name": indicator_config.name,
                        "params": indicator_config.parameters
                    })

                result = await processor.compute_indicators_for_instrument(
                    instrument_key=config.instrument_key,
                    indicators=indicators
                )
                log_info(f"Triggered indicator computation for {config.instrument_key}: {result is not None}")

            if config.external_functions:
                # Trigger external function execution using SignalProcessor's existing method
                from app.schemas.config_schema import TickProcessingContext

                # External functions require real market data for proper execution
                # Get latest market data - fail fast if unavailable (no synthetic fallback)
                market_data = await processor._get_latest_market_data(config.instrument_key)
                if not market_data:
                    log_error(f"No market data available for external function execution: {config.instrument_key}")
                    log_warning(f"Skipping {len(config.external_functions)} external functions due to missing market data")
                else:
                    context = TickProcessingContext(
                        tick_data=market_data,  # Required field - only real data
                        instrument_key=config.instrument_key,
                        timestamp=datetime.utcnow()
                    )

                    result = await processor.compute_external_functions(config, context)
                    log_info(f"Triggered external function computation for {config.instrument_key}: {result is not None}")

            if not config.option_greeks and not config.technical_indicators and not config.external_functions:
                log_warning(f"No computation types configured for {config.instrument_key}")

        except Exception as e:
            log_exception(f"Failed to trigger computation for {config.instrument_key}: {e}")
            raise

    async def get_active_configs(self) -> dict[str, dict]:
        """Get all active configurations"""
        return self.current_configs.copy()

    async def get_configs_for_instrument(self, instrument_key: str) -> list[SignalConfigData]:
        """Get all configurations for a specific instrument"""
        configs = []

        for config_key, config_data in self.current_configs.items():
            if config_data.get('instrument_key') == instrument_key:
                try:
                    config = SignalConfigData(**config_data)
                    configs.append(config)
                except Exception as e:
                    log_exception(f"Failed to parse config {config_key}: {e}")

        return configs

    async def invalidate_cache_for_config(self, config: SignalConfigData):
        """Invalidate cached data related to configuration"""
        await self.invalidate_cache_for_instrument(
            config.instrument_key,
            config.interval.value,
            config.frequency.value
        )

    async def invalidate_cache_for_instrument(self, instrument_key: str, interval: str, frequency: str):
        """Invalidate cached data for instrument"""
        try:
            # Invalidate aggregated data cache
            agg_cache_key = settings.get_aggregated_data_cache_key(instrument_key, interval)
            await self.redis_client.delete(agg_cache_key)

            # Invalidate TA results cache
            ta_cache_key = settings.get_ta_results_cache_key(instrument_key, interval, frequency)
            await self.redis_client.delete(ta_cache_key)

            # Invalidate computed data (keep recent entries, clear old ones)
            computed_key = settings.get_computed_data_key(instrument_key)
            await self.redis_client.ltrim(computed_key, 0, 99)  # Keep last 100 entries

            log_info(f"Invalidated cache for {instrument_key}:{interval}:{frequency}")

        except Exception as e:
            log_exception(f"Failed to invalidate cache: {e}")

    def get_config_key(self, config: SignalConfigData) -> str:
        """Generate cache key for configuration"""
        return settings.get_config_cache_key(
            config.instrument_key,
            config.interval.value,
            config.frequency.value
        )

    def parse_interval_to_seconds(self, interval: str) -> int | None:
        """Parse interval string to seconds"""
        try:
            if interval.endswith('minute'):
                minutes = int(interval.replace('minute', ''))
                return minutes * 60
            if interval.endswith('hour'):
                hours = int(interval.replace('hour', ''))
                return hours * 3600
            if interval.endswith('day'):
                days = int(interval.replace('day', ''))
                return days * 86400
            log_warning(f"Unknown interval format: {interval}")
            return None
        except ValueError:
            log_warning(f"Failed to parse interval: {interval}")
            return None

    def is_market_close_time(self, current_time: datetime) -> bool:
        """Check if current time is market close (simplified)"""
        # Simplified logic - in reality would integrate with market calendar
        # Indian market typically closes at 3:30 PM
        hour = current_time.hour
        minute = current_time.minute

        # Check if it's around 3:30 PM (15:30)
        return hour == 15 and 25 <= minute <= 35

    async def cleanup(self):
        """Cleanup all active tasks"""
        try:
            for config_key in list(self.active_tasks.keys()):
                await self.cancel_config_tasks(config_key)
            log_info("ConfigHandler cleanup completed")
        except Exception as e:
            log_exception(f"Error during ConfigHandler cleanup: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get configuration handler metrics"""
        return {
            "active_configs": len(self.current_configs),
            "active_tasks": len(self.active_tasks),
            "task_status": {
                config_key: "running" if not task.done() else "completed"
                for config_key, task in self.active_tasks.items()
            }
        }
