"""Centralised literals and default values for LLM repair context (Phase L0)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Prompt section ordering (fixed, must not depend on construct_type)
# ---------------------------------------------------------------------------

PROMPT_SECTION_ORDER: tuple[str, ...] = (
    "task",
    "issue_facts",
    "source_facts",
    "target_construct_facts",
    "local_workflow_facts",
    "primary_extension",
    "auxiliary_extensions",
    "allowed_repair_action",
    "payload_schema",
    "safety_rules",
    "previous_suggestions",
    "internal_allowed_ids",
    "json_only_output",
)

# ---------------------------------------------------------------------------
# Standard low-confidence prompt instruction
# ---------------------------------------------------------------------------

LOW_CONFIDENCE_INSTRUCTION = (
    "The available context is incomplete. "
    "Prefer a conservative clarification-style suggestion. "
    "Do not invent missing business facts. "
    "Use user_repair_instruction if provided. "
    "If required business facts are absent, produce a suggestion that asks "
    "for the missing fact rather than fabricating an action."
)

# ---------------------------------------------------------------------------
# Internal ids section header
# ---------------------------------------------------------------------------

INTERNAL_IDS_SECTION_HEADER = (
    "Internal allowed ids — do NOT use as business wording.\n"
    "Use these only in JSON payload fields where ids are required.\n"
    "Do NOT mention these ids in title, explanation, handler_text,\n"
    "producer_text, request prompt text, or user-visible preview."
)

# ---------------------------------------------------------------------------
# JSON-only output instruction
# ---------------------------------------------------------------------------

JSON_ONLY_INSTRUCTION = "Only output the JSON object — no markdown fences, no commentary."

# ---------------------------------------------------------------------------
# Default schema version
# ---------------------------------------------------------------------------

DEFAULT_FACTS_SCHEMA_VERSION = "1.0"
