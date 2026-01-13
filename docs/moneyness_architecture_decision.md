# Moneyness Architecture Decision

## Current State
Moneyness calculations are currently in the Instrument Service, with Signal Service calling it for moneyness-based Greeks calculations.

## Architectural Options

### Option 1: Keep Moneyness in Instrument Service (Current)

**Architecture:**
```
Execution Engine → Signal Service → Instrument Service
                        ↓
                   Greeks Calculation
```

**Pros:**
- Single source of truth for instrument metadata
- Centralized moneyness definitions
- Consistent moneyness levels across all services
- Other services can reuse moneyness logic
- Clear separation of concerns

**Cons:**
- Network latency (adds ~20-50ms per request)
- Dependency on Instrument Service availability
- Harder to optimize for high-frequency calculations
- Complex caching requirements

**Best for:**
- Systems prioritizing consistency
- Lower frequency calculations
- Multiple services needing moneyness

### Option 2: Move Moneyness to Signal Service

**Architecture:**
```
Execution Engine → Signal Service (self-contained)
                        ↓
                   Greeks + Moneyness
```

**Pros:**
- Better performance (no network calls)
- Lower latency for real-time calculations
- Self-contained service
- Can optimize for specific use cases
- Natural fit with Greeks calculations

**Cons:**
- Potential code duplication
- Risk of inconsistent definitions
- Harder to maintain centralized rules

**Best for:**
- High-frequency trading
- Real-time analytics
- Performance-critical applications

### Option 3: Hybrid Approach (Recommended)

**Architecture:**
```
Instrument Service:
- Moneyness definitions & rules
- Strike generation patterns
- Exchange-specific configurations
- Historical moneyness data

Signal Service:
- Real-time moneyness calculations
- Greeks aggregation by moneyness
- Performance-optimized caching
- Moneyness-based streaming
```

**Implementation:**

1. **Initial Load (on startup):**
   ```python
   # Signal Service loads moneyness rules from Instrument Service
   moneyness_rules = await instrument_service.get_moneyness_configuration()
   local_calculator.initialize(moneyness_rules)
   ```

2. **Real-time Calculation:**
   ```python
   # Signal Service calculates locally
   moneyness = local_calculator.classify_moneyness(strike, spot, option_type)
   greeks = self.aggregate_greeks_by_moneyness(moneyness, options)
   ```

3. **Periodic Sync:**
   ```python
   # Refresh rules periodically (e.g., daily)
   await self.sync_moneyness_rules()
   ```

## Performance Comparison

| Metric | Instrument Service | Signal Service | Hybrid |
|--------|-------------------|----------------|---------|
| Latency | 20-50ms | <1ms | <1ms |
| Consistency | Excellent | Risk of drift | Good |
| Maintenance | Centralized | Distributed | Balanced |
| Scalability | Network bottleneck | Excellent | Excellent |
| Flexibility | Limited | High | High |

## Recommendation: Hybrid Approach

The hybrid approach provides the best balance:

1. **Instrument Service** remains the source of truth for:
   - Moneyness level definitions
   - Exchange-specific rules
   - Strike generation patterns
   - Configuration management

2. **Signal Service** handles:
   - Real-time calculations
   - High-frequency operations
   - Performance-critical paths
   - Caching and optimization

3. **Benefits:**
   - Sub-millisecond latency for calculations
   - Consistency through periodic sync
   - Reduced network traffic
   - Service resilience
   - Flexibility for optimization

## Implementation Plan

### Phase 1: Local Calculator (1 week)
- Implement `LocalMoneynessCalculator` in Signal Service
- Add configuration sync mechanism
- Maintain backward compatibility

### Phase 2: Performance Optimization (1 week)
- Add intelligent caching
- Implement batch calculations
- Optimize for streaming scenarios

### Phase 3: Migration (1 week)
- Gradually migrate real-time calculations
- Monitor performance improvements
- Update documentation

### Phase 4: Enhancement (1 week)
- Add advanced features (custom moneyness levels)
- Implement fallback mechanisms
- Performance tuning

## Code Example

```python
# Signal Service with local moneyness calculation
class EnhancedSignalProcessor:
    def __init__(self):
        self.moneyness_calculator = LocalMoneynessCalculator()
        self.last_rule_sync = None
        
    async def initialize(self):
        # Load rules from Instrument Service
        rules = await self.instrument_client.get_moneyness_configuration()
        self.moneyness_calculator.initialize(rules)
        
    async def calculate_moneyness_greeks(self, underlying, spot_price):
        # Fast local calculation
        strikes = self.get_available_strikes(underlying)
        
        moneyness_groups = {}
        for strike in strikes:
            level = self.moneyness_calculator.classify_moneyness(
                strike, spot_price, 'call'
            )
            if level not in moneyness_groups:
                moneyness_groups[level] = []
            moneyness_groups[level].append(strike)
            
        # Aggregate Greeks by moneyness
        return self.aggregate_by_moneyness(moneyness_groups)
```

## Conclusion

The hybrid approach offers the best of both worlds:
- **Performance** of local calculations
- **Consistency** of centralized definitions
- **Flexibility** for future enhancements
- **Resilience** through reduced dependencies

This architecture supports both current needs and future scaling requirements while maintaining system coherence.