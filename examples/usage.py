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

    raw_text = """
# Internal Communications Drafting

## Task Family

**Name:** internal communications drafting  
**Scope:** Includes recurring digests and executive memos; excludes crisis communications.  
**Examples:**  
- Internal newsletters  
- Announcements  
- Update digests  
- Executive briefs  
- Related internal-communications artifacts  

## Inputs for Each Run

**Required:**  
- Topic summary  
- Target audience  
- Key dates or deadlines  

## Required Outputs

- Finished draft (Word or Google Doc, 200–500 words, no approval marks)  
- Status flag (values: `'drafting'`, `'ready for review'`, `'approved'`)  

## Reusable Process

1. Requestor provides topic/audience  
2. IC writer drafts using the standard internal communications template (Appendix A of the style guide)  
3. Routes to the relevant communications lead for review  

## Policies

**Hard:**  
- Must use the approved template  
- Must follow plain-language and inclusive tone guidelines  
- Require final sign-off from the communications lead before flagging as approved  

## Failure Handling

**Anticipated:**  
- Topic summary too vague to draft from  
- Template unavailable  
- Communications lead unresponsive for over two days  

## Delegation Policy

**Delegable:**  
- Initial drafting using template and topic summary  

**Non‑delegable:**  
- Final review and approval by communications lead

"""

    # Load configuration
    config = load_config(
        llm=llm_config,
        log_level="INFO",
        save_intermediate=True,
        output_dir=Path(__file__).parent / "output",
        run_name="demo",
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


if __name__ == "__main__":
    main()
