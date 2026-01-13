# Signal Watermarking Implementation

## Overview

This document describes the implementation of marketplace signal watermarking with anti-retransmission enforcement in the signal service.

## Items Completed

### 1. Wire Subscription Metadata for Watermarking

**Changes Made:**
- Modified `signal_service/app/api/v2/sdk_signals.py` to capture subscription metadata when marketplace subscriptions are created
- Added caching of marketplace metadata (subscription_id, product_id, signal_id) keyed by connection token
- Updated WebSocket connection handler to retrieve cached metadata and store in connection_metadata
- Modified broadcast_to_subscription to pass stream-specific metadata to watermark service

**Key Code Locations:**
- `sdk_signals.py:142-192` - Capture subscription_id from marketplace response
- `sdk_signals.py:205-226` - Cache metadata with connection token
- `sdk_signals.py:278-298` - Retrieve metadata on WebSocket connection
- `websocket.py:312-327` - Pass metadata to watermark_signal()

### 2. Enforce Anti-Retransmission Blocking

**Changes Made:**
- Updated `broadcast_to_subscription()` in `websocket.py` to block signal delivery when leaks are detected
- Added enforcement policy checking (auto-enforce vs audit-only)
- Implemented should_block flag handling
- Modified watermark service to set should_block=True for auto-enforce mode
- Added comprehensive logging for blocked deliveries

**Key Code Locations:**
- `websocket.py:336-361` - Enforcement logic with blocking
- `watermark_integration.py:352` - Set should_block flag
- Log blocked deliveries with original owner info

## Architecture

```
SDK Signal Subscribe
        │
        ▼
  Store metadata in cache
  (subscription_id, product_id)
        │
        ▼
  WebSocket Connection
  (retrieve metadata)
        │
        ▼
  Signal Broadcast
        │
        ├─► Watermark Signal
        │   (with subscription_id)
        │
        └─► Detect Leak
            │
            ├─► No Leak → Deliver
            │
            └─► Leak Detected
                │
                ├─► auto-enforce → BLOCK
                │
                └─► audit-only → Deliver + Log
```

## Testing

### Unit Tests Created:
1. `test_subscription_metadata_watermarking.py` - Verifies metadata is captured and passed correctly
2. `test_leak_blocking.py` - Verifies leak detection blocks delivery

### Test Coverage:
- ✅ Marketplace subscriptions include subscription_id in metadata
- ✅ WebSocket connections retrieve cached metadata
- ✅ Watermark service receives correct metadata
- ✅ Leaked signals are blocked with auto-enforce policy
- ✅ Audit-only policy still delivers but logs
- ✅ Non-marketplace signals are never blocked
- ✅ Service failures fail-open for availability

## Configuration

### Environment Variables:
- `WATERMARK_ENFORCEMENT_ENABLED` - Enable/disable watermarking (default: true)
- `WATERMARK_ENFORCEMENT_POLICY` - Set to "auto-enforce" or "audit-only" (default: auto-enforce)
- `WATERMARK_SECRET` - Secret for watermark generation

### Config Service Keys:
- `WATERMARK_SECRET` - Required for marketplace watermarking
- `WATERMARK_ENFORCEMENT_ENABLED` - Enable flag
- `WATERMARK_ENFORCEMENT_POLICY` - Policy setting

## Security Considerations

1. **Fail-Open Design**: If watermarking service fails, signals are delivered to maintain availability
2. **Marketplace Only**: Only marketplace signals are watermarked and checked for leaks
3. **Multi-User Protection**: Each user receives uniquely watermarked signals
4. **Audit Trail**: All leak detections are logged with violation IDs

## Production Deployment

1. Set `WATERMARK_ENFORCEMENT_POLICY=auto-enforce` in production
2. Monitor logs for "BLOCKED signal delivery" messages
3. Review violation reports from marketplace service
4. Consider rate limiting for repeat violators

## Next Steps

- Implement signal script execution from MinIO (Item 3)
- Make SDK signal listing real (Item 4)
- Add violation reporting dashboard
- Consider caching watermark results for performance