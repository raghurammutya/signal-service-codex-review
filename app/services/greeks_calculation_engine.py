# [AGENT-1] Enhanced Greeks calculation engine with vectorized processing support
"""Core Greeks calculation engine using py_vollib with vectorized processing support"""
import asyncio
from typing import Dict, Optional, Union, List, Any
from datetime import datetime, date
import math

from app.utils.logging_utils import log_warning, log_exception, log_info
from app.errors import GreeksCalculationError, UnsupportedModelError
from app.core.greeks_model_config import get_greeks_model_config
from app.core.circuit_breaker import get_circuit_breaker


class GreeksCalculationEngine:
    """
    [AGENT-1] Core engine for calculating option Greeks using py_vollib library.
    Provides stateless mathematical functions for all Greeks calculations.
    Enhanced with vectorized processing for bulk option calculations.
    """

    def __init__(self, enable_vectorized: bool = True, vectorized_threshold: int = 10):
        # Load model configuration from config_service
        self._model_config = get_greeks_model_config()
        self._model_config.initialize()  # Ensure it's initialized
        
        self.enable_vectorized = enable_vectorized
        self.vectorized_threshold = vectorized_threshold
        
        # Initialize circuit breakers for production resilience
        self._individual_breaker = get_circuit_breaker("individual")
        self._bulk_breaker = get_circuit_breaker("bulk")
        
        # Initialize vectorized engine if enabled
        self._vectorized_engine = None
        if enable_vectorized:
            try:
                from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine
                self._vectorized_engine = VectorizedPyvolibGreeksEngine()
                log_info(f"[AGENT-1] Vectorized Greeks engine initialized (threshold: {vectorized_threshold} options)")
            except ImportError as e:
                log_warning(f"[AGENT-1] Failed to initialize vectorized engine: {e}, falling back to single-option mode")
                self.enable_vectorized = False
        
        log_info(f"[AGENT-1] Greeks engine initialized with model: {self._model_config.model_name}")
    
    def _get_effective_risk_free_rate(self, risk_free_rate: Optional[float]) -> float:
        """Get effective risk-free rate from parameter or model config"""
        return risk_free_rate if risk_free_rate is not None else self._model_config.parameters.risk_free_rate
    
    async def calculate_implied_volatility(
        self,
        price: float,
        underlying_price: float,
        strike: float,
        time_to_expiry: float,
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate implied volatility"""
        try:
            r = risk_free_rate or self.risk_free_rate
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            # Validate inputs
            if any(x <= 0 for x in [price, underlying_price, strike]):
                raise GreeksCalculationError("Price values must be positive")
            
            if time_to_expiry <= 0:
                raise GreeksCalculationError("Time to expiry must be positive")
            
            # Calculate implied volatility
            iv = await asyncio.get_event_loop().run_in_executor(
                None,
                implied_volatility,
                price,
                underlying_price,
                strike,
                time_to_expiry,
                r,
                flag
            )
            
            # Validate result
            if iv is None or math.isnan(iv) or iv <= 0:
                return None
            
            return min(iv, 5.0)  # Cap at 500% volatility
            
        except Exception as e:
            log_exception(f"Failed to calculate implied volatility: {e}")
            return None
    
    async def calculate_delta(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate Delta using configured model"""
        try:
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            # Validate inputs
            if not self._validate_greeks_inputs(underlying_price, strike, time_to_expiry, volatility):
                return None
            
            # Use model configuration to calculate delta
            delta_value = await asyncio.get_event_loop().run_in_executor(
                None,
                self._model_config.calculate_greek,
                'delta',
                flag,
                underlying_price,
                strike,
                time_to_expiry,
                volatility,
                risk_free_rate
            )
            
            return self._validate_greek_output(delta_value, "delta")
            
        except Exception as e:
            log_exception(f"Failed to calculate delta using {self._model_config.model_name}: {e}")
            return None
    
    async def calculate_gamma(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate Gamma using configured model"""
        try:
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            if not self._validate_greeks_inputs(underlying_price, strike, time_to_expiry, volatility):
                return None
            
            gamma_value = await asyncio.get_event_loop().run_in_executor(
                None,
                self._model_config.calculate_greek,
                'gamma',
                flag,
                underlying_price,
                strike,
                time_to_expiry,
                volatility,
                risk_free_rate
            )
            
            return self._validate_greek_output(gamma_value, "gamma")
            
        except Exception as e:
            log_exception(f"Failed to calculate gamma using {self._model_config.model_name}: {e}")
            return None
    
    async def calculate_theta(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate Theta"""
        try:
            r = risk_free_rate or self.risk_free_rate
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            if not self._validate_greeks_inputs(underlying_price, strike, time_to_expiry, volatility):
                return None
            
            theta_value = await asyncio.get_event_loop().run_in_executor(
                None,
                theta,
                flag,
                underlying_price,
                strike,
                time_to_expiry,
                r,
                volatility
            )
            
            return self._validate_greek_output(theta_value, "theta")
            
        except Exception as e:
            log_exception(f"Failed to calculate theta: {e}")
            return None
    
    async def calculate_vega(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate Vega"""
        try:
            r = risk_free_rate or self.risk_free_rate
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            if not self._validate_greeks_inputs(underlying_price, strike, time_to_expiry, volatility):
                return None
            
            vega_value = await asyncio.get_event_loop().run_in_executor(
                None,
                vega,
                flag,
                underlying_price,
                strike,
                time_to_expiry,
                r,
                volatility
            )
            
            return self._validate_greek_output(vega_value, "vega")
            
        except Exception as e:
            log_exception(f"Failed to calculate vega: {e}")
            return None
    
    async def calculate_rho(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """Calculate Rho"""
        try:
            r = risk_free_rate or self.risk_free_rate
            flag = 'c' if option_type.upper() in ['CE', 'CALL'] else 'p'
            
            if not self._validate_greeks_inputs(underlying_price, strike, time_to_expiry, volatility):
                return None
            
            rho_value = await asyncio.get_event_loop().run_in_executor(
                None,
                rho,
                flag,
                underlying_price,
                strike,
                time_to_expiry,
                r,
                volatility
            )
            
            return self._validate_greek_output(rho_value, "rho")
            
        except Exception as e:
            log_exception(f"Failed to calculate rho: {e}")
            return None
    
    async def calculate_all_greeks(
        self, 
        underlying_price: float, 
        strike: float, 
        time_to_expiry: float, 
        volatility: float, 
        option_type: str,
        risk_free_rate: Optional[float] = None,
        greeks_to_calculate: Optional[list] = None
    ) -> Dict[str, Optional[float]]:
        """Calculate all requested Greeks in parallel"""
        if greeks_to_calculate is None:
            greeks_to_calculate = ['delta', 'gamma', 'theta', 'vega', 'rho']
        
        results = {}
        tasks = []
        
        # Create tasks for each Greek
        for greek in greeks_to_calculate:
            if greek == 'delta':
                task = self.calculate_delta(underlying_price, strike, time_to_expiry, volatility, option_type, risk_free_rate)
            elif greek == 'gamma':
                task = self.calculate_gamma(underlying_price, strike, time_to_expiry, volatility, option_type, risk_free_rate)
            elif greek == 'theta':
                task = self.calculate_theta(underlying_price, strike, time_to_expiry, volatility, option_type, risk_free_rate)
            elif greek == 'vega':
                task = self.calculate_vega(underlying_price, strike, time_to_expiry, volatility, option_type, risk_free_rate)
            elif greek == 'rho':
                task = self.calculate_rho(underlying_price, strike, time_to_expiry, volatility, option_type, risk_free_rate)
            else:
                continue
            
            tasks.append((greek, task))
        
        # Execute all tasks in parallel
        if tasks:
            task_results = await asyncio.gather(
                *[task for _, task in tasks], 
                return_exceptions=True
            )
            
            for (greek, _), result in zip(tasks, task_results):
                if isinstance(result, Exception):
                    log_exception(f"Failed to calculate {greek}: {result}")
                    results[greek] = None
                else:
                    results[greek] = result
        
        return results
    
    async def calculate_option_chain_greeks(
        self,
        option_chain_data: List[Dict],
        underlying_price: float,
        greeks_to_calculate: Optional[List[str]] = None,
        force_vectorized: bool = False
    ) -> Dict[str, Any]:
        """
        [AGENT-1] Calculate Greeks for entire option chain with automatic vectorized/legacy switching.
        
        Args:
            option_chain_data: List of option data dicts
            underlying_price: Current underlying asset price
            greeks_to_calculate: List of Greeks to calculate
            force_vectorized: Force use of vectorized mode regardless of threshold
            
        Returns:
            Dict with results and performance metrics
        """
        n_options = len(option_chain_data)
        
        # Determine if vectorized processing should be used
        use_vectorized = (
            self.enable_vectorized and 
            self._vectorized_engine is not None and 
            (force_vectorized or n_options >= self.vectorized_threshold)
        )
        
        if use_vectorized:
            log_info(f"[AGENT-1] Using vectorized processing for {n_options} options")
            try:
                return await self._vectorized_engine.calculate_option_chain_greeks_vectorized(
                    option_chain_data, underlying_price, greeks_to_calculate
                )
            except Exception as e:
                log_warning(f"[AGENT-1] Vectorized processing failed, falling back to legacy: {e}")
                # Fallback to legacy processing
        
        # Legacy single-option processing
        log_info(f"[AGENT-1] Using legacy single-option processing for {n_options} options")
        return await self._legacy_option_chain_calculation(
            option_chain_data, underlying_price, greeks_to_calculate or ['delta', 'gamma', 'theta', 'vega', 'rho']
        )
    
    async def calculate_bulk_greeks(
        self,
        bulk_options_data: List[Dict],
        include_performance_metrics: bool = True
    ) -> Dict[str, Any]:
        """
        [AGENT-1] Calculate Greeks for bulk options data with performance tracking.
        
        Args:
            bulk_options_data: List of options with underlying_price included
            include_performance_metrics: Whether to include detailed performance metrics
            
        Returns:
            Bulk calculation results with performance comparison
        """
        if not self.enable_vectorized or self._vectorized_engine is None:
            # Fallback to processing each option individually
            return await self._legacy_bulk_calculation(bulk_options_data)
        
        try:
            return await self._vectorized_engine.calculate_bulk_greeks_with_performance_metrics(
                bulk_options_data, compare_with_legacy=include_performance_metrics
            )
        except Exception as e:
            log_exception(f"[AGENT-1] Bulk vectorized calculation failed: {e}")
            return await self._legacy_bulk_calculation(bulk_options_data)
    
    async def _legacy_option_chain_calculation(
        self,
        option_chain_data: List[Dict],
        underlying_price: float,
        greeks_to_calculate: List[str]
    ) -> Dict[str, Any]:
        """Legacy single-option calculation for option chain."""
        import time
        start_time = time.perf_counter()
        
        results = []
        
        for option_data in option_chain_data:
            try:
                strike = float(option_data['strike'])
                time_to_expiry = self.calculate_time_to_expiry(option_data['expiry_date'])
                option_type = option_data['option_type']
                
                # Get or calculate volatility
                if 'volatility' in option_data and option_data['volatility'] is not None:
                    volatility = float(option_data['volatility'])
                elif 'price' in option_data:
                    volatility = await self.calculate_implied_volatility(
                        float(option_data['price']), underlying_price, strike,
                        time_to_expiry, option_type
                    )
                    volatility = volatility if volatility is not None else 0.2
                else:
                    volatility = 0.2  # Default volatility
                
                # Calculate Greeks with circuit breaker protection - fail fast in production
                cache_key = f"greeks_{underlying_price}_{strike}_{time_to_expiry}_{volatility}_{option_type}"
                greeks = await self._individual_breaker.execute(
                    self.calculate_all_greeks,
                    underlying_price, strike, time_to_expiry, volatility, 
                    option_type, None, greeks_to_calculate,
                    cache_key=cache_key
                )
                
                results.append(greeks)
                
            except Exception as e:
                log_exception(f"[AGENT-1] Failed to calculate Greeks for option: {e}")
                results.append({greek: None for greek in greeks_to_calculate})
        
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        
        return {
            'results': results,
            'performance': {
                'execution_time_ms': execution_time_ms,
                'options_processed': len(option_chain_data),
                'options_per_second': len(option_chain_data) / (execution_time_ms / 1000) if execution_time_ms > 0 else 0
            },
            'method_used': 'legacy'
        }
    
    async def _legacy_bulk_calculation(self, bulk_options_data: List[Dict]) -> Dict[str, Any]:
        """Legacy bulk calculation using single-option processing."""
        import time
        start_time = time.perf_counter()
        
        # Group by underlying price for processing
        grouped_options = {}
        for option in bulk_options_data:
            underlying_price = option.get('underlying_price', 0.0)
            if underlying_price not in grouped_options:
                grouped_options[underlying_price] = []
            grouped_options[underlying_price].append(option)
        
        results = {}
        for underlying_price, options in grouped_options.items():
            result = await self._legacy_option_chain_calculation(
                options, underlying_price, ['delta', 'gamma', 'theta', 'vega', 'rho']
            )
            results[underlying_price] = result['results']
        
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        
        return {
            'legacy_results': results,
            'performance_comparison': {
                'legacy_time_ms': execution_time_ms,
                'total_options': len(bulk_options_data),
                'options_per_second_legacy': len(bulk_options_data) / (execution_time_ms / 1000) if execution_time_ms > 0 else 0
            },
            'method_used': 'legacy_bulk'
        }
    
    def get_vectorized_performance_metrics(self) -> Optional[Dict[str, Any]]:
        """Get performance metrics from vectorized engine."""
        if self._vectorized_engine is not None:
            return self._vectorized_engine.get_performance_metrics()
        return None
    
    def reset_vectorized_performance_metrics(self):
        """Reset vectorized engine performance metrics."""
        if self._vectorized_engine is not None:
            self._vectorized_engine.reset_performance_metrics()
    
    def calculate_time_to_expiry(self, expiry_date: Union[str, date, datetime]) -> float:
        """Calculate time to expiry in years"""
        try:
            if isinstance(expiry_date, str):
                # Parse string date
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
            time_to_expiry = time_diff.total_seconds() / (365.25 * 24 * 3600)  # Convert to years
            
            return max(time_to_expiry, 1/365.25)  # Minimum 1 day
            
        except Exception as e:
            log_exception(f"Failed to calculate time to expiry: {e}")
            return 1/365.25  # Default to 1 day
    
    def _validate_greeks_inputs(self, underlying_price: float, strike: float, time_to_expiry: float, volatility: float) -> bool:
        """Validate inputs for Greeks calculations"""
        try:
            # Check for positive values
            if any(x <= 0 for x in [underlying_price, strike, time_to_expiry, volatility]):
                return False
            
            # Check for reasonable ranges
            if volatility > 5.0:  # 500% volatility is unreasonable
                return False
            
            if time_to_expiry > 10.0:  # More than 10 years is unreasonable
                return False
            
            return True
            
        except Exception:
            return False
    
    def _validate_greek_output(self, value: float, greek_name: str) -> Optional[float]:
        """Validate Greek calculation output"""
        try:
            if value is None or math.isnan(value) or math.isinf(value):
                return None
            
            # Apply reasonable bounds
            bounds = {
                'delta': (-1.0, 1.0),
                'gamma': (0.0, 1.0),
                'theta': (-1.0, 1.0),
                'vega': (0.0, 100.0),
                'rho': (-100.0, 100.0)
            }
            
            if greek_name in bounds:
                min_val, max_val = bounds[greek_name]
                if value < min_val or value > max_val:
                    log_warning(f"{greek_name} value {value} outside reasonable bounds [{min_val}, {max_val}]")
                    return None
            
            return value

        except Exception:
            return None