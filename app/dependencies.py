"""
FastAPI dependency injection for Signal Service
"""

from app.repositories.signal_repository import SignalRepository
from app.services.flexible_timeframe_manager import FlexibleTimeframeManager
from app.services.formula_engine import FormulaEngine
from app.services.instrument_service_client import InstrumentServiceClient
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
from app.services.moneyness_historical_processor import MoneynessHistoricalProcessor
from app.services.universal_calculator import UniversalCalculator
from app.utils.redis import get_redis_client

# Global instances
_signal_repository: SignalRepository | None = None
_timeframe_manager: FlexibleTimeframeManager | None = None
_moneyness_calculator: MoneynessAwareGreeksCalculator | None = None
_moneyness_processor: MoneynessHistoricalProcessor | None = None
_instrument_client: InstrumentServiceClient | None = None
_universal_calculator: UniversalCalculator | None = None
_formula_engine: FormulaEngine | None = None


async def get_signal_repository() -> SignalRepository:
    """Get or create signal repository instance"""
    global _signal_repository
    if not _signal_repository:
        _signal_repository = SignalRepository()
        await _signal_repository.initialize()
    return _signal_repository


async def get_timeframe_manager() -> FlexibleTimeframeManager:
    """Get or create timeframe manager instance"""
    global _timeframe_manager
    if not _timeframe_manager:
        redis = await get_redis_client()
        _timeframe_manager = FlexibleTimeframeManager(redis)
    return _timeframe_manager


async def get_instrument_client() -> InstrumentServiceClient:
    """Get or create instrument service client"""
    global _instrument_client
    if not _instrument_client:
        from app.clients.client_factory import get_client_manager
        manager = get_client_manager()
        _instrument_client = await manager.get_client('instrument_service')
    return _instrument_client


async def get_moneyness_calculator() -> MoneynessAwareGreeksCalculator:
    """Get or create moneyness calculator instance"""
    global _moneyness_calculator
    if not _moneyness_calculator:
        instrument_client = await get_instrument_client()
        _moneyness_calculator = MoneynessAwareGreeksCalculator(instrument_client)
    return _moneyness_calculator


async def get_moneyness_processor() -> MoneynessHistoricalProcessor:
    """Get or create moneyness historical processor instance"""
    global _moneyness_processor
    if not _moneyness_processor:
        moneyness_calculator = await get_moneyness_calculator()
        signal_repository = await get_signal_repository()
        timeframe_manager = await get_timeframe_manager()
        instrument_client = await get_instrument_client()

        _moneyness_processor = MoneynessHistoricalProcessor(
            moneyness_calculator,
            signal_repository,
            timeframe_manager,
            instrument_client
        )
    return _moneyness_processor


async def get_universal_calculator() -> 'UniversalCalculator':
    """Get or create universal calculator instance"""
    global _universal_calculator
    if not _universal_calculator:
        from app.services.universal_calculator import UniversalCalculator
        _universal_calculator = UniversalCalculator()
    return _universal_calculator


async def get_formula_engine() -> 'FormulaEngine':
    """Get or create formula engine instance"""
    global _formula_engine
    if not _formula_engine:
        from app.services.formula_engine import FormulaEngine
        _formula_engine = FormulaEngine()
    return _formula_engine
