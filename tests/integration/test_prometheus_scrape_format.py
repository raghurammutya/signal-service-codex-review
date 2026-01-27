#!/usr/bin/env python3
"""
Prometheus Scrape Format Test

Validates that /api/v1/metrics endpoint produces parsable Prometheus format output.
"""
import re

import pytest
from fastapi.testclient import TestClient


class TestPrometheusScrapeFOrmat:
    """Test Prometheus metrics format compliance."""

    def test_metrics_endpoint_format(self):
        """Test that metrics endpoint returns valid Prometheus format."""
        try:
            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/metrics")

            # Should return 200 with text/plain
            assert response.status_code == 200
            content_type = response.headers.get("content-type", "")
            assert "text/plain" in content_type

            content = response.text

            # Validate Prometheus format patterns
            self._validate_prometheus_format(content)

        except ImportError:
            pytest.skip("Main app not available for testing")

    def test_metrics_content_validation(self):
        """Test specific metric content for signal service."""
        try:
            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/metrics")
            content = response.text

            # Check for expected signal service metrics
            expected_metrics = [
                "signal_service_requests_total",
                "signal_service_processing_duration_seconds",
                "signal_service_active_connections",
                "signal_service_errors_total"
            ]

            for metric in expected_metrics:
                assert metric in content, f"Missing expected metric: {metric}"

            # Validate metric values are numeric
            metric_lines = [line for line in content.split('\n')
                          if line and not line.startswith('#')]

            for line in metric_lines:
                if ' ' in line:
                    metric_name, value = line.rsplit(' ', 1)
                    try:
                        float(value)
                    except ValueError:
                        pytest.fail(f"Invalid metric value: {line}")

        except ImportError:
            pytest.skip("Main app not available for testing")

    def _validate_prometheus_format(self, content: str):
        """Validate Prometheus format compliance."""
        lines = content.split('\n')

        for line in lines:
            if not line.strip():
                continue

            if line.startswith('#'):
                # Validate comment format
                assert line.startswith('# HELP ') or line.startswith('# TYPE ')
                continue

            # Validate metric line format
            # Format: metric_name{labels} value [timestamp]
            metric_pattern = r'^[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})?\s+[0-9.+-eE]+(?:\s+[0-9]+)?$'
            assert re.match(metric_pattern, line), f"Invalid metric line: {line}"
