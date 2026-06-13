"""JSON schemas for the missing_handler repair handler.

The LLM is prompted to output JSON matching this structure.
"""

MISSING_HANDLER_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "patch_type": {
            "type": "string",
            "enum": ["AddExceptionHandlerStep"],
            "description": "Must be 'AddExceptionHandlerStep'.",
        },
        "title": {
            "type": "string",
            "description": "Short human-readable title for the suggestion.",
        },
        "explanation": {
            "type": "string",
            "description": "Why this handler action fits the exception condition.",
        },
        "payload": {
            "type": "object",
            "properties": {
                "handler_text": {
                    "type": "string",
                    "description": "The handler step action text.",
                },
                "command_type": {
                    "type": "string",
                    "enum": ["GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE"],
                    "description": "SPL command type for the handler.",
                },
                "inputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Input variable names.",
                },
                "outputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Output variable names.",
                },
            },
            "required": ["handler_text", "command_type"],
        },
    },
    "required": ["patch_type", "title", "explanation", "payload"],
}
