from typing import Dict, Any, Callable, Awaitable, Optional, Type
from pydantic import BaseModel, ValidationError
from app.orchestrator.tools.permissions import ToolPermission, has_tool_permission
from app.orchestrator.tools.schemas import ToolDefinitionSchema
from app.orchestrator.tools.exceptions import UnknownToolError, InvalidToolArgumentsError
from app.orchestrator.tools.definitions import (
    GetUserResumeInput, GetUserResumeOutput, handle_get_user_resume,
    AnalyzeResumeInput, AnalyzeResumeOutput, handle_analyze_resume,
    RAGSearchInput, RAGSearchOutput, handle_rag_search,
    SearchJobsInput, SearchJobsOutput, handle_search_jobs,
    MatchJobsInput, MatchJobsOutput, handle_match_jobs,
    AnalyzeSkillGapInput, AnalyzeSkillGapOutput, handle_analyze_skill_gap,
    TailorResumeInput, TailorResumeOutput, handle_tailor_resume,
    GenerateInterviewQuestionsInput, GenerateInterviewQuestionsOutput, handle_generate_interview_questions,
    GenerateCareerRoadmapInput, GenerateCareerRoadmapOutput, handle_generate_career_roadmap,
    GetUserProfileInput, GetUserProfileOutput, handle_get_user_profile,
)

class ToolEntry:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema_class: Type[BaseModel],
        output_schema_class: Type[BaseModel],
        handler: Callable[..., Awaitable[Dict[str, Any]]],
        permission: ToolPermission = ToolPermission.EXECUTE,
        timeout: float = 30.0,
        enabled: bool = True
    ):
        self.name = name
        self.description = description
        self.input_schema_class = input_schema_class
        self.output_schema_class = output_schema_class
        self.handler = handler
        self.permission = permission
        self.timeout = timeout
        self.enabled = enabled

    def to_schema(self) -> ToolDefinitionSchema:
        input_schema = (
            self.input_schema_class.model_json_schema()
            if hasattr(self.input_schema_class, "model_json_schema")
            else self.input_schema_class.schema()
        )
        output_schema = (
            self.output_schema_class.model_json_schema()
            if hasattr(self.output_schema_class, "model_json_schema")
            else self.output_schema_class.schema()
        )
        return ToolDefinitionSchema(
            name=self.name,
            description=self.description,
            input_schema=input_schema,
            output_schema=output_schema,
            permission=self.permission,
            timeout=self.timeout,
            enabled=self.enabled
        )


