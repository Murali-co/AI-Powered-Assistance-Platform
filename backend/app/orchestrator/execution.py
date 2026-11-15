"""Persisted, owned workflows with explicit approval for application records.

Only the fixed catalog below is executable. No arbitrary Python, shell, URLs or
user-supplied executors are evaluated. Execution is synchronous with the request;
durable dispatch after process loss remains separate from persisted state.
"""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Literal
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.db.models import Workflow, WorkflowTask
from app.db.session import SessionLocal
from app.auth.models import DBManager

logger = logging.getLogger(__name__)
CATALOG = {
    'profile_summary': ('Read your extracted resume profile.', False),
    'search_jobs': ('Fetch dated public job listings for an explicit search.', False),
    'generate_application': ('Draft application materials using local AI.', False),
    'record_application': ('Write an application tracking record; does not submit to an employer.', True),
}


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    location: str = Field(default='Any', min_length=1, max_length=200)
    hours_old: int = Field(default=168, ge=1, le=720)


class JobInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(min_length=1, max_length=200)


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Literal['profile_summary', 'search_jobs', 'generate_application', 'record_application']
    input: dict[str, Any] = Field(default_factory=dict)


class WorkflowRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=8)


def validate_input(tool, payload):
    from app.models.schemas import ApplicationSubmitRequest
    if tool == 'profile_summary':
        if payload:
            raise ValueError('Profile summary does not accept inputs.')
        return {}
    schema = {'search_jobs': SearchInput, 'generate_application': JobInput,
              'record_application': ApplicationSubmitRequest}[tool]
    return schema.model_validate(payload).model_dump(mode='json')


def create(request, user_id):
    # Validate the entire plan before making any database changes.
    try:
        inputs = [validate_input(step.tool, step.input) for step in request.steps]
    except (ValueError, KeyError):
        raise HTTPException(422, 'Invalid input for a workflow step.') from None
    workflow_id = str(uuid.uuid4())
    with SessionLocal.begin() as db:
        db.add(Workflow(id=workflow_id, user_id=user_id, goal=request.goal, status='PENDING'))
        db.flush()
        for index, step in enumerate(request.steps):
            task_id = f'step-{index + 1:03}'
            db.add(WorkflowTask(id=f'{workflow_id}:{task_id}', task_id=task_id,
                workflow_id=workflow_id, task_type=step.tool, description=CATALOG[step.tool][0],
                status='PENDING', input_json=json.dumps(inputs[index]),
                dependencies_json=json.dumps([f'step-{index:03}'] if index else [])))
    return workflow_id


def claim(workflow_id, user_id, approved_task=None, reject=False):
    with SessionLocal.begin() as db:
        workflow = db.query(Workflow).filter_by(id=workflow_id, user_id=user_id).with_for_update().first()
        if workflow is None:
            raise HTTPException(404, 'Workflow not found.')
        tasks = db.query(WorkflowTask).filter_by(workflow_id=workflow_id).order_by(WorkflowTask.task_id).all()
        if approved_task:
            task = next((task for task in tasks if task.task_id == approved_task), None)
            if task is None:
                raise HTTPException(404, 'Workflow task not found.')
            if task.status != 'AWAITING_APPROVAL' or workflow.status != 'AWAITING_APPROVAL':
                raise HTTPException(409, 'This task is no longer awaiting approval.')
            if reject:
                for remaining in tasks:
                    if remaining.status in {'PENDING', 'AWAITING_APPROVAL'}:
                        remaining.status = 'CANCELLED'
                workflow.status = 'CANCELLED'
                workflow.completed_at = datetime.now(timezone.utc)
                return None
        elif workflow.status in {'COMPLETED', 'FAILED', 'CANCELLED', 'AWAITING_APPROVAL'}:
            return None
        if any(task.status == 'RUNNING' for task in tasks):
            return None
        task = next((task for task in tasks if task.status != 'COMPLETED'), None)
        if task is None:
            workflow.status = 'COMPLETED'
            workflow.completed_at = datetime.now(timezone.utc)
            return None
        if task.task_type not in CATALOG:
            raise HTTPException(409, 'The saved task uses an unsupported executor. No action was performed.')
        if CATALOG[task.task_type][1] and approved_task != task.task_id:
            task.status = 'AWAITING_APPROVAL'
            workflow.status = 'AWAITING_APPROVAL'
            return None
        task.status = 'RUNNING'
        workflow.status = 'RUNNING'
        return {'id': task.id, 'tool': task.task_type, 'input': json.loads(task.input_json or '{}')}


async def execute(task, user):
    tool, data = task['tool'], task['input']
    if tool == 'profile_summary':
        from app.vector_db.profile_store import ProfileStore
        profile = await run_in_threadpool(ProfileStore.get_profile, user['id'])
        if not profile:
            raise HTTPException(400, 'Upload a resume first.')
        return {'skills': profile.get('skills', []), 'resume_preview': profile.get('resume_text', '')[:1000]}
    if tool == 'search_jobs':
        from app.jobs.scraper import JobScraper
        from app.jobs.matcher import JobMatcher
        jobs = await run_in_threadpool(JobScraper.scrape, data['title'], data['location'], 30, data['hours_old'])
        await run_in_threadpool(JobMatcher.upsert_jobs, jobs)
        return {'count': len(jobs), 'job_ids': [job['id'] for job in jobs]}
    if tool == 'generate_application':
        from app.applications.generator import ApplicationGenerator
        return await ApplicationGenerator.generate_package(user['id'], data['job_id'], user['full_name'])
    from app.applications.router import record_submission
    from app.models.schemas import ApplicationSubmitRequest
    return await record_submission(ApplicationSubmitRequest.model_validate(data), current_user=user)


def finish_task(workflow_id, task_id, output=None, failed=False):
    with SessionLocal.begin() as db:
        task = db.get(WorkflowTask, task_id)
        if task is None or task.status != 'RUNNING':
            raise HTTPException(409, 'Workflow task changed during execution.')
        task.status = 'FAILED' if failed else 'COMPLETED'
        task.completed_at = datetime.now(timezone.utc)
        task.output_json = json.dumps(output) if not failed else None
        if failed:
            task.error = 'Task execution failed. No successful result was recorded.'
            workflow = db.get(Workflow, workflow_id)
            workflow.status = 'FAILED'
            workflow.error = task.error
            workflow.completed_at = datetime.now(timezone.utc)


async def advance(workflow_id, user, approved_task=None, reject=False):
    while True:
        task = await run_in_threadpool(claim, workflow_id, user['id'], approved_task, reject)
        approved_task = None
        if task is None:
            break
        try:
            result = await execute(task, user)
        except Exception as error:
            logger.warning('Workflow task failed (%s).', type(error).__name__)
            await run_in_threadpool(finish_task, workflow_id, task['id'], failed=True)
            raise HTTPException(503, 'Workflow execution failed. Inspect the saved workflow state before retrying.') from None
        await run_in_threadpool(finish_task, workflow_id, task['id'], result)
    return await run_in_threadpool(DBManager.get_workflow, workflow_id)
