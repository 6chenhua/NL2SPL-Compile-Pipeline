"""Example usage of NL2SPL pipeline."""

from pathlib import Path

from nl2spl.config import load_config
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def main() -> None:
    """Run example."""
    # Sample input
    raw_text = """
Task family:
Internal newsletters, announcements, update digests, executive briefs, and related
internal-comms artifacts.

Inputs for each run:
A user request, optional known topics, optional timeframe, available connectors or
source repositories, and optional format preferences.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log for any
unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested. Then identify which required
fields are still missing. Ask only the highest-value clarifying questions needed to move
forward. If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts. When enough required
information is available, produce a draft. If the user asks for revision, revise while re
checking constraints. Do not finalize if required slots remain missing unless the draft is
explicitly marked as assumption-bearing and the user confirms.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims. Limit questions
per turn. Prefer tool evidence over unnecessary user questioning. Deny finalization if
critical slots are missing or provenance fails.

Failure handling:
Missing timeframe, conflicting instructions, insufficient source access, evidence
shortage, user refusal to answer, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers.
"""

    # Load configuration
    config = load_config(
        log_level="INFO",
        save_intermediate=True,
        output_dir=Path("output"),
        run_name="internal-comms",
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Run pipeline
    result = orchestrator.run(raw_text)

    # Print results
    print("=" * 60)
    print("Generated SPL:")
    print("=" * 60)
    print(result.spl_text)

    if result.validation_errors:
        print("\nValidation Errors:")
        for error in result.validation_errors:
            print(f"  - {error}")

    if result.validation_warnings:
        print("\nValidation Warnings:")
        for warning in result.validation_warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