class ToolRegistry:
    """
    Centralized Tool Registry managing registration, validation, schemas, and permissions.
    """
    _registry: Dict[str, ToolEntry] = {}

    @classmethod
    def register(
        cls,
        name: str,
        description: str,
        input_schema_class: Type[BaseModel],
        output_schema_class: Type[BaseModel],
        handler: Callable[..., Awaitable[Dict[str, Any]]],
        permission: ToolPermission = ToolPermission.EXECUTE,
        timeout: float = 30.0,
        enabled: bool = True
    ):
        cls._registry[name] = ToolEntry(
            name=name,
            description=description,
            input_schema_class=input_schema_class,
            output_schema_class=output_schema_class,
            handler=handler,
            permission=permission,
            timeout=timeout,
            enabled=enabled
        )

    @classmethod
    def get_tool(cls, name: str) -> ToolEntry:
        if name not in cls._registry:
            raise UnknownToolError(name)
        return cls._registry[name]

    @classmethod
    def is_valid_tool(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    def get_all_tools(cls) -> Dict[str, ToolEntry]:
        return cls._registry

    @classmethod
    def get_enabled_tools(cls) -> Dict[str, ToolEntry]:
        return {k: v for k, v in cls._registry.items() if v.enabled}

    @classmethod
    def set_tool_enabled(cls, name: str, enabled: bool):
        tool = cls.get_tool(name)
        tool.enabled = enabled

    @classmethod
    def validate_input(cls, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = cls.get_tool(name)
        try:
            validated_model = tool.input_schema_class(**arguments)
            dump_fn = getattr(validated_model, "model_dump", getattr(validated_model, "dict", None))
            return dump_fn()
        except ValidationError as ve:
            raise InvalidToolArgumentsError(name, str(ve))

    @classmethod
    def validate_output(cls, name: str, output_data: Dict[str, Any]) -> Dict[str, Any]:
        tool = cls.get_tool(name)
        try:
            validated_model = tool.output_schema_class(**output_data)
            dump_fn = getattr(validated_model, "model_dump", getattr(validated_model, "dict", None))
            return dump_fn()
        except ValidationError as ve:
            # If output fails strict schema validation, return raw dict gracefully
            print(f"[ToolRegistry] Output schema warning for tool '{name}': {ve}")
            return output_data


# Register initial 10 local AI Powered Assistance Platform tools
ToolRegistry.register(
    name="get_user_resume",
    description="Retrieve user resume text, extracted skills, and parsed sections.",
    input_schema_class=GetUserResumeInput,
    output_schema_class=GetUserResumeOutput,
    handler=handle_get_user_resume,
    permission=ToolPermission.READ,
    timeout=10.0
)

ToolRegistry.register(
    name="analyze_resume",
    description="Perform deep NLP analysis on candidate resume skills and sections.",
    input_schema_class=AnalyzeResumeInput,
    output_schema_class=AnalyzeResumeOutput,
    handler=handle_analyze_resume,
    permission=ToolPermission.EXECUTE,
    timeout=15.0
)

ToolRegistry.register(
    name="rag_search",
    description="Perform semantically grounded vector search and RAG query for career/job guidance.",
    input_schema_class=RAGSearchInput,
    output_schema_class=RAGSearchOutput,
    handler=handle_rag_search,
    permission=ToolPermission.READ,
    timeout=30.0
)

ToolRegistry.register(
    name="search_jobs",
    description="Search active job postings matching title, skills, and location criteria.",
    input_schema_class=SearchJobsInput,
    output_schema_class=SearchJobsOutput,
    handler=handle_search_jobs,
    permission=ToolPermission.EXECUTE,
    timeout=30.0
)

ToolRegistry.register(
    name="match_jobs",
    description="Calculate semantic cosine-similarity matching scores for job listings against user profile.",
    input_schema_class=MatchJobsInput,
    output_schema_class=MatchJobsOutput,
    handler=handle_match_jobs,
    permission=ToolPermission.EXECUTE,
    timeout=20.0
)

ToolRegistry.register(
    name="analyze_skill_gap",
    description="Diagnose missing skills and recommend learning resources for a target job role.",
    input_schema_class=AnalyzeSkillGapInput,
    output_schema_class=AnalyzeSkillGapOutput,
    handler=handle_analyze_skill_gap,
    permission=ToolPermission.EXECUTE,
    timeout=30.0
)

ToolRegistry.register(
    name="tailor_resume",
    description="Rewrite resume experience and generate optimized bullet points aligned with job description.",
    input_schema_class=TailorResumeInput,
    output_schema_class=TailorResumeOutput,
    handler=handle_tailor_resume,
    permission=ToolPermission.EXECUTE,
    timeout=45.0
)

ToolRegistry.register(
    name="generate_interview_questions",
    description="Generate tailored technical and behavioral mock interview practice questions.",
    input_schema_class=GenerateInterviewQuestionsInput,
    output_schema_class=GenerateInterviewQuestionsOutput,
    handler=handle_generate_interview_questions,
    permission=ToolPermission.EXECUTE,
    timeout=30.0
)

ToolRegistry.register(
    name="generate_career_roadmap",
    description="Generate an actionable step-by-step career transition and upskilling roadmap.",
    input_schema_class=GenerateCareerRoadmapInput,
    output_schema_class=GenerateCareerRoadmapOutput,
    handler=handle_generate_career_roadmap,
    permission=ToolPermission.EXECUTE,
    timeout=30.0
)

ToolRegistry.register(
    name="get_user_profile",
    description="Retrieve user metadata, preferences, and active job search criteria.",
    input_schema_class=GetUserProfileInput,
    output_schema_class=GetUserProfileOutput,
    handler=handle_get_user_profile,
    permission=ToolPermission.READ,
    timeout=10.0
)
