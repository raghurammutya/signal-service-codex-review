#!/usr/bin/env python3
"""
Test script to verify that including the universal router in main.py provides the expected endpoints
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_router_inclusion():
    """Test that universal router endpoints are available when included"""
    print("🔍 Testing Universal Router Inclusion")
    print("=" * 50)
    
    # Create a test FastAPI app
    app = FastAPI()
    
    # Test without universal router
    print("1. Testing app WITHOUT universal router...")
    client = TestClient(app)
    
    # These endpoints should return 404
    universal_endpoints = [
        "/api/v2/universal/computations",
        "/api/v2/universal/health",
        "/api/v2/universal/validate"
    ]
    
    missing_endpoints = []
    for endpoint in universal_endpoints:
        response = client.get(endpoint)
        if response.status_code == 404:
            missing_endpoints.append(endpoint)
    
    print(f"   Missing endpoints: {len(missing_endpoints)}/{len(universal_endpoints)}")
    if len(missing_endpoints) == len(universal_endpoints):
        print("   ✅ Correct - universal endpoints not available without router")
    else:
        print("   ❌ Unexpected - some endpoints were available")
    
    # Test with universal router included
    print("\n2. Testing app WITH universal router...")
    
    try:
        # Import the universal router
        from app.api.v2.universal import router as universal_router
        
        # Include it in the app
        app.include_router(universal_router, prefix="/api/v2")
        
        # Create new client
        client = TestClient(app)
        
        # Now test the endpoints
        available_endpoints = []
        for endpoint in universal_endpoints:
            response = client.get(endpoint)
            # Even if they return errors, they should not return 404 if the router is included
            if response.status_code != 404:
                available_endpoints.append(endpoint)
        
        print(f"   Available endpoints: {len(available_endpoints)}/{len(universal_endpoints)}")
        if len(available_endpoints) == len(universal_endpoints):
            print("   ✅ Success - universal endpoints are now available with router!")
        else:
            print("   ❌ Some endpoints still missing")
            
        return len(available_endpoints) == len(universal_endpoints)
        
    except ImportError as e:
        print(f"   ❌ Could not import universal router: {e}")
        return False


def test_main_py_inclusion():
    """Test that the main.py file includes the universal router correctly"""
    print("\n3. Testing main.py router inclusion...")
    
    try:
        # Read the main.py file
        with open('app/main.py', 'r') as f:
            main_py_content = f.read()
        
        # Check for universal router import and inclusion
        has_import = 'from app.api.v2.universal import router as universal_router' in main_py_content
        has_include = 'app.include_router(universal_router, prefix="/api/v2")' in main_py_content
        has_log_message = '✓ Universal computation router included' in main_py_content
        
        print(f"   Universal router import: {'✅' if has_import else '❌'}")
        print(f"   Universal router include: {'✅' if has_include else '❌'}")
        print(f"   Log message: {'✅' if has_log_message else '❌'}")
        
        if has_import and has_include and has_log_message:
            print("   ✅ main.py correctly includes universal router")
            return True
        else:
            print("   ❌ main.py missing universal router inclusion")
            return False
            
    except Exception as e:
        print(f"   ❌ Error reading main.py: {e}")
        return False


def main():
    """Run all tests to verify the router inclusion fix"""
    print("🚀 Testing Universal Router Inclusion Fix")
    print("=" * 60)
    
    router_test_passed = test_router_inclusion()
    main_py_test_passed = test_main_py_inclusion()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS:")
    print(f"Router functionality test: {'PASS' if router_test_passed else 'FAIL'}")
    print(f"main.py inclusion test: {'PASS' if main_py_test_passed else 'FAIL'}")
    
    if router_test_passed and main_py_test_passed:
        print("\n✅ CONCLUSION: Universal router inclusion is working correctly!")
        print("   The /api/v2/universal/* endpoints should now be available when the service runs")
    else:
        print("\n❌ CONCLUSION: There are issues with the universal router inclusion")
    
    return router_test_passed and main_py_test_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)