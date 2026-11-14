from enum import Enum

class ToolPermission(str, Enum):
    READ = "READ"
    EXECUTE = "EXECUTE"
    ADMIN = "ADMIN"

def has_tool_permission(user_dict: dict, required_permission: ToolPermission) -> bool:
    """
    Checks if a user has sufficient permission to execute a tool.
    ADMIN permission requires is_admin=True on user.
    READ and EXECUTE permissions are granted to authenticated users.
    """
    if not user_dict:
        return False

    if required_permission == ToolPermission.ADMIN:
        return bool(user_dict.get("is_admin", False))

    # All authenticated users have READ and EXECUTE permissions
    return True
