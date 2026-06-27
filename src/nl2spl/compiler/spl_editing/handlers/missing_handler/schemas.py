"""JSON schemas for the missing_handler repair handler.

The LLM is prompted to output a strategy-level handler intent. Final command
family is decided by stage policy, not by this schema.
"""

MISSING_HANDLER_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "patch_type": {
            "type": "string",
            "enum": ["AddExceptionHandlerStep"],
            "description": "Execution adapter for the confirmed strategy.",
        },
        "title": {
            "type": "string",
            "description": "Short human-readable title for the suggestion.",
        },
        "explanation": {
            "type": "string",
            "description": "Why this handler intent fits the exception condition.",
        },
        "payload": {
            "type": "object",
            "properties": {
                "handler_goal": {
                    "type": "string",
                    "description": "Plain-language handler intent.",
                },
                "handler_text": {
                    "type": "string",
                    "description": "Legacy synonym accepted during migration.",
                },
            },
            "anyOf": [
                {"required": ["handler_goal"]},
                {"required": ["handler_text"]},
            ],
        },
    },
    "required": ["patch_type", "title", "explanation", "payload"],
}