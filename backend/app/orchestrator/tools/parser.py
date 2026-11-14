import json
import re
from typing import Dict, Any
from app.orchestrator.tools.schemas import LLMToolCallPayload
from app.orchestrator.tools.exceptions import MalformedToolRequestError

class LLMToolParser:
    """
    Parses LLM text output into structured LLMToolCallPayload instances.
    Safely handles markdown wrapping, extra whitespace, or malformed JSON payloads.
    """

    @classmethod
    def parse_tool_call(cls, raw_llm_output: str) -> LLMToolCallPayload:
        if not raw_llm_output or not raw_llm_output.strip():
            raise MalformedToolRequestError(raw_input=raw_llm_output or "", reason="LLM output is empty.")

        cleaned = raw_llm_output.strip()

        # Remove code block formatting
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
            if match:
                cleaned = match.group(1).strip()
            else:
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Fallback regex search for JSON object
            json_match = re.search(r"\{[\s\S]*\}", cleaned)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    raise MalformedToolRequestError(raw_input=raw_llm_output, reason=f"Invalid JSON syntax: {e}")
            else:
                raise MalformedToolRequestError(raw_input=raw_llm_output, reason=f"Could not parse JSON object from output: {e}")

        if not isinstance(data, dict):
            raise MalformedToolRequestError(raw_input=raw_llm_output, reason="JSON output is not a dictionary.")

        if "tool_name" not in data:
            # Check common key aliases e.g. "name", "tool"
            if "name" in data:
                data["tool_name"] = data.pop("name")
            elif "tool" in data:
                data["tool_name"] = data.pop("tool")
            else:
                raise MalformedToolRequestError(raw_input=raw_llm_output, reason="Missing required 'tool_name' field.")

        if "arguments" not in data and "args" in data:
            data["arguments"] = data.pop("args")
        elif "arguments" not in data and "input" in data:
            data["arguments"] = data.pop("input")

        try:
            return LLMToolCallPayload(**data)
        except Exception as ve:
            raise MalformedToolRequestError(raw_input=raw_llm_output, reason=f"Validation failed for tool payload: {ve}")
