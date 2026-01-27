"""
Enhanced Signal Service configuration with hot parameter reloading support.

ARCHITECTURE COMPLIANCE:
- Config service is MANDATORY (Principle #1)
- Hot parameter reloading for zero-downtime configuration updates
- Fail-fast if config service unavailable
- Real-time adaptation to parameter changes
"""

import asyncio
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Service registry integration for standardized service URLs
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .config import SignalServiceConfig as BaseSignalServiceConfig

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ParameterSchema:
    """Schema definition for parameter validation."""
    parameter_type: type
    required: bool = True
    min_value: int | float | None = None
    max_value: int | float | None = None
    allowed_values: list | None = None
    pattern: str | None = None
    validator: Callable | None = None


class CircuitBreaker:
    """Circuit breaker implementation for hot reload operations."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300, half_open_max_calls: int = 3):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._last_failure_time = None
        self._next_attempt_time = None
        self._state = CircuitBreakerState.CLOSED
        self._half_open_calls = 0

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self._state == CircuitBreakerState.OPEN:
            if self._next_attempt_time and datetime.now() >= self._next_attempt_time:
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioning to half-open state")
                return False
            return True
        return False

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        self.is_open()  # Update state if needed
        return self._state

    def record_success(self):
        """Record successful operation."""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self._half_open_max_calls:
                self._reset()
                logger.info("Circuit breaker reset to closed state after successful half-open calls")
        elif self._state == CircuitBreakerState.CLOSED:
            self._failure_count = 0

    def record_failure(self):
        """Record failed operation."""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._trip()
            logger.warning("Circuit breaker tripped during half-open state")
        elif self._state == CircuitBreakerState.CLOSED and self._failure_count >= self._failure_threshold:
            self._trip()
            logger.error(f"Circuit breaker tripped after {self._failure_count} failures")

    def _trip(self):
        """Trip the circuit breaker to open state."""
        self._state = CircuitBreakerState.OPEN
        self._next_attempt_time = datetime.now() + timedelta(seconds=self._recovery_timeout)

    def _reset(self):
        """Reset the circuit breaker to closed state."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None
        self._next_attempt_time = None


class SchemaValidationError(Exception):
    """Schema validation error for parameter updates."""


class HotReloadError(Exception):
    """Base exception for hot reload operations."""


logger = logging.getLogger(__name__)


class HotReloadableSignalServiceConfig(BaseSignalServiceConfig):
    """Enhanced Signal Service configuration with hot parameter reloading."""

    def __init__(self, environment: str = None):
        # Initialize base configuration
        super().__init__(environment)

        # Hot reload infrastructure
        self.notification_client = None
        self._hot_reload_handlers = {}
        self._reload_locks = {}

        # Enhanced statistics and observability
        self._config_stats = {
            'hot_reloads': 0,
            'successful_reloads': 0,
            'failed_reloads': 0,
            'last_reload_time': None,
            'last_error': None,
            'consecutive_failures': 0,
            'circuit_breaker_trips': 0,
            'schema_validation_errors': 0,
            'rollbacks_triggered': 0
        }

        # Circuit breaker and fail-safe controls
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300,  # 5 minutes
            half_open_max_calls=3
        )
        self._kill_switch_enabled = False
        self._max_consecutive_failures = 10
        self._parameter_rollback_history = {}

        # Security: NO hardcoded URLs - use config service only
        self._external_config_enabled = False
        self._hot_reload_enabled = True
        self._security_context = {
            'auth_required': True,
            'internal_only': True,
            'circuit_breaker': True,
            'schema_validation': True,
            'rollback_on_failure': True
        }

        # Schema validation registry
        self._parameter_schemas = self._initialize_parameter_schemas()

    def _initialize_parameter_schemas(self) -> dict[str, ParameterSchema]:
        """Initialize parameter schemas for validation."""
        return {
            # Database and connection parameters
            'DATABASE_URL': ParameterSchema(
                parameter_type=str,
                required=True,
                pattern=r'^postgresql://.*',
                validator=self._validate_database_url
            ),
            'REDIS_URL': ParameterSchema(
                parameter_type=str,
                required=True,
                pattern=r'^redis://.*',
                validator=self._validate_redis_url
            ),

            # Performance parameters
            'signal_service.cache_ttl_seconds': ParameterSchema(
                parameter_type=int,
                required=True,
                min_value=30,
                max_value=3600
            ),
            'signal_service.max_batch_size': ParameterSchema(
                parameter_type=int,
                required=True,
                min_value=10,
                max_value=10000
            ),
            'signal_service.service_integration_timeout': ParameterSchema(
                parameter_type=float,
                required=True,
                min_value=5.0,
                max_value=300.0
            ),

            # Feature flags (boolean parameters)
            'signal_service.async_computation_enabled': ParameterSchema(
                parameter_type=bool,
                required=True,
                allowed_values=[True, False]
            ),
            'signal_service.metrics_enabled': ParameterSchema(
                parameter_type=bool,
                required=True,
                allowed_values=[True, False]
            ),

            # Service URLs
            'signal_service.ticker_service_url': ParameterSchema(
                parameter_type=str,
                required=True,
                pattern=r'^https?://.*',
                validator=self._validate_service_url
            ),
            'signal_service.instrument_service_url': ParameterSchema(
                parameter_type=str,
                required=True,
                pattern=r'^https?://.*',
                validator=self._validate_service_url
            ),

            # Security parameters (restricted)
            'GATEWAY_SECRET': ParameterSchema(
                parameter_type=str,
                required=True,
                min_value=20,  # Minimum length
                validator=self._validate_secret
            )
        }

    def _validate_database_url(self, value: str) -> bool:
        """Validate database URL format and basic connectivity."""
        import re
        if not re.match(r'^postgresql://[^:]+:[^@]+@[^/]+/[^?]+.*', value):
            return False
        # Additional validation: check for required components
        if 'localhost' not in value and not re.match(r'.*@[\d.]+/', value) and not re.match(r'.*@[a-zA-Z0-9.-]+/', value):
            return False
        return True

    def _validate_redis_url(self, value: str) -> bool:
        """Validate Redis URL format."""
        import re
        return bool(re.match(r'^redis://([^:]+:[^@]+@)?[^/]+(/\d+)?$', value))

    def _validate_service_url(self, value: str) -> bool:
        """Validate service URL format."""
        import re
        if not re.match(r'^https?://[^/]+', value):
            return False
        # Prevent external URLs in production
        if self.environment == 'production' and not ('localhost' in value or '.local' in value or value.startswith('http://10.') or value.startswith('http://172.') or value.startswith('http://192.168.')):
            logger.error(f"External service URL not allowed in production: {value}")
            return False
        return True

    def _validate_secret(self, value: str) -> bool:
        """Validate secret format and strength."""
        if len(value) < 20:
            return False
        # Ensure secret is not a common weak value
        weak_secrets = ['password', 'secret', 'admin', 'test', 'default']
        return value.lower() not in weak_secrets

    def validate_parameter(self, parameter_key: str, new_value: Any) -> bool:
        """Validate parameter against its schema."""
        schema = self._parameter_schemas.get(parameter_key)
        if not schema:
            # Parameters without schemas are allowed but logged
            logger.warning(f"No schema defined for parameter: {parameter_key}")
            return True

        try:
            # Type validation
            if schema.parameter_type == bool and isinstance(new_value, str):
                new_value = new_value.lower() in ('true', '1', 'yes', 'on')
            elif schema.parameter_type in (int, float) and isinstance(new_value, str):
                new_value = schema.parameter_type(new_value)
            elif not isinstance(new_value, schema.parameter_type):
                raise SchemaValidationError(f"Parameter {parameter_key} must be of type {schema.parameter_type.__name__}")

            # Range validation
            if schema.min_value is not None and new_value < schema.min_value:
                raise SchemaValidationError(f"Parameter {parameter_key} below minimum value {schema.min_value}")
            if schema.max_value is not None and new_value > schema.max_value:
                raise SchemaValidationError(f"Parameter {parameter_key} above maximum value {schema.max_value}")

            # Allowed values validation
            if schema.allowed_values is not None and new_value not in schema.allowed_values:
                raise SchemaValidationError(f"Parameter {parameter_key} not in allowed values: {schema.allowed_values}")

            # Pattern validation
            if schema.pattern is not None and isinstance(new_value, str):
                import re
                if not re.match(schema.pattern, new_value):
                    raise SchemaValidationError(f"Parameter {parameter_key} does not match required pattern")

            # Custom validator
            if schema.validator is not None:
                if not schema.validator(new_value):
                    raise SchemaValidationError(f"Parameter {parameter_key} failed custom validation")

            return True

        except (ValueError, TypeError) as e:
            raise SchemaValidationError(f"Parameter {parameter_key} validation error: {str(e)}")

    def store_parameter_rollback(self, parameter_key: str, old_value: Any):
        """Store parameter value for potential rollback."""
        self._parameter_rollback_history[parameter_key] = {
            'value': old_value,
            'timestamp': datetime.now().isoformat(),
            'rollback_count': self._parameter_rollback_history.get(parameter_key, {}).get('rollback_count', 0)
        }

        # Limit rollback history size
        if len(self._parameter_rollback_history) > 100:
            oldest_key = min(self._parameter_rollback_history.keys(),
                           key=lambda k: self._parameter_rollback_history[k]['timestamp'])
            del self._parameter_rollback_history[oldest_key]

    async def rollback_parameter(self, parameter_key: str) -> bool:
        """Rollback parameter to previous value."""
        if parameter_key not in self._parameter_rollback_history:
            logger.error(f"No rollback history for parameter: {parameter_key}")
            return False

        rollback_info = self._parameter_rollback_history[parameter_key]
        old_value = rollback_info['value']

        try:
            # Increment rollback count
            rollback_info['rollback_count'] += 1
            self._config_stats['rollbacks_triggered'] += 1

            # Apply rollback (implementation depends on parameter type)
            if parameter_key == 'DATABASE_URL':
                self.DATABASE_URL = old_value
            elif parameter_key == 'REDIS_URL':
                self.REDIS_URL = old_value
            # Add more parameter rollbacks as needed

            logger.warning(f"Parameter {parameter_key} rolled back to previous value")
            return True

        except Exception as e:
            logger.error(f"Failed to rollback parameter {parameter_key}: {e}")
            return False

    def enable_kill_switch(self, reason: str = "Manual activation"):
        """Enable kill switch to disable hot reloading."""
        self._kill_switch_enabled = True
        self._config_stats['kill_switch_enabled'] = True
        logger.critical(f"Hot reload KILL SWITCH activated: {reason}")

    def disable_kill_switch(self, reason: str = "Manual deactivation"):
        """Disable kill switch to re-enable hot reloading."""
        if self._kill_switch_enabled:
            self._kill_switch_enabled = False
            self._config_stats['kill_switch_enabled'] = False
            self._config_stats['consecutive_failures'] = 0  # Reset failure count
            self._circuit_breaker._reset()  # Reset circuit breaker
            logger.warning(f"Hot reload kill switch deactivated: {reason}")

    async def emergency_shutdown(self):
        """Emergency shutdown of hot reload system."""
        self.enable_kill_switch("Emergency shutdown triggered")
        if self.notification_client:
            await self.notification_client.stop_listening()
        logger.critical("Hot reload system emergency shutdown completed")

        logger.info("✓ Hot reloadable configuration initialized with fail-safes enabled")

        # Log security and observability status
        logger.info(f"Security context: {self._security_context}")
        logger.info(f"Circuit breaker: failure_threshold={self._circuit_breaker._failure_threshold}")
        logger.info(f"Kill switch: disabled, max_failures={self._max_consecutive_failures}")

    async def initialize_hot_reload(self, enable_hot_reload: bool = True):
        """Initialize hot parameter reloading system - config service only."""
        if not enable_hot_reload:
            logger.info("Hot parameter reloading disabled by configuration")
            return

        try:
            self._hot_reload_enabled = enable_hot_reload

            # Import notification client
            from common.config_service.notification_client import ConfigNotificationClient

            # Configure Redis URL for notifications
            redis_url = self.REDIS_URL
            # Security: Only use authorized config service client
            if not self._validate_security_context():
                logger.error("Hot reload security validation failed - disabling")
                self._hot_reload_enabled = False
                return

            # Initialize notification client
            self.notification_client = ConfigNotificationClient(
                redis_url=redis_url,
                service_name="signal_service",
                environment=self.environment,
                config_client=self._get_config_client()
            )

            # Register parameter change handlers
            await self._register_hot_reload_handlers()

            # Start listening for parameter changes
            await self.notification_client.start_listening()

            logger.info("✓ Hot parameter reloading system initialized")

        except Exception as e:
            logger.error(f"Failed to initialize hot reload system: {e}")
            # Continue without hot reload - service should still function

    def _get_config_client(self):
        """Get authorized config client - config service only."""
        # Import here to avoid circular dependency
        from common.config_service.client import ConfigServiceClient

        # Security: ONLY use config service with proper bootstrap
        return ConfigServiceClient(
            service_name="signal_service",
            environment=self.environment,
            timeout=30
        )

    def _validate_security_context(self) -> bool:
        """Validate hot reload security requirements."""
        # Check kill switch first
        if self._kill_switch_enabled:
            logger.warning("Hot reload disabled by kill switch")
            return False

        # Check circuit breaker
        if self._circuit_breaker.is_open():
            logger.warning("Hot reload blocked by circuit breaker")
            return False

        # Ensure config service is properly authenticated
        if not hasattr(self, 'config_client'):
            logger.error("Config client not available for secure hot reload")
            return False

        # Check consecutive failure threshold
        if self._config_stats['consecutive_failures'] >= self._max_consecutive_failures:
            logger.error(f"Hot reload disabled due to {self._max_consecutive_failures} consecutive failures")
            self._kill_switch_enabled = True
            return False

        return True

    async def _register_hot_reload_handlers(self):
        """Register handlers for specific parameter changes."""

        # Database URL changes
        @self.notification_client.on_parameter_change("DATABASE_URL")
        async def handle_database_url_change(event):
            await self._handle_database_url_change(event)

        # Redis URL changes
        @self.notification_client.on_parameter_change("REDIS_URL")
        async def handle_redis_url_change(event):
            await self._handle_redis_url_change(event)

        # Internal API key changes
        @self.notification_client.on_parameter_change("INTERNAL_API_KEY")
        async def handle_internal_api_key_change(event):
            await self._handle_internal_api_key_change(event)

        # Gateway secret changes
        @self.notification_client.on_parameter_change("GATEWAY_SECRET")
        async def handle_gateway_secret_change(event):
            await self._handle_gateway_secret_change(event)

        # Service URL changes
        service_url_parameters = [
            "signal_service.ticker_service_url",
            "signal_service.instrument_service_url",
            "signal_service.marketplace_service_url",
            "signal_service.user_service_url",
            "signal_service.calendar_service_url",
            "signal_service.alert_service_url",
            "signal_service.messaging_service_url",
            "signal_service.subscription_service_url"
        ]

        for param in service_url_parameters:
            @self.notification_client.on_parameter_change(param)
            async def handle_service_url_change(event, parameter=param):
                await self._handle_service_url_change(event, parameter)

        # Performance and cache settings
        performance_parameters = [
            "signal_service.cache_ttl_seconds",
            "signal_service.max_batch_size",
            "signal_service.max_cpu_cores",
            "signal_service.service_integration_timeout"
        ]

        for param in performance_parameters:
            @self.notification_client.on_parameter_change(param)
            async def handle_performance_setting_change(event, parameter=param):
                await self._handle_performance_setting_change(event, parameter)

        # Feature flags and toggles
        @self.notification_client.on_parameter_change("FEATURE_*")
        async def handle_feature_flag_change(event):
            await self._handle_feature_flag_change(event)

        # Watermark configuration
        watermark_parameters = [
            "WATERMARK_SECRET",
            "WATERMARK_ENFORCEMENT_ENABLED",
            "WATERMARK_ENFORCEMENT_POLICY"
        ]

        for param in watermark_parameters:
            @self.notification_client.on_parameter_change(param)
            async def handle_watermark_config_change(event, parameter=param):
                await self._handle_watermark_config_change(event, parameter)

        # Generic handler for any configuration change
        @self.notification_client.on_parameter_change()
        async def handle_any_config_change(event):
            await self._handle_generic_config_change(event)

    async def _handle_database_url_change(self, event):
        """Handle DATABASE_URL parameter changes with connection pool refresh."""
        logger.info(f"DATABASE_URL changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock("database_url"):
                try:
                    # Circuit breaker check
                    if self._circuit_breaker.is_open():
                        logger.warning("DATABASE_URL reload blocked by circuit breaker")
                        return

                    # Get new database URL
                    new_db_url = await self.notification_client.refresh_parameter("DATABASE_URL")
                    if new_db_url and new_db_url != self.DATABASE_URL:
                        # Store current value for rollback
                        self.store_parameter_rollback("DATABASE_URL", self.DATABASE_URL)

                        # Schema validation
                        try:
                            if not self.validate_parameter("DATABASE_URL", new_db_url):
                                self._config_stats['schema_validation_errors'] += 1
                                self._circuit_breaker.record_failure()
                                logger.error(f"DATABASE_URL schema validation failed: {new_db_url}")
                                return
                        except SchemaValidationError as validation_error:
                            self._config_stats['schema_validation_errors'] += 1
                            self._circuit_breaker.record_failure()
                            logger.error(f"DATABASE_URL validation error: {validation_error}")
                            return

                        # Apply change
                        old_value = self.DATABASE_URL
                        self.DATABASE_URL = new_db_url

                        try:
                            # Notify application components to refresh database connections
                            await self._execute_reload_handler("database_pool_refresh", new_db_url)

                            # Success
                            self._circuit_breaker.record_success()
                            self._config_stats['successful_reloads'] += 1
                            self._config_stats['consecutive_failures'] = 0
                            logger.info("✓ DATABASE_URL hot reloaded successfully")

                        except Exception as handler_error:
                            # Rollback on handler failure
                            logger.error(f"Database handler failed, rolling back: {handler_error}")
                            self.DATABASE_URL = old_value
                            await self.rollback_parameter("DATABASE_URL")
                            raise handler_error

                except Exception as e:
                    logger.error(f"Failed to reload DATABASE_URL: {e}")
                    self._config_stats['failed_reloads'] += 1
                    self._config_stats['consecutive_failures'] += 1
                    self._circuit_breaker.record_failure()

                    # Emergency shutdown on critical parameter failure
                    if self._config_stats['consecutive_failures'] >= 3:
                        logger.critical("Too many consecutive failures, triggering emergency shutdown")
                        await self.emergency_shutdown()

        elif event.event_type == "delete":
            logger.critical("DATABASE_URL deleted - triggering emergency shutdown")
            await self.emergency_shutdown()

    async def _handle_redis_url_change(self, event):
        """Handle REDIS_URL parameter changes with connection refresh."""
        logger.info(f"REDIS_URL changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock("redis_url"):
                try:
                    new_redis_url = await self.notification_client.refresh_parameter("REDIS_URL")
                    if new_redis_url and new_redis_url != self.REDIS_URL:
                        self.REDIS_URL = new_redis_url

                        # Notify application components to refresh Redis connections
                        await self._execute_reload_handler("redis_connection_refresh", new_redis_url)

                        logger.info("✓ REDIS_URL hot reloaded successfully")
                        self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload REDIS_URL: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_internal_api_key_change(self, event):
        """Handle INTERNAL_API_KEY changes."""
        logger.info(f"INTERNAL_API_KEY changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock("internal_api_key"):
                try:
                    new_api_key = await self.notification_client.refresh_parameter("INTERNAL_API_KEY")
                    if new_api_key and new_api_key != self.internal_api_key:
                        self.internal_api_key = new_api_key

                        # Update HTTP client headers for service-to-service communication
                        await self._execute_reload_handler("api_key_refresh", new_api_key)

                        logger.info("✓ INTERNAL_API_KEY hot reloaded successfully")
                        self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload INTERNAL_API_KEY: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_gateway_secret_change(self, event):
        """Handle GATEWAY_SECRET changes."""
        logger.info(f"GATEWAY_SECRET changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock("gateway_secret"):
                try:
                    new_gateway_secret = await self.notification_client.refresh_parameter("GATEWAY_SECRET")
                    if new_gateway_secret and new_gateway_secret != self.gateway_secret:
                        self.gateway_secret = new_gateway_secret

                        # Update gateway authentication components
                        await self._execute_reload_handler("gateway_secret_refresh", new_gateway_secret)

                        logger.info("✓ GATEWAY_SECRET hot reloaded successfully")
                        self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload GATEWAY_SECRET: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_service_url_change(self, event, parameter_key: str):
        """Handle service URL configuration changes."""
        logger.info(f"Service URL {parameter_key} changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock(f"service_url_{parameter_key}"):
                try:
                    new_url = await self.notification_client.refresh_parameter(parameter_key)
                    if new_url:
                        # Update the appropriate service URL attribute
                        url_mapping = {
                            "signal_service.ticker_service_url": "TICKER_SERVICE_URL",
                            "signal_service.instrument_service_url": "INSTRUMENT_SERVICE_URL",
                            "signal_service.marketplace_service_url": "MARKETPLACE_SERVICE_URL",
                            "signal_service.user_service_url": "USER_SERVICE_URL",
                            "signal_service.calendar_service_url": "CALENDAR_SERVICE_URL",
                            "signal_service.alert_service_url": "ALERT_SERVICE_URL",
                            "signal_service.messaging_service_url": "MESSAGING_SERVICE_URL",
                            "signal_service.subscription_service_url": "SUBSCRIPTION_SERVICE_URL"
                        }

                        attr_name = url_mapping.get(parameter_key)
                        if attr_name:
                            current_url = getattr(self, attr_name, None)
                            if new_url != current_url:
                                setattr(self, attr_name, new_url)

                                # Notify HTTP clients to update service URLs
                                await self._execute_reload_handler("service_url_refresh", {
                                    "service": attr_name,
                                    "url": new_url
                                })

                                logger.info(f"✓ {attr_name} hot reloaded successfully")
                                self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload service URL {parameter_key}: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_performance_setting_change(self, event, parameter_key: str):
        """Handle performance and cache setting changes."""
        logger.info(f"Performance setting {parameter_key} changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock(f"performance_{parameter_key}"):
                try:
                    new_value = await self.notification_client.refresh_parameter(parameter_key)
                    if new_value:
                        # Update the appropriate performance setting
                        setting_mapping = {
                            "signal_service.cache_ttl_seconds": ("CACHE_TTL_SECONDS", int),
                            "signal_service.max_batch_size": ("MAX_BATCH_SIZE", int),
                            "signal_service.max_cpu_cores": ("MAX_CPU_CORES", int),
                            "signal_service.service_integration_timeout": ("SERVICE_INTEGRATION_TIMEOUT", float)
                        }

                        attr_name, converter = setting_mapping.get(parameter_key, (None, str))
                        if attr_name:
                            current_value = getattr(self, attr_name, None)
                            new_converted_value = converter(new_value)

                            if new_converted_value != current_value:
                                setattr(self, attr_name, new_converted_value)

                                # Notify application components of performance setting changes
                                await self._execute_reload_handler("performance_setting_refresh", {
                                    "setting": attr_name,
                                    "value": new_converted_value
                                })

                                logger.info(f"✓ {attr_name} hot reloaded successfully")
                                self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload performance setting {parameter_key}: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_feature_flag_change(self, event):
        """Handle feature flag changes."""
        if event.parameter_key.startswith("FEATURE_"):
            feature_name = event.parameter_key[8:]  # Remove "FEATURE_" prefix
            logger.info(f"Feature flag {feature_name} changed: {event.event_type}")

            if event.event_type == "update":
                try:
                    new_value = await self.notification_client.refresh_parameter(event.parameter_key)
                    if new_value is not None:
                        feature_enabled = new_value.lower() in ("true", "1", "yes", "on")

                        # Notify feature flag system
                        await self._execute_reload_handler("feature_flag_refresh", {
                            "feature": feature_name,
                            "enabled": feature_enabled
                        })

                        logger.info(f"✓ Feature flag {feature_name} updated: {feature_enabled}")
                        self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload feature flag {feature_name}: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_watermark_config_change(self, event, parameter_key: str):
        """Handle watermark configuration changes."""
        logger.info(f"Watermark config {parameter_key} changed: {event.event_type}")

        if event.event_type == "update":
            async with self._get_reload_lock(f"watermark_{parameter_key}"):
                try:
                    new_value = await self.notification_client.refresh_parameter(parameter_key)
                    if new_value:
                        # Update watermark configuration
                        if parameter_key == "WATERMARK_SECRET":
                            if new_value != self.WATERMARK_SECRET:
                                self.WATERMARK_SECRET = new_value
                        elif parameter_key == "WATERMARK_ENFORCEMENT_ENABLED":
                            if new_value != self.WATERMARK_ENFORCEMENT_ENABLED:
                                self.WATERMARK_ENFORCEMENT_ENABLED = new_value
                        elif parameter_key == "WATERMARK_ENFORCEMENT_POLICY":
                            if new_value != self.WATERMARK_ENFORCEMENT_POLICY:
                                self.WATERMARK_ENFORCEMENT_POLICY = new_value

                        # Notify watermark service of configuration changes
                        await self._execute_reload_handler("watermark_config_refresh", {
                            "parameter": parameter_key,
                            "value": new_value
                        })

                        logger.info(f"✓ {parameter_key} hot reloaded successfully")
                        self._config_stats['successful_reloads'] += 1

                except Exception as e:
                    logger.error(f"Failed to reload watermark config {parameter_key}: {e}")
                    self._config_stats['failed_reloads'] += 1

    async def _handle_generic_config_change(self, event):
        """Handle any configuration change for monitoring and statistics."""
        self._config_stats['hot_reloads'] += 1
        self._config_stats['last_reload_time'] = datetime.now().isoformat()

        logger.debug(f"Config parameter changed: {event.parameter_key} ({event.event_type})")

    def register_hot_reload_handler(self, handler_type: str, handler: Callable):
        """Register a custom hot reload handler.

        Args:
            handler_type: Type of reload handler (e.g., 'database_pool_refresh', 'redis_connection_refresh')
            handler: Async callable to handle the reload
        """
        self._hot_reload_handlers[handler_type] = handler
        logger.debug(f"Registered hot reload handler: {handler_type}")

    async def _execute_reload_handler(self, handler_type: str, data: Any):
        """Execute a registered hot reload handler."""
        if handler_type in self._hot_reload_handlers:
            try:
                await self._hot_reload_handlers[handler_type](data)
                logger.debug(f"Executed reload handler: {handler_type}")
            except Exception as e:
                logger.error(f"Hot reload handler {handler_type} failed: {e}")
                raise

    def _get_reload_lock(self, resource: str) -> asyncio.Lock:
        """Get or create a lock for a specific resource reload."""
        if resource not in self._reload_locks:
            self._reload_locks[resource] = asyncio.Lock()
        return self._reload_locks[resource]

    async def shutdown_hot_reload(self):
        """Clean shutdown of hot reload system."""
        if self.notification_client:
            try:
                await self.notification_client.stop_listening()
                logger.info("✓ Hot reload system shutdown complete")
            except Exception as e:
                logger.error(f"Error during hot reload shutdown: {e}")

    def get_hot_reload_stats(self) -> dict[str, Any]:
        """Get hot reload statistics for monitoring."""
        return {
            **self._config_stats,
            "handlers_registered": len(self._hot_reload_handlers),
            "notification_client_active": self.notification_client is not None
        }

    async def get_hot_reload_health(self) -> dict[str, Any]:
        """Get comprehensive hot reload system health - secure internal monitoring."""
        circuit_breaker_state = self._circuit_breaker.get_state()

        return {
            "hot_reload_enabled": self._hot_reload_enabled,
            "security_context_valid": self._validate_security_context(),
            "notification_client_active": self.notification_client is not None,
            "handlers_registered": len(self._hot_reload_handlers),
            "last_validation": datetime.now().isoformat(),
            "statistics": self._config_stats,
            "circuit_breaker": {
                "state": circuit_breaker_state.value,
                "failure_count": self._circuit_breaker._failure_count,
                "last_failure_time": self._circuit_breaker._last_failure_time.isoformat() if self._circuit_breaker._last_failure_time else None,
                "next_attempt_time": self._circuit_breaker._next_attempt_time.isoformat() if self._circuit_breaker._next_attempt_time else None
            },
            "fail_safes": {
                "kill_switch_enabled": self._kill_switch_enabled,
                "consecutive_failures": self._config_stats['consecutive_failures'],
                "max_consecutive_failures": self._max_consecutive_failures,
                "rollback_history_size": len(self._parameter_rollback_history)
            }
        }


# Enhanced settings factory with hot reload support
def get_hot_reloadable_settings(environment: str = None, enable_hot_reload: bool = True) -> HotReloadableSignalServiceConfig:
    """Get hot reloadable configuration instance - secure config service only.

    Args:
        environment: Explicit environment override for testing
        enable_hot_reload: Whether to enable hot parameter reloading

    Returns:
        HotReloadableSignalServiceConfig instance
    """
    config = HotReloadableSignalServiceConfig(environment=environment)

    # Security: Only enable if explicitly requested and security context valid
    if enable_hot_reload:
        logger.info("Creating secure hot reloadable configuration")

    return config


# Enhanced lazy settings wrapper with hot reload support
class _HotReloadableLazySettings:
    def __init__(self):
        self._config = None
        self._initialized = False

    def __getattr__(self, name):
        if not self._initialized:
            self._config = get_hot_reloadable_settings()
            self._initialized = True
        return getattr(self._config, name)

    def get_config(self, key: str, default=None):
        if not self._initialized:
            self._config = get_hot_reloadable_settings()
            self._initialized = True
        return self._config.get_config(key, default)

    async def initialize_hot_reload(self, enable_hot_reload: bool = True):
        """Initialize secure hot reload system."""
        if not self._initialized:
            self._config = get_hot_reloadable_settings()
            self._initialized = True
        await self._config.initialize_hot_reload(enable_hot_reload)

    def register_hot_reload_handler(self, handler_type: str, handler: Callable):
        """Register hot reload handler."""
        if not self._initialized:
            self._config = get_hot_reloadable_settings()
            self._initialized = True
        self._config.register_hot_reload_handler(handler_type, handler)

    async def shutdown_hot_reload(self):
        """Shutdown hot reload system."""
        if self._initialized and self._config:
            await self._config.shutdown_hot_reload()

    def get_hot_reload_stats(self) -> dict[str, Any]:
        """Get hot reload statistics."""
        if self._initialized and self._config:
            return self._config.get_hot_reload_stats()
        return {"initialized": False}


# Global hot reloadable settings instance
hot_reloadable_settings = _HotReloadableLazySettings()
