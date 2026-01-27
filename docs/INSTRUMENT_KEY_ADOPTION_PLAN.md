# Accelerated instrument_key Adoption Plan

## Executive Overview

Building on Phase 3's successful registry integration (100% production with 98% SLA), this plan accelerates the complete migration from `instrument_token` to `instrument_key` as the primary identifier across all services.

**Timeline**: 6 weeks total | **Status**: Ready to execute after Phase 3 completion

---

## Phase 0: Audit & Contract Enforcement (Week 1)

### **Objectives**
- Complete inventory of remaining token-dependent code paths
- Establish `instrument_key` as primary identifier contract
- Update architectural documentation to codify new standards

### **Tasks**

#### **1.1 Comprehensive Token Usage Audit**
- [ ] **Inventory Analysis**
  - Audit all services using current `instrument_usage` summaries
  - Identify legacy scripts and proxy services still accepting tokens
  - Map token persistence points in databases and caches
  - Document broker-specific token requirements vs internal usage

- [ ] **Code Path Analysis** 
  - Scan codebase for `instrument_token` references
  - Identify APIs that accept tokens as input parameters
  - Find services that persist tokens as primary keys
  - Catalog token-dependent business logic

#### **1.2 API Contract Definition**
- [ ] **Primary Contract Establishment**
  - Define `instrument_key` as required primary identifier for all APIs
  - Specify tokens as derived metadata only (not input parameters)
  - Establish registry-first lookup patterns for all services
  - Document backward compatibility requirements during transition

- [ ] **Contract Validation**
  - Create contract compliance tests
  - Define API versioning strategy for migration
  - Establish token derivation validation rules

#### **1.3 Architectural Documentation Updates**
- [ ] **Update Core Architecture Documents**
  - `INSTRUMENT_DATA_ARCHITECTURE.md`: Codify instrument_key primacy
  - `INSTRUMENT_SUBSCRIPTION_ARCHITECTURE.md`: Define key-based subscription patterns
  - `REGISTRY_INTEGRATION_CONTRACTS.md`: Formalize registry-first patterns

- [ ] **Governance Documentation**
  - Update API design standards to require instrument_key
  - Document token usage restrictions and patterns
  - Create compliance checklist for new service development

### **Week 1 Deliverables**
- Complete token usage inventory with remediation plan
- Updated architectural contracts and documentation
- API compliance testing framework
- Token usage governance standards

---

## Phase 1: SDK & Strategy Layer Migration (Weeks 2-3)

### **Objectives**
- Migrate algo_engine/pythonsdk to instrument_key primary usage
- Update strategy hosts and risk services to key-based APIs
- Establish regression testing for token derivation

### **Tasks**

#### **2.1 SDK Strategy Host Migration**
- [ ] **PythonSDK Updates**
  - Update strategy host APIs to require `instrument_key` input
  - Implement internal token resolution for broker communication
  - Add registry client integration for metadata lookup
  - Maintain backward compatibility during transition

- [ ] **Algo Engine Integration**
  - Migrate strategy execution to key-based instrument resolution
  - Update portfolio and position tracking to use keys
  - Implement token derivation for ticker channel communication
  - Add performance monitoring for registry lookup overhead

#### **2.2 Risk & Position Service Migration**
- [ ] **API Interface Updates**
  - Remove token parameters from risk service APIs
  - Implement key-based position tracking
  - Add internal registry lookup for broker token derivation
  - Update trailing stop services to key-based operations

- [ ] **Service Coordination**
  - Ensure cross-service consistency during migration
  - Implement service-to-service key validation
  - Add circuit breakers for registry lookup failures

#### **2.3 Regression Testing Framework**
- [ ] **Token Derivation Validation**
  - Create tests ensuring tokens are registry-derived
  - Validate no direct token persistence as primary keys
  - Test backward compatibility during transition
  - Add performance benchmarks for key-based operations

### **Weeks 2-3 Deliverables**
- Updated SDK and strategy services with key-based APIs
- Migrated risk and position services
- Comprehensive regression testing suite
- Performance validation for registry lookups

---

## Phase 2: Subscription & Data Pipeline Migration (Weeks 4-5)

### **Objectives**
- Rebuild subscription bridge for key-based operations
- Harden dual-write tables with registry as single source
- Execute data migration and cache cleanup

### **Tasks**

#### **3.1 Subscription Bridge Rebuild**
- [ ] **Key-Based Subscription Architecture**
  - Rebuild subscription bridge to accept instrument_key
  - Implement registry lookup for broker-specific tokens
  - Add subscription state management by key
  - Ensure ticker channel mapping consistency

- [ ] **Market Data Integration**
  - Update market data services to key-based subscriptions
  - Implement token resolution for broker feeds
  - Add data consistency validation between key and token
  - Monitor subscription performance and reliability

#### **3.2 Dual-Write Table Hardening**
- [ ] **Single Source Architecture**
  - Make `broker_instrument_tokens` the authoritative source
  - Update downstream services to consume canonical events
  - Implement key-based event publishing
  - Add data consistency monitoring

- [ ] **Legacy Token Elimination**
  - Remove direct token caches after consumer migration
  - Implement registry-first lookup patterns
  - Add token derivation caching for performance
  - Validate data consistency across services

#### **3.3 Data Migration & Validation**
- [ ] **Migration Execution**
  - Run data validation scripts for key-token consistency
  - Execute cache cleanup for redundant token storage
  - Validate subscription state after migration
  - Monitor data integrity during transition

### **Weeks 4-5 Deliverables**
- Rebuilt subscription bridge with key-based architecture
- Hardened dual-write tables and data pipelines
- Completed data migration with validation
- Legacy token cache elimination

---

## Phase 3: Observability & Governance (Week 6)

### **Objectives**
- Implement monitoring for token usage violations
- Add feature flags to disable legacy token flows
- Complete governance documentation and compliance

### **Tasks**

#### **4.1 Advanced Monitoring**
- [ ] **Token Usage Detection**
  - Add monitoring to flag direct token usage bypassing registry
  - Implement telemetry analysis for token-only log entries
  - Create alerts for contract violations
  - Monitor registry lookup performance and failures

- [ ] **Compliance Monitoring**
  - Track API calls using tokens as primary identifiers
  - Monitor database queries persisting tokens as keys
  - Add dashboard for token usage compliance metrics
  - Implement automated compliance reporting

#### **4.2 Feature Flag Implementation**
- [ ] **Legacy Flow Disabling**
  - Add config-driven feature flags for token-only flows
  - Implement gradual disabling of legacy patterns
  - Add safety mechanisms for rollback if needed
  - Monitor impact of legacy flow disabling

#### **4.3 Governance Documentation**
- [ ] **Compliance Playbooks**
  - Document token usage restrictions in runbooks
  - Add compliance checklist for service reviews
  - Update architectural decision records
  - Create enforcement procedures for violations

### **Week 6 Deliverables**
- Advanced monitoring for token usage compliance
- Feature flags for legacy flow management
- Complete governance and compliance documentation
- Automated compliance reporting

---

## Rollout & Verification Strategy

### **Gradual Rollout Plan**
Following established Phase 3 rollout methodology:

1. **Shadow Mode** (10% traffic)
   - Run key-based services alongside token services
   - Compare responses and performance
   - Validate data consistency

2. **Progressive Deployment** (25% → 50% → 100%)
   - Gradual migration of services to key-based operations
   - Monitor for token-drop regressions
   - Maintain rollback capability throughout

3. **Legacy Retirement**
   - Disable legacy proxies and caches
   - Mark token usage as metadata-only in documentation
   - Complete architecture transition validation

### **Success Criteria**
- [ ] 100% of APIs use `instrument_key` as primary identifier
- [ ] All token usage is registry-derived metadata only
- [ ] No direct token persistence as primary keys
- [ ] Registry lookup performance <50ms P95
- [ ] Zero data consistency violations
- [ ] Complete compliance monitoring coverage

---

## Risk Management

### **Technical Risks**
| Risk | Mitigation | Contingency |
|------|------------|-------------|
| Registry lookup latency | Implement caching and performance monitoring | Rollback to token mode if P95 >100ms |
| Data consistency issues | Comprehensive validation and monitoring | Automated data correction scripts |
| Service integration failures | Gradual rollout with circuit breakers | Service-by-service rollback capability |
| Performance degradation | Baseline monitoring and alerting | Horizontal scaling and optimization |

### **Business Risks**
| Risk | Mitigation | Contingency |
|------|------------|-------------|
| Trading disruption | Shadow mode and gradual rollout | Immediate rollback procedures |
| Customer impact | Comprehensive testing and monitoring | Communication plan and rollback |
| Compliance violations | Automated monitoring and reporting | Emergency compliance procedures |

---

## Success Metrics

### **Technical Metrics**
- **API Compliance**: 100% of APIs use instrument_key as primary identifier
- **Performance**: Registry lookup latency <50ms P95
- **Data Consistency**: Zero token-key mapping violations
- **Monitoring Coverage**: 100% of token usage monitored for compliance

### **Business Metrics**
- **Service Reliability**: Maintain >99.9% availability during migration
- **Trading Performance**: No degradation in order execution latency
- **Operational Efficiency**: Reduced token management overhead
- **Compliance Readiness**: Automated compliance reporting active

---

## Implementation Timeline

```
Week 1: Phase 0 - Audit & Contracts
├── Token usage inventory
├── API contract definition  
└── Documentation updates

Week 2-3: Phase 1 - SDK & Strategy Migration
├── PythonSDK instrument_key migration
├── Risk/position service updates
└── Regression testing framework

Week 4-5: Phase 2 - Subscription & Data Migration
├── Subscription bridge rebuild
├── Dual-write table hardening
└── Data migration execution

Week 6: Phase 3 - Observability & Governance
├── Advanced monitoring implementation
├── Feature flag deployment
└── Governance documentation

Rollout: Progressive deployment using Phase 3 methodology
```

---

## Resource Requirements

### **Development Team**
- Lead architect (1 FTE) - Overall coordination and technical leadership
- Backend developers (2 FTE) - Service migration and API updates
- SDK developers (1 FTE) - PythonSDK and algo_engine integration
- DevOps engineer (0.5 FTE) - Deployment and monitoring
- QA engineer (0.5 FTE) - Testing and validation

### **Infrastructure**
- Development environments for migration testing
- Shadow deployment infrastructure
- Enhanced monitoring and alerting systems
- Registry performance optimization

---

## Dependencies

### **Completed Prerequisites** (from Phase 3)
- ✅ Registry integration at 100% production traffic
- ✅ SLA monitoring and alerting infrastructure
- ✅ Cross-service coordination framework
- ✅ Automated rollback procedures

### **External Dependencies**
- [ ] Broker API documentation for token requirements
- [ ] Compliance team approval for token usage changes
- [ ] Operations team capacity for migration support
- [ ] Customer communication plan for any service impacts

---

## Deliverables Summary

1. **Updated Contracts & Documentation**
   - Revised architectural documents with instrument_key primacy
   - API design standards and compliance checklists
   - Governance playbooks and enforcement procedures

2. **SDK & Strategy Changes**
   - Migrated PythonSDK with key-based APIs
   - Updated strategy hosts and risk services
   - Regression testing framework

3. **Rebuilt Subscription Bridge**
   - Key-based subscription architecture
   - Registry-integrated market data services
   - Data consistency monitoring

4. **Monitoring & Alerts**
   - Token usage compliance monitoring
   - Performance tracking for registry lookups
   - Automated compliance reporting

5. **Final Compliance Report**
   - Complete token-to-key migration validation
   - Performance impact analysis
   - Governance compliance certification

This plan leverages Phase 3's proven rollout methodology while accelerating the complete transition to instrument_key-based architecture across all services.