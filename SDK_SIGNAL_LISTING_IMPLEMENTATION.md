# SDK Signal Listing - Real Implementation

## Overview

This document describes the implementation of Item 4: Make SDK signal listing real (not placeholder) for Sprint 5A.

## Implementation Details

### 1. Enhanced List Endpoint (`/api/v2/signals/sdk/signals/streams`)

The listing endpoint now provides real signal streams from multiple sources:

**Key Enhancements:**
- Fetches user's active marketplace subscriptions
- Lists user's personal signal scripts from MinIO
- Maintains public and common signals
- Supports instrument filtering
- Returns detailed metadata for each stream

**Request Parameters:**
```
GET /api/v2/signals/sdk/signals/streams
Query params:
  - signal_type: Filter by type (public, common, marketplace, personal)
  - instruments: List of instruments (defaults to user watchlist)
```

**Response Structure:**
```json
{
  "streams": {
    "public": ["public:NIFTY50:price:realtime", ...],
    "common": ["common:NIFTY50:rsi:period-14", ...],
    "marketplace": [
      {
        "stream_key": "marketplace:prod-123:NIFTY50:momentum:period-14",
        "product_id": "prod-123",
        "product_name": "Advanced Momentum Signals",
        "signal_name": "momentum",
        "instrument": "NIFTY50",
        "subscription_id": "sub-456",
        "execution_token": "exec-token-789"
      }
    ],
    "personal": [
      {
        "stream_key": "personal:user-123:signal-001:NIFTY50:default",
        "script_id": "signal-001",
        "script_name": "My RSI Divergence",
        "instrument": "NIFTY50",
        "owner_id": "user-123"
      }
    ]
  },
  "counts": {
    "public": 15,
    "common": 40,
    "marketplace": 6,
    "personal": 4
  },
  "total": 65
}
```

### 2. Marketplace Client Service (`app/services/marketplace_client.py`)

Created/enhanced marketplace client for real integration:

**Key Methods:**
- `get_user_subscriptions()` - Fetches active subscriptions with signal definitions
- `get_product_signals()` - Gets signal metadata for products
- `verify_execution_token()` - Validates execution tokens
- `report_signal_usage()` - Reports signal execution for analytics

**Configuration:**
```python
MARKETPLACE_SERVICE_URL = "http://marketplace_service:8090"
MARKETPLACE_API_KEY = "internal-api-key"  # From config service
```

### 3. Enhanced Token Validation

The token validation endpoint now uses real marketplace integration:

```
POST /api/v2/signals/sdk/signals/validate-token
Query params:
  - execution_token: Token to validate
  - product_id: Product being accessed

Response:
{
  "is_valid": true,
  "user_id": "user-123",
  "product_id": "prod-momentum",
  "subscription_id": "sub-456",
  "expires_at": "2024-12-31T23:59:59Z"
}
```

### 4. Integration Points

**Marketplace Service Integration:**
- Fetches user's active subscriptions
- Validates execution tokens
- Retrieves product signal definitions
- Reports usage for billing/analytics

**Personal Script Service Integration:**
- Lists user's personal signal scripts
- Uses existing PersonalScriptService from algo_engine
- Maintains ACL (only owner's scripts listed)

## Architecture

```
SDK Client Request
      │
      ▼
List Streams Endpoint
      │
      ├─► Get Public/Common Streams
      │   (Always available)
      │
      ├─► Fetch Marketplace Subscriptions
      │   │
      │   └─► MarketplaceClient.get_user_subscriptions()
      │       │
      │       └─► For each subscription:
      │           - Get product signals
      │           - Generate stream keys
      │           - Include execution token
      │
      └─► Fetch Personal Signals
          │
          └─► PersonalScriptService.list_scripts()
              │
              └─► For each script:
                  - Generate stream keys
                  - Include metadata
```

## Security Considerations

1. **Authentication Required**: All endpoints require gateway authentication
2. **Subscription Validation**: Only shows signals for active subscriptions
3. **ACL Enforcement**: Personal signals only show owner's scripts
4. **Token Isolation**: Execution tokens are subscription-specific
5. **Graceful Degradation**: Service failures don't break the endpoint

## Error Handling

- **Marketplace Unavailable**: Returns empty marketplace array, continues with others
- **Personal Scripts Unavailable**: Returns empty personal array, continues
- **Invalid Authentication**: Returns 401 Unauthorized
- **Server Errors**: Returns 500 with error details

## Testing

Comprehensive test suite in `test_sdk_signal_listing.py`:
- ✅ List all signal types with real data
- ✅ Filter by signal type
- ✅ Default instruments when none specified
- ✅ Marketplace integration with subscriptions
- ✅ Personal signals integration
- ✅ Graceful failure handling
- ✅ Token validation with marketplace
- ✅ Stream key format validation

## Production Considerations

1. **Caching**: Consider caching subscription data (5-minute TTL)
2. **Pagination**: Add pagination for users with many signals
3. **Instrument Limits**: Cap instruments to prevent response bloat
4. **Rate Limiting**: Limit listing requests per user
5. **Monitoring**: Track marketplace API latency

## Benefits

1. **Real Data**: SDK clients see actual available signals
2. **Dynamic Updates**: New subscriptions immediately visible
3. **Execution Tokens**: Included for seamless subscription
4. **Rich Metadata**: Product names, signal descriptions, etc.
5. **Type Safety**: Structured responses with clear schemas

## Next Steps

- Item 5: Remove hardcoded billing tiers
- Item 6: Expose author-controlled version policy
- Item 7: Add receive_email support in SDK