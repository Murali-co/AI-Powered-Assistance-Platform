from __future__ import annotations

from typing import Any, Dict


class ToolCallParser:
    """Very small parser for tool instructions."""

    @staticmethod
    def parse(raw: str) -> Dict[str, Any]:
        cleaned = (raw or "").strip()
        if not cleaned:
            return {"name": "", "arguments": {}}
        if "(" in cleaned and cleaned.endswith(")"):
            name, args = cleaned.split("(", 1)
            args = args[:-1]
            pieces = [part.strip() for part in args.split(",") if part.strip()]
            payload: Dict[str, Any] = {}
            for piece in pieces:
                if "=" in piece:
                    key, value = piece.split("=", 1)
                    payload[key.strip()] = value.strip().strip("\"'")
            return {"name": name.strip(), "arguments": payload}
        return {"name": cleaned, "arguments": {}}
