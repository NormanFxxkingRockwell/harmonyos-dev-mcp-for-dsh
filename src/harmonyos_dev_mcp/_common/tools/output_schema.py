"""Generate MCP output schemas from the result payload TypedDicts."""

from __future__ import annotations

from typing import Any, Callable, get_type_hints

from pydantic import TypeAdapter


_ENVELOPE_FIELDS = {"tool", "ok", "result", "error", "meta"}


def build_output_schema(func: Callable) -> dict[str, Any]:
    """Build the structuredContent contract exposed by ``tools/list``."""
    return_type = getattr(func, "_mcp_payload_type", None)
    if return_type is None:
        return_type = get_type_hints(func).get("return")
    payload_properties: dict[str, Any] = {}
    payload_required: list[str] = []
    definitions: dict[str, Any] = {}

    if return_type is not None:
        annotated_schema = TypeAdapter(return_type).json_schema(mode="serialization")
        payload_properties = {
            name: schema
            for name, schema in annotated_schema.get("properties", {}).items()
            if name not in _ENVELOPE_FIELDS
        }
        payload_required = [
            name
            for name in annotated_schema.get("required", [])
            if name not in _ENVELOPE_FIELDS
        ]
        definitions = annotated_schema.get("$defs", {})

    result_schema: dict[str, Any] = {
        "type": "object",
        "properties": payload_properties,
        "additionalProperties": True,
    }
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "ok": {"type": "boolean"},
            "result": {
                "anyOf": [
                    result_schema,
                    {"type": "null"},
                ]
            },
            "error": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["code", "detail"],
                        "additionalProperties": False,
                    },
                    {"type": "null"},
                ]
            },
            "meta": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "duration_ms": {"type": "integer", "minimum": 0},
                },
                "required": ["request_id", "timestamp", "duration_ms"],
                "additionalProperties": True,
            },
        },
        "required": ["tool", "ok", "result", "error", "meta"],
        "additionalProperties": False,
    }
    if definitions:
        schema["$defs"] = definitions
    if payload_required:
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"ok": {"const": True}},
                    "required": ["ok"],
                },
                "then": {
                    "properties": {
                        "result": {
                            "type": "object",
                            "required": payload_required,
                        }
                    }
                },
            }
        ]
    return schema
