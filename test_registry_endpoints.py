#!/usr/bin/env python3
"""
Quick test of indicator registry endpoints to verify 277 indicators without ticker service
"""

import asyncio

import httpx


async def test_endpoints():
    """Test the specific endpoints that can show indicator registry status"""

    base_url = "http://localhost:8003"

    print("🔍 Testing Signal Service Indicator Registry Endpoints")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # 1. Test service health
        print("1. Testing service health...")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("   ✅ Service is running")
            else:
                print(f"   ❌ Service health check failed: {response.status_code}")
                return
        except Exception as e:
            print(f"   ❌ Service not accessible: {e}")
            return

        # 2. Test available pandas_ta indicators
        print("\n2. Testing available pandas_ta indicators endpoint...")
        try:
            response = await client.get(f"{base_url}/api/v2/indicators/available-indicators")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    indicators = data.get("data", {})
                    print(f"   ✅ Found {len(indicators)} pandas_ta indicators")
                    print(f"   📋 Sample indicators: {list(indicators.keys())[:10]}")
                else:
                    print(f"   ❌ API error: {data.get('message')}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 3. Test universal computations
        print("\n3. Testing universal computations endpoint...")
        try:
            response = await client.get(f"{base_url}/api/v2/universal/computations")
            if response.status_code == 200:
                data = response.json()
                computations = data.get("computations", [])
                print(f"   ✅ Found {len(computations)} universal computations")
                print(f"   📋 Total from API: {data.get('total')}")
                if computations:
                    print(f"   📋 Sample types: {[comp['name'] for comp in computations[:5]]}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 4. Test universal health endpoint for registry info
        print("\n4. Testing universal computation engine health...")
        try:
            response = await client.get(f"{base_url}/api/v2/universal/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    capabilities = data.get("capabilities", {})
                    print("   ✅ Universal engine is healthy")
                    print(f"   📋 Total computations: {capabilities.get('total_computations')}")
                    print(f"   📋 Asset coverage: {capabilities.get('asset_coverage')}")
                    print(f"   📋 Supported assets: {capabilities.get('supported_assets', [])}")
                else:
                    print(f"   ❌ Engine status: {data.get('status')}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 5. Test cache stats
        print("\n5. Testing indicator cache statistics...")
        try:
            response = await client.get(f"{base_url}/api/v2/indicators/cache/stats")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    cache_stats = data.get("data", {})
                    print(f"   ✅ Cache stats available: {cache_stats}")
                else:
                    print(f"   ❌ API error: {data.get('message')}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 6. Test worker affinity status
        print("\n6. Testing worker affinity status...")
        try:
            response = await client.get(f"{base_url}/api/v2/indicators/worker-affinity/status")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    affinity_stats = data.get("data", {})
                    print(f"   ✅ Worker affinity available: {affinity_stats}")
                else:
                    print(f"   ❌ API error: {data.get('message')}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 7. Test validation endpoint (without execution)
        print("\n7. Testing computation validation (no execution)...")
        try:
            test_request = {
                "asset_type": "equity",
                "instrument_key": "TEST@SYMBOL@equity",
                "computations": [
                    {"type": "indicator", "params": {"indicator": "sma", "period": 20}},
                    {"type": "indicator", "params": {"indicator": "rsi", "period": 14}}
                ]
            }
            response = await client.post(
                f"{base_url}/api/v2/universal/validate",
                json=test_request
            )
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Validation successful: {data.get('valid')}")
                if not data.get('valid'):
                    print(f"   📋 Errors: {data.get('errors')}")
                else:
                    print(f"   📋 Validated {data.get('computations_validated')} computations")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # 8. Test examples endpoint
        print("\n8. Testing computation examples...")
        try:
            response = await client.get(f"{base_url}/api/v2/universal/examples/equity")
            if response.status_code == 200:
                data = response.json()
                examples = data.get("examples", [])
                print(f"   ✅ Found {len(examples)} computation examples")
                for example in examples:
                    print(f"   📋 {example.get('name')}")
            else:
                print(f"   ❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("🎯 SUMMARY:")
    print("These endpoints can verify indicator registry status WITHOUT requiring ticker service:")
    print("  • /api/v2/indicators/available-indicators - Shows pandas_ta indicators")
    print("  • /api/v2/universal/computations - Shows all registered computations")
    print("  • /api/v2/universal/health - Shows registry health and counts")
    print("  • /api/v2/universal/validate - Validates computations without execution")
    print("  • /api/v2/universal/examples/{asset_type} - Shows example requests")
    print("  • /api/v2/indicators/cache/stats - Shows cache statistics")
    print("  • /api/v2/indicators/worker-affinity/status - Shows worker status")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
