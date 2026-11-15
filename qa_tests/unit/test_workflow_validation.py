import pytest
from pydantic import ValidationError

from app.orchestrator.execution import WorkflowRequest, validate_input


def test_workflows_only_accept_registered_tools_and_bounded_plans():
    with pytest.raises(ValidationError):
        WorkflowRequest(goal='run code', steps=[{'tool': 'shell', 'input': {'cmd': 'echo unsafe'}}])
    with pytest.raises(ValidationError):
        WorkflowRequest(goal='empty', steps=[])
    with pytest.raises(ValidationError):
        validate_input('search_jobs', {'title': 'Engineer', 'hours_old': -1})
    with pytest.raises(ValidationError):
        validate_input('search_jobs', {'title': 'Engineer', 'user_id': 999})
    with pytest.raises(ValueError):
        validate_input('profile_summary', {'user_id': 999})
