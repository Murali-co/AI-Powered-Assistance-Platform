import asyncio
import time
from typing import Dict, Any, Optional
from app.orchestrator.tools.registry import ToolRegistry
from app.orchestrator.tools.permissions import has_tool_permission
from app.orchestrator.tools.schemas import ToolExecutionRequest, ToolExecutionResult
from app.orchestrator.tools.exceptions import (
    UnknownToolError,
    UnauthorizedToolError,
    InvalidToolArgumentsError,
    ToolExecutionTimeoutError,
    ToolExecutionError
)

class ToolRunner:
    """
    Execution engine for local tools enforcing permissions, input validation,
    execution timeouts, retries, output validation, and audit logging.
    """

    @classmethod
    async def execute_tool(
        cls,
        user_dict: dict,
        request: ToolExecutionRequest,
        max_retries: int = 2
    ) -> ToolExecutionResult:
        start_time = time.perf_counter()
        tool_name = request.tool_name
        user_id = user_dict.get("id") or user_dict.get("user_id")

        if not user_id:
            raise UnauthorizedToolError(tool_name, "Authenticated user required")

        # 1. Tool Lookup & Enabled Check
        tool = ToolRegistry.get_tool(tool_name)
        if not tool.enabled:
            raise ToolExecutionError(tool_name, f"Tool '{tool_name}' is currently disabled.")

        # 2. Permission Check
        if not has_tool_permission(user_dict, tool.permission):
            raise UnauthorizedToolError(tool_name, tool.permission.value)

        # 3. Input Argument Validation
        validated_args = ToolRegistry.validate_input(tool_name, request.arguments)

        # 4. Controlled Execution Loop with Timeout & Retries
        task_output = None
        last_error = None
        status_str = "FAILED"

        for attempt in range(max_retries + 1):
            try:
                task_output = await asyncio.wait_for(
                    tool.handler(user_id=user_id, **validated_args),
                    timeout=tool.timeout
                )
                status_str = "SUCCESS"
                break
            except asyncio.TimeoutError:
                last_error = f"Tool '{tool_name}' execution timed out after {tool.timeout:.1f}s."
                status_str = "TIMEOUT"
                print(f"[ToolRunner] Tool '{tool_name}' attempt {attempt + 1} timed out.")
                if attempt < max_retries:
                    await asyncio.sleep(0.5)
            except Exception as e:
                last_error = str(e) or type(e).__name__
                status_str = "FAILED"
                print(f"[ToolRunner] Tool '{tool_name}' attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Handle terminal failure
        if status_str == "TIMEOUT":
            raise ToolExecutionTimeoutError(tool_name, tool.timeout)
        if status_str != "SUCCESS" or task_output is None:
            raise ToolExecutionError(tool_name, last_error or "Unknown tool error")

        # 5. Output Payload Validation
        validated_output = ToolRegistry.validate_output(tool_name, task_output)

        # 6. Audit Logging
        print(f"[ToolRunner Audit] User {user_id} executed '{tool_name}' in {elapsed_ms:.1f}ms (Status: {status_str})")

        return ToolExecutionResult(
            tool_name=tool_name,
            status=status_str,
            output=validated_output,
            execution_time_ms=round(elapsed_ms, 2)
        )
