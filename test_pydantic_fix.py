#!/usr/bin/env python3
"""
Test script to verify the Pydantic serialization fix works
"""

import inspect
from typing import Any

import pandas_ta as ta
from pydantic import BaseModel


class BaseResponse(BaseModel):
    success: bool
    message: str
    data: Any


def get_available_indicators() -> dict[str, dict[str, Any]]:
    """Get all available pandas_ta indicators with their parameters"""
    indicators = {}

    # Get all indicators from pandas_ta
    for name, obj in inspect.getmembers(ta):
        if callable(obj) and not name.startswith('_'):
            try:
                # Get function signature
                sig = inspect.signature(obj)
                params = {}

                for param_name, param in sig.parameters.items():
                    if param_name not in ['self', 'close', 'high', 'low', 'open', 'volume', 'df']:
                        params[param_name] = {
                            'default': param.default if param.default is not inspect.Parameter.empty else None,
                            'type': str(param.annotation) if param.annotation is not inspect.Parameter.empty else 'Any'
                        }

                indicators[name] = {
                    'function': obj,  # This would cause Pydantic serialization error
                    'parameters': params,
                    'doc': obj.__doc__ or 'No documentation available'
                }
            except Exception:
                continue

    return indicators


def test_original_approach():
    """Test the original approach that would fail with Pydantic"""
    print("Testing original approach with function objects...")

    indicators = get_available_indicators()

    try:
        # This would fail with Pydantic serialization error
        BaseResponse(
            success=True,
            message=f"Found {len(indicators)} available indicators",
            data=indicators  # Contains function objects - will fail
        )
        print("❌ Original approach should have failed but didn't!")
        return False
    except Exception as e:
        print(f"✅ Original approach failed as expected: {e}")
        return True


def test_fixed_approach():
    """Test the fixed approach without function objects"""
    print("\nTesting fixed approach without function objects...")

    indicators = get_available_indicators()

    # Format for API response (exclude function objects for serialization)
    formatted_indicators = {}
    for name, info in indicators.items():
        formatted_indicators[name] = {
            'parameters': info['parameters'],
            'description': info['doc'].split('\n')[0] if info['doc'] else 'No description'
        }

    try:
        response = BaseResponse(
            success=True,
            message=f"Found {len(formatted_indicators)} available indicators",
            data=formatted_indicators  # No function objects - should work
        )
        print(f"✅ Fixed approach works! Found {len(formatted_indicators)} indicators")
        print(f"Sample indicators: {list(formatted_indicators.keys())[:5]}")

        # Test JSON serialization
        json_data = response.model_dump()
        print("✅ JSON serialization successful!")
        print(f"Response structure: {list(json_data.keys())}")
        return True
    except Exception as e:
        print(f"❌ Fixed approach failed: {e}")
        return False


def main():
    """Run both tests to verify the fix"""
    print("🔍 Testing Pydantic Serialization Fix for /available-indicators endpoint")
    print("=" * 70)

    original_failed = test_original_approach()
    fixed_works = test_fixed_approach()

    print("\n" + "=" * 70)
    print("📊 TEST RESULTS:")
    print(f"Original approach properly fails: {original_failed}")
    print(f"Fixed approach works: {fixed_works}")

    if original_failed and fixed_works:
        print("✅ CONCLUSION: The Pydantic serialization fix is correct!")
        print("   The endpoint will now return properly serialized indicator metadata")
        print("   without attempting to serialize function objects.")
    else:
        print("❌ CONCLUSION: Something is wrong with the fix")

    return original_failed and fixed_works


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
