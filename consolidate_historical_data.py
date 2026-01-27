#!/usr/bin/env python3
"""
Consolidate Historical Data Services

Eliminates redundancy by consolidating historical data fetchers into single entry points.
"""
import os


class HistoricalDataConsolidator:
    """Consolidates duplicate historical data services."""

    def __init__(self):
        self.consolidation_plan = {
            "unified_service": "app/services/unified_historical_data_service.py",
            "files_to_consolidate": [
                "app/services/historical_data_manager_production.py",
                "app/clients/historical_data_client.py"
            ],
            "imports_to_update": []
        }

    def create_unified_historical_service(self):
        """Create unified historical data service."""
        print("🔧 Creating Unified Historical Data Service...")

        unified_content = '''"""
Unified Historical Data Service

Single entry point for all historical data operations, eliminating redundancy.
Consolidates functionality from historical_data_manager_production.py and historical_data_client.py.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import httpx
import pandas as pd
from contextlib import asynccontextmanager
from collections import defaultdict
import threading

from app.core.config import settings
from app.errors import DataAccessError
from app.utils.logging_utils import log_info, log_error, log_warning
from app.clients.ticker_service_client import get_ticker_service_client

logger = logging.getLogger(__name__)


class UnifiedHistoricalDataService:
    """
    Unified historical data service that provides single entry point for:
    - Indicator historical data (replacing historical_data_manager_production)
    - Timeframe/OHLCV data (replacing historical_data_client)
    - Moneyness-specific data
    - Cross-cutting concerns: caching, error handling, rate limiting
    """

    def __init__(self):
        self._cache = {}
        self._cache_locks = defaultdict(threading.Lock)
        self._ticker_client = None

    async def get_ticker_client(self):
        """Get ticker service client with lazy initialization."""
        if self._ticker_client is None:
            self._ticker_client = get_ticker_service_client()
        return self._ticker_client

    # === INDICATOR DATA METHODS (from historical_data_manager_production) ===

    async def get_historical_data_for_indicator(
        self,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """
        Get historical data optimized for indicator calculations.
        Replaces ProductionHistoricalDataManager.get_historical_data_for_indicator()
        """
        cache_key = f"indicator:{instrument_key}:{start_time}:{end_time}:{interval}"

        # Check cache first
        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                log_info(f"Cache hit for indicator data: {instrument_key}")
                return self._cache[cache_key]

        try:
            client = await self.get_ticker_client()
            data = await self._fetch_from_ticker_service(
                client, instrument_key, start_time, end_time, interval
            )

            # Cache the result
            with self._cache_locks[cache_key]:
                self._cache[cache_key] = data

            log_info(f"Fetched {len(data)} records for indicator {instrument_key}")
            return data

        except Exception as e:
            log_error(f"Failed to fetch indicator data for {instrument_key}: {e}")
            raise DataAccessError(f"Historical data fetch failed: {e}")

    # === TIMEFRAME DATA METHODS (from historical_data_client) ===

    async def get_historical_timeframe_data(
        self,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1m"
    ) -> List[Dict[str, Any]]:
        """
        Get OHLCV timeframe data.
        Replaces HistoricalDataClient.get_historical_timeframe_data()
        """
        cache_key = f"timeframe:{instrument_key}:{start_time}:{end_time}:{timeframe}"

        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                log_info(f"Cache hit for timeframe data: {instrument_key}")
                return self._cache[cache_key]

        try:
            client = await self.get_ticker_client()
            data = await self._fetch_ohlcv_data(
                client, instrument_key, start_time, end_time, timeframe
            )

            with self._cache_locks[cache_key]:
                self._cache[cache_key] = data

            return data

        except Exception as e:
            log_error(f"Failed to fetch timeframe data for {instrument_key}: {e}")
            raise DataAccessError(f"Timeframe data fetch failed: {e}")

    async def get_historical_moneyness_data(
        self,
        underlying: str,
        strike: float,
        expiry: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get moneyness-specific historical data.
        """
        cache_key = f"moneyness:{underlying}:{strike}:{expiry}:{start_time}:{end_time}"

        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            # Get underlying price data for moneyness calculations
            underlying_key = f"{underlying}@INDEX" if "@" not in underlying else underlying
            client = await self.get_ticker_client()

            data = await self._fetch_from_ticker_service(
                client, underlying_key, start_time, end_time, "1m"
            )

            # Enhance with moneyness calculations
            enhanced_data = self._calculate_moneyness_metrics(data, strike, expiry)

            with self._cache_locks[cache_key]:
                self._cache[cache_key] = enhanced_data

            return enhanced_data

        except Exception as e:
            log_error(f"Failed to fetch moneyness data for {underlying}: {e}")
            raise DataAccessError(f"Moneyness data fetch failed: {e}")

    # === CORE FETCHING METHODS ===

    async def _fetch_from_ticker_service(
        self,
        client,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ) -> List[Dict[str, Any]]:
        """Core ticker service fetching logic."""
        try:
            response = await client.get_historical_data(
                instrument_key=instrument_key,
                start_time=start_time,
                end_time=end_time,
                interval=interval
            )

            if response.get('success', False):
                return response.get('data', [])
            else:
                error_msg = response.get('error', 'Unknown error')
                raise DataAccessError(f"Ticker service error: {error_msg}")

        except httpx.HTTPError as e:
            raise DataAccessError(f"HTTP error fetching from ticker service: {e}")

    async def _fetch_ohlcv_data(
        self,
        client,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV data with specific formatting."""
        raw_data = await self._fetch_from_ticker_service(
            client, instrument_key, start_time, end_time, timeframe
        )

        # Ensure OHLCV format
        ohlcv_data = []
        for record in raw_data:
            ohlcv_data.append({
                'timestamp': record.get('timestamp'),
                'open': float(record.get('open', 0)),
                'high': float(record.get('high', 0)),
                'low': float(record.get('low', 0)),
                'close': float(record.get('close', 0)),
                'volume': int(record.get('volume', 0))
            })

        return ohlcv_data

    def _calculate_moneyness_metrics(
        self,
        price_data: List[Dict[str, Any]],
        strike: float,
        expiry: str
    ) -> List[Dict[str, Any]]:
        """Calculate moneyness metrics for historical data."""
        enhanced_data = []

        for record in price_data:
            current_price = float(record.get('close', 0))
            moneyness = current_price / strike if strike > 0 else 0

            enhanced_record = record.copy()
            enhanced_record.update({
                'strike': strike,
                'expiry': expiry,
                'moneyness': moneyness,
                'itm': moneyness > 1.0,  # In-the-money for calls
                'distance_from_strike': abs(current_price - strike)
            })

            enhanced_data.append(enhanced_record)

        return enhanced_data

    # === CACHE MANAGEMENT ===

    def clear_cache(self):
        """Clear the internal cache."""
        with threading.Lock():
            self._cache.clear()
            log_info("Historical data cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._cache),
            'cache_keys': list(self._cache.keys())
        }


# Global service instance
_unified_historical_service = None


def get_unified_historical_service() -> UnifiedHistoricalDataService:
    """Get the global unified historical data service instance."""
    global _unified_historical_service
    if _unified_historical_service is None:
        _unified_historical_service = UnifiedHistoricalDataService()
    return _unified_historical_service


# === BACKWARD COMPATIBILITY ALIASES ===

# For historical_data_manager_production.py compatibility
def get_production_historical_data_manager():
    """Backward compatibility alias."""
    return get_unified_historical_service()

class ProductionHistoricalDataManager:
    """Backward compatibility class."""
    def __init__(self):
        self._service = get_unified_historical_service()

    async def get_historical_data_for_indicator(self, *args, **kwargs):
        return await self._service.get_historical_data_for_indicator(*args, **kwargs)

# For historical_data_client.py compatibility
class HistoricalDataClient:
    """Backward compatibility class."""
    def __init__(self):
        self._service = get_unified_historical_service()

    async def get_historical_timeframe_data(self, *args, **kwargs):
        return await self._service.get_historical_timeframe_data(*args, **kwargs)

    async def get_historical_moneyness_data(self, *args, **kwargs):
        return await self._service.get_historical_moneyness_data(*args, **kwargs)
'''

        os.makedirs(os.path.dirname(self.consolidation_plan["unified_service"]), exist_ok=True)
        with open(self.consolidation_plan["unified_service"], 'w') as f:
            f.write(unified_content)

        print(f"    ✅ Created: {self.consolidation_plan['unified_service']}")
        return True

    def update_imports(self):
        """Update import statements to use unified service."""
        print("🔄 Updating Import Statements...")

        # Update files that import from historical_data_manager_production
        files_to_update = [
            ("tests/test_timeframe_integration.py",
             "from app.services.historical_data_manager_production import ProductionHistoricalDataManager as HistoricalDataManager",
             "from app.services.unified_historical_data_service import ProductionHistoricalDataManager as HistoricalDataManager"),

            ("app/services/pandas_ta_executor.py",
             "from app.services.historical_data_manager_production import get_production_historical_data_manager as get_historical_data_manager",
             "from app.services.unified_historical_data_service import get_production_historical_data_manager as get_historical_data_manager")
        ]

        updated_count = 0
        for file_path, old_import, new_import in files_to_update:
            if os.path.exists(file_path):
                try:
                    with open(file_path) as f:
                        content = f.read()

                    if old_import in content:
                        updated_content = content.replace(old_import, new_import)
                        with open(file_path, 'w') as f:
                            f.write(updated_content)
                        print(f"    ✅ Updated imports in: {file_path}")
                        updated_count += 1
                except Exception as e:
                    print(f"    ❌ Failed to update {file_path}: {e}")

        print(f"  📊 Updated {updated_count} files")
        return updated_count

    def create_lint_rule_for_ci(self):
        """Create lint rule to prevent future duplication."""
        print("📝 Creating Lint Rule for CI...")

        lint_rule_content = r'''#!/usr/bin/env python3
"""
Redundancy Prevention Lint Rule

Prevents duplicate historical data services and unused imports.
"""
import os
import re
from typing import List, Tuple


def check_historical_data_duplication() -> List[str]:
    """Check for duplicate historical data services."""
    violations = []

    # Patterns that should only exist in the unified service
    restricted_patterns = [
        (r'class.*HistoricalDataManager', "Multiple HistoricalDataManager classes found"),
        (r'def get_historical_data_for_indicator', "Multiple indicator data fetchers found"),
        (r'async def.*historical.*ticker', "Multiple ticker service integrations found")
    ]

    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith('.py') and file != 'unified_historical_data_service.py':
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()

                    for pattern, message in restricted_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            violations.append(f"{file_path}: {message}")
                except:
                    continue

    return violations


def check_unused_imports() -> List[str]:
    """Check for obvious unused imports."""
    violations = []

    # Simple patterns for obviously unused imports
    unused_patterns = [
        r'^import\s+(os|sys|json|re)\s*$',  # Common imports that might be unused
        r'^from\s+typing\s+import.*$'      # Typing imports often become unused
    ]

    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        lines = f.readlines()

                    for i, line in enumerate(lines):
                        for pattern in unused_patterns:
                            if re.match(pattern, line.strip()):
                                # Simple check: if import name doesn't appear later in file
                                import_match = re.search(r'import\s+(\w+)', line)
                                if import_match:
                                    import_name = import_match.group(1)
                                    file_content = ''.join(lines[i+1:])  # Skip the import line itself
                                    if import_name not in file_content:
                                        violations.append(f"{file_path}:{i+1}: Potentially unused import: {line.strip()}")
                except:
                    continue

    return violations


def main():
    """Run redundancy prevention checks."""
    print("🔍 Redundancy Prevention Lint Check")
    print("=" * 50)

    duplication_violations = check_historical_data_duplication()
    unused_import_violations = check_unused_imports()

    total_violations = len(duplication_violations) + len(unused_import_violations)

    if duplication_violations:
        print("❌ Historical Data Duplication Violations:")
        for violation in duplication_violations:
            print(f"  {violation}")
        print()

    if unused_import_violations:
        print("⚠️ Potential Unused Import Violations:")
        for violation in unused_import_violations[:10]:  # Show first 10
            print(f"  {violation}")
        if len(unused_import_violations) > 10:
            print(f"  ... and {len(unused_import_violations) - 10} more")
        print()

    if total_violations == 0:
        print("✅ No redundancy violations found")
        return 0
    else:
        print(f"❌ Found {total_violations} violations")
        return 1


if __name__ == "__main__":
    exit(main())
'''

        lint_file = "scripts/lint_redundancy_prevention.py"
        os.makedirs(os.path.dirname(lint_file), exist_ok=True)
        with open(lint_file, 'w') as f:
            f.write(lint_rule_content)

        # Make it executable
        os.chmod(lint_file, 0o755)

        print(f"    ✅ Created: {lint_file}")
        return lint_file

    def run_consolidation(self):
        """Run the complete consolidation process."""
        print("🔧 Historical Data Consolidation")
        print("=" * 60)

        steps_completed = 0

        # Step 1: Create unified service
        if self.create_unified_historical_service():
            steps_completed += 1
        print()

        # Step 2: Update imports
        if self.update_imports() > 0:
            steps_completed += 1
        print()

        # Step 3: Create lint rule
        if self.create_lint_rule_for_ci():
            steps_completed += 1
        print()

        print("=" * 60)
        print(f"🎯 Consolidation Complete: {steps_completed}/3 steps")

        if steps_completed >= 2:
            print("✅ Historical data consolidation successful")
            print("\n📋 Next Steps:")
            print("  1. Test the unified service with existing functionality")
            print("  2. Remove old files after validation:")
            for file_path in self.consolidation_plan["files_to_consolidate"]:
                print(f"     - {file_path}")
            print("  3. Add lint rule to CI pipeline")
            return True
        print("❌ Consolidation incomplete")
        return False


def main():
    """Run historical data consolidation."""
    consolidator = HistoricalDataConsolidator()
    success = consolidator.run_consolidation()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
