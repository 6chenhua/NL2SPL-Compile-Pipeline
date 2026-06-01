"""Example usage of NL2SPL pipeline with v5 IRS diagnostics."""

import os
from pathlib import Path

from dotenv import load_dotenv
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.config import load_config, LLMConfig
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def main() -> None:
    """Run example."""
    load_dotenv()  # ensure .env is loaded before LLMConfig construction

    # LLM configuration from environment variables
    llm_config = LLMConfig(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
    )

    # Sample input
    raw_text = """
# Structural Requirement: Internal Communications Drafting

## Task Family

**Name:** internal communications drafting  
**Scope:** Includes routine newsletters, announcements, update digests, and executive briefs; excludes crisis memos requiring legal review.  
**Examples:** Internal newsletters, announcements, update digests, executive briefs, and related internal-comms artifacts.

## Inputs for Each Run

**Required:**
- topic
- audience
- tone
- key facts

**Optional:** None

## Required Outputs

- polished draft
- revision history
- assumptions log
- evidence trail
- readiness status

## Reusable Process

1. Receive and parse request (topic, audience, tone, key facts)
2. Scope and ask clarifying questions for missing inputs
3. Gather allowed evidence from approved internal sources
4. Draft using organization-approved templates and brand tone
5. Review for confidentiality, citations, no invented data, approvals
6. Iterate with user on specific sections (max two rounds)
7. Finalize with revision history, assumptions log, evidence trail, readiness status
8. Deliver polished draft and artifacts

## Policies

**Hard Rules:**
- No external data
- Cite all sources
- Avoid legal/financial language
- Preserve brand tone and confidentiality
- Require approvals for sensitive topics

**Soft Rules:** None

## Failure Handling

**Anticipated Failures:**
- Missing inputs
- Tone mismatch
- Unverified facts
- Source unavailability
- Policy conflict

**Blocking Failures:** None

## Delegation Policy

**Delegable Work:**
- Drafting
- Fact-checking
- Formatting
- Revision history

**Non‑Delegable Work:**
- Approvals
- Sensitivity checks
- Final sign‑off
"""

    # Load configuration
    config = load_config(
        llm=llm_config,
        log_level="INFO",
        save_intermediate=True,
        output_dir=Path(__file__).parent / "output",
        run_name="internal-comms-3",
        enable_worker_boundary_planner=True,
        enable_worker_boundary_planner_split=True,
        # --- v5 IRS flags (non-disruptive post-hoc checks) ---
        # enable_irs_prompt_builder: Stage 4 (EXCEPTION_FLOW) +
        #   Stage 7 (4 command types). Stage 3.5 uses dedicated prompt files.
        enable_irs_prompt_builder=True,
        enable_irs_stage4_exception_flow_check=True,
        enable_irs_stage7_step_check=True,
        enable_irs_diagnostic_consolidation=True,
        adapter_llm_engine='all',
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Run pipeline
    result = orchestrator.run(raw_text)

    # ── Print results ──────────────────────────────────────────────
    print("=" * 60)
    print(f"Completeness: {result.completeness}")
    print(f"SPL length:   {len(result.spl_text)} chars")
    print(f"Diagnostics:  {len(result.compile_diagnostics)}")
    print(f"Traces:       {len(result.traces)}")
    print(f"Assumptions:  {len(result.assumptions)}")
    print(f"Validation:   {len(result.validation_errors)} errors, "
          f"{len(result.validation_warnings)} warnings")
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

    # compile_report.txt
    report_path = run_dir / "compile_report.txt"
    report_path.write_text(result.readable_report, encoding="utf-8")
    print(f"\nCompile report saved: {report_path}")

    # feedback_report.md
    feedback = render_feedback_report(
        spl_text=result.spl_text,
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
    print(f"Final SPL saved:      {spl_path}")

    print(f"\nOpen {feedback_path} for the human-readable feedback report.")
    print(f"Open {report_path} for the deterministic compile report.")


if __name__ == "__main__":
    main()
