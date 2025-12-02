import subprocess
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.base_command import BaseCommand, CommandResult, print_command_result


class DockerCommand(BaseCommand):
    """
    Build and push Docker images.

    Required parameters:
        operation: Operation to perform (build, push, build-and-push)
        image_name: Docker image name (e.g., myapp or registry.com/myapp)

    Optional parameters for build:
        dockerfile_path: Path to Dockerfile (default: ./Dockerfile)
        build_context: Build context path (default: .)
        build_args: Dictionary of build arguments
        target_stage: Multi-stage build target
        no_cache: Disable build cache (default: false)

    Optional parameters for tagging:
        tags: List of tags to apply (default: ['latest'])
        auto_tag_commit: Auto-tag with git commit SHA (default: false)
        auto_tag_branch: Auto-tag with git branch name (default: false)
        auto_tag_date: Auto-tag with current date (default: false)

    Optional parameters for push:
        registry_url: Docker registry URL (default: Docker Hub)
        registry_username: Registry username for authentication
        registry_password: Registry password for authentication
    """

    VALID_OPERATIONS = ['build', 'push', 'build-and-push']

    def validate_parameters(self) -> None:
        """Validate required parameters are present."""
        self._require_parameters('operation', 'image_name')

        operation = self.parameters['operation']
        if operation not in self.VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation: {operation}. "
                f"Valid operations: {', '.join(self.VALID_OPERATIONS)}"
            )

        # Validate Dockerfile exists if building
        if operation in ['build', 'build-and-push']:
            dockerfile_path = Path(self._get_parameter('dockerfile_path', './Dockerfile'))
            if not dockerfile_path.exists():
                raise ValueError(f"Dockerfile not found: {dockerfile_path}")

    def execute(self) -> CommandResult:
        """Execute the Docker command."""
        operation = self.parameters['operation']
        image_name = self.parameters['image_name']

        result_data = {
            'operation': operation,
            'image_name': image_name,
            'tags_applied': [],
            'build_completed': False,
            'push_completed': False
        }

        # Generate all tags
        all_tags = self._generate_all_tags()
        result_data['tags_applied'] = all_tags

        # Build image if required
        if operation in ['build', 'build-and-push']:
            build_output = self._build_image(image_name, all_tags)
            result_data['build_completed'] = True
            result_data['image_id'] = self._extract_image_id(build_output)
            result_data['image_size'] = self._get_image_size(image_name, all_tags[0])

        # Push image if required
        if operation in ['push', 'build-and-push']:
            self._authenticate_registry()
            push_results = self._push_image(image_name, all_tags)
            result_data['push_completed'] = True
            result_data['push_results'] = push_results

        message = self._generate_result_message(operation, result_data)

        return CommandResult(
            success=True,
            message=message,
            output_data=result_data
        )

    def _generate_all_tags(self) -> List[str]:
        """
        Generate all tags for the image.

        Returns:
            List of tag strings
        """
        tags = []

        # Add explicitly specified tags
        explicit_tags = self._get_parameter('tags', ['latest'])
        tags.extend(explicit_tags)

        # Auto-tag with commit SHA
        if self._get_parameter('auto_tag_commit', False):
            commit_sha = self._get_git_commit_sha()
            if commit_sha:
                tags.append(f'commit-{commit_sha[:8]}')

        # Auto-tag with branch name
        if self._get_parameter('auto_tag_branch', False):
            branch_name = self._get_git_branch_name()
            if branch_name:
                # Sanitize branch name for Docker tag
                safe_branch = re.sub(r'[^a-zA-Z0-9._-]', '-', branch_name)
                tags.append(f'branch-{safe_branch}')

        # Auto-tag with date
        if self._get_parameter('auto_tag_date', False):
            date_tag = datetime.now().strftime('%Y%m%d')
            tags.append(date_tag)

        return tags

    def _build_image(self, image_name: str, tags: List[str]) -> str:
        """
        Build Docker image.

        Args:
            image_name: Name of the image
            tags: List of tags to apply

        Returns:
            Build output

        Raises:
            RuntimeError: If build fails
        """
        dockerfile_path = self._get_parameter('dockerfile_path', 'Dockerfile')
        build_context = self._get_parameter('build_context', '.')

        # Start building command
        command_parts = ['docker', 'build']

        # Add tags
        for tag in tags:
            command_parts.extend(['-t', f'{image_name}:{tag}'])

        # Add Dockerfile path
        command_parts.extend(['-f', dockerfile_path])

        # Add build args
        build_args = self._get_parameter('build_args', {})
        for arg_name, arg_value in build_args.items():
            command_parts.extend(['--build-arg', f'{arg_name}={arg_value}'])

        # Add target stage if specified
        target_stage = self._get_parameter('target_stage')
        if target_stage:
            command_parts.extend(['--target', target_stage])

        # Add no-cache flag
        if self._get_parameter('no_cache', False):
            command_parts.append('--no-cache')

        # Add build context
        command_parts.append(build_context)

        # Execute build
        process_result = subprocess.run(
            command_parts,
            capture_output=True,
            text=True
        )

        if process_result.returncode != 0:
            raise RuntimeError(
                f"Docker build failed with exit code {process_result.returncode}\n"
                f"Error output:\n{process_result.stderr}"
            )

        return process_result.stdout + process_result.stderr

    def _authenticate_registry(self) -> None:
        """
        Authenticate with Docker registry if credentials provided.

        Raises:
            RuntimeError: If authentication fails
        """
        registry_username = self._get_parameter('registry_username')
        registry_password = self._get_parameter('registry_password')
        registry_url = self._get_parameter('registry_url')

        if not (registry_username and registry_password):
            return  # No credentials provided, skip authentication

        command_parts = [
            'docker', 'login',
            '-u', registry_username,
            '--password-stdin'
        ]

        if registry_url:
            command_parts.append(registry_url)

        process_result = subprocess.run(
            command_parts,
            input=registry_password,
            capture_output=True,
            text=True
        )

        if process_result.returncode != 0:
            raise RuntimeError(
                f"Registry authentication failed: {process_result.stderr}"
            )

    def _push_image(self, image_name: str, tags: List[str]) -> List[Dict[str, Any]]:
        """
        Push Docker image to registry.

        Args:
            image_name: Name of the image
            tags: List of tags to push

        Returns:
            List of push results for each tag

        Raises:
            RuntimeError: If push fails
        """
        push_results = []

        for tag in tags:
            full_image_name = f'{image_name}:{tag}'

            process_result = subprocess.run(
                ['docker', 'push', full_image_name],
                capture_output=True,
                text=True
            )

            if process_result.returncode != 0:
                raise RuntimeError(
                    f"Failed to push {full_image_name}: {process_result.stderr}"
                )

            # Extract digest from output
            digest = self._extract_digest(process_result.stdout)

            push_results.append({
                'tag': tag,
                'full_name': full_image_name,
                'digest': digest,
                'success': True
            })

        return push_results

    def _get_git_commit_sha(self) -> Optional[str]:
        """
        Get current git commit SHA.

        Returns:
            Commit SHA or None if not in git repo
        """
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _get_git_branch_name(self) -> Optional[str]:
        """
        Get current git branch name.

        Returns:
            Branch name or None if not in git repo
        """
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _extract_image_id(self, build_output: str) -> Optional[str]:
        """
        Extract image ID from build output.

        Args:
            build_output: Docker build output

        Returns:
            Image ID or None
        """
        match = re.search(r'sha256:([a-f0-9]{64})', build_output)
        if match:
            return match.group(1)[:12]  # Return short ID
        return None

    def _extract_digest(self, push_output: str) -> Optional[str]:
        """
        Extract digest from push output.

        Args:
            push_output: Docker push output

        Returns:
            Digest or None
        """
        match = re.search(r'digest: (sha256:[a-f0-9]{64})', push_output)
        if match:
            return match.group(1)
        return None

    def _get_image_size(self, image_name: str, tag: str) -> Optional[str]:
        """
        Get image size.

        Args:
            image_name: Name of the image
            tag: Image tag

        Returns:
            Human-readable size or None
        """
        try:
            result = subprocess.run(
                ['docker', 'images', f'{image_name}:{tag}', '--format', '{{.Size}}'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def _generate_result_message(
            self,
            operation: str,
            result_data: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable result message.

        Args:
            operation: Operation performed
            result_data: Result data dictionary

        Returns:
            Result message string
        """
        image_name = result_data['image_name']
        tags = result_data['tags_applied']

        if operation == 'build':
            message = f"Successfully built image {image_name} with tags: {', '.join(tags)}"
        elif operation == 'push':
            message = f"Successfully pushed image {image_name} with tags: {', '.join(tags)}"
        else:  # build-and-push
            message = (
                f"Successfully built and pushed image {image_name} "
                f"with tags: {', '.join(tags)}"
            )

        if result_data.get('image_size'):
            message += f" (Size: {result_data['image_size']})"

        return message


def main():
    """Main entry point for CLI usage."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Build and push Docker images'
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

    command = DockerCommand(parameters)
    result = command.run()
    print_command_result(result, args.format)

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()