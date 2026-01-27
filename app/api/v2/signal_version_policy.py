"""
Signal Version Policy API

Sprint 5A: Expose author-controlled version policy for signals.
Allows signal authors to control versioning and upgrade behavior.
"""
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_from_gateway
from app.core.logging import log_error, log_info
from app.services.marketplace_client import create_marketplace_client

router = APIRouter(prefix="/api/v2/signals/version-policy", tags=["signal-version-policy"])


class VersionPolicyRequest(BaseModel):
    """Request to set version policy for a signal."""
    signal_id: str = Field(..., description="Signal script ID")
    policy: str = Field(..., description="Version policy: locked, auto, or range")
    min_version: str | None = Field(None, description="Minimum version for range policy")
    max_version: str | None = Field(None, description="Maximum version for range policy")
    pinned_version: str | None = Field(None, description="Specific version for locked policy")


class VersionPolicyResponse(BaseModel):
    """Response with version policy details."""
    signal_id: str
    policy: str
    current_version: str
    effective_version: str
    min_version: str | None = None
    max_version: str | None = None
    pinned_version: str | None = None
    auto_upgrade_enabled: bool
    last_updated: str | None = None


class SignalVersionInfo(BaseModel):
    """Information about a signal version."""
    version: str
    status: str  # draft, published, deprecated
    created_at: str
    description: str | None = None
    breaking_changes: bool = False
    min_compatible_version: str | None = None


@router.get("/{signal_id}")
async def get_signal_version_policy(
    signal_id: str,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> VersionPolicyResponse:
    """
    Get version policy for a signal.

    Returns the current version policy settings including:
    - Policy type (locked, auto, range)
    - Version constraints
    - Effective version based on policy
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))

        # Get signal info from marketplace (signals are products)
        marketplace_client = create_marketplace_client()

        # Fetch signal product info
        signal_product = await marketplace_client.get_product_definition(
            product_id=signal_id,
            user_id=user_id
        )

        if not signal_product:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Check ownership
        if signal_product.get("creator_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this signal's policy")

        # Extract version policy info
        version_info = signal_product.get("version_info", {})
        policy = version_info.get("policy", "auto")
        current_version = version_info.get("current_version", "1.0.0")
        effective_version = version_info.get("effective_version", current_version)

        return VersionPolicyResponse(
            signal_id=signal_id,
            policy=policy,
            current_version=current_version,
            effective_version=effective_version,
            min_version=version_info.get("min_version"),
            max_version=version_info.get("max_version"),
            pinned_version=version_info.get("pinned_version"),
            auto_upgrade_enabled=(policy == "auto"),
            last_updated=version_info.get("last_updated")
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error getting signal version policy: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{signal_id}")
async def update_signal_version_policy(
    signal_id: str,
    request: VersionPolicyRequest,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> VersionPolicyResponse:
    """
    Update version policy for a signal.

    Allows signal authors to control:
    - How their signal versions are managed (locked/auto/range)
    - Version constraints for range-based policies
    - Specific version pinning for locked policies
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))

        log_info(f"Updating version policy for signal {signal_id}: {request.policy}")

        # Validate policy
        if request.policy not in ["locked", "auto", "range"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid policy. Must be: locked, auto, or range"
            )

        # Validate policy-specific requirements
        if request.policy == "locked" and not request.pinned_version:
            raise HTTPException(
                status_code=400,
                detail="Locked policy requires pinned_version"
            )

        if request.policy == "range" and not request.min_version:
            raise HTTPException(
                status_code=400,
                detail="Range policy requires at least min_version"
            )

        # Update via marketplace service
        marketplace_client = create_marketplace_client()

        # First verify ownership
        signal_product = await marketplace_client.get_product_definition(
            product_id=signal_id,
            user_id=user_id
        )

        if not signal_product or signal_product.get("creator_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this signal")

        # Update version policy
        update_data = {
            "version_policy": request.policy,
            "min_version": request.min_version,
            "max_version": request.max_version,
            "pinned_version": request.pinned_version
        }

        # Call marketplace API to update
        async with marketplace_client._get_client() as client:
            response = await client.put(
                f"/api/v1/products/{signal_id}/version-policy",
                json=update_data,
                headers={
                    "X-User-ID": user_id,
                    "X-Gateway-Secret": x_gateway_secret or ""
                }
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to update version policy: {response.text}"
                )

            result = response.json()

        # Return updated policy
        return VersionPolicyResponse(
            signal_id=signal_id,
            policy=result.get("policy", request.policy),
            current_version=result.get("current_version", "1.0.0"),
            effective_version=result.get("effective_version", "1.0.0"),
            min_version=result.get("min_version"),
            max_version=result.get("max_version"),
            pinned_version=result.get("pinned_version"),
            auto_upgrade_enabled=(result.get("policy") == "auto"),
            last_updated=result.get("last_updated")
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error updating signal version policy: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{signal_id}/versions")
async def list_signal_versions(
    signal_id: str,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> list[SignalVersionInfo]:
    """
    list all versions of a signal.

    Returns version history including:
    - Version numbers
    - Status (draft, published, deprecated)
    - Breaking change indicators
    - Compatibility information
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))

        # Get versions from marketplace
        marketplace_client = create_marketplace_client()

        async with marketplace_client._get_client() as client:
            response = await client.get(
                f"/api/v1/products/{signal_id}/versions",
                headers={
                    "X-User-ID": user_id,
                    "X-Gateway-Secret": x_gateway_secret or ""
                }
            )

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Signal not found")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to fetch versions: {response.text}"
                )

            versions_data = response.json()

        # Transform to our schema
        versions = []
        for v in versions_data.get("versions", []):
            versions.append(SignalVersionInfo(
                version=v.get("version"),
                status=v.get("status", "draft"),
                created_at=v.get("created_at"),
                description=v.get("description"),
                breaking_changes=v.get("breaking_changes", False),
                min_compatible_version=v.get("min_compatible_version")
            ))

        return versions

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error listing signal versions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{signal_id}/versions/{version}/publish")
async def publish_signal_version(
    signal_id: str,
    version: str,
    breaking_changes: bool = False,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> SignalVersionInfo:
    """
    Publish a signal version.

    Marks a version as published and available for use.
    Authors can indicate if there are breaking changes.
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))

        log_info(f"Publishing signal {signal_id} version {version}")

        # Publish via marketplace
        marketplace_client = create_marketplace_client()

        async with marketplace_client._get_client() as client:
            response = await client.post(
                f"/api/v1/products/{signal_id}/versions/{version}/publish",
                json={"breaking_changes": breaking_changes},
                headers={
                    "X-User-ID": user_id,
                    "X-Gateway-Secret": x_gateway_secret or ""
                }
            )

            if response.status_code == 403:
                raise HTTPException(status_code=403, detail="Not authorized to publish this signal")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to publish version: {response.text}"
                )

            version_data = response.json()

        return SignalVersionInfo(
            version=version_data.get("version"),
            status="published",
            created_at=version_data.get("created_at"),
            description=version_data.get("description"),
            breaking_changes=breaking_changes,
            min_compatible_version=version_data.get("min_compatible_version")
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error publishing signal version: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/recommendations/{signal_id}")
async def get_version_policy_recommendations(
    signal_id: str,
    subscriber_count: int | None = None,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> dict[str, Any]:
    """
    Get recommended version policy for a signal.

    Provides intelligent recommendations based on:
    - Signal type and risk level
    - Number of subscribers
    - Breaking changes in recent versions
    - Industry best practices
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))

        # Get signal info
        marketplace_client = create_marketplace_client()
        signal_product = await marketplace_client.get_product_definition(
            product_id=signal_id,
            user_id=user_id
        )

        if not signal_product:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Determine recommendations
        risk_level = signal_product.get("risk_level", "medium")
        actual_subscriber_count = subscriber_count or signal_product.get("subscriber_count", 0)

        # High subscriber count suggests more conservative policy
        if actual_subscriber_count > 100:
            recommended_policy = "range"
            reason = "High subscriber count - range policy prevents breaking changes"
        elif actual_subscriber_count > 10:
            recommended_policy = "range" if risk_level != "low" else "auto"
            reason = "Moderate subscribers - balance stability with updates"
        else:
            # Few subscribers, can be more aggressive
            if risk_level == "high":
                recommended_policy = "locked"
                reason = "High risk signal - locked policy for predictability"
            elif risk_level == "medium":
                recommended_policy = "range"
                reason = "Medium risk - range policy for controlled updates"
            else:
                recommended_policy = "auto"
                reason = "Low risk signal - auto updates for latest improvements"

        return {
            "signal_id": signal_id,
            "recommended_policy": recommended_policy,
            "reason": reason,
            "factors_considered": {
                "risk_level": risk_level,
                "subscriber_count": actual_subscriber_count,
                "signal_type": signal_product.get("product_type", "signal")
            },
            "policy_descriptions": {
                "locked": "Stay on specific version - maximum stability",
                "auto": "Auto-upgrade to latest - get newest features",
                "range": "Stay within version range - balanced approach"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error getting policy recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
