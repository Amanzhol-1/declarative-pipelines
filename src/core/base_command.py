import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class CommandResult:
    """
    Standard result format returned by all commands.

    Attributes:
        success: Whether the command executed successfully
        message: Human-readable message describing the result
        output_data: Dictionary containing command-specific output data
        error_details: Error message if command failed, None otherwise
    """
    success: bool
    message: str
    output_data: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None

    def to_json(self) -> str:
        """
        Convert result to JSON string.

        Returns:
            Formatted JSON string representation of the result
        """
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary.

        Returns:
            Dictionary representation of the result
        """
        return asdict(self)


class BaseCommand(ABC):
    """
    Abstract base class for all pipeline commands.

    All commands must inherit from this class and implement
    the required abstract methods.
    """

    def __init__(self, parameters: Dict[str, Any]):
        """
        Initialize command with parameters.

        Args:
            parameters: Dictionary of command parameters
        """
        self.parameters = parameters
        self.validate_parameters()

    @abstractmethod
    def validate_parameters(self) -> None:
        """
        Validate that all required parameters are present and valid.

        Raises:
            ValueError: If required parameters are missing or invalid
        """
        pass

    @abstractmethod
    def execute(self) -> CommandResult:
        """
        Execute the command logic.

        Returns:
            CommandResult object with execution results

        Raises:
            Exception: If command execution fails
        """
        pass

    def run(self) -> CommandResult:
        """
        Run the command with error handling.

        Returns:
            CommandResult object with execution results
        """
        try:
            result = self.execute()
            return result
        except Exception as error:
            return CommandResult(
                success=False,
                message=f"Command execution failed: {type(error).__name__}",
                error_details=str(error)
            )

    def _require_parameters(self, *parameter_names: str) -> None:
        """
        Check that required parameters are present.

        Args:
            *parameter_names: Names of required parameters

        Raises:
            ValueError: If any required parameter is missing
        """
        missing_parameters = [
            param_name for param_name in parameter_names
            if param_name not in self.parameters
        ]

        if missing_parameters:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing_parameters)}"
            )

    def _get_parameter(self, parameter_name: str, default_value: Any = None) -> Any:
        """
        Get parameter value with optional default.

        Args:
            parameter_name: Name of the parameter
            default_value: Value to return if parameter is not present

        Returns:
            Parameter value or default value
        """
        return self.parameters.get(parameter_name, default_value)


def print_command_result(result: CommandResult, output_format: str = 'json') -> None:
    """
    Print command result to stdout.

    Args:
        result: CommandResult object to print
        output_format: Output format ('json' or 'text')
    """
    if output_format == 'json':
        print(result.to_json())
    else:
        print(f"Success: {result.success}")
        print(f"Message: {result.message}")

        if result.output_data:
            print(f"Output Data: {json.dumps(result.output_data, indent=2)}")

        if result.error_details:
            print(f"Error: {result.error_details}", file=sys.stderr)