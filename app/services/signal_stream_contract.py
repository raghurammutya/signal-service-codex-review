"""
Signal Stream Contract and Key Management

Sprint 5A: Signal execution + delivery contract
- Define stream key formats for public/common vs marketplace signals
- Manage entitlement checking for signal access
- Provide unified interface for SDK signal subscription
"""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Signal types for access control."""
    PUBLIC = "public"           # Free signals available to all users
    COMMON = "common"           # Common indicators (RSI, SMA, etc.)
    MARKETPLACE = "marketplace" # Premium signals requiring entitlement
    PERSONAL = "personal"       # User's personal/custom signals


class StreamKeyFormat:
    """
    Sprint 5A: Stream key formats for signal routing and entitlement.

    Format patterns:
    - Public/common: "{signal_type}:{instrument}:{indicator}:{params}"
    - Marketplace: "marketplace:{product_id}:{instrument}:{signal}:{params}"
    - Personal: "personal:{user_id}:{signal_id}:{instrument}:{params}"
    """

    @staticmethod
    def create_public_key(instrument: str, indicator: str, params: dict | None = None) -> str:
        """
        Create stream key for public/common signals.
        No entitlement required for these signals.

        Examples:
        - "public:SYMBOL:price:realtime"
        - "common:SYMBOL:rsi:14"
        - "common:SYMBOL:sma:20"
        """
        params_str = StreamKeyFormat._serialize_params(params)
        return f"public:{instrument}:{indicator}:{params_str}"

    @staticmethod
    def create_common_key(instrument: str, indicator: str, params: dict | None = None) -> str:
        """Create stream key for common indicators."""
        params_str = StreamKeyFormat._serialize_params(params)
        return f"common:{instrument}:{indicator}:{params_str}"

    @staticmethod
    def create_marketplace_key(
        product_id: str,
        instrument: str,
        signal: str,
        params: dict | None = None
    ) -> str:
        """
        Create stream key for marketplace signals.
        Requires entitlement check via marketplace service.

        Example: "marketplace:prod-123:SYMBOL:premium_momentum:fast"
        """
        params_str = StreamKeyFormat._serialize_params(params)
        return f"marketplace:{product_id}:{instrument}:{signal}:{params_str}"

    @staticmethod
    def create_personal_key(
        user_id: str,
        signal_id: str,
        instrument: str,
        params: dict | None = None
    ) -> str:
        """
        Create stream key for personal signals.
        Only accessible by the owning user.

        Example: "personal:user-456:signal-789:SYMBOL:custom"
        """
        params_str = StreamKeyFormat._serialize_params(params)
        return f"personal:{user_id}:{signal_id}:{instrument}:{params_str}"

    @staticmethod
    def parse_key(stream_key: str) -> dict[str, Any]:
        """Parse a stream key to extract components."""
        parts = stream_key.split(":")

        if len(parts) < 3:
            raise ValueError(f"Invalid stream key format: {stream_key}")

        signal_type = parts[0]

        if signal_type in ["public", "common"]:
            return {
                "type": signal_type,
                "instrument": parts[1],
                "indicator": parts[2],
                "params": StreamKeyFormat._deserialize_params(parts[3] if len(parts) > 3 else "")
            }
        if signal_type == "marketplace":
            return {
                "type": signal_type,
                "product_id": parts[1],
                "instrument": parts[2],
                "signal": parts[3],
                "params": StreamKeyFormat._deserialize_params(parts[4] if len(parts) > 4 else "")
            }
        if signal_type == "personal":
            return {
                "type": signal_type,
                "user_id": parts[1],
                "signal_id": parts[2],
                "instrument": parts[3],
                "params": StreamKeyFormat._deserialize_params(parts[4] if len(parts) > 4 else "")
            }
        raise ValueError(f"Unknown signal type: {signal_type}")

    @staticmethod
    def _serialize_params(params: dict | None) -> str:
        """Serialize parameters to string format."""
        if not params:
            return "default"

        # Sort keys for consistent keys
        sorted_items = sorted(params.items())
        return "_".join([f"{k}-{v}" for k, v in sorted_items])

    @staticmethod
    def _deserialize_params(params_str: str) -> dict | None:
        """Deserialize parameters from string format."""
        if not params_str or params_str == "default":
            return None

        params = {}
        for item in params_str.split("_"):
            if "-" in item:
                key, value = item.split("-", 1)
                # Try to convert to appropriate type
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Keep as string
                params[key] = value

        return params


@dataclass
class SignalEntitlement:
    """Entitlement info for a signal stream."""
    stream_key: str
    signal_type: SignalType
    is_allowed: bool
    user_id: str | None = None
    product_id: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None


class SignalStreamContract:
    """
    Sprint 5A: Signal delivery contract for the signal service.

    Manages:
    - Stream key generation and parsing
    - Entitlement checking for signal access
    - Signal routing to appropriate computation engines
    """

    # Common indicators available to all users (no entitlement required)
    COMMON_INDICATORS = {
        # Price-based
        "sma", "ema", "wma", "hma", "tema", "dema",
        # Momentum
        "rsi", "macd", "stochastic", "cci", "mfi", "roc",
        # Volatility
        "bb", "atr", "kc", "dc", "adx",
        # Volume
        "obv", "vwap", "ad", "cmf",
        # Trend
        "ichimoku", "psar", "supertrend"
    }

    def __init__(self, marketplace_client=None):
        """
        Initialize signal stream contract.

        Args:
            marketplace_client: Client for checking marketplace entitlements
        """
        self.marketplace_client = marketplace_client
        self._entitlement_cache: dict[str, SignalEntitlement] = {}

    async def check_entitlement(
        self,
        stream_key: str,
        user_id: str,
        execution_token: str | None = None
    ) -> SignalEntitlement:
        """
        Check if user has entitlement to access a signal stream.

        Args:
            stream_key: Signal stream key
            user_id: User requesting access
            execution_token: Marketplace execution token (for premium signals)

        Returns:
            SignalEntitlement with access decision
        """
        try:
            # Check cache first
            cache_key = f"{user_id}:{stream_key}"
            if cache_key in self._entitlement_cache:
                cached = self._entitlement_cache[cache_key]
                # Check if cache is still valid
                if cached.expires_at and cached.expires_at > datetime.now(UTC):
                    return cached

            # Parse stream key
            key_info = StreamKeyFormat.parse_key(stream_key)
            signal_type = SignalType(key_info["type"])

            # Check based on signal type
            if signal_type == SignalType.PUBLIC:
                # Public signals are always allowed
                entitlement = SignalEntitlement(
                    stream_key=stream_key,
                    signal_type=signal_type,
                    is_allowed=True,
                    user_id=user_id,
                    reason="Public signal"
                )

            elif signal_type == SignalType.COMMON:
                # Common indicators are allowed for all authenticated users
                indicator = key_info.get("indicator", "")
                if indicator.lower() in self.COMMON_INDICATORS:
                    entitlement = SignalEntitlement(
                        stream_key=stream_key,
                        signal_type=signal_type,
                        is_allowed=True,
                        user_id=user_id,
                        reason="Common indicator"
                    )
                else:
                    entitlement = SignalEntitlement(
                        stream_key=stream_key,
                        signal_type=signal_type,
                        is_allowed=False,
                        user_id=user_id,
                        reason=f"Unknown common indicator: {indicator}"
                    )

            elif signal_type == SignalType.MARKETPLACE:
                # Marketplace signals require entitlement check
                product_id = key_info.get("product_id")

                if not execution_token:
                    entitlement = SignalEntitlement(
                        stream_key=stream_key,
                        signal_type=signal_type,
                        is_allowed=False,
                        user_id=user_id,
                        product_id=product_id,
                        reason="No execution token provided"
                    )
                else:
                    # Check with marketplace service
                    is_allowed = await self._check_marketplace_entitlement(
                        user_id, product_id, execution_token
                    )
                    entitlement = SignalEntitlement(
                        stream_key=stream_key,
                        signal_type=signal_type,
                        is_allowed=is_allowed,
                        user_id=user_id,
                        product_id=product_id,
                        expires_at=datetime.now(UTC).replace(hour=23, minute=59),  # Daily expiry
                        reason="Marketplace entitlement" if is_allowed else "No active subscription"
                    )

            elif signal_type == SignalType.PERSONAL:
                # Personal signals only accessible by owner
                owner_id = key_info.get("user_id")
                is_owner = (user_id == owner_id)

                entitlement = SignalEntitlement(
                    stream_key=stream_key,
                    signal_type=signal_type,
                    is_allowed=is_owner,
                    user_id=user_id,
                    reason="Owner access" if is_owner else "Not signal owner"
                )

            else:
                # Unknown signal type
                entitlement = SignalEntitlement(
                    stream_key=stream_key,
                    signal_type=signal_type,
                    is_allowed=False,
                    user_id=user_id,
                    reason=f"Unknown signal type: {signal_type}"
                )

            # Cache the result
            self._entitlement_cache[cache_key] = entitlement

            # Log entitlement decision
            logger.info(
                f"Entitlement check for user {user_id} on {stream_key}: "
                f"allowed={entitlement.is_allowed}, reason={entitlement.reason}"
            )

            return entitlement

        except Exception as e:
            logger.error(f"Error checking entitlement: {e}")
            # Deny on error
            return SignalEntitlement(
                stream_key=stream_key,
                signal_type=SignalType.PUBLIC,  # Default
                is_allowed=False,
                user_id=user_id,
                reason=f"Entitlement check error: {str(e)}"
            )

    async def _check_marketplace_entitlement(
        self,
        user_id: str,
        product_id: str,
        execution_token: str
    ) -> bool:
        """
        Check marketplace entitlement via marketplace service.

        Returns:
            True if user has valid subscription/entitlement
        """
        if not self.marketplace_client:
            logger.warning("No marketplace client configured - denying access")
            return False

        try:
            # Call marketplace service to verify token and subscription
            response = await self.marketplace_client.verify_execution_token(
                token=execution_token,
                product_id=product_id,
                user_id=user_id
            )

            return response.get("is_valid", False)

        except Exception as e:
            logger.error(f"Marketplace entitlement check failed: {e}")
            return False

    def get_public_streams(self, instruments: list[str]) -> list[str]:
        """Get list of public stream keys for given instruments."""
        streams = []

        # Basic price streams
        for instrument in instruments:
            streams.append(StreamKeyFormat.create_public_key(instrument, "price"))
            streams.append(StreamKeyFormat.create_public_key(instrument, "quote"))
            streams.append(StreamKeyFormat.create_public_key(instrument, "ohlc"))

        return streams

    def get_common_streams(self, instruments: list[str]) -> list[str]:
        """Get list of common indicator streams for given instruments."""
        streams = []

        # Popular indicators with default params
        common_configs = [
            ("rsi", {"period": 14}),
            ("sma", {"period": 20}),
            ("ema", {"period": 20}),
            ("macd", {"fast": 12, "slow": 26, "signal": 9}),
            ("bb", {"period": 20, "std": 2}),
            ("atr", {"period": 14}),
            ("adx", {"period": 14}),
            ("vwap", None),
        ]

        for instrument in instruments:
            for indicator, params in common_configs:
                streams.append(StreamKeyFormat.create_common_key(
                    instrument, indicator, params
                ))

        return streams
