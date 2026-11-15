class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot be executed."""


class ToolPermissionError(PermissionError):
    """Raised when a tool is not permitted to run."""
