"""Prompt templates for NL2SPL pipeline."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"

# Mapping of stage names to prompt file paths
STAGE_PROMPT_FILES = {
    "stage0_section_mapper": PROMPTS_DIR / "stage0_section_mapper.txt",
    "stage1": PROMPTS_DIR / "stage1_system.txt",
    "stage1_source_constrained": PROMPTS_DIR / "stage1_source_constrained_segmentation_system.txt",
    "stage1_source_constrained_user": PROMPTS_DIR / "stage1_source_constrained_segmentation_user_template.txt",
    "stage2": PROMPTS_DIR / "stage2_system.txt",
    "stage3": PROMPTS_DIR / "stage3_system.txt",
    "stage3_5": PROMPTS_DIR / "stage3_5_system.txt",
    "stage3_5a": PROMPTS_DIR / "stage3_5a_candidate_extractor_system.txt",
    "stage3_5b": PROMPTS_DIR / "stage3_5b_boundary_decision_system.txt",
    "stage4": PROMPTS_DIR / "stage4_system.txt",
    "stage5": PROMPTS_DIR / "stage5_system.txt",
    "stage6": PROMPTS_DIR / "stage6_system.txt",
    "stage6_5_condition_reference": PROMPTS_DIR / "stage6_5_condition_reference_system.txt",
    "stage7": PROMPTS_DIR / "stage7_system.txt",
    "stage8": PROMPTS_DIR / "stage8_system.txt",
    "stage9": PROMPTS_DIR / "stage9_system.txt",
    "input_adapter_fact_extractor": PROMPTS_DIR / "input_adapter_fact_extractor_system.txt",
    "stage2_adapter_guided": PROMPTS_DIR / "stage2_adapter_guided_system.txt",
    "external_capability_semantic_extractor": (
        PROMPTS_DIR / "capability_semantic_extractor_system.txt"
    ),
}


def load_prompt(stage_name: str) -> str:
    """Load prompt template for a stage.

    Args:
        stage_name: Name of the stage (e.g., "stage1", "stage2")

    Returns:
        Prompt template text
    """
    if stage_name not in STAGE_PROMPT_FILES:
        available_stages = list(STAGE_PROMPT_FILES.keys())
        raise ValueError(
            f"Unknown stage: {stage_name}. Available stages: {available_stages}"
        )
    prompt_file = STAGE_PROMPT_FILES[stage_name]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8")


def get_available_stages() -> list[str]:
    """Get list of all available stage names.

    Returns:
        List of stage names (e.g., ["stage1", "stage2", ...])
    """
    return list(STAGE_PROMPT_FILES.keys())
