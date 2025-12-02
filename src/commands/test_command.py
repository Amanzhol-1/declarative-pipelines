import subprocess
import re
from typing import Dict, Any, Optional
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.base_command import BaseCommand, CommandResult, print_command_result


class TestCommand(BaseCommand):
    """
    Run automated tests using various testing frameworks.

    Supported frameworks:
        - Maven/Gradle (Java/Kotlin - JUnit, TestNG)
        - pytest (Python)
        - Jest (JavaScript/TypeScript)
        - Go test (Go)

    Required parameters:
        test_framework: Testing framework name (maven, gradle, pytest, jest, gotest)
        project_path: Path to project directory

    Optional parameters:
        test_command: Custom test command (overrides default)
        test_pattern: Pattern for test files to run (e.g., **/Test*.java)
        coverage_enabled: Enable code coverage collection (default: false)
        coverage_threshold: Minimum coverage percentage required (default: 80)
        fail_fast: Stop on first test failure (default: false)
        parallel_execution: Run tests in parallel (default: false)
        test_arguments: Additional arguments for test framework
    """

    # Default test commands for each framework
    DEFAULT_TEST_COMMANDS = {
        'maven': 'mvn test',
        'gradle': './gradlew test',
        'pytest': 'pytest',
        'jest': 'npm test',
        'gotest': 'go test ./...'
    }

    def validate_parameters(self) -> None:
        """Validate required parameters are present."""
        self._require_parameters('test_framework', 'project_path')

        test_framework = self.parameters['test_framework']
        if test_framework not in self.DEFAULT_TEST_COMMANDS:
            raise ValueError(
                f"Unsupported test framework: {test_framework}. "
                f"Supported frameworks: {', '.join(self.DEFAULT_TEST_COMMANDS.keys())}"
            )

        project_path = Path(self.parameters['project_path'])
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")

    def execute(self) -> CommandResult:
        """Execute the test command."""
        test_framework = self.parameters['test_framework']
        project_path = Path(self.parameters['project_path'])

        # Prepare test command
        test_command = self._prepare_test_command()

        # Execute tests
        test_output = self._execute_tests(test_command, project_path)

        # Parse test results
        test_results = self._parse_test_results(test_framework, test_output)

        # Check coverage threshold if enabled
        coverage_check = self._check_coverage_threshold(test_results)

        # Determine overall success
        tests_passed = test_results['tests_failed'] == 0
        coverage_passed = coverage_check['passed'] if coverage_check else True
        overall_success = tests_passed and coverage_passed

        message = self._generate_result_message(test_results, coverage_check)

        return CommandResult(
            success=overall_success,
            message=message,
            output_data={
                'test_framework': test_framework,
                'project_path': str(project_path),
                'command_executed': test_command,
                'test_results': test_results,
                'coverage_check': coverage_check
            }
        )

    def _prepare_test_command(self) -> str:
        """
        Prepare the test command with all arguments.

        Returns:
            Complete test command string
        """
        # Use custom command if provided
        if 'test_command' in self.parameters:
            base_command = self.parameters['test_command']
        else:
            test_framework = self.parameters['test_framework']
            base_command = self.DEFAULT_TEST_COMMANDS[test_framework]

        # Handle coverage flag
        coverage_enabled = self._get_parameter('coverage_enabled', False)
        if coverage_enabled:
            if 'maven' in base_command:
                base_command = 'mvn test jacoco:report'
            elif 'gradle' in base_command:
                base_command += ' jacocoTestReport'
            elif 'pytest' in base_command:
                base_command += ' --cov --cov-report=term --cov-report=html'
            elif 'jest' in base_command:
                base_command += ' --coverage'

        # Handle fail_fast flag
        fail_fast = self._get_parameter('fail_fast', False)
        if fail_fast:
            if 'pytest' in base_command:
                base_command += ' -x'
            elif 'maven' in base_command:
                base_command += ' -DfailIfNoTests=false'

        # Handle parallel execution
        parallel_execution = self._get_parameter('parallel_execution', False)
        if parallel_execution:
            if 'pytest' in base_command:
                base_command += ' -n auto'
            elif 'maven' in base_command:
                base_command += ' -T 1C'
            elif 'jest' in base_command:
                base_command += ' --maxWorkers=50%'

        # Handle test pattern
        test_pattern = self._get_parameter('test_pattern')
        if test_pattern:
            if 'pytest' in base_command:
                base_command += f' -k "{test_pattern}"'
            elif 'maven' in base_command:
                base_command += f' -Dtest={test_pattern}'

        # Add custom arguments
        test_arguments = self._get_parameter('test_arguments', '')
        if test_arguments:
            base_command += f' {test_arguments}'

        return base_command

    def _execute_tests(self, test_command: str, project_path: Path) -> str:
        """
        Execute the test command.

        Args:
            test_command: Command to execute
            project_path: Directory to execute command in

        Returns:
            Combined stdout and stderr output

        Raises:
            RuntimeError: If tests fail (only in non-fail-fast mode)
        """
        process_result = subprocess.run(
            test_command,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        # Tests might fail, but we still want to parse results
        # So we don't raise immediately
        return process_result.stdout + process_result.stderr

    def _parse_test_results(self, test_framework: str, test_output: str) -> Dict[str, Any]:
        """
        Parse test results from output.

        Args:
            test_framework: Name of test framework used
            test_output: Raw test output

        Returns:
            Dictionary with parsed test results
        """
        results = {
            'tests_total': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'tests_skipped': 0,
            'coverage_percentage': None,
            'duration_seconds': None
        }

        # Maven/Gradle (JUnit/TestNG patterns)
        if test_framework in ['maven', 'gradle']:
            # Match: Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
            match = re.search(
                r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)',
                test_output
            )
            if match:
                tests_run, failures, errors, skipped = map(int, match.groups())
                results['tests_total'] = tests_run
                results['tests_failed'] = failures + errors
                results['tests_passed'] = tests_run - failures - errors - skipped
                results['tests_skipped'] = skipped

        # pytest patterns
        elif test_framework == 'pytest':
            # Match: 5 passed, 2 failed, 1 skipped
            passed_match = re.search(r'(\d+) passed', test_output)
            failed_match = re.search(r'(\d+) failed', test_output)
            skipped_match = re.search(r'(\d+) skipped', test_output)

            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            skipped = int(skipped_match.group(1)) if skipped_match else 0

            results['tests_passed'] = passed
            results['tests_failed'] = failed
            results['tests_skipped'] = skipped
            results['tests_total'] = passed + failed + skipped

            # Coverage: TOTAL ... 85%
            coverage_match = re.search(r'TOTAL.*?(\d+)%', test_output)
            if coverage_match:
                results['coverage_percentage'] = int(coverage_match.group(1))

        # Jest patterns
        elif test_framework == 'jest':
            # Match: Tests: 5 passed, 5 total
            match = re.search(r'Tests:\s+(\d+) passed.*?(\d+) total', test_output)
            if match:
                passed, total = map(int, match.groups())
                results['tests_passed'] = passed
                results['tests_total'] = total
                results['tests_failed'] = total - passed

            # Coverage: All files | 85.5 | 80.3 | 90.1 | 85.5
            coverage_match = re.search(r'All files\s+\|\s+([\d.]+)', test_output)
            if coverage_match:
                results['coverage_percentage'] = float(coverage_match.group(1))

        # Go test patterns
        elif test_framework == 'gotest':
            # Match: PASS or FAIL
            if 'PASS' in test_output:
                # Count ok lines
                ok_count = test_output.count('\tok\t')
                results['tests_passed'] = ok_count
                results['tests_total'] = ok_count
            elif 'FAIL' in test_output:
                results['tests_failed'] = 1
                results['tests_total'] = 1

        return results

    def _check_coverage_threshold(
            self,
            test_results: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if coverage meets threshold.

        Args:
            test_results: Parsed test results

        Returns:
            Coverage check results or None if not enabled
        """
        coverage_enabled = self._get_parameter('coverage_enabled', False)
        if not coverage_enabled:
            return None

        coverage_threshold = self._get_parameter('coverage_threshold', 80)
        coverage_percentage = test_results.get('coverage_percentage')

        if coverage_percentage is None:
            return {
                'enabled': True,
                'passed': True,
                'threshold': coverage_threshold,
                'actual': None,
                'message': 'Coverage data not available'
            }

        passed = coverage_percentage >= coverage_threshold

        return {
            'enabled': True,
            'passed': passed,
            'threshold': coverage_threshold,
            'actual': coverage_percentage,
            'message': (
                f'Coverage {coverage_percentage}% meets threshold {coverage_threshold}%'
                if passed else
                f'Coverage {coverage_percentage}% below threshold {coverage_threshold}%'
            )
        }

    def _generate_result_message(
            self,
            test_results: Dict[str, Any],
            coverage_check: Optional[Dict[str, Any]]
    ) -> str:
        """
        Generate human-readable result message.

        Args:
            test_results: Parsed test results
            coverage_check: Coverage check results

        Returns:
            Result message string
        """
        total = test_results['tests_total']
        passed = test_results['tests_passed']
        failed = test_results['tests_failed']
        skipped = test_results['tests_skipped']

        message = f"Tests completed: {passed}/{total} passed"

        if failed > 0:
            message += f", {failed} failed"
        if skipped > 0:
            message += f", {skipped} skipped"

        if coverage_check and coverage_check['actual'] is not None:
            message += f" | Coverage: {coverage_check['actual']}%"

        return message


def main():
    """Main entry point for CLI usage."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Run tests using various testing frameworks'
    )
    parser.add_argument(
        '--params',
        type=str,
        required=True,
        help='JSON string with command parameters'
    )
    parser.add_argument(
        '--format',
        type=str,
        default='json',
        choices=['json', 'text'],
        help='Output format'
    )

    args = parser.parse_args()
    parameters = json.loads(args.params)

    command = TestCommand(parameters)
    result = command.run()
    print_command_result(result, args.format)

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()