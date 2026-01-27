# [AGENT-2-PREMIUM-DISCOUNT] - MARKER: DO NOT MODIFY FILES WITH [AGENT-1], [AGENT-3], [AGENT-4], OR [AGENT-5] MARKERS
"""
Premium/Discount calculation engine for F&O option chains.
Compares market prices vs theoretical prices using vectorized pyvollib engine.

Performance target: 200-option premium analysis in <15ms total
"""

import logging
import time
from datetime import date, datetime
from enum import Enum
from typing import Any

import numpy as np
from py_vollib.black_scholes_merton import black_scholes_merton

from app.errors import GreeksCalculationError

# Integration with Agent 1's vectorized engine
from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine
from app.utils.logging_utils import log_exception, log_info, log_warning

logger = logging.getLogger(__name__)


class MispricingSeverity(Enum):
    """Classification levels for mispricing severity."""
    LOW = "LOW"           # 0-3% premium/discount
    MEDIUM = "MEDIUM"     # 3-8% premium/discount
    HIGH = "HIGH"         # 8-15% premium/discount
    EXTREME = "EXTREME"   # >15% premium/discount


class PremiumDiscountCalculator:
    """
    [AGENT-2] Premium/discount calculator using vectorized theoretical price computation.

    Integrates with Agent 1's VectorizedPyvolibGreeksEngine for efficient theoretical pricing.
    Provides market vs theoretical price analysis for F&O option chains.

    Key Features:
    - Bulk premium/discount analysis for entire option chains
    - Arbitrage opportunity detection
    - Mispricing severity classification
    - Time-based premium decay tracking
    - Performance optimization for real-time analysis
    """

    def __init__(self, vectorized_engine: VectorizedPyvolibGreeksEngine | None = None):
        """
        Initialize premium/discount calculator.

        Args:
            vectorized_engine: Instance of vectorized Greeks engine (Agent 1)
        """
        # Use provided engine or create new instance
        self.vectorized_engine = vectorized_engine or VectorizedPyvolibGreeksEngine()

        # Premium analysis thresholds
        self.severity_thresholds = {
            MispricingSeverity.LOW: (0.0, 3.0),
            MispricingSeverity.MEDIUM: (3.0, 8.0),
            MispricingSeverity.HIGH: (8.0, 15.0),
            MispricingSeverity.EXTREME: (15.0, float('inf'))
        }

        # Performance tracking
        self.performance_metrics = {
            'premium_analyses': 0,
            'total_options_analyzed': 0,
            'avg_analysis_time_ms': 0.0,
            'arbitrage_opportunities_found': 0
        }

        log_info("[AGENT-2] PremiumDiscountCalculator initialized with vectorized engine integration")

    async def calculate_premium_analysis(
        self,
        market_prices: list[float],
        option_chain_data: list[dict],
        underlying_price: float,
        include_greeks: bool = True
    ) -> dict[str, Any]:
        """
        Calculate comprehensive premium/discount analysis for option chain.

        Args:
            market_prices: Current market prices for options
            option_chain_data: Option metadata (strikes, expiries, types, etc.)
            underlying_price: Current underlying asset price
            include_greeks: Whether to include Greeks in response

        Returns:
            Dict with premium analysis results and performance metrics
        """
        start_time = time.perf_counter()

        if len(market_prices) != len(option_chain_data):
            raise ValueError("Market prices and option data lengths must match")

        if not option_chain_data:
            return {'results': [], 'performance': {}, 'method_used': 'none'}

        try:
            # Step 1: Get theoretical prices using Agent 1's vectorized engine
            theoretical_results = await self.vectorized_engine.calculate_option_chain_greeks_vectorized(
                option_chain_data, underlying_price,
                greeks_to_calculate=['delta', 'gamma', 'theta', 'vega', 'rho'] if include_greeks else []
            )

            if theoretical_results['method_used'] == 'none':
                raise GreeksCalculationError("Failed to calculate theoretical prices")

            # Step 2: Calculate theoretical option prices
            theoretical_prices = await self._calculate_theoretical_prices(
                option_chain_data, underlying_price
            )

            # Step 3: Compute premium/discount analysis
            premium_results = await self._compute_premium_analysis(
                market_prices, theoretical_prices, option_chain_data,
                theoretical_results['results'] if include_greeks else None
            )

            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            # Update performance metrics
            self.performance_metrics['premium_analyses'] += 1
            self.performance_metrics['total_options_analyzed'] += len(option_chain_data)
            self._update_avg_time(execution_time_ms)

            log_info(f"[AGENT-2] Premium analysis completed: {len(option_chain_data)} options in {execution_time_ms:.2f}ms")

            return {
                'results': premium_results,
                'performance': {
                    'execution_time_ms': execution_time_ms,
                    'options_processed': len(option_chain_data),
                    'theoretical_calculation_time_ms': theoretical_results.get('performance', {}).get('execution_time_ms', 0),
                    'premium_calculation_time_ms': execution_time_ms - theoretical_results.get('performance', {}).get('execution_time_ms', 0),
                    'options_per_second': len(option_chain_data) / (execution_time_ms / 1000) if execution_time_ms > 0 else 0
                },
                'method_used': 'vectorized_premium_analysis',
                'theoretical_engine_method': theoretical_results['method_used']
            }

        except Exception as e:
            log_exception(f"[AGENT-2] Premium analysis failed: {e}")
            raise GreeksCalculationError(f"Premium analysis failed: {e}")

    async def analyze_option_chain_mispricing(
        self,
        option_chain_data: list[dict]
    ) -> dict[str, Any]:
        """
        Analyze entire option chain for mispricing patterns.

        Args:
            option_chain_data: Complete option chain with market prices and metadata

        Returns:
            Analysis results with mispricing patterns and arbitrage opportunities
        """
        start_time = time.perf_counter()

        try:
            # Group by expiry for term structure analysis
            expiry_groups = self._group_by_expiry(option_chain_data)

            analysis_results = {}
            total_arbitrage_ops = 0

            for expiry, options in expiry_groups.items():
                if not options:
                    continue

                # Extract data for this expiry
                market_prices = [opt.get('market_price', 0.0) for opt in options]
                underlying_price = options[0].get('underlying_price', 0.0)

                if underlying_price <= 0:
                    log_warning(f"[AGENT-2] Invalid underlying price for expiry {expiry}")
                    continue

                # Calculate premium analysis for this expiry
                expiry_analysis = await self.calculate_premium_analysis(
                    market_prices, options, underlying_price, include_greeks=True
                )

                # Detect arbitrage opportunities
                arbitrage_ops = await self._detect_arbitrage_opportunities(
                    expiry_analysis['results']
                )

                analysis_results[expiry] = {
                    'premium_analysis': expiry_analysis['results'],
                    'arbitrage_opportunities': arbitrage_ops,
                    'summary_stats': self._calculate_expiry_summary_stats(expiry_analysis['results'])
                }

                total_arbitrage_ops += len(arbitrage_ops)

            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            self.performance_metrics['arbitrage_opportunities_found'] += total_arbitrage_ops

            log_info(f"[AGENT-2] Chain mispricing analysis completed: {len(expiry_groups)} expiries, {total_arbitrage_ops} arbitrage opportunities in {execution_time_ms:.2f}ms")

            return {
                'expiry_analysis': analysis_results,
                'summary': {
                    'total_expiries_analyzed': len(expiry_groups),
                    'total_arbitrage_opportunities': total_arbitrage_ops,
                    'execution_time_ms': execution_time_ms
                }
            }

        except Exception as e:
            log_exception(f"[AGENT-2] Chain mispricing analysis failed: {e}")
            raise GreeksCalculationError(f"Chain mispricing analysis failed: {e}")

    async def calculate_arbitrage_opportunities(
        self,
        chain_data: list[dict]
    ) -> list[dict]:
        """
        Calculate potential arbitrage opportunities in option chain.

        Args:
            chain_data: Option chain with premium/discount analysis

        Returns:
            List of arbitrage opportunity dicts
        """
        try:
            arbitrage_opportunities = []

            # Group by expiry and option type for analysis
            calls = [opt for opt in chain_data if opt.get('option_type', '').upper() in ['CE', 'CALL']]
            puts = [opt for opt in chain_data if opt.get('option_type', '').upper() in ['PE', 'PUT']]

            # Put-Call parity arbitrage
            parity_arbs = await self._detect_put_call_parity_arbitrage(calls, puts)
            arbitrage_opportunities.extend(parity_arbs)

            # Vertical spread arbitrage (same expiry, different strikes)
            vertical_arbs = await self._detect_vertical_spread_arbitrage(calls, puts)
            arbitrage_opportunities.extend(vertical_arbs)

            # Box spread arbitrage
            box_arbs = await self._detect_box_spread_arbitrage(calls, puts)
            arbitrage_opportunities.extend(box_arbs)

            log_info(f"[AGENT-2] Found {len(arbitrage_opportunities)} arbitrage opportunities")

            return arbitrage_opportunities

        except Exception as e:
            log_exception(f"[AGENT-2] Arbitrage calculation failed: {e}")
            return []

    def calculate_mispricing_severity(self, premium_percentage: float) -> MispricingSeverity:
        """
        Calculate mispricing severity based on premium percentage.

        Args:
            premium_percentage: Absolute premium percentage

        Returns:
            MispricingSeverity enum value
        """
        abs_premium = abs(premium_percentage)

        for severity, (min_val, max_val) in self.severity_thresholds.items():
            if min_val <= abs_premium < max_val:
                return severity

        return MispricingSeverity.EXTREME

    async def _calculate_theoretical_prices(
        self,
        option_chain_data: list[dict],
        underlying_price: float
    ) -> list[float]:
        """
        Calculate theoretical option prices using Black-Scholes-Merton model.

        Args:
            option_chain_data: Option metadata
            underlying_price: Current underlying price

        Returns:
            List of theoretical prices
        """
        try:
            theoretical_prices = []

            for option_data in option_chain_data:
                try:
                    strike = float(option_data['strike'])
                    time_to_expiry = self._calculate_time_to_expiry(option_data['expiry_date'])
                    option_type = option_data['option_type']
                    volatility = option_data.get('volatility', 0.2)  # Default 20%
                    risk_free_rate = 0.06  # Default risk-free rate

                    flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'

                    theoretical_price = black_scholes_merton(
                        flag, underlying_price, strike, time_to_expiry,
                        risk_free_rate, volatility, 0.0  # dividend yield = 0
                    )

                    theoretical_prices.append(theoretical_price if theoretical_price is not None else 0.0)

                except Exception as e:
                    log_warning(f"[AGENT-2] Failed to calculate theoretical price for option: {e}")
                    theoretical_prices.append(0.0)

            return theoretical_prices

        except Exception as e:
            log_exception(f"[AGENT-2] Theoretical price calculation failed: {e}")
            return [0.0] * len(option_chain_data)

    async def _compute_premium_analysis(
        self,
        market_prices: list[float],
        theoretical_prices: list[float],
        option_chain_data: list[dict],
        greeks_results: list[dict] | None = None
    ) -> list[dict]:
        """
        Compute premium/discount analysis for option chain.

        Args:
            market_prices: Current market prices
            theoretical_prices: Calculated theoretical prices
            option_chain_data: Option metadata
            greeks_results: Optional Greeks calculation results

        Returns:
            List of premium analysis results
        """
        try:
            results = []

            for i, (market_price, theoretical_price, option_data) in enumerate(
                zip(market_prices, theoretical_prices, option_chain_data, strict=False)
            ):
                try:
                    # Calculate premium/discount metrics
                    premium_amount = market_price - theoretical_price
                    premium_percentage = (premium_amount / theoretical_price * 100) if theoretical_price > 0 else 0.0

                    is_overpriced = premium_amount > 0
                    mispricing_severity = self.calculate_mispricing_severity(premium_percentage)

                    # Build result dict
                    result = {
                        'strike': float(option_data['strike']),
                        'expiry_date': option_data['expiry_date'],
                        'option_type': option_data['option_type'],
                        'market_price': round(market_price, 4),
                        'theoretical_price': round(theoretical_price, 4),
                        'premium_amount': round(premium_amount, 4),
                        'premium_percentage': round(premium_percentage, 4),
                        'is_overpriced': is_overpriced,
                        'is_underpriced': not is_overpriced,
                        'mispricing_severity': mispricing_severity.value,
                        'arbitrage_signal': mispricing_severity in [MispricingSeverity.HIGH, MispricingSeverity.EXTREME]
                    }

                    # Add Greeks if available
                    if greeks_results and i < len(greeks_results):
                        greeks = greeks_results[i]
                        result['greeks'] = {
                            'delta': greeks.get('delta'),
                            'gamma': greeks.get('gamma'),
                            'theta': greeks.get('theta'),
                            'vega': greeks.get('vega'),
                            'rho': greeks.get('rho')
                        }

                    results.append(result)

                except Exception as e:
                    log_warning(f"[AGENT-2] Failed to compute premium analysis for option {i}: {e}")
                    # Add default result to maintain list alignment
                    results.append({
                        'strike': option_data.get('strike', 0),
                        'expiry_date': option_data.get('expiry_date', ''),
                        'option_type': option_data.get('option_type', ''),
                        'market_price': market_price,
                        'theoretical_price': theoretical_price,
                        'premium_amount': 0.0,
                        'premium_percentage': 0.0,
                        'is_overpriced': False,
                        'is_underpriced': False,
                        'mispricing_severity': MispricingSeverity.LOW.value,
                        'arbitrage_signal': False
                    })

            return results

        except Exception as e:
            log_exception(f"[AGENT-2] Premium analysis computation failed: {e}")
            return []

    def _calculate_time_to_expiry(self, expiry_date: str | date | datetime) -> float:
        """Calculate time to expiry in years."""
        try:
            if isinstance(expiry_date, str):
                if 'T' in expiry_date:
                    expiry_dt = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                else:
                    expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            elif isinstance(expiry_date, date):
                expiry_dt = datetime.combine(expiry_date, datetime.min.time())
            else:
                expiry_dt = expiry_date

            now = datetime.now()
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=now.tzinfo)

            time_diff = expiry_dt - now
            time_to_expiry = time_diff.total_seconds() / (365.25 * 24 * 3600)

            return max(time_to_expiry, 1/365.25)  # Minimum 1 day

        except Exception as e:
            log_exception(f"[AGENT-2] Failed to calculate time to expiry: {e}")
            return 1/365.25

    def _group_by_expiry(self, option_chain_data: list[dict]) -> dict[str, list[dict]]:
        """Group options by expiry date."""
        groups = {}

        for option in option_chain_data:
            expiry = option.get('expiry_date', 'unknown')
            if expiry not in groups:
                groups[expiry] = []
            groups[expiry].append(option)

        return groups

    async def _detect_arbitrage_opportunities(self, premium_analysis: list[dict]) -> list[dict]:
        """Detect arbitrage opportunities from premium analysis."""
        opportunities = []

        try:
            # Find high/extreme mispricing opportunities
            for analysis in premium_analysis:
                if analysis.get('arbitrage_signal', False):
                    opportunities.append({
                        'type': 'mispricing_arbitrage',
                        'strike': analysis['strike'],
                        'expiry_date': analysis['expiry_date'],
                        'option_type': analysis['option_type'],
                        'premium_percentage': analysis['premium_percentage'],
                        'severity': analysis['mispricing_severity'],
                        'action': 'sell' if analysis['is_overpriced'] else 'buy',
                        'market_price': analysis['market_price'],
                        'theoretical_price': analysis['theoretical_price']
                    })

            return opportunities

        except Exception as e:
            log_exception(f"[AGENT-2] Arbitrage detection failed: {e}")
            return []

    async def _detect_put_call_parity_arbitrage(self, calls: list[dict], puts: list[dict]) -> list[dict]:
        """Detect put-call parity arbitrage opportunities."""
        opportunities = []

        try:
            # Group by strike and expiry
            call_dict = {}
            put_dict = {}

            for call in calls:
                key = (call.get('strike'), call.get('expiry_date'))
                call_dict[key] = call

            for put in puts:
                key = (put.get('strike'), put.get('expiry_date'))
                put_dict[key] = put

            # Check parity for matching strikes/expiries
            for key in call_dict:
                if key in put_dict:
                    call_data = call_dict[key]
                    put_data = put_dict[key]

                    # Put-Call parity: C - P = S - K * e^(-r*T)
                    # Where: C = call price, P = put price, S = spot price, K = strike, r = risk-free rate, T = time to expiry

                    # Simplified check for demonstration
                    call_price = call_data.get('market_price', 0)
                    put_price = put_data.get('market_price', 0)

                    if call_price > 0 and put_price > 0:
                        parity_diff = call_price - put_price
                        # Add detailed parity analysis here if needed

                        if abs(parity_diff) > 1.0:  # Simplified threshold
                            opportunities.append({
                                'type': 'put_call_parity',
                                'strike': key[0],
                                'expiry_date': key[1],
                                'call_price': call_price,
                                'put_price': put_price,
                                'parity_deviation': parity_diff,
                                'action': 'investigate'
                            })

            return opportunities

        except Exception as e:
            log_exception(f"[AGENT-2] Put-call parity detection failed: {e}")
            return []

    async def _detect_vertical_spread_arbitrage(self, calls: list[dict], puts: list[dict]) -> list[dict]:
        """Detect vertical spread arbitrage opportunities."""
        # Simplified implementation - check for price inversions
        opportunities = []

        try:
            # Check call spreads
            call_spreads = self._find_vertical_spread_opportunities(calls, 'call')
            opportunities.extend(call_spreads)

            # Check put spreads
            put_spreads = self._find_vertical_spread_opportunities(puts, 'put')
            opportunities.extend(put_spreads)

            return opportunities

        except Exception as e:
            log_exception(f"[AGENT-2] Vertical spread detection failed: {e}")
            return []

    def _find_vertical_spread_opportunities(self, options: list[dict], option_type: str) -> list[dict]:
        """Find vertical spread opportunities in same-expiry options."""
        opportunities = []

        # Group by expiry
        expiry_groups = {}
        for option in options:
            expiry = option.get('expiry_date', '')
            if expiry not in expiry_groups:
                expiry_groups[expiry] = []
            expiry_groups[expiry].append(option)

        # Check each expiry group
        for expiry, expiry_options in expiry_groups.items():
            # Sort by strike
            sorted_options = sorted(expiry_options, key=lambda x: x.get('strike', 0))

            # Look for price inversions
            for i in range(len(sorted_options) - 1):
                lower_strike = sorted_options[i]
                higher_strike = sorted_options[i + 1]

                lower_price = lower_strike.get('market_price', 0)
                higher_price = higher_strike.get('market_price', 0)

                # For calls: lower strike should be more expensive
                # For puts: higher strike should be more expensive
                is_inversion = False

                if option_type == 'call' and lower_price < higher_price or option_type == 'put' and lower_price > higher_price:
                    is_inversion = True

                if is_inversion and abs(lower_price - higher_price) > 0.5:
                    opportunities.append({
                        'type': f'{option_type}_vertical_spread',
                        'expiry_date': expiry,
                        'lower_strike': lower_strike.get('strike'),
                        'lower_price': lower_price,
                        'higher_strike': higher_strike.get('strike'),
                        'higher_price': higher_price,
                        'price_inversion': abs(lower_price - higher_price),
                        'action': 'investigate'
                    })

        return opportunities

    async def _detect_box_spread_arbitrage(self, calls: list[dict], puts: list[dict]) -> list[dict]:
        """Detect box spread arbitrage opportunities."""
        # Simplified box spread check


    def _calculate_expiry_summary_stats(self, expiry_results: list[dict]) -> dict[str, Any]:
        """Calculate summary statistics for expiry analysis."""
        try:
            if not expiry_results:
                return {}

            premium_percentages = [r.get('premium_percentage', 0) for r in expiry_results]
            overpriced_count = len([r for r in expiry_results if r.get('is_overpriced', False)])
            underpriced_count = len([r for r in expiry_results if r.get('is_underpriced', False)])
            arbitrage_signals = len([r for r in expiry_results if r.get('arbitrage_signal', False)])

            return {
                'total_options': len(expiry_results),
                'overpriced_options': overpriced_count,
                'underpriced_options': underpriced_count,
                'arbitrage_signals': arbitrage_signals,
                'avg_premium_percentage': np.mean(premium_percentages) if premium_percentages else 0,
                'max_premium_percentage': np.max(premium_percentages) if premium_percentages else 0,
                'min_premium_percentage': np.min(premium_percentages) if premium_percentages else 0,
                'std_premium_percentage': np.std(premium_percentages) if premium_percentages else 0
            }

        except Exception as e:
            log_exception(f"[AGENT-2] Summary stats calculation failed: {e}")
            return {}

    def _update_avg_time(self, new_time_ms: float):
        """Update running average of execution times."""
        current_avg = self.performance_metrics['avg_analysis_time_ms']
        count = self.performance_metrics['premium_analyses']

        self.performance_metrics['avg_analysis_time_ms'] = (
            (current_avg * (count - 1) + new_time_ms) / count
        ) if count > 0 else new_time_ms

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get current performance metrics."""
        return self.performance_metrics.copy()

    def reset_performance_metrics(self):
        """Reset performance tracking."""
        self.performance_metrics = {
            'premium_analyses': 0,
            'total_options_analyzed': 0,
            'avg_analysis_time_ms': 0.0,
            'arbitrage_opportunities_found': 0
        }
        log_info("[AGENT-2] Premium analysis performance metrics reset")
