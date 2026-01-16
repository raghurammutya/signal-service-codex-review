# Custom Script Execution Design (Python + MinIO)

## Goals
- Allow custom scripts to read: market data, signal_service metrics, and outputs of other custom scripts.
- Support both real-time execution and one-time execution.
- Behave like built-in indicators (same delivery shape, caching, and streaming).
- Restrict availability to users with proper permissions.
- No cross-tenant access to scripts or outputs (explicitly disallowed).

## Non-Goals
- Cross-tenant sharing of private scripts.
- Running scripts inside the signal_service process.
- Allowing arbitrary network access from scripts.

## Key Decisions
- Language: Python.
- Script storage: MinIO (code and metadata objects).
- Cross-tenant script reads: not allowed.
- API surface: approved by user.

## High-Level Architecture
1) Script Registry Service
   - Manages script metadata, versions, ownership, permissions, and dependency graph.
   - Stores code and metadata in MinIO.
2) Execution Service (Isolated)
   - Runs scripts in a hardened sandbox container or micro-VM.
   - No direct network access except to the Data Access Gateway.
3) Data Access Gateway
   - Read-only, typed APIs for market data, metrics, and script outputs.
   - Enforces user-level authorization and tier/feature permissions.
4) Signal Service Integration
   - Treats script outputs as indicators (cache + stream + history).

## Data Flow
### Realtime Execution
1) Market tick or schedule event triggers execution request.
2) Execution Service resolves dependencies (other scripts), with user permissions enforced.
3) Execution Service pulls required inputs via Data Access Gateway.
4) Script runs in sandbox; output validated and published to signal_service.
5) signal_service caches output in Redis and stores time-series in TimescaleDB.
6) Subscribers receive output through existing indicator streaming paths.

### One-Time Execution
1) User calls execute API with parameters.
2) Permissions validated against script and subscription tier.
3) Execution Service runs script; output validated.
4) Response returned to caller and optionally stored for audit/history.

## Script Registry (MinIO)
- MinIO object layout:
  - scripts/{owner_id}/{script_id}/{version}/script.py
  - scripts/{owner_id}/{script_id}/{version}/meta.json
- meta.json contents:
  - script_id, version, owner_id
  - runtime_mode: realtime | onetime
  - permissions: tiers/features/allowed_users
  - input_schema, output_schema
  - depends_on: [script_id@version]
  - created_at, updated_at, status

## Permissions Model
- Script access requires:
  - Ownership or explicit entitlement (team/org/marketplace subscription).
  - Feature tier allowing custom scripts.
- Dependency access:
  - All dependencies must be accessible by the same user.
  - No cross-tenant reads. Dependency resolution fails if ownership/entitlement mismatch.

## Execution Service
- Runs outside signal_service.
- Sandbox requirements:
  - CPU and memory quotas per execution.
  - Wall-time timeout per run.
  - No filesystem writes except /tmp.
  - No outbound network except Data Access Gateway.
  - Allowlisted Python modules only.
- Execution context injected:
  - context: instrument_key, timeframe, params, timestamp
  - read APIs: get_market_data(), get_metric(), get_script_output()

## Data Access Gateway
- Read-only APIs:
  - Market data: /data/market
  - Metrics: /data/metrics
  - Script output: /data/scripts/{script_id}/latest or /data/scripts/{script_id}/history
- Enforces:
  - User authorization and entitlements.
  - Script ownership boundaries.
  - Rate limits per user and per script.

## Output Handling
- Output schema matches indicator response shape:
  - value, timestamp, metadata
- Validation:
  - Output must match meta.json output_schema.
  - Invalid outputs are rejected and logged.
- Storage:
  - Redis (hot cache) for realtime.
  - TimescaleDB for historical analysis.

## Dependency Resolution
- Dependencies declared in meta.json.
- Resolution steps:
  - Verify access to each dependency.
  - Ensure no cycles (graph validation at publish time).
  - Retrieve dependency outputs via Data Access Gateway.

## Observability
- Execution metrics:
  - duration_ms, cpu_ms, memory_mb, error_count, timeout_count
- Health metrics:
  - queue depth, execution success rate, dependency failures
- Audit:
  - script_id, version, user_id, params hash, output hash

## Failure Modes
- Dependency unavailable -> execution fails with explicit error.
- Data gateway failure -> retry with backoff; fail with clear error.
- Sandbox timeout -> terminate and return timeout error.
- Permission denied -> return 403 before any execution.

## API Surface (Summary)
- POST /scripts (create draft)
- POST /scripts/{id}/publish
- GET /scripts/{id}/versions
- POST /scripts/{id}/execute (onetime)
- POST /scripts/{id}/subscribe (realtime)
- GET /signals/{instrument_key}/custom/{script_id}

## Open Questions (For Future)
- Rate limit thresholds per tier.
- Granularity of dependency caching.
- Multi-tenant org/team sharing rules.

