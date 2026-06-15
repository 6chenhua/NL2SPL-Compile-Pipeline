"""LLM Repair Context — registry-driven prompt context projection layer.

This package provides the infrastructure for projecting structured
backend state into LLM-consumable prompt context.  It does NOT:
  - Decide issue repairability (that is RepairCatalog's job)
  - Declare new patch capabilities (that is PatchRegistry's job)
  - Modify IR or final SPL
  - Call LLM directly (that is the handler's job)
  - Parse rendered SPL / feedback_report / stage debug JSON
"""

from __future__ import annotations
