# Phase 1 Week 2: Strategy Services Migration - Executable Checklist

**Duration**: 5 days (Days 6-10)  
**Building On**: Week 1 SDK/Client foundation with instrument_key-first contracts  
**Guardrails**: Phase 3 SLA monitoring (98% uptime, <107ms latency) maintained  

## 🎯 Week 2 Overview

**Focus**: Migrate strategy host, risk engine, and trailing services to instrument_key contracts  
**Success Metrics**: Registry metadata enrichment active, zero token exposure in responses, 98% SLA maintained

---

## 📅 Day 6-7: Strategy Host & Risk Engine

### ✅ **STRATEGY_001: Update Strategy Host APIs (10h) - IN PROGRESS**
**Priority**: Critical | **Owner**: Strategy Team

**Acceptance Criteria**:
- [ ] All strategy APIs require instrument_key parameters
- [ ] Strategy execution uses registry-derived tokens internally
- [ ] Position tracking by instrument_key, not token
- [ ] Historical performance data keyed by instrument_key
- [ ] Strategy results include enriched instrument metadata

**Implementation Steps**:
1. Update `StrategyExecutionService` to accept instrument_key in all public methods
2. Integrate with Phase 1 SDK `InstrumentClient` for token resolution
3. Modify position tracking to use instrument_key as primary identifier
4. Update performance analytics aggregation by instrument_key
5. Ensure strategy responses include registry metadata enrichment

### **STRATEGY_002: Risk Engine Contract Updates (8h)**
**Priority**: Critical | **Owner**: Risk Team | **Dependencies**: STRATEGY_001

**Acceptance Criteria**:
- [ ] Risk calculations based on instrument metadata from registry
- [ ] Position limits enforced by instrument_key
- [ ] Risk monitoring alerts use instrument symbols, not tokens
- [ ] Portfolio analytics aggregated by instrument_key
- [ ] Risk thresholds configurable by instrument metadata (sector, market cap, etc.)

**Implementation Steps**:
1. Update `RiskCalculationEngine` to consume registry metadata
2. Modify position limit checking to use instrument_key grouping
3. Update alert system to display symbols from enriched metadata
4. Implement metadata-based risk rules (sector limits, volatility thresholds)
5. Update portfolio risk aggregation by instrument characteristics

---

## 📅 Day 8-9: Trailing Services & Alert Integration

### **TRAILING_001: Trailing Stop Service Migration (8h)**
**Priority**: High | **Owner**: Trading Team | **Dependencies**: STRATEGY_002

**Acceptance Criteria**:
- [ ] Trailing stops created with instrument_key reference
- [ ] Price monitoring uses registry-enriched metadata
- [ ] Stop execution derives broker tokens internally
- [ ] Order state tracking by instrument_key
- [ ] Trailing stop history maintains instrument metadata

**Implementation Steps**:
1. Update `TrailingStopService` to accept instrument_key in creation methods
2. Integrate with Phase 1 SDK for internal token resolution
3. Modify price monitoring to use enriched metadata for display
4. Update order execution to derive broker tokens via registry
5. Ensure stop history includes complete instrument information

### **TRAILING_002: Alert Service Integration (6h)**
**Priority**: Medium | **Owner**: Alerts Team | **Dependencies**: TRAILING_001

**Acceptance Criteria**:
- [ ] Price alerts reference instrument_key
- [ ] Alert notifications include instrument symbols from registry
- [ ] Alert history keyed by instrument metadata
- [ ] User preferences stored by instrument_key
- [ ] Alert rules support metadata-based conditions

**Implementation Steps**:
1. Update `AlertService` to use instrument_key as primary identifier
2. Modify alert notifications to include enriched instrument metadata
3. Update alert history storage and retrieval by instrument_key
4. Implement metadata-based alert conditions (sector, exchange, etc.)
5. Migrate existing alert preferences to instrument_key format

---

## 📅 Day 10: Metadata Enrichment & Integration Testing

