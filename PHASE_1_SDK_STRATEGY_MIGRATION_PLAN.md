# Phase 1: SDK & Strategy Migration - Executable Plan

**Duration**: 2 weeks  
**Building On**: Phase 0 automation + Phase 3 registry infrastructure  
**Guardrails**: Phase 3 SLA monitoring, rollback procedures maintained  

## 🎯 Phase 1 Overview

**Week 1**: PythonSDK & Client Migration  
**Week 2**: Strategy Services Contract Migration  
**Success Metrics**: 98% SLA maintained, zero token exposure in responses, 100% registry-derived lookups

---

## 📅 WEEK 1: PythonSDK & Client Migration

### **Day 1-2: PythonSDK Core Migration**

#### **Task SDK_001: Update PythonSDK instrument_key Requirements**
**Priority**: Critical | **Effort**: 12 hours | **Owner**: SDK Team

**Acceptance Criteria**:
- [ ] All public SDK methods require `instrument_key` parameter
- [ ] Remove all `instrument_token` input parameters from public APIs
- [ ] Deprecation warnings implemented for legacy token methods
- [ ] Backward compatibility layer preserves existing integrations

**Implementation Steps**:
1. Update `InstrumentClient` class to require instrument_key
2. Modify `OrderClient`, `DataClient`, `PositionClient` constructors
3. Add `@deprecated` decorators to token-based methods
4. Implement internal token resolution via registry client

#### **Task SDK_002: Implement Internal Token Resolution**
**Priority**: Critical | **Effort**: 10 hours | **Owner**: SDK Team

**Acceptance Criteria**:
- [ ] Registry client integrated for broker token lookups
- [ ] Token derivation occurs internally before broker calls
- [ ] Cache layer implemented for registry lookups (sub-50ms)
- [ ] Error handling for missing instrument mappings

**Implementation Steps**:
1. Integrate registry client from Phase 3 infrastructure
2. Wrap all broker API calls with token resolution
3. Add Redis caching for registry lookups
4. Implement fallback/retry logic for registry failures

#### **Task SDK_003: Remove Direct Token Inputs**
**Priority**: High | **Effort**: 8 hours | **Owner**: SDK Team

**Acceptance Criteria**:
- [ ] No public methods accept raw instrument tokens
- [ ] All token handling moved to internal resolution layer
- [ ] Documentation updated with instrument_key examples
- [ ] Migration guide created for SDK consumers

### **Day 3-4: Client Layer Updates**

#### **Task CLIENT_001: Update HTTP Client Contracts**
**Priority**: Critical | **Effort**: 8 hours | **Owner**: Integration Team

**Acceptance Criteria**:
- [ ] All API clients send instrument_key in requests
- [ ] HTTP client middleware derives tokens internally
- [ ] Request/response logging excludes sensitive tokens
- [ ] Client-side validation ensures instrument_key presence

#### **Task CLIENT_002: Broker Integration Wrapper**
**Priority**: High | **Effort**: 10 hours | **Owner**: Integration Team

**Acceptance Criteria**:
- [ ] Kite, Zerodha, IBKR clients wrapped with token resolution
- [ ] Multi-broker token support via registry lookup
- [ ] Broker-specific token formats handled internally
- [ ] Connection pooling and rate limiting preserved

### **Day 5: Testing & Validation**

#### **Task TEST_SDK_001: SDK Contract Compliance Tests**
**Priority**: High | **Effort**: 6 hours | **Owner**: QA Team

**Acceptance Criteria**:
- [ ] Unit tests cover all instrument_key-based methods
- [ ] Integration tests validate registry token resolution
- [ ] Performance tests ensure <50ms lookup latency
- [ ] Backward compatibility tests pass with deprecation warnings

---

## 📅 WEEK 2: Strategy Services Migration

### **Day 6-7: Strategy Host Migration**

#### **Task STRATEGY_001: Update Strategy Host APIs**
**Priority**: Critical | **Effort**: 10 hours | **Owner**: Strategy Team

**Acceptance Criteria**:
- [ ] All strategy APIs require instrument_key parameters
- [ ] Strategy execution uses registry-derived tokens
- [ ] Position tracking by instrument_key, not token
- [ ] Historical performance data keyed by instrument_key

#### **Task STRATEGY_002: Risk Engine Contract Updates**
**Priority**: Critical | **Effort**: 8 hours | **Owner**: Risk Team

**Acceptance Criteria**:
- [ ] Risk calculations based on instrument metadata from registry
- [ ] Position limits enforced by instrument_key
- [ ] Risk monitoring alerts use instrument symbols, not tokens
- [ ] Portfolio analytics aggregated by instrument_key

### **Day 8-9: Trailing Services Migration**

#### **Task TRAILING_001: Trailing Stop Service Migration**
**Priority**: High | **Effort**: 8 hours | **Owner**: Trading Team

**Acceptance Criteria**:
- [ ] Trailing stops created with instrument_key reference
- [ ] Price monitoring uses registry-enriched metadata
- [ ] Stop execution derives broker tokens internally
- [ ] Order state tracking by instrument_key

#### **Task TRAILING_002: Alert Service Integration**
**Priority**: Medium | **Effort**: 6 hours | **Owner**: Alerts Team

**Acceptance Criteria**:
- [ ] Price alerts reference instrument_key
- [ ] Alert notifications include instrument symbols from registry
- [ ] Alert history keyed by instrument metadata
- [ ] User preferences stored by instrument_key

### **Day 10: Metadata Enrichment & Testing**

#### **Task META_001: Registry Metadata Enrichment**
**Priority**: High | **Effort**: 8 hours | **Owner**: Data Team

**Acceptance Criteria**:
- [ ] All API responses include instrument metadata from registry
- [ ] Symbol, exchange, sector information automatically populated
- [ ] Market data enriched with registry-sourced attributes
- [ ] Response schemas updated to include metadata fields

#### **Task TEST_STRATEGY_001: End-to-End Integration Tests**
**Priority**: Critical | **Effort**: 10 hours | **Owner**: QA Team

**Acceptance Criteria**:
- [ ] Complete order flow tests using instrument_key
- [ ] Strategy execution tests validate metadata enrichment
- [ ] Multi-broker compatibility tests pass
- [ ] Performance tests maintain 98% SLA from Phase 3

---

## 🛡️ Phase 3 Guardrails Maintained

### **SLA Monitoring**
- **98% uptime requirement** maintained throughout migration
- **<107ms coordination latency** preserved from Phase 3 baseline
- **Registry lookup performance** <50ms cached, <200ms uncached

### **Rollback Procedures**
- **Feature flags** for gradual rollout (10% → 25% → 50% → 100%)
- **Circuit breakers** on registry failures with token fallback
- **Monitoring alerts** for SLA degradation triggers automatic rollback

### **Production Safety**
- **Blue-green deployments** for all service updates
- **Canary releases** for SDK updates with client-side feature flags
- **Health checks** validate registry connectivity before traffic routing

---

## ✅ Phase 1 Success Criteria

### **Week 1 Completion**
- [ ] PythonSDK requires instrument_key for all public methods
- [ ] Internal token resolution via Phase 3 registry operational
- [ ] Zero direct token inputs in public SDK APIs
- [ ] Backward compatibility maintained with deprecation warnings

### **Week 2 Completion**  
- [ ] Strategy services migrated to instrument_key contracts
- [ ] Registry metadata enrichment active in all responses
- [ ] API responses contain tokens only as internal metadata
- [ ] End-to-end tests validate complete migration

### **Overall Phase 1 Success**
- [ ] **98% SLA maintained** throughout 2-week migration
- [ ] **Zero production incidents** related to migration
- [ ] **Complete contract compliance** across SDK and strategy layers
- [ ] **Registry integration** proven at production scale

---

## 🚀 Phase 2 Preparation

Upon Phase 1 completion, **Phase 2: Subscription & Data Pipeline Migration** will begin with:
- **Subscription services** updated to use instrument_key-based subscriptions
- **Data pipelines** migrated from token-based to key-based processing
- **Market data streaming** enhanced with registry metadata

**Phase 1 execution begins immediately** leveraging Phase 0's 6,854 identified API parameters and Phase 3's production-ready registry infrastructure.