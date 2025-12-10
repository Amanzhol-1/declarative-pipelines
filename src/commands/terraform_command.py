import subprocess
import re
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.base_command import BaseCommand, CommandResult, print_command_result


class TerraformCommand(BaseCommand):
    """
    Execute Terraform operations for infrastructure provisioning.

    Supported operations:
        - init: Initialize Terraform working directory
        - plan: Create execution plan
        - apply: Apply changes to infrastructure
        - destroy: Destroy managed infrastructure
        - validate: Validate configuration files
        - output: Read output values

    Required parameters:
        operation: Terraform operation (init, plan, apply, destroy, validate, output)
        working_dir: Path to Terraform configuration directory

    Optional parameters:
        var_file: Path to variables file (.tfvars)
        variables: Dictionary of Terraform variables
        backend_config: Dictionary of backend configuration options
        auto_approve: Skip interactive approval (default: false)
        target: List of resource addresses to target
        workspace: Terraform workspace name
        parallelism: Number of concurrent operations (default: 10)
        lock: Lock state file during operation (default: true)
        lock_timeout: Duration to wait for state lock (default: 0s)
        reconfigure: Reconfigure backend during init (default: false)
        upgrade: Upgrade modules and plugins during init (default: false)
        plan_output_file: Save plan to file for later apply
        destroy_plan: Create destroy plan instead of apply plan
    """

    VALID_OPERATIONS = ['init', 'plan', 'apply', 'destroy', 'validate', 'output']

    def validate_parameters(self) -> None:
        """Validate required parameters are present."""
        self._require_parameters('operation', 'working_dir')

        operation = self.parameters['operation']
        if operation not in self.VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation: {operation}. "
                f"Valid operations: {', '.join(self.VALID_OPERATIONS)}"
            )

        working_dir = Path(self.parameters['working_dir'])
        if not working_dir.exists():
            raise ValueError(f"Working directory does not exist: {working_dir}")

        # Check for .tf files
        tf_files = list(working_dir.glob('*.tf'))
        if not tf_files and operation != 'init':
            raise ValueError(f"No Terraform files found in: {working_dir}")

    def execute(self) -> CommandResult:
        """Execute the Terraform command."""
        operation = self.parameters['operation']
        working_dir = Path(self.parameters['working_dir'])

        result_data = {
            'operation': operation,
            'working_dir': str(working_dir),
            'workspace': self._get_parameter('workspace', 'default')
        }

        # Select workspace if specified
        workspace = self._get_parameter('workspace')
        if workspace and operation != 'init':
            self._select_workspace(workspace, working_dir)
            result_data['workspace'] = workspace

        # Execute operation
        if operation == 'init':
            output = self._execute_init(working_dir)
            result_data['initialized'] = True
            result_data['providers'] = self._parse_providers(output)

        elif operation == 'validate':
            output = self._execute_validate(working_dir)
            result_data['valid'] = True

        elif operation == 'plan':
            output = self._execute_plan(working_dir)
            changes = self._parse_plan_changes(output)
            result_data['changes'] = changes
            result_data['has_changes'] = any(
                changes[k] > 0 for k in ['add', 'change', 'destroy']
            )

        elif operation == 'apply':
            output = self._execute_apply(working_dir)
            result_data['applied'] = True
            result_data['resources'] = self._parse_apply_results(output)

        elif operation == 'destroy':
            output = self._execute_destroy(working_dir)
            result_data['destroyed'] = True
            result_data['resources_destroyed'] = self._count_destroyed(output)

        elif operation == 'output':
            outputs = self._execute_output(working_dir)
            result_data['outputs'] = outputs

        message = self._generate_result_message(operation, result_data)

        return CommandResult(
            success=True,
            message=message,
            output_data=result_data
        )

    def _build_base_command(self) -> List[str]:
        """Build base terraform command with common flags."""
        cmd = ['terraform']
        return cmd

    def _add_var_flags(self, cmd: List[str]) -> List[str]:
        """Add variable-related flags to command."""
        # Add var-file
        var_file = self._get_parameter('var_file')
        if var_file:
            cmd.extend(['-var-file', var_file])

        # Add individual variables
        variables = self._get_parameter('variables', {})
        for var_name, var_value in variables.items():
            if isinstance(var_value, (dict, list)):
                var_value = json.dumps(var_value)
            cmd.extend(['-var', f'{var_name}={var_value}'])

        return cmd

    def _add_common_flags(self, cmd: List[str]) -> List[str]:
        """Add common flags to command."""
        # Target specific resources
        targets = self._get_parameter('target', [])
        for target in targets:
            cmd.extend(['-target', target])

        # Parallelism
        parallelism = self._get_parameter('parallelism')
        if parallelism:
            cmd.extend(['-parallelism', str(parallelism)])

        # Lock settings
        lock = self._get_parameter('lock', True)
        if not lock:
            cmd.append('-lock=false')

        lock_timeout = self._get_parameter('lock_timeout')
        if lock_timeout:
            cmd.extend(['-lock-timeout', lock_timeout])

        return cmd

    def _execute_init(self, working_dir: Path) -> str:
        """Execute terraform init."""
        cmd = self._build_base_command()
        cmd.append('init')

        # Backend config
        backend_config = self._get_parameter('backend_config', {})
        for key, value in backend_config.items():
            cmd.extend(['-backend-config', f'{key}={value}'])

        # Reconfigure flag
        if self._get_parameter('reconfigure', False):
            cmd.append('-reconfigure')

        # Upgrade flag
        if self._get_parameter('upgrade', False):
            cmd.append('-upgrade')

        # No color for easier parsing
        cmd.append('-no-color')

        return self._run_terraform(cmd, working_dir)

    def _execute_validate(self, working_dir: Path) -> str:
        """Execute terraform validate."""
        cmd = self._build_base_command()
        cmd.extend(['validate', '-no-color'])
        return self._run_terraform(cmd, working_dir)

    def _execute_plan(self, working_dir: Path) -> str:
        """Execute terraform plan."""
        cmd = self._build_base_command()
        cmd.append('plan')

        cmd = self._add_var_flags(cmd)
        cmd = self._add_common_flags(cmd)

        # Output file for plan
        plan_output = self._get_parameter('plan_output_file')
        if plan_output:
            cmd.extend(['-out', plan_output])

        # Destroy plan
        if self._get_parameter('destroy_plan', False):
            cmd.append('-destroy')

        cmd.append('-no-color')

        return self._run_terraform(cmd, working_dir)

    def _execute_apply(self, working_dir: Path) -> str:
        """Execute terraform apply."""
        cmd = self._build_base_command()
        cmd.append('apply')

        # Check if applying from plan file
        plan_file = self._get_parameter('plan_output_file')
        if plan_file and Path(working_dir / plan_file).exists():
            cmd.append(plan_file)
        else:
            cmd = self._add_var_flags(cmd)
            cmd = self._add_common_flags(cmd)

        # Auto approve
        if self._get_parameter('auto_approve', False):
            cmd.append('-auto-approve')

        cmd.append('-no-color')

        return self._run_terraform(cmd, working_dir)

    def _execute_destroy(self, working_dir: Path) -> str:
        """Execute terraform destroy."""
        cmd = self._build_base_command()
        cmd.append('destroy')

        cmd = self._add_var_flags(cmd)
        cmd = self._add_common_flags(cmd)

        # Auto approve
        if self._get_parameter('auto_approve', False):
            cmd.append('-auto-approve')

        cmd.append('-no-color')

        return self._run_terraform(cmd, working_dir)

    def _execute_output(self, working_dir: Path) -> Dict[str, Any]:
        """Execute terraform output and return parsed outputs."""
        cmd = self._build_base_command()
        cmd.extend(['output', '-json'])

        output = self._run_terraform(cmd, working_dir)

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {}

    def _select_workspace(self, workspace: str, working_dir: Path) -> None:
        """Select or create Terraform workspace."""
        # Try to select existing workspace
        cmd = ['terraform', 'workspace', 'select', workspace]
        result = subprocess.run(
            cmd, cwd=working_dir, capture_output=True, text=True
        )

        # If workspace doesn't exist, create it
        if result.returncode != 0:
            cmd = ['terraform', 'workspace', 'new', workspace]
            subprocess.run(
                cmd, cwd=working_dir, capture_output=True, text=True, check=True
            )

    def _run_terraform(self, cmd: List[str], working_dir: Path) -> str:
        """Run terraform command and return output."""
        result = subprocess.run(
            cmd, cwd=working_dir, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Terraform command failed with exit code {result.returncode}\n"
                f"Command: {' '.join(cmd)}\n"
                f"Error:\n{result.stderr}"
            )

        return result.stdout + result.stderr

    def _parse_providers(self, output: str) -> List[str]:
        """Parse initialized providers from init output."""
        providers = []
        pattern = r'- Installed ([^\s]+) v([\d.]+)'
        for match in re.finditer(pattern, output):
            providers.append(f"{match.group(1)}@{match.group(2)}")
        return providers

    def _parse_plan_changes(self, output: str) -> Dict[str, int]:
        """Parse plan changes from output."""
        changes = {'add': 0, 'change': 0, 'destroy': 0}

        # Pattern: Plan: X to add, Y to change, Z to destroy
        match = re.search(
            r'Plan: (\d+) to add, (\d+) to change, (\d+) to destroy',
            output
        )
        if match:
            changes['add'] = int(match.group(1))
            changes['change'] = int(match.group(2))
            changes['destroy'] = int(match.group(3))

        return changes

    def _parse_apply_results(self, output: str) -> Dict[str, int]:
        """Parse apply results from output."""
        results = {'added': 0, 'changed': 0, 'destroyed': 0}

        # Pattern: Apply complete! Resources: X added, Y changed, Z destroyed
        match = re.search(
            r'(\d+) added, (\d+) changed, (\d+) destroyed',
            output
        )
        if match:
            results['added'] = int(match.group(1))
            results['changed'] = int(match.group(2))
            results['destroyed'] = int(match.group(3))

        return results

    def _count_destroyed(self, output: str) -> int:
        """Count destroyed resources from destroy output."""
        match = re.search(r'Destroy complete! Resources: (\d+) destroyed', output)
        return int(match.group(1)) if match else 0

    def _generate_result_message(
            self,
            operation: str,
            result_data: Dict[str, Any]
    ) -> str:
        """Generate human-readable result message."""
        workspace = result_data.get('workspace', 'default')

        if operation == 'init':
            providers = result_data.get('providers', [])
            msg = f"Terraform initialized successfully"
            if providers:
                msg += f" with providers: {', '.join(providers)}"
            return msg

        elif operation == 'validate':
            return "Terraform configuration is valid"

        elif operation == 'plan':
            changes = result_data.get('changes', {})
            if result_data.get('has_changes'):
                return (
                    f"Plan: {changes['add']} to add, "
                    f"{changes['change']} to change, "
                    f"{changes['destroy']} to destroy"
                )
            return "No changes. Infrastructure is up-to-date"

        elif operation == 'apply':
            res = result_data.get('resources', {})
            return (
                f"Apply complete: {res.get('added', 0)} added, "
                f"{res.get('changed', 0)} changed, "
                f"{res.get('destroyed', 0)} destroyed"
            )

        elif operation == 'destroy':
            count = result_data.get('resources_destroyed', 0)
            return f"Destroy complete: {count} resources destroyed"

        elif operation == 'output':
            outputs = result_data.get('outputs', {})
            return f"Retrieved {len(outputs)} output values"

        return f"Operation {operation} completed successfully"


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Execute Terraform operations'
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

    command = TerraformCommand(parameters)
    result = command.run()
    print_command_result(result, args.format)

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()