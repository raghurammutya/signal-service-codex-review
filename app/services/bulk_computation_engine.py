# Bulk Computation Engine - Parallel Greeks/TA computation for option chains
import asyncio
import json
import time
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import numpy as np
from scipy.stats import norm

from app.utils.logging_config import get_logger
from app.utils.redis import get_redis_client

# Import metrics
from ..metrics.threshold_metrics import get_metrics_collector

logger = get_logger(__name__)


@dataclass
class OptionData:
    """Option data for computation"""
    instrument_key: str
    symbol: str
    strike_price: float
    option_type: str  # 'CE' or 'PE'
    expiry_date: str
    ltp: float
    volume: int
    oi: int
    bid: float
    ask: float
    
    # Computed values (populated by computation engine)
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    
    # Technical indicators
    rsi: Optional[float] = None
    sma_5: Optional[float] = None
    sma_20: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None


@dataclass
class ComputationRequest:
    """Request for bulk computation"""
    request_id: str
    underlying: str
    underlying_price: float
    expiry_date: str
    risk_free_rate: float
    options: List[OptionData]
    
    # Computation flags
    compute_greeks: bool = True
    compute_technical_indicators: bool = False
    
    # Performance settings
    use_parallel_processing: bool = True
    max_workers: int = 4
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ComputationResult:
    """Result of bulk computation"""
    request_id: str
    underlying: str
    computation_time_ms: float
    options_processed: int
    greeks_computed: bool
    technical_indicators_computed: bool
    
    # Updated options with computed values
    options: List[OptionData]
    
    # Summary statistics
    total_call_iv: float = 0.0
    total_put_iv: float = 0.0
    avg_call_delta: float = 0.0
    avg_put_delta: float = 0.0
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class GreeksCalculator:
    """Black-Scholes Greeks calculator for options"""
    
    @staticmethod
    def black_scholes_price(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float, 
        option_type: str
    ) -> float:
        """Calculate Black-Scholes option price"""
        
        if time_to_expiry <= 0 or volatility <= 0:
            return max(0, (spot - strike) if option_type == 'CE' else (strike - spot))
        
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
        d2 = d1 - volatility * math.sqrt(time_to_expiry)
        
        if option_type == 'CE':  # Call
            price = spot * norm.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        else:  # Put
            price = strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        
        return max(0, price)
    
    @staticmethod
    def calculate_implied_volatility(
        market_price: float, 
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        option_type: str
    ) -> float:
        """Calculate implied volatility using Newton-Raphson method"""
        
        if time_to_expiry <= 0:
            return 0.0
        
        # Initial guess
        volatility = 0.2
        
        for _ in range(100):  # Max iterations
            try:
                price = GreeksCalculator.black_scholes_price(spot, strike, time_to_expiry, risk_free_rate, volatility, option_type)
                vega = GreeksCalculator.calculate_vega(spot, strike, time_to_expiry, risk_free_rate, volatility)
                
                if abs(vega) < 1e-6:
                    break
                
                price_diff = price - market_price
                if abs(price_diff) < 0.01:  # Convergence threshold
                    break
                
                volatility = volatility - price_diff / vega
                volatility = max(0.01, min(5.0, volatility))  # Constrain volatility
                
            except (ValueError, ZeroDivisionError, OverflowError):
                break
        
        return max(0.01, min(5.0, volatility))
    
    @staticmethod
    def calculate_delta(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float, 
        option_type: str
    ) -> float:
        """Calculate option delta"""
        
        if time_to_expiry <= 0 or volatility <= 0:
            if option_type == 'CE':
                return 1.0 if spot > strike else 0.0
            else:
                return -1.0 if spot < strike else 0.0
        
        try:
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
            
            if option_type == 'CE':  # Call
                return norm.cdf(d1)
            else:  # Put
                return norm.cdf(d1) - 1.0
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
    
    @staticmethod
    def calculate_gamma(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float
    ) -> float:
        """Calculate option gamma (same for calls and puts)"""
        
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0
        
        try:
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
            return norm.pdf(d1) / (spot * volatility * math.sqrt(time_to_expiry))
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
    
    @staticmethod
    def calculate_theta(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float, 
        option_type: str
    ) -> float:
        """Calculate option theta"""
        
        if time_to_expiry <= 0:
            return 0.0
        
        try:
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
            d2 = d1 - volatility * math.sqrt(time_to_expiry)
            
            if option_type == 'CE':  # Call
                theta = (-spot * norm.pdf(d1) * volatility / (2 * math.sqrt(time_to_expiry)) 
                        - risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2))
            else:  # Put
                theta = (-spot * norm.pdf(d1) * volatility / (2 * math.sqrt(time_to_expiry)) 
                        + risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2))
            
            return theta / 365  # Convert to per-day theta
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
    
    @staticmethod
    def calculate_vega(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float
    ) -> float:
        """Calculate option vega (same for calls and puts)"""
        
        if time_to_expiry <= 0:
            return 0.0
        
        try:
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
            return spot * norm.pdf(d1) * math.sqrt(time_to_expiry) / 100  # Divide by 100 for 1% volatility change
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
    
    @staticmethod
    def calculate_rho(
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        volatility: float, 
        option_type: str
    ) -> float:
        """Calculate option rho"""
        
        if time_to_expiry <= 0:
            return 0.0
        
        try:
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
            d2 = d1 - volatility * math.sqrt(time_to_expiry)
            
            if option_type == 'CE':  # Call
                rho = strike * time_to_expiry * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            else:  # Put
                rho = -strike * time_to_expiry * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)
            
            return rho / 100  # Divide by 100 for 1% interest rate change
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0


class TechnicalIndicatorCalculator:
    """Technical indicator calculator for options"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """Calculate RSI for price series"""
        
        if len(prices) < period + 1:
            # Fail fast when insufficient data - no synthetic data allowed
            raise ValueError(f"Insufficient price data for RSI calculation: {len(prices)} prices, need at least {period + 1}")
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average"""
        
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        
        return sum(prices[-period:]) / period
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands (middle, upper, lower)"""
        
        if len(prices) < period:
            avg = sum(prices) / len(prices) if prices else 0.0
            return avg, avg, avg
        
        recent_prices = prices[-period:]
        middle = sum(recent_prices) / period
        
        variance = sum((price - middle) ** 2 for price in recent_prices) / period
        std = math.sqrt(variance)
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return middle, upper, lower


class BulkComputationEngine:
    """
    Parallel computation engine for option chains.
    Processes entire option chains efficiently instead of individual options.
    """
    
    def __init__(self):
        self.redis = None
        self.thread_pool = ThreadPoolExecutor(max_workers=8)
        self.process_pool = ProcessPoolExecutor(max_workers=4)
        
        # Performance tracking
        self.computation_stats = {
            'total_requests': 0,
            'total_options_processed': 0,
            'avg_computation_time_ms': 0.0,
            'last_computation': None
        }
        
        # Prometheus metrics collector
        self.metrics_collector = get_metrics_collector()
        
    async def initialize(self):
        """Initialize the bulk computation engine"""
        self.redis = await get_redis_client()
        
        # Start listening for computation requests
        asyncio.create_task(self._listen_for_computation_requests())
        
        logger.info("BulkComputationEngine initialized")
    
    async def process_option_chain(self, request: ComputationRequest) -> ComputationResult:
        """
        Process an entire option chain with parallel computation
        """
        
        start_time = time.time()
        
        try:
            logger.info(f"Processing option chain: {request.underlying} {request.expiry_date} ({len(request.options)} options)")
            
            # Calculate time to expiry
            time_to_expiry = self._calculate_time_to_expiry(request.expiry_date)
            
            if request.use_parallel_processing and len(request.options) > 10:
                # Use parallel processing for large option chains
                updated_options = await self._parallel_computation(request, time_to_expiry)
            else:
                # Use sequential processing for small chains
                updated_options = await self._sequential_computation(request, time_to_expiry)
            
            computation_time = (time.time() - start_time) * 1000
            
            # Create result
            result = ComputationResult(
                request_id=request.request_id,
                underlying=request.underlying,
                computation_time_ms=computation_time,
                options_processed=len(updated_options),
                greeks_computed=request.compute_greeks,
                technical_indicators_computed=request.compute_technical_indicators,
                options=updated_options
            )
            
            # Calculate summary statistics
            self._calculate_summary_statistics(result)
            
            # Update performance stats
            self._update_performance_stats(computation_time, len(updated_options))
            
            logger.info(f"Completed option chain processing: {request.underlying} in {computation_time:.2f}ms")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing option chain {request.request_id}: {e}")
            raise
    
    async def _parallel_computation(self, request: ComputationRequest, time_to_expiry: float) -> List[OptionData]:
        """Process options in parallel using thread pool"""
        
        # Split options into batches for parallel processing
        batch_size = max(1, len(request.options) // request.max_workers)
        batches = [request.options[i:i + batch_size] for i in range(0, len(request.options), batch_size)]
        
        # Create tasks for each batch
        tasks = []
        for batch in batches:
            task = asyncio.create_task(
                self._process_option_batch(
                    batch, 
                    request.underlying_price, 
                    time_to_expiry, 
                    request.risk_free_rate,
                    request.compute_greeks,
                    request.compute_technical_indicators
                )
            )
            tasks.append(task)
        
        # Wait for all batches to complete
        batch_results = await asyncio.gather(*tasks)
        
        # Flatten results
        updated_options = []
        for batch_result in batch_results:
            updated_options.extend(batch_result)
        
        return updated_options
    
    async def _sequential_computation(self, request: ComputationRequest, time_to_expiry: float) -> List[OptionData]:
        """Process options sequentially"""
        
        return await self._process_option_batch(
            request.options,
            request.underlying_price,
            time_to_expiry,
            request.risk_free_rate,
            request.compute_greeks,
            request.compute_technical_indicators
        )
    
    async def _process_option_batch(
        self,
        options: List[OptionData],
        underlying_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        compute_greeks: bool,
        compute_technical_indicators: bool
    ) -> List[OptionData]:
        """Process a batch of options"""
        
        # Run the async computation directly since it's now async
        return await self._compute_option_batch(
            options,
            underlying_price,
            time_to_expiry,
            risk_free_rate,
            compute_greeks,
            compute_technical_indicators
        )
    
    async def _compute_option_batch(
        self,
        options: List[OptionData],
        underlying_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        compute_greeks: bool,
        compute_technical_indicators: bool
    ) -> List[OptionData]:
        """Compute Greeks and technical indicators for a batch of options"""
        
        updated_options = []
        ticker_adapter = None
        if compute_technical_indicators:
            from app.adapters.ticker_adapter import EnhancedTickerAdapter
            ticker_adapter = EnhancedTickerAdapter()
        
        try:
            for option in options:
                try:
                    # Create a copy to avoid modifying the original
                    updated_option = OptionData(
                        instrument_key=option.instrument_key,
                        symbol=option.symbol,
                        strike_price=option.strike_price,
                        option_type=option.option_type,
                        expiry_date=option.expiry_date,
                        ltp=option.ltp,
                        volume=option.volume,
                        oi=option.oi,
                        bid=option.bid,
                        ask=option.ask
                    )
                    
                    if compute_greeks and option.ltp > 0:
                        # Calculate implied volatility first
                        iv = GreeksCalculator.calculate_implied_volatility(
                            option.ltp,
                            underlying_price,
                            option.strike_price,
                            time_to_expiry,
                            risk_free_rate,
                            option.option_type
                        )
                        updated_option.iv = round(iv, 4)
                        
                        # Calculate Greeks using implied volatility
                        if iv > 0:
                            updated_option.delta = round(GreeksCalculator.calculate_delta(
                                underlying_price, option.strike_price, time_to_expiry, risk_free_rate, iv, option.option_type
                            ), 4)
                            
                            updated_option.gamma = round(GreeksCalculator.calculate_gamma(
                                underlying_price, option.strike_price, time_to_expiry, risk_free_rate, iv
                            ), 6)
                            
                            updated_option.theta = round(GreeksCalculator.calculate_theta(
                                underlying_price, option.strike_price, time_to_expiry, risk_free_rate, iv, option.option_type
                            ), 4)
                            
                            updated_option.vega = round(GreeksCalculator.calculate_vega(
                                underlying_price, option.strike_price, time_to_expiry, risk_free_rate, iv
                            ), 4)
                            
                            updated_option.rho = round(GreeksCalculator.calculate_rho(
                                underlying_price, option.strike_price, time_to_expiry, risk_free_rate, iv, option.option_type
                            ), 4)
                    
                    if compute_technical_indicators:
                        # Calculate technical indicators using historical data
                        try:
                            # Get historical data for the option
                            historical_data = await ticker_adapter.get_historical_data(
                                symbol=option.instrument_key,
                                timeframe="1day",
                                periods=30  # Get 30 days of data for indicators
                            )
                            
                            if historical_data.empty:
                                raise ValueError(f"No historical data available for {option.instrument_key}")
                            
                            # Extract closing prices
                            prices = historical_data['close'].tolist()
                            
                            # Calculate real technical indicators
                            updated_option.rsi = TechnicalIndicatorCalculator.calculate_rsi(prices, 14)
                            updated_option.sma_5 = TechnicalIndicatorCalculator.calculate_sma(prices, 5)
                            updated_option.sma_20 = TechnicalIndicatorCalculator.calculate_sma(prices, 20)
                            
                            # Calculate Bollinger Bands
                            middle, upper, lower = TechnicalIndicatorCalculator.calculate_bollinger_bands(prices, 20, 2.0)
                            updated_option.bollinger_upper = upper
                            updated_option.bollinger_lower = lower
                            
                        except Exception as e:
                            # Fail fast - no synthetic fallback data allowed
                            logger.error(f"Failed to calculate technical indicators for {option.instrument_key}: {e}")
                            raise ValueError(
                                f"Unable to calculate technical indicators for {option.instrument_key}: {e}. "
                                "No synthetic fallback values allowed."
                            )
                    
                    updated_options.append(updated_option)
                    
                except Exception as e:
                    logger.error(f"Error computing option {option.instrument_key}: {e}")
                    # Add the original option without computed values
                    updated_options.append(option)
        finally:
            if ticker_adapter:
                await ticker_adapter.close()
        
        return updated_options
    
    def _calculate_time_to_expiry(self, expiry_date: str) -> float:
        """Calculate time to expiry in years"""
        
        try:
            if len(expiry_date) == 10:  # YYYY-MM-DD format
                expiry = datetime.strptime(expiry_date, '%Y-%m-%d')
            else:
                # Try other common formats
                expiry = datetime.strptime(expiry_date, '%d-%b-%Y')
            
            now = datetime.utcnow()
            time_diff = expiry - now
            
            # Convert to years (assuming 365 days per year)
            time_to_expiry = time_diff.total_seconds() / (365 * 24 * 3600)
            
            return max(0, time_to_expiry)  # Ensure non-negative
            
        except ValueError as e:
            logger.error(f"Error parsing expiry date {expiry_date}: {e}")
            return 0.0
    
    def _calculate_summary_statistics(self, result: ComputationResult):
        """Calculate summary statistics for the computation result"""
        
        call_ivs = []
        put_ivs = []
        call_deltas = []
        put_deltas = []
        
        for option in result.options:
            if option.option_type == 'CE' and option.iv is not None:
                call_ivs.append(option.iv)
                if option.delta is not None:
                    call_deltas.append(option.delta)
            elif option.option_type == 'PE' and option.iv is not None:
                put_ivs.append(option.iv)
                if option.delta is not None:
                    put_deltas.append(option.delta)
        
        # Calculate averages
        result.total_call_iv = sum(call_ivs) / len(call_ivs) if call_ivs else 0.0
        result.total_put_iv = sum(put_ivs) / len(put_ivs) if put_ivs else 0.0
        result.avg_call_delta = sum(call_deltas) / len(call_deltas) if call_deltas else 0.0
        result.avg_put_delta = sum(put_deltas) / len(put_deltas) if put_deltas else 0.0
    
    def _update_performance_stats(self, computation_time: float, options_processed: int):
        """Update performance statistics"""
        
        self.computation_stats['total_requests'] += 1
        self.computation_stats['total_options_processed'] += options_processed
        
        # Update average computation time (exponential moving average)
        if self.computation_stats['avg_computation_time_ms'] == 0:
            self.computation_stats['avg_computation_time_ms'] = computation_time
        else:
            alpha = 0.1  # Smoothing factor
            self.computation_stats['avg_computation_time_ms'] = (
                alpha * computation_time + 
                (1 - alpha) * self.computation_stats['avg_computation_time_ms']
            )
        
        self.computation_stats['last_computation'] = datetime.utcnow().isoformat()
    
    async def _listen_for_computation_requests(self):
        """Listen for computation requests from Redis streams"""
        
        while True:
            try:
                # Listen for requests from ticker_service
                streams = await self.redis.xread(
                    {"signal_config_updates": "$"},
                    count=10,
                    block=1000  # 1 second timeout
                )
                
                for stream, messages in streams:
                    for message_id, fields in messages:
                        try:
                            if fields.get(b'action') == b'bulk_compute':
                                await self._handle_computation_request(fields)
                        except Exception as e:
                            logger.error(f"Error handling computation request: {e}")
                
            except Exception as e:
                logger.error(f"Error in computation request listener: {e}")
                await asyncio.sleep(5)
    
    async def _handle_computation_request(self, fields: Dict[bytes, bytes]):
        """Handle incoming computation request"""
        
        try:
            # Parse request data
            option_chain_data = json.loads(fields[b'option_chain_data'])
            computations = json.loads(fields[b'computations'])
            request_id = fields[b'request_id'].decode()
            
            # Convert to computation request
            options = []
            for strike_data in option_chain_data['strikes']:
                strike_price = strike_data['strike_price']
                
                # Process call option
                if strike_data.get('call'):
                    call_data = strike_data['call']
                    call_option = OptionData(
                        instrument_key=call_data['instrument_key'],
                        symbol=option_chain_data['underlying'],
                        strike_price=strike_price,
                        option_type='CE',
                        expiry_date=option_chain_data['expiry'],
                        ltp=call_data['ltp'],
                        volume=call_data['volume'],
                        oi=call_data['oi'],
                        bid=call_data['bid'],
                        ask=call_data['ask']
                    )
                    options.append(call_option)
                
                # Process put option
                if strike_data.get('put'):
                    put_data = strike_data['put']
                    put_option = OptionData(
                        instrument_key=put_data['instrument_key'],
                        symbol=option_chain_data['underlying'],
                        strike_price=strike_price,
                        option_type='PE',
                        expiry_date=option_chain_data['expiry'],
                        ltp=put_data['ltp'],
                        volume=put_data['volume'],
                        oi=put_data['oi'],
                        bid=put_data['bid'],
                        ask=put_data['ask']
                    )
                    options.append(put_option)
            
            # Create computation request
            request = ComputationRequest(
                request_id=request_id,
                underlying=option_chain_data['underlying'],
                underlying_price=option_chain_data['underlying_price'],
                expiry_date=option_chain_data['expiry'],
                risk_free_rate=0.05,  # Default 5% (would be configurable)
                options=options,
                compute_greeks=computations['greeks'],
                compute_technical_indicators=computations['technical_indicators']
            )
            
            # Process the request
            result = await self.process_option_chain(request)
            
            # Send result back via Redis
            result_data = {
                'request_id': result.request_id,
                'underlying': result.underlying,
                'computation_time_ms': result.computation_time_ms,
                'options_processed': result.options_processed,
                'computed_options': [
                    {
                        'instrument_key': opt.instrument_key,
                        'strike_price': opt.strike_price,
                        'option_type': opt.option_type,
                        'iv': opt.iv,
                        'delta': opt.delta,
                        'gamma': opt.gamma,
                        'theta': opt.theta,
                        'vega': opt.vega,
                        'rho': opt.rho,
                        'rsi': opt.rsi,
                        'sma_5': opt.sma_5,
                        'sma_20': opt.sma_20,
                        'bollinger_upper': opt.bollinger_upper,
                        'bollinger_lower': opt.bollinger_lower
                    }
                    for opt in result.options
                ],
                'summary': {
                    'total_call_iv': result.total_call_iv,
                    'total_put_iv': result.total_put_iv,
                    'avg_call_delta': result.avg_call_delta,
                    'avg_put_delta': result.avg_put_delta
                },
                'timestamp': result.timestamp.isoformat()
            }
            
            await self.redis.xadd("bulk_computation_results", result_data)
            
            logger.info(f"Completed bulk computation request: {request_id}")
            
        except Exception as e:
            logger.error(f"Error handling computation request: {e}")
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        
        return {
            'stats': self.computation_stats,
            'thread_pool_active': self.thread_pool._threads,
            'process_pool_active': getattr(self.process_pool, '_processes', {}),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def shutdown(self):
        """Shutdown the computation engine"""
        
        logger.info("Shutting down BulkComputationEngine...")
        
        # Shutdown thread pools
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)
        
        logger.info("BulkComputationEngine shutdown complete")
