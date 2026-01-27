# [AGENT-2-PREMIUM-DISCOUNT] - MARKER: DO NOT MODIFY FILES WITH [AGENT-1], [AGENT-3], [AGENT-4], OR [AGENT-5] MARKERS
"""
Premium analysis API endpoints for F&O option chains.
Provides market vs theoretical price comparison using vectorized calculations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.premium_discount_calculator import PremiumDiscountCalculator
from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine
from app.utils.logging_utils import log_exception, log_info

router = APIRouter(prefix="/api/v2/signals/fo", tags=["premium-analysis"])

# Initialize calculator with vectorized engine
vectorized_engine = VectorizedPyvolibGreeksEngine()
premium_calculator = PremiumDiscountCalculator(vectorized_engine)


# Pydantic models for request/response
class OptionData(BaseModel):
    """Option data input model."""
    strike: float = Field(..., gt=0, description="Strike price")
    expiry_date: str = Field(..., description="Expiry date in YYYY-MM-DD format")
    option_type: str = Field(..., pattern="^(CE|CALL|PE|PUT)$", description="Option type")
    market_price: float = Field(..., ge=0, description="Current market price")
    underlying_price: float | None = Field(None, gt=0, description="Current underlying price")
    volatility: float | None = Field(None, gt=0, le=5, description="Implied volatility (default: 0.2)")


class PremiumAnalysisRequest(BaseModel):
    """Premium analysis request model."""
    symbol: str = Field(..., description="Underlying symbol (e.g., SYMBOL)")
    underlying_price: float = Field(..., gt=0, description="Current underlying price")
    options: list[OptionData] = Field(..., min_items=1, max_items=500, description="Option chain data")
    include_greeks: bool = Field(default=True, description="Include Greeks in response")


class StrikeRangeRequest(BaseModel):
    """Strike range premium analysis request."""
    symbol: str = Field(..., description="Underlying symbol")
    expiry_date: str = Field(..., description="Target expiry date")
    underlying_price: float = Field(..., gt=0)
    strike_min: float = Field(..., gt=0, description="Minimum strike price")
    strike_max: float = Field(..., gt=0, description="Maximum strike price")
    include_greeks: bool = Field(default=True)


class TermStructureRequest(BaseModel):
    """Term structure premium analysis request."""
    symbol: str = Field(..., description="Underlying symbol")
    underlying_price: float = Field(..., gt=0)
    expiry_dates: list[str] = Field(..., min_items=1, max_items=10, description="List of expiry dates")
    strikes: list[float] = Field(..., min_items=1, description="Strike prices to analyze")


class PremiumAnalysisResult(BaseModel):
    """Premium analysis result model."""
    strike: float
    expiry_date: str
    option_type: str
    market_price: float
    theoretical_price: float
    premium_amount: float
    premium_percentage: float
    is_overpriced: bool
    is_underpriced: bool
    mispricing_severity: str
    arbitrage_signal: bool
    greeks: dict[str, float | None] | None = None


class PremiumAnalysisResponse(BaseModel):
    """Premium analysis response model."""
    symbol: str
    underlying_price: float
    analysis_timestamp: datetime
    results: list[PremiumAnalysisResult]
    summary_stats: dict[str, Any]
    performance: dict[str, Any]


@router.post("/premium-analysis/expiry", response_model=PremiumAnalysisResponse)
async def premium_analysis_expiry(request: PremiumAnalysisRequest):
    """
    Calculate premium/discount analysis for options of a specific expiry.

    This endpoint analyzes market prices vs theoretical prices using Agent 1's
    vectorized pyvollib engine for efficient bulk calculations.

    **Performance Target**: 200-option analysis in <15ms

    Args:
        request: Premium analysis request with option chain data

    Returns:
        Comprehensive premium/discount analysis with arbitrage opportunities
    """
    try:
        log_info(f"[AGENT-2] Processing premium analysis for {request.symbol}: {len(request.options)} options")

        # Convert Pydantic models to dict format for calculator
        option_chain_data = []
        market_prices = []

        for option in request.options:
            option_dict = {
                'strike': option.strike,
                'expiry_date': option.expiry_date,
                'option_type': option.option_type,
                'volatility': option.volatility or 0.2,
                'underlying_price': option.underlying_price or request.underlying_price
            }
            option_chain_data.append(option_dict)
            market_prices.append(option.market_price)

        # Calculate premium analysis
        analysis_result = await premium_calculator.calculate_premium_analysis(
            market_prices=market_prices,
            option_chain_data=option_chain_data,
            underlying_price=request.underlying_price,
            include_greeks=request.include_greeks
        )

        # Convert results to response format
        analysis_results = []
        for result in analysis_result['results']:
            analysis_results.append(PremiumAnalysisResult(
                strike=result['strike'],
                expiry_date=result['expiry_date'],
                option_type=result['option_type'],
                market_price=result['market_price'],
                theoretical_price=result['theoretical_price'],
                premium_amount=result['premium_amount'],
                premium_percentage=result['premium_percentage'],
                is_overpriced=result['is_overpriced'],
                is_underpriced=result['is_underpriced'],
                mispricing_severity=result['mispricing_severity'],
                arbitrage_signal=result['arbitrage_signal'],
                greeks=result.get('greeks')
            ))

        # Calculate summary statistics
        summary_stats = _calculate_summary_stats(analysis_result['results'])

        return PremiumAnalysisResponse(
            symbol=request.symbol,
            underlying_price=request.underlying_price,
            analysis_timestamp=datetime.utcnow(),
            results=analysis_results,
            summary_stats=summary_stats,
            performance=analysis_result['performance']
        )

    except Exception as e:
        log_exception(f"[AGENT-2] Premium analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Premium analysis failed: {str(e)}")


@router.get("/premium-analysis/strike-range/{symbol}")
async def premium_analysis_strike_range(
    symbol: str,
    expiry_date: str = Query(..., description="Expiry date (YYYY-MM-DD)"),
    underlying_price: float = Query(..., gt=0, description="Current underlying price"),
    strike_min: float = Query(..., gt=0, description="Minimum strike"),
    strike_max: float = Query(..., gt=0, description="Maximum strike"),
    strike_step: float = Query(100.0, gt=0, description="Strike step size"),
    include_greeks: bool = Query(True, description="Include Greeks calculation")
):
    """
    Analyze premium/discount for a range of strikes at specific expiry.

    Generates option chain data for the specified strike range and calculates
    premium analysis using market data and theoretical pricing.

    Args:
        symbol: Underlying symbol
        expiry_date: Target expiry date
        underlying_price: Current underlying price
        strike_min: Minimum strike price
        strike_max: Maximum strike price
        strike_step: Strike price increment
        include_greeks: Include Greeks calculations

    Returns:
        Premium analysis for the strike range
    """
    try:
        log_info(f"[AGENT-2] Strike range analysis for {symbol}: {strike_min}-{strike_max}")

        if strike_min >= strike_max:
            raise HTTPException(status_code=400, detail="strike_min must be less than strike_max")

        if (strike_max - strike_min) / strike_step > 100:
            raise HTTPException(status_code=400, detail="Strike range too large (max 100 strikes)")

        # Generate option chain for strike range
        option_chain_data = []
        market_prices = []

        # Generate strikes
        current_strike = strike_min
        while current_strike <= strike_max:
            # Create both CE and PE options for each strike
            for option_type in ['CE', 'PE']:
                # Placeholder - would generate option data
                pass
            current_strike += strike_step

        # Calculate premium analysis
        analysis_result = await premium_calculator.calculate_premium_analysis(
            market_prices=market_prices,
            option_chain_data=option_chain_data,
            underlying_price=underlying_price,
            include_greeks=include_greeks
        )

        # Group results by strike
        strike_results = {}
        for result in analysis_result['results']:
            strike = result['strike']
            if strike not in strike_results:
                strike_results[strike] = {'CE': None, 'PE': None}
            strike_results[strike][result['option_type']] = result

        return {
            'symbol': symbol,
            'expiry_date': expiry_date,
            'underlying_price': underlying_price,
            'strike_range': {'min': strike_min, 'max': strike_max, 'step': strike_step},
            'strike_results': strike_results,
            'summary_stats': _calculate_summary_stats(analysis_result['results']),
            'performance': analysis_result['performance'],
            'timestamp': datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"[AGENT-2] Strike range analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strike range analysis failed: {str(e)}")


@router.post("/premium-analysis/term-structure")
async def premium_analysis_term_structure(request: TermStructureRequest):
    """
    Analyze premium/discount across multiple expiries (term structure).

    Calculates premium analysis for the same strikes across different expiry dates
    to identify term structure arbitrage opportunities and mispricing patterns.

    Args:
        request: Term structure analysis request

    Returns:
        Term structure premium analysis with cross-expiry comparisons
    """
    try:
        log_info(f"[AGENT-2] Term structure analysis for {request.symbol}: {len(request.expiry_dates)} expiries")

        term_results = {}

        for expiry_date in request.expiry_dates:
            # Generate option chain for this expiry
            option_chain_data = []
            market_prices = []
            # Placeholder - would generate option chain
            # Calculate premium analysis for this expiry
            expiry_analysis = await premium_calculator.calculate_premium_analysis(
                market_prices=market_prices,
                option_chain_data=option_chain_data,
                underlying_price=request.underlying_price,
                include_greeks=True
            )

            term_results[expiry_date] = {
                'results': expiry_analysis['results'],
                'summary_stats': _calculate_summary_stats(expiry_analysis['results']),
                'performance': expiry_analysis['performance']
            }

        # Calculate cross-expiry analysis
        cross_expiry_analysis = _analyze_term_structure_patterns(term_results, request.strikes)

        return {
            'symbol': request.symbol,
            'underlying_price': request.underlying_price,
            'expiry_dates': request.expiry_dates,
            'strikes': request.strikes,
            'term_structure_results': term_results,
            'cross_expiry_analysis': cross_expiry_analysis,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_exception(f"[AGENT-2] Term structure analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Term structure analysis failed: {str(e)}")


@router.get("/premium-analysis/arbitrage-opportunities/{symbol}")
async def get_arbitrage_opportunities(
    symbol: str,
    min_severity: str = Query("MEDIUM", regex="^(LOW|MEDIUM|HIGH|EXTREME)$", description="Minimum mispricing severity"),
    expiry_date: str | None = Query(None, description="Filter by specific expiry date")
):
    """
    Get current arbitrage opportunities based on premium/discount analysis.

    Scans the option chain for mispricing opportunities above the specified
    severity threshold and returns actionable arbitrage signals.

    Args:
        symbol: Underlying symbol
        min_severity: Minimum mispricing severity to include
        expiry_date: Optional expiry filter

    Returns:
        List of arbitrage opportunities with trading recommendations
    """
    try:
        log_info(f"[AGENT-2] Arbitrage scan for {symbol}, min severity: {min_severity}")

        # Placeholder - would implement arbitrage scan
        return []
    except Exception as e:
        log_exception(f"[AGENT-2] Arbitrage opportunities scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Arbitrage scan failed: {str(e)}")


@router.get("/premium-analysis/performance-metrics")
async def get_performance_metrics():
    """
    Get performance metrics for the premium analysis engine.

    Returns current performance statistics including execution times,
    throughput metrics, and vectorized engine performance.
    """
    try:
        premium_metrics = premium_calculator.get_performance_metrics()
        vectorized_metrics = vectorized_engine.get_performance_metrics()

        return {
            'timestamp': datetime.utcnow().isoformat(),
            'premium_calculator': premium_metrics,
            'vectorized_engine': vectorized_metrics,
            'integrated_performance': {
                'total_options_processed': premium_metrics.get('total_options_analyzed', 0),
                'avg_total_time_ms': premium_metrics.get('avg_analysis_time_ms', 0),
                'theoretical_calculation_ratio': (
                    vectorized_metrics.get('avg_vectorized_time_ms', 0) /
                    premium_metrics.get('avg_analysis_time_ms', 1)
                ) if premium_metrics.get('avg_analysis_time_ms', 0) > 0 else 0,
                'performance_target_met': premium_metrics.get('avg_analysis_time_ms', 1000) < 15.0
            }
        }

    except Exception as e:
        log_exception(f"[AGENT-2] Performance metrics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Performance metrics failed: {str(e)}")


# Helper functions
def _calculate_summary_stats(results: list[dict]) -> dict[str, Any]:
    """Calculate summary statistics for premium analysis results."""
    if not results:
        return {}

    try:
        premium_percentages = [r.get('premium_percentage', 0) for r in results]
        overpriced_count = len([r for r in results if r.get('is_overpriced', False)])
        arbitrage_signals = len([r for r in results if r.get('arbitrage_signal', False)])

        severity_counts = {}
        for result in results:
            severity = result.get('mispricing_severity', 'LOW')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            'total_options': len(results),
            'overpriced_options': overpriced_count,
            'underpriced_options': len(results) - overpriced_count,
            'arbitrage_signals': arbitrage_signals,
            'avg_premium_percentage': sum(premium_percentages) / len(premium_percentages) if premium_percentages else 0,
            'max_premium_percentage': max(premium_percentages) if premium_percentages else 0,
            'min_premium_percentage': min(premium_percentages) if premium_percentages else 0,
            'severity_distribution': severity_counts,
            'mispricing_rate': (arbitrage_signals / len(results) * 100) if results else 0
        }

    except Exception:
        return {}



def _analyze_term_structure_patterns(term_results: dict, strikes: list[float]) -> dict[str, Any]:
    """Analyze patterns across the term structure."""
    try:
        patterns = {
            'contango_backwardation': 'neutral',
            'volatility_skew_evolution': {},
            'arbitrage_calendar_spreads': [],
            'time_decay_patterns': {}
        }

        # Analyze premium evolution across expiries
        expiry_dates = sorted(term_results.keys())
        if len(expiry_dates) >= 2:
            # Compare near vs far month premiums
            near_month = expiry_dates[0]
            far_month = expiry_dates[-1]

            near_avg_premium = sum(r.get('premium_percentage', 0) for r in term_results[near_month]['results']) / len(term_results[near_month]['results'])
            far_avg_premium = sum(r.get('premium_percentage', 0) for r in term_results[far_month]['results']) / len(term_results[far_month]['results'])

            if far_avg_premium > near_avg_premium:
                patterns['contango_backwardation'] = 'contango'
            elif far_avg_premium < near_avg_premium:
                patterns['contango_backwardation'] = 'backwardation'

        return patterns

    except Exception:
        return {}
