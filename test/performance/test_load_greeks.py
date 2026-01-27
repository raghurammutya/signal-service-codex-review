"""Load testing for Greeks calculation endpoints."""
import json
import random

from locust import HttpUser, between, task


class GreeksCalculationUser(HttpUser):
    """Load testing for Greeks calculation endpoints."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    def on_start(self):
        """Initialize test data."""
        self.test_instruments = [
            f"NSE@TESTSYM{i}@CE@{20000 + i*100}"
            for i in range(100)
        ]

        self.test_equities = [
            f"NSE@TESTSYM{i}" for i in range(50)
        ]

    @task(3)
    def calculate_greeks(self):
        """Test Greeks calculation under load."""
        instrument = random.choice(self.test_instruments)
        spot_price = random.uniform(19000, 21000)

        request_data = {
            "spot_price": spot_price,
            "options": [{
                "instrument_key": instrument,
                "strike_price": 20000,
                "option_type": random.choice(["call", "put"]),
                "expiry_date": "2024-12-28"
            }]
        }

        with self.client.post("/api/v2/greeks/calculate",
                             json=request_data,
                             catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed with status {response.status_code}")
            elif response.elapsed.total_seconds() > 5.0:
                response.failure("Response too slow (>5s)")
            else:
                try:
                    data = response.json()
                    if "options" not in data or not data["options"]:
                        response.failure("Invalid response structure")
                    elif "delta" not in data["options"][0]:
                        response.failure("Missing Greeks in response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")

    @task(2)
    def get_historical_data(self):
        """Test historical data retrieval under load."""
        instrument = random.choice(self.test_instruments)

        with self.client.get(f"/api/v2/signals/historical/greeks/{instrument}",
                           params={
                               "start_time": "2024-01-01T00:00:00Z",
                               "end_time": "2024-01-31T23:59:59Z",
                               "timeframe": random.choice(["1m", "5m", "15m"])
                           },
                           catch_response=True) as response:
            if response.status_code == 404:
                # Expected for some test instruments
                response.success()
            elif response.status_code != 200:
                response.failure(f"Failed with status {response.status_code}")
            elif response.elapsed.total_seconds() > 3.0:
                response.failure("Historical data too slow (>3s)")

    @task(2)
    def smart_money_calculation(self):
        """Test Smart Money indicators under load."""
        equity = random.choice(self.test_equities)

        # Generate random OHLCV data
        market_data = {
            "instrument_key": equity,
            "timeframe": random.choice(["5m", "15m", "1h"]),
            "ohlcv_data": []
        }

        base_price = random.uniform(19000, 21000)
        for i in range(50):  # 50 data points
            price = base_price * (1 + random.uniform(-0.02, 0.02))  # ±2% variation
            high = price * (1 + abs(random.uniform(0, 0.01)))
            low = price * (1 - abs(random.uniform(0, 0.01)))

            market_data["ohlcv_data"].append({
                "timestamp": f"2024-01-01T{9 + i//12:02d}:{(i*5)%60:02d}:00Z",
                "open": round(base_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(price, 2),
                "volume": random.randint(50000, 200000)
            })
            base_price = price

        with self.client.post("/api/v2/indicators/smart-money/calculate",
                             json=market_data,
                             catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed with status {response.status_code}")
            elif response.elapsed.total_seconds() > 10.0:
                response.failure("Smart Money calculation too slow (>10s)")
            else:
                try:
                    data = response.json()
                    expected_fields = ["break_of_structure", "order_blocks", "fair_value_gaps"]
                    for field in expected_fields:
                        if field not in data:
                            response.failure(f"Missing {field} in Smart Money response")
                            break
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")

    @task(1)
    def process_tick_data(self):
        """Test tick data processing under load."""
        instrument = random.choice(self.test_instruments + self.test_equities)

        tick_data = {
            "instrument_key": instrument,
            "last_price": random.uniform(100, 300),
            "bid": random.uniform(100, 300),
            "ask": random.uniform(100, 300),
            "volume": random.randint(1000, 50000),
            "timestamp": "2024-01-01T10:00:00Z"
        }

        with self.client.post("/api/v2/signals/process-tick",
                             json=tick_data,
                             catch_response=True) as response:
            if response.status_code not in [200, 201]:
                response.failure(f"Failed with status {response.status_code}")
            elif response.elapsed.total_seconds() > 1.0:
                response.failure("Tick processing too slow (>1s)")

class SystemLoadUser(HttpUser):
    """System-wide load testing."""

    wait_time = between(0.5, 2)

    @task(1)
    def health_check(self):
        """Regular health checks."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code not in [200, 503]:
                response.failure(f"Unexpected health status: {response.status_code}")
            elif response.elapsed.total_seconds() > 2.0:
                response.failure("Health check too slow")

    @task(1)
    def websocket_info(self):
        """Test WebSocket endpoint info."""
        with self.client.get("/api/v2/signals/subscriptions/websocket",
                           catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"WebSocket info failed: {response.status_code}")

class StressTestUser(HttpUser):
    """Stress testing with aggressive load."""

    wait_time = between(0.1, 0.5)  # Very short wait times

    @task(1)
    def aggressive_greeks_calculation(self):
        """Aggressive Greeks calculation load."""
        instruments = [f"NSE@STRESS{i}@CE@{20000 + i*50}" for i in range(10)]

        # Multiple options in single request
        request_data = {
            "spot_price": 20000,
            "options": [
                {
                    "instrument_key": random.choice(instruments),
                    "strike_price": 20000 + random.randint(-500, 500),
                    "option_type": random.choice(["call", "put"]),
                    "expiry_date": "2024-12-28"
                }
                for _ in range(5)  # 5 options per request
            ]
        }

        with self.client.post("/api/v2/greeks/calculate",
                             json=request_data,
                             catch_response=True) as response:
            if response.status_code != 200:
                if response.status_code == 503:
                    # Service unavailable under stress is acceptable
                    response.success()
                else:
                    response.failure(f"Stress test failed: {response.status_code}")
            elif response.elapsed.total_seconds() > 15.0:
                response.failure("Stress test too slow (>15s)")

# Custom load test scenarios
class MemoryIntensiveUser(HttpUser):
    """Test memory-intensive operations."""

    wait_time = between(5, 10)  # Longer waits for memory-intensive ops

    @task(1)
    def large_smart_money_calculation(self):
        """Test Smart Money with large dataset."""
        market_data = {
            "instrument_key": "NSE@MEMTEST",
            "timeframe": "1m",
            "ohlcv_data": []
        }

        # Large dataset (1000 data points)
        base_price = 20000
        for i in range(1000):
            price = base_price * (1 + random.uniform(-0.001, 0.001))
            market_data["ohlcv_data"].append({
                "timestamp": f"2024-01-01T{9 + i//60:02d}:{i%60:02d}:00Z",
                "open": round(base_price, 2),
                "high": round(price * 1.001, 2),
                "low": round(price * 0.999, 2),
                "close": round(price, 2),
                "volume": random.randint(10000, 100000)
            })
            base_price = price

        with self.client.post("/api/v2/indicators/smart-money/calculate",
                             json=market_data,
                             timeout=60,  # Longer timeout for large datasets
                             catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Memory test failed: {response.status_code}")
            elif response.elapsed.total_seconds() > 30.0:
                response.failure("Memory test too slow (>30s)")

# Load test execution configuration
if __name__ == "__main__":
    import subprocess
    import sys

    # Run different load test scenarios
    scenarios = [
        {
            "name": "Standard Load Test",
            "users": 50,
            "spawn_rate": 5,
            "run_time": "300s",
            "user_class": "GreeksCalculationUser"
        },
        {
            "name": "System Load Test",
            "users": 100,
            "spawn_rate": 10,
            "run_time": "180s",
            "user_class": "SystemLoadUser"
        },
        {
            "name": "Stress Test",
            "users": 200,
            "spawn_rate": 20,
            "run_time": "120s",
            "user_class": "StressTestUser"
        },
        {
            "name": "Memory Test",
            "users": 10,
            "spawn_rate": 1,
            "run_time": "300s",
            "user_class": "MemoryIntensiveUser"
        }
    ]

    host = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8003"

    for scenario in scenarios:
        print(f"\n{'='*50}")
        print(f"Running {scenario['name']}")
        print(f"{'='*50}")

        cmd = [
            "locust",
            "-f", __file__,
            "--host", host,
            "--headless",
            "--users", str(scenario["users"]),
            "--spawn-rate", str(scenario["spawn_rate"]),
            "--run-time", scenario["run_time"],
            "--html", f"performance-reports/{scenario['name'].lower().replace(' ', '-')}.html",
            "--csv", f"performance-reports/{scenario['name'].lower().replace(' ', '-')}",
            scenario["user_class"]
        ]

        try:
            subprocess.run(cmd, check=True)
            print(f"✅ {scenario['name']} completed successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ {scenario['name']} failed: {e}")
        except KeyboardInterrupt:
            print(f"⏹️  {scenario['name']} interrupted")
            break
