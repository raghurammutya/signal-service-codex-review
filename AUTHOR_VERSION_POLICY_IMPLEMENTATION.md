# Author-Controlled Version Policy - Implementation

## Overview

This document describes the implementation of Item 6: Expose author-controlled version policy for Sprint 5A.

## Implementation Details

### 1. Version Policy API (`app/api/v2/signal_version_policy.py`)

Created comprehensive API endpoints for signal authors to control versioning:

**Key Endpoints:**
- `GET /api/v2/signals/version-policy/{signal_id}` - Get current policy
- `PUT /api/v2/signals/version-policy/{signal_id}` - Update policy
- `GET /api/v2/signals/version-policy/{signal_id}/versions` - List versions
- `POST /api/v2/signals/version-policy/{signal_id}/versions/{version}/publish` - Publish version
- `GET /api/v2/signals/version-policy/recommendations/{signal_id}` - Get recommendations

### 2. Version Policy Types

Authors can choose from three policy types:

**1. Locked Policy**
- Signal stays on a specific version
- No automatic updates
- Maximum stability and predictability
- Requires `pinned_version` parameter

**2. Auto Policy**
- Automatically upgrades to latest published version
- Gets newest features and improvements
- Default for most signal types
- Optional `min_version` constraint

**3. Range Policy**
- Stays within specified version range
- Balances stability with controlled updates
- Requires `min_version`, optional `max_version`
- Good for production environments

### 3. Schema Definitions

```python
class VersionPolicyRequest:
    signal_id: str
    policy: str  # locked, auto, or range
    min_version: Optional[str]
    max_version: Optional[str]
    pinned_version: Optional[str]

class VersionPolicyResponse:
    signal_id: str
    policy: str
    current_version: str
    effective_version: str
    auto_upgrade_enabled: bool
```

### 4. Intelligent Recommendations

The system provides policy recommendations based on:
- **Subscriber Count**: High count → conservative policy
- **Risk Level**: High risk → locked policy
- **Signal Type**: Different defaults per type
- **Breaking Changes**: Recent breaking changes → locked/range

**Recommendation Logic:**
```
Subscribers > 100 → Range (prevent disruption)
Subscribers 10-100 + High Risk → Range
Subscribers 10-100 + Low Risk → Auto
Subscribers < 10 + High Risk → Locked
Subscribers < 10 + Low Risk → Auto
```

### 5. Integration with Marketplace

The implementation integrates with the marketplace service:
- Fetches signal metadata and ownership
- Updates version policies via marketplace API
- Retrieves version history
- Publishes new versions

## Usage Examples

### Setting Locked Policy
```bash
PUT /api/v2/signals/version-policy/signal-123
{
    "policy": "locked",
    "pinned_version": "1.2.0"
}
```

### Setting Range Policy
```bash
PUT /api/v2/signals/version-policy/signal-123
{
    "policy": "range",
    "min_version": "1.0.0",
    "max_version": "2.0.0"
}
```

### Publishing with Breaking Changes
```bash
POST /api/v2/signals/version-policy/signal-123/versions/2.0.0/publish?breaking_changes=true
```

### Getting Recommendations
```bash
GET /api/v2/signals/version-policy/recommendations/signal-123

Response:
{
    "recommended_policy": "range",
    "reason": "Moderate subscribers - balance stability with updates",
    "factors_considered": {
        "risk_level": "medium",
        "subscriber_count": 25,
        "signal_type": "signal"
    }
}
```

## Architecture

```
Signal Author
      │
      ▼
Version Policy API
      │
      ├─► Get/Set Policy
      │   └─► Marketplace Service
      │       └─► Store in Product Metadata
      │
      ├─► List Versions
      │   └─► Marketplace Version History
      │
      └─► Get Recommendations
          └─► Analyze Factors
              ├─► Subscriber Count
              ├─► Risk Level
              └─► Breaking Changes
```

## Security

1. **Ownership Verification**: Only signal authors can modify policies
2. **Authentication**: Uses gateway authentication headers
3. **Authorization**: Checks creator_id matches user_id
4. **Audit Trail**: All policy changes are logged

## Benefits

1. **Author Control**: Signal authors decide update behavior
2. **Subscriber Protection**: Prevents unexpected breaking changes
3. **Flexibility**: Three policy types for different needs
4. **Intelligence**: Smart recommendations based on context
5. **Transparency**: Clear version history and status

## Testing

Comprehensive test suite in `test_signal_version_policy.py`:
- ✅ Get current version policy
- ✅ Authorization checks (only owners)
- ✅ Update to different policy types
- ✅ Policy validation rules
- ✅ List signal versions
- ✅ Publish new versions
- ✅ Get intelligent recommendations
- ✅ Risk-based recommendations

## SDK Integration

Signal authors can manage version policies through the SDK:

```python
# Get current policy
policy = await sdk.signals.get_version_policy("signal-123")

# Set locked policy
await sdk.signals.set_version_policy(
    "signal-123",
    policy="locked",
    pinned_version="1.2.0"
)

# Publish new version
await sdk.signals.publish_version(
    "signal-123",
    version="2.0.0",
    breaking_changes=True
)
```

## Next Steps

- Item 7: Add receive_email support in SDK
- Add version policy to signal creation flow
- Create UI for version management
- Add webhook notifications for version changes
- Implement automatic rollback on errors