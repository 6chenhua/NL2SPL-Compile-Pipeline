"""Example usage of NL2SPL pipeline with v5 IRS diagnostics."""

import os
from pathlib import Path

from dotenv import load_dotenv

from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.config import LLMConfig, Stage1SegmentationConfig, load_config
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def main() -> None:
    """Run example."""
    load_dotenv()  # ensure .env is loaded before LLMConfig construction

    # LLM configuration from environment variables
    llm_config = LLMConfig(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
    )

    # Read input from a text file
    input_path = Path(__file__).parent / "input" / "wjf.txt"
    raw_text = input_path.read_text(encoding="utf-8")

    # Load configuration
    config = load_config(
        llm=llm_config,
        log_level="INFO",
        save_intermediate=True,
        output_dir=Path(__file__).parent / "output",
        run_name="wjf",
        snapshot=SnapshotPersistenceConfig(),
        stage1=Stage1SegmentationConfig(
            mode=os.getenv("NL2SPL_STAGE1_SEGMENTATION_MODE", "llm_source_constrained")
        ),
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Run pipeline
    result = orchestrator.run(raw_text)

    # Explicitly call the Rendering Subsystem to render the SPL text
    from nl2spl.rendering import render_full_spl
    if result.final_ir_package is not None:
        rendered_doc = render_full_spl(result.final_ir_package)
        spl_text = rendered_doc.text
    else:
        spl_text = result.spl_text

    # ── Print results ──────────────────────────────────────────────
    print("=" * 60)
    print(f"Completeness: {result.completeness}")
    print(f"SPL length:   {len(spl_text)} chars")
    print(f"Diagnostics:  {len(result.compile_diagnostics)}")
    print(f"Traces:       {len(result.traces)}")
    print(f"Assumptions:  {len(result.assumptions)}")
    print(f"Validation:   {len(result.validation_errors)} errors, "
          f"{len(result.validation_warnings)} warnings")
    print(f"Snapshot:     {result.spl_editing_snapshot_status}")
    if result.spl_editing_snapshot_path:
        print(f"Snapshot path:{result.spl_editing_snapshot_path}")
    if result.spl_editing_snapshot_error:
        print(f"Snapshot err: {result.spl_editing_snapshot_error}")
    print("=" * 60)

    if result.compile_diagnostics:
        print("\nCompile Diagnostics:")
        for d in result.compile_diagnostics:
            print(f"  [{d.kind}] {d.message[:120]}")
            if d.target_ref:
                print(f"           target: {d.target_ref}")

    if result.assumptions:
        print(f"\nAssumptions ({len(result.assumptions)}):")
        for a in result.assumptions:
            print(f"  {a.assumption_id}: {a.text[:120]}")

    if result.validation_errors:
        print("\nValidation Errors:")
        for e in result.validation_errors:
            print(f"  - {e}")

    if result.validation_warnings:
        print("\nValidation Warnings:")
        for w in result.validation_warnings:
            print(f"  - {w}")

    # ── Save outputs ───────────────────────────────────────────────
    run_dir = config.run_dir

    # feedback_report.md
    feedback = render_feedback_report(
        spl_text=spl_text,
        completeness=result.completeness,
        diagnostics=result.compile_diagnostics,
        assumptions=result.assumptions,
        traces=result.traces,
        adapter_warnings=result.adapter_warnings,
        validation_errors=result.validation_errors,
        validation_warnings=result.validation_warnings,
    )
    feedback_path = run_dir / "feedback_report.md"
    feedback_path.write_text(feedback, encoding="utf-8")
    print(f"Feedback report saved: {feedback_path}")

    # SPL text
    spl_path = run_dir / "final_spl.txt"
    spl_path.write_text(spl_text, encoding="utf-8")
    print(f"Final SPL saved:      {spl_path}")

    print(f"\nOpen {feedback_path} for the human-readable feedback report.")


if __name__ == "__main__":
    main()