### **META_001: Registry Metadata Enrichment (8h)**
**Priority**: High | **Owner**: Data Team | **Dependencies**: TRAILING_002

**Acceptance Criteria**:
- [ ] All API responses include instrument metadata from registry
- [ ] Symbol, exchange, sector information automatically populated
- [ ] Market data enriched with registry-sourced attributes
- [ ] Response schemas updated to include metadata fields
- [ ] Metadata enrichment maintains <50ms performance impact

**Implementation Steps**:
1. Implement automatic metadata enrichment middleware for all strategy APIs
2. Update response schemas to include standard metadata fields
3. Ensure market data responses include enriched instrument information
4. Add metadata caching layer for performance optimization
5. Validate enrichment doesn't impact Phase 3 SLA requirements

### **TEST_STRATEGY_001: End-to-End Integration Tests (10h)**
**Priority**: Critical | **Owner**: QA Team | **Dependencies**: META_001

**Acceptance Criteria**:
- [ ] Complete order flow tests using instrument_key
- [ ] Strategy execution tests validate metadata enrichment
- [ ] Multi-broker compatibility tests pass
- [ ] Performance tests maintain 98% SLA from Phase 3
- [ ] Integration tests cover all Week 2 components

**Implementation Steps**:
1. Create comprehensive integration test suite for strategy services
2. Test complete order flows from strategy execution to broker integration
3. Validate metadata enrichment across all service boundaries
4. Performance test strategy services maintain Phase 3 SLA requirements
5. Test multi-broker compatibility with Week 1 broker integration layer

---

## 🛡️ Phase 3 Guardrails Maintained

### **SLA Monitoring**
- **98% uptime requirement** continuously monitored during migration
- **<107ms coordination latency** baseline maintained from Phase 3
- **Registry lookup performance** <50ms cached, <200ms uncached

### **Rollback Procedures**
- **Feature flags** for gradual strategy service rollout (10% → 25% → 50% → 100%)
- **Circuit breakers** on registry failures with fallback to cached metadata
- **Monitoring alerts** for SLA degradation trigger automatic rollback to Week 1 state

### **Production Safety**
- **Blue-green deployments** for all strategy service updates
- **Canary releases** for strategy API changes with gradual traffic routing
- **Health checks** validate registry connectivity before processing strategy requests

---

## 📊 Week 2 Success Criteria

### **Day-by-Day Completion**
- **Day 6**: Strategy host APIs migrated to instrument_key contracts
- **Day 7**: Risk engine consuming registry metadata for calculations
- **Day 8**: Trailing stops operational with instrument_key references
- **Day 9**: Alert system migrated with metadata-enriched notifications
- **Day 10**: Complete integration testing validates end-to-end flow

### **Technical Milestones**
- [ ] **Zero token exposure** in strategy service responses
- [ ] **Registry metadata enrichment** active across all strategy APIs
- [ ] **Multi-broker compatibility** maintained through Week 1 integration layer
- [ ] **Performance SLA compliance** 98% uptime, <107ms latency preserved
- [ ] **Complete test coverage** validates instrument_key-first operations

### **Business Impact**
- [ ] **Strategy performance tracking** by instrument_key with enriched metadata
- [ ] **Risk management** enhanced with metadata-based rules and limits
- [ ] **User notifications** include human-readable symbols and exchange information
- [ ] **Historical analytics** aggregated by meaningful instrument characteristics
- [ ] **Operational visibility** improved through metadata-enriched monitoring

---

## 🚀 Week 2 → Phase 2 Preparation

Upon Week 2 completion, **Phase 2: Subscription & Data Pipeline Migration** will begin with:

- **Subscription Services**: Update to use instrument_key-based subscriptions
- **Data Pipelines**: Migrate from token-based to key-based processing  
- **Market Data Streaming**: Enhanced with registry metadata enrichment
- **Event Processing**: Complete instrument_key adoption across all data flows

**Week 2 execution maintains Phase 3 production stability** while systematically addressing the remaining token usage patterns identified in Phase 0's comprehensive audit.