import subprocess
import os
from typing import Dict, Any, List
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.base_command import BaseCommand, CommandResult, print_command_result


class BuildCommand(BaseCommand):
    """
    Build projects using various build tools.

    Supported build systems:
        - Maven (Java)
        - Gradle (Java/Kotlin)
        - npm (JavaScript/TypeScript)
        - pip (Python)
        - go build (Go)

    Required parameters:
        build_tool: Build tool name (maven, gradle, npm, pip, go)
        project_path: Path to project directory

    Optional parameters:
        build_command: Custom build command (overrides default)
        build_arguments: Additional arguments for build tool
        skip_tests: Skip running tests during build (default: false)
        clean_before_build: Clean before building (default: true)
        output_directory: Custom output directory for artifacts
    """

    # Default build commands for each tool
    DEFAULT_BUILD_COMMANDS = {
        'maven': 'mvn clean install',
        'gradle': './gradlew clean build',
        'npm': 'npm run build',
        'pip': 'pip install -e .',
        'go': 'go build -o ./bin/app'
    }

    def validate_parameters(self) -> None:
        """Validate required parameters are present."""
        self._require_parameters('build_tool', 'project_path')

        build_tool = self.parameters['build_tool']
        if build_tool not in self.DEFAULT_BUILD_COMMANDS:
            raise ValueError(
                f"Unsupported build tool: {build_tool}. "
                f"Supported tools: {', '.join(self.DEFAULT_BUILD_COMMANDS.keys())}"
            )

        project_path = Path(self.parameters['project_path'])
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")

    def execute(self) -> CommandResult:
        """Execute the build command."""
        build_tool = self.parameters['build_tool']
        project_path = Path(self.parameters['project_path'])

        # Prepare build command
        build_command = self._prepare_build_command()

        # Execute build
        build_output = self._execute_build(build_command, project_path)

        # Find build artifacts
        artifacts = self._find_build_artifacts(build_tool, project_path)

        return CommandResult(
            success=True,
            message=f"Build completed successfully using {build_tool}",
            output_data={
                'build_tool': build_tool,
                'project_path': str(project_path),
                'command_executed': build_command,
                'artifacts': artifacts,
                'build_output_lines': len(build_output.split('\n'))
            }
        )

    def _prepare_build_command(self) -> str:
        """
        Prepare the build command with all arguments.

        Returns:
            Complete build command string
        """
        # Use custom command if provided
        if 'build_command' in self.parameters:
            base_command = self.parameters['build_command']
        else:
            build_tool = self.parameters['build_tool']
            base_command = self.DEFAULT_BUILD_COMMANDS[build_tool]

        # Handle skip_tests flag
        skip_tests = self._get_parameter('skip_tests', False)
        if skip_tests:
            if 'maven' in base_command:
                base_command += ' -DskipTests'
            elif 'gradle' in base_command:
                base_command += ' -x test'

        # Handle clean flag
        clean_before_build = self._get_parameter('clean_before_build', True)
        if not clean_before_build:
            base_command = base_command.replace('clean ', '')

        # Add custom arguments
        build_arguments = self._get_parameter('build_arguments', '')
        if build_arguments:
            base_command += f' {build_arguments}'

        return base_command

    def _execute_build(self, build_command: str, project_path: Path) -> str:
        """
        Execute the build command.

        Args:
            build_command: Command to execute
            project_path: Directory to execute command in

        Returns:
            Combined stdout and stderr output

        Raises:
            RuntimeError: If build fails
        """
        process_result = subprocess.run(
            build_command,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        if process_result.returncode != 0:
            raise RuntimeError(
                f"Build failed with exit code {process_result.returncode}\n"
                f"Error output:\n{process_result.stderr}"
            )

        return process_result.stdout + process_result.stderr

    def _find_build_artifacts(self, build_tool: str, project_path: Path) -> List[str]:
        """
        Find build artifacts based on build tool.

        Args:
            build_tool: Name of build tool used
            project_path: Project directory path

        Returns:
            List of artifact file paths
        """
        artifact_patterns = {
            'maven': ['target/*.jar', 'target/*.war'],
            'gradle': ['build/libs/*.jar'],
            'npm': ['dist/**/*', 'build/**/*'],
            'go': ['bin/*']
        }

        artifacts = []
        patterns = artifact_patterns.get(build_tool, [])

        for pattern in patterns:
            matching_files = list(project_path.glob(pattern))
            artifacts.extend([str(f.relative_to(project_path)) for f in matching_files])

        return artifacts


def main():
    """Main entry point for CLI usage."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Build projects using various build tools'
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

    command = BuildCommand(parameters)
    result = command.run()
    print_command_result(result, args.format)

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()