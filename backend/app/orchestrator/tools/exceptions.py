class ToolError(Exception):
    """Base exception for all tool-related errors."""
    pass

class UnknownToolError(ToolError):
    """Raised when a requested tool does not exist in the registry."""
    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' is unknown or not registered.")
        self.tool_name = tool_name

class UnauthorizedToolError(ToolError):
    """Raised when the user does not have permission to execute the tool."""
    def __init__(self, tool_name: str, required_permission: str):
        super().__init__(f"Unauthorized to execute tool '{tool_name}'. Required permission: '{required_permission}'.")
        self.tool_name = tool_name
        self.required_permission = required_permission

class InvalidToolArgumentsError(ToolError):
    """Raised when provided arguments fail input schema validation."""
    def __init__(self, tool_name: str, details: str):
        super().__init__(f"Invalid arguments for tool '{tool_name}': {details}")
        self.tool_name = tool_name
        self.details = details

class ToolExecutionTimeoutError(ToolError):
    """Raised when tool execution exceeds the configured timeout."""
    def __init__(self, tool_name: str, timeout: float):
        super().__init__(f"Tool '{tool_name}' execution timed out after {timeout:.1f}s.")
        self.tool_name = tool_name
        self.timeout = timeout

class ToolExecutionError(ToolError):
    """Raised when an unhandled error occurs during tool execution."""
    def __init__(self, tool_name: str, error_msg: str):
        super().__init__(f"Tool '{tool_name}' execution failed: {error_msg}")
        self.tool_name = tool_name
        self.error_msg = error_msg

class MalformedToolRequestError(ToolError):
    """Raised when LLM tool request payload cannot be parsed."""
    def __init__(self, raw_input: str, reason: str):
        super().__init__(f"Malformed LLM tool request: {reason}")
        self.raw_input = raw_input
        self.reason = reason
