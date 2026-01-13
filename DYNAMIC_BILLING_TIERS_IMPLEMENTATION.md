# Dynamic Billing Tiers - Implementation

## Overview

This document describes the implementation of Item 5: Remove hardcoded billing tiers for Sprint 5A.

## Implementation Details

### 1. Stream Abuse Protection Service Updates

The `StreamAbuseProtectionService` has been updated to fetch connection limits dynamically from marketplace subscriptions instead of using hardcoded tiers.

**Key Changes:**
- Renamed `DEFAULT_LIMITS` to `FALLBACK_LIMITS` (used only when marketplace is unavailable)
- Added `_get_user_limits()` method to fetch dynamic limits
- Added `_get_tier_limits()` method to calculate tier-specific limits
- Integrated marketplace client for subscription lookups
- Added caching to reduce API calls (5-minute TTL)

### 2. Dynamic Tier Resolution

**Tier Priority (highest to lowest):**
1. Enterprise (10x base limits)
2. Premium (5x base limits)
3. Standard (2x base limits)
4. Free (1x base limits)

**Implementation:**
```python
async def _get_user_limits(self, user_id: str, stream_type: StreamType) -> ConnectionLimits:
    # 1. Check cache
    # 2. Fetch user subscriptions from marketplace
    # 3. Find best active tier
    # 4. Calculate limits based on tier multiplier
    # 5. Cache result
    return limits
```

### 3. Marketplace Integration

The marketplace client was enhanced to ensure tier information is included:

```python
# Sprint 5A: Add tier extraction for dynamic limits
for subscription in data.get("subscriptions", []):
    if "tier" not in subscription:
        # Extract from product metadata
        subscription["tier"] = product_data.get("tier", "free")
```

### 4. Connection Limit Calculation

Limits are calculated using multipliers applied to base (fallback) values:

```python
tier_multipliers = {
    "free": 1.0,
    "standard": 2.0,
    "premium": 5.0,
    "enterprise": 10.0
}
```

**Example for PUBLIC stream type:**
- Free: 50 concurrent connections, 10 subscriptions per connection
- Standard: 100 concurrent connections, 20 subscriptions per connection
- Premium: 250 concurrent connections, 50 subscriptions per connection
- Enterprise: 500 concurrent connections, 100 subscriptions per connection

### 5. Graceful Degradation

If the marketplace service is unavailable:
1. Service logs a warning
2. Falls back to base limits (equivalent to free tier)
3. Continues operation without disruption
4. Retries on next request after cache expires

## Architecture

```
Connection Request
      │
      ▼
Check Connection Allowed
      │
      ▼
Get User Limits ─────► Check Cache
      │                    │ Hit
      │                    ▼
      │                Return Cached
      │
      │ Miss
      ▼
Fetch from Marketplace
      │
      ├─► Get User Subscriptions
      │   │
      │   └─► Extract Best Tier
      │
      └─► Calculate Limits
          │
          └─► Cache Result (5 min)
```

## Benefits

1. **Dynamic Pricing**: Limits automatically adjust with subscription changes
2. **No Code Changes**: New tiers can be added without modifying code
3. **Consistent Experience**: Users get limits based on their subscription
4. **Performance**: Caching prevents excessive marketplace API calls
5. **Reliability**: Fallback ensures service continues if marketplace is down

## Testing

Comprehensive test suite in `test_dynamic_billing_tiers.py`:
- ✅ Free tier gets base limits
- ✅ Premium tier gets 5x limits
- ✅ Enterprise tier gets 10x limits
- ✅ Best tier selected from multiple subscriptions
- ✅ Limits are cached for performance
- ✅ Cache expires after TTL
- ✅ Fallback to base limits on marketplace failure
- ✅ Different stream types have different bases
- ✅ Connection checks use dynamic limits

## Configuration

No configuration changes required. The service automatically:
- Detects marketplace service availability
- Fetches user subscriptions
- Calculates appropriate limits
- Caches results for performance

## Migration

No migration required. The change is backward compatible:
- Existing connections continue working
- New connections get dynamic limits
- Marketplace integration is optional (fallback exists)

## Monitoring

Monitor these metrics:
- `marketplace_client.get_user_subscriptions` success rate
- Cache hit rate for `_limits_cache`
- Distribution of tiers in use
- Connection rejection rates by tier

## Next Steps

- Item 6: Expose author-controlled version policy
- Item 7: Add receive_email support in SDK
- Consider adding custom tier definitions in marketplace
- Add metrics for tier-based usage patterns