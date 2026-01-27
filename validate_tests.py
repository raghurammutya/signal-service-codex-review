#!/usr/bin/env python3
"""
Test validation script for Signal Service
Validates test coverage and completeness
"""
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


class TestValidator:
    """Validates test coverage and quality"""

    def __init__(self, service_root):
        self.service_root = Path(service_root)
        self.app_dir = self.service_root / "app"
        self.tests_dir = self.service_root / "tests"

    def get_python_files(self, directory):
        """Get all Python files in directory"""
        return list(directory.rglob("*.py"))

    def parse_python_file(self, file_path):
        """Parse Python file and extract classes and functions"""
        try:
            with open(file_path) as f:
                content = f.read()

            # Count test methods directly from content
            test_methods = []
            lines = content.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("def test_", "async def test_")):
                    # Extract method name
                    method_name = stripped.split('(')[0].replace('def ', '').replace('async def ', '')
                    test_methods.append(method_name)

            # Also parse AST for classes
            try:
                tree = ast.parse(content)
                classes = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                return classes, test_methods
            except Exception:
                return [], test_methods

        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return [], []

    def validate_test_structure(self):
        """Validate test directory structure"""
        print("🔍 Validating test structure...")

        required_dirs = [
            self.tests_dir / "unit",
            self.tests_dir / "integration",
            self.tests_dir / "performance",
            self.tests_dir / "e2e"
        ]

        missing_dirs = []
        for dir_path in required_dirs:
            if not dir_path.exists():
                missing_dirs.append(str(dir_path))

        if missing_dirs:
            print(f"❌ Missing test directories: {missing_dirs}")
            return False

        print("✅ Test directory structure is complete")
        return True

    def validate_test_files(self):
        """Validate test files exist for core components"""
        print("\n🔍 Validating test file coverage...")

        # Core components that must have tests

        # Expected test files
        expected_tests = [
            "tests/unit/test_moneyness_calculator.py",
            "tests/unit/test_market_profile_calculator.py",
            "tests/unit/test_frequency_feed_manager.py",
            "tests/unit/test_scaling_components.py",
            "tests/integration/test_service_integrations.py",
            "tests/performance/test_load_performance.py",
            "tests/e2e/test_complete_workflows.py"
        ]

        missing_tests = []
        for test_file in expected_tests:
            if not (self.service_root / test_file).exists():
                missing_tests.append(test_file)

        if missing_tests:
            print(f"❌ Missing test files: {missing_tests}")
            return False

        print("✅ All required test files exist")
        return True

    def validate_test_content(self):
        """Validate test content and coverage"""
        print("\n🔍 Validating test content...")

        test_files = self.get_python_files(self.tests_dir)
        test_stats = {
            'total_test_files': len(test_files),
            'total_test_classes': 0,
            'total_test_methods': 0,
            'test_types': defaultdict(int)
        }

        for test_file in test_files:
            classes, functions = self.parse_python_file(test_file)

            # Count test classes and methods
            test_classes = [c for c in classes if c.startswith('Test')]
            test_methods = [f for f in functions if f.startswith('test_')]

            test_stats['total_test_classes'] += len(test_classes)
            test_stats['total_test_methods'] += len(test_methods)

            # Categorize tests by directory
            test_file_str = str(test_file)
            if '/unit/' in test_file_str:
                test_stats['test_types']['unit'] += len(test_methods)
            elif '/integration/' in test_file_str:
                test_stats['test_types']['integration'] += len(test_methods)
            elif '/performance/' in test_file_str:
                test_stats['test_types']['performance'] += len(test_methods)
            elif '/e2e/' in test_file_str:
                test_stats['test_types']['e2e'] += len(test_methods)

        print("📊 Test Statistics:")
        print(f"   Total test files: {test_stats['total_test_files']}")
        print(f"   Total test classes: {test_stats['total_test_classes']}")
        print(f"   Total test methods: {test_stats['total_test_methods']}")
        print(f"   Unit tests: {test_stats['test_types']['unit']}")
        print(f"   Integration tests: {test_stats['test_types']['integration']}")
        print(f"   Performance tests: {test_stats['test_types']['performance']}")
        print(f"   E2E tests: {test_stats['test_types']['e2e']}")

        # Use actual counts from grep since parsing might miss some
        import subprocess

        # Get actual counts using grep
        try:
            total_count = int(subprocess.check_output(['grep', '-r', 'def test_', 'tests/'], cwd=self.service_root).decode().count('\n'))
            unit_count = int(subprocess.check_output(['grep', '-r', 'def test_', 'tests/unit/'], cwd=self.service_root).decode().count('\n'))
            integration_count = int(subprocess.check_output(['grep', '-r', 'def test_', 'tests/integration/'], cwd=self.service_root).decode().count('\n'))
            performance_count = int(subprocess.check_output(['grep', '-r', 'def test_', 'tests/performance/'], cwd=self.service_root).decode().count('\n'))
            e2e_count = int(subprocess.check_output(['grep', '-r', 'def test_', 'tests/e2e/'], cwd=self.service_root).decode().count('\n'))

            print("📊 Actual Test Counts (via grep):")
            print(f"   Total test methods: {total_count}")
            print(f"   Unit tests: {unit_count}")
            print(f"   Integration tests: {integration_count}")
            print(f"   Performance tests: {performance_count}")
            print(f"   E2E tests: {e2e_count}")

            # Use actual counts for validation
            test_stats['total_test_methods'] = total_count
            test_stats['test_types']['unit'] = unit_count
            test_stats['test_types']['integration'] = integration_count
            test_stats['test_types']['performance'] = performance_count
            test_stats['test_types']['e2e'] = e2e_count

        except Exception as e:
            print(f"Warning: Could not get actual counts via grep: {e}")

        # Minimum requirements
        min_requirements = {
            'total_test_methods': 50,
            'unit': 20,
            'integration': 10,
            'performance': 5,
            'e2e': 10
        }

        validation_passed = True

        if test_stats['total_test_methods'] < min_requirements['total_test_methods']:
            print(f"❌ Insufficient total test methods: {test_stats['total_test_methods']} < {min_requirements['total_test_methods']}")
            validation_passed = False

        for test_type, min_count in min_requirements.items():
            if test_type == 'total_test_methods':
                continue

            actual_count = test_stats['test_types'][test_type]
            if actual_count < min_count:
                print(f"❌ Insufficient {test_type} tests: {actual_count} < {min_count}")
                validation_passed = False

        if validation_passed:
            print("✅ Test content validation passed")

        return validation_passed

    def validate_test_configuration(self):
        """Validate test configuration files"""
        print("\n🔍 Validating test configuration...")

        required_files = [
            "pytest.ini",
            "conftest.py",
            "docker-compose.test.yml",
            "tests/requirements.txt"
        ]

        missing_files = []
        for file_name in required_files:
            if not (self.service_root / file_name).exists():
                missing_files.append(file_name)

        if missing_files:
            print(f"❌ Missing configuration files: {missing_files}")
            return False

        # Validate pytest.ini content
        pytest_ini = self.service_root / "pytest.ini"
        with open(pytest_ini) as f:
            content = f.read()

        required_sections = ['testpaths', 'python_files', 'addopts', 'markers']
        missing_sections = []

        for section in required_sections:
            if section not in content:
                missing_sections.append(section)

        if missing_sections:
            print(f"❌ Missing pytest.ini sections: {missing_sections}")
            return False

        print("✅ Test configuration validation passed")
        return True

    def validate_test_markers(self):
        """Validate test markers are properly used"""
        print("\n🔍 Validating test markers...")

        test_files = self.get_python_files(self.tests_dir)
        marker_usage = defaultdict(int)

        for test_file in test_files:
            try:
                with open(test_file) as f:
                    content = f.read()

                # Count marker usage
                markers = ['unit', 'integration', 'performance', 'e2e', 'slow', 'redis', 'postgres']
                for marker in markers:
                    if f'@pytest.mark.{marker}' in content:
                        marker_usage[marker] += content.count(f'@pytest.mark.{marker}')

            except Exception as e:
                print(f"Error reading {test_file}: {e}")

        print("📊 Marker Usage:")
        for marker, count in marker_usage.items():
            print(f"   @pytest.mark.{marker}: {count}")

        # Ensure critical markers are used
        required_markers = ['unit', 'integration', 'performance', 'e2e']
        missing_markers = []

        for marker in required_markers:
            if marker_usage[marker] == 0:
                missing_markers.append(marker)

        if missing_markers:
            print(f"❌ Missing marker usage: {missing_markers}")
            return False

        print("✅ Test marker validation passed")
        return True

    def validate_mock_setup(self):
        """Validate mock setup for external dependencies"""
        print("\n🔍 Validating mock setup...")

        # Check for mock files
        mock_files = [
            "tests/mocks/instrument_service_responses.json"
        ]

        missing_mocks = []
        for mock_file in mock_files:
            if not (self.service_root / mock_file).exists():
                missing_mocks.append(mock_file)

        if missing_mocks:
            print(f"❌ Missing mock files: {missing_mocks}")
            return False

        # Validate conftest.py has proper mock fixtures
        conftest_path = self.service_root / "conftest.py"
        with open(conftest_path) as f:
            content = f.read()

        required_fixtures = [
            'mock_instrument_service',
            'mock_ticker_service',
            'mock_subscription_service',
            'sample_tick_data',
            'sample_greeks_data'
        ]

        missing_fixtures = []
        for fixture in required_fixtures:
            if f'def {fixture}' not in content:
                missing_fixtures.append(fixture)

        if missing_fixtures:
            print(f"❌ Missing conftest fixtures: {missing_fixtures}")
            return False

        print("✅ Mock setup validation passed")
        return True

    def generate_test_report(self):
        """Generate comprehensive test report"""
        print("\n📊 Generating test validation report...")

        report = {
            'timestamp': str(datetime.now()),
            'validation_results': {
                'test_structure': False,
                'test_files': False,
                'test_content': False,
                'test_configuration': False,
                'test_markers': False,
                'mock_setup': False
            },
            'overall_status': 'FAILED'
        }

        # Run all validations
        validations = [
            ('test_structure', self.validate_test_structure),
            ('test_files', self.validate_test_files),
            ('test_content', self.validate_test_content),
            ('test_configuration', self.validate_test_configuration),
            ('test_markers', self.validate_test_markers),
            ('mock_setup', self.validate_mock_setup)
        ]

        all_passed = True
        for name, validation_func in validations:
            try:
                result = validation_func()
                report['validation_results'][name] = result
                if not result:
                    all_passed = False
            except Exception as e:
                print(f"❌ Validation error for {name}: {e}")
                report['validation_results'][name] = False
                all_passed = False

        report['overall_status'] = 'PASSED' if all_passed else 'FAILED'

        # Save report
        report_file = self.service_root / "test_validation_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 Test validation report saved to: {report_file}")

        return all_passed

def main():
    """Main validation function"""
    service_root = Path(__file__).parent
    validator = TestValidator(service_root)

    print("🧪 Signal Service Test Validation")
    print("=" * 50)

    success = validator.generate_test_report()

    if success:
        print("\n✅ All test validations passed!")
        print("\n🚀 Test suite is ready for execution")
        print("\nTo run tests:")
        print("  ./run_tests.py --suite all")
        print("  ./run_tests.py --suite unit")
        print("  ./run_tests.py --coverage")
    else:
        print("\n❌ Test validation failed!")
        print("Please fix the issues above before running tests")
        sys.exit(1)

if __name__ == "__main__":
    from datetime import datetime
    main()
