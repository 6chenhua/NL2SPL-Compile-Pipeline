# NL2SPL

Natural Language to Structured Prompt Language Compiler.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

NL2SPL compiles natural-language process descriptions into SPL (Structured Prompt Language) through a 12-stage pipeline. Nine stages call an LLM for semantic analysis; stages 9.5, 10, and 11 are pure code that normalizes, assembles, and renders the final SPL.

The compiler is intentionally not a one-shot "ask the model for SPL" flow. Each LLM stage emits a constrained IR. Downstream code stages enforce structural consistency, validate against information requirements (IRS), gate assumed content, and produce provenance traces and diagnostics. The output is a **source-backed partial SPL** — complete where evidence supports it, partial with diagnostics where evidence is missing.

### Key design properties

- **No invention**: Commands, handlers, and worker invocations require source evidence. Missing evidence produces diagnostics, not fabricated behavior.
- **Partial-first**: The compiler renders what it can prove from source and diagnoses what it cannot.
- **Worker-aware execution**: Stage 3.5 always builds a `WorkerPlanIR`; downstream stages run through worker-scoped flow, block, resource, step, normalization, and assembly paths.
- **IRS-driven validation**: The Information Requirements Specification (IRS) defines per-construct slot contracts. Post-normalize IRS is the final construct-level diagnostic authority.

## Quick Start

### Installation

```bash
git clone <repository-url>
cd nl2spl
pip install -e ".[dev]"
```

### Configuration

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LOG_LEVEL=INFO
LOG_FILE=logs/nl2spl.log
```

Or copy the template:

```bash
cp .env.example .env
```

### Python API

```python
from pathlib import Path

from dotenv import load_dotenv

from nl2spl.config import load_config
from nl2spl.pipeline.orchestrator import PipelineOrchestrator

load_dotenv(Path(".env"))

config = load_config()
orchestrator = PipelineOrchestrator(config)

raw_text = """
Task family: Internal newsletters and announcements.
Inputs for each run: A user request, optional known topics.
Required outputs: A draft communication, source evidence set, assumptions log.
Reusable process: First determine communication type. Then identify missing fields.
If sources are needed and available, retrieve them using approved source recipes.
Policies: Do not invent facts. Require evidence for claims.
"""

result = orchestrator.run(raw_text)
print(result.spl_text)
print(result.compile_diagnostics)
```

### Command Line

```bash
python -m nl2spl.main input.txt
python -m nl2spl.main input.txt --output-dir output --run-name example
```

The installed console script is also available:

```bash
nl2spl input.txt
```

## Architecture

### Data flow

```
raw_text → InputAdapter → CanonicalCompileInput → [Stage 1–11] → SPL text
```

The `InputAdapter` (stage 0) converts raw text into a structured `CanonicalCompileInput` containing hard facts (inputs, outputs, failure modes, delegation intents), compile hints, and evidence refs. Adapter parsing is deterministic; semantic routing refinement happens in Stage 2.

`PipelineOrchestrator.run()` coordinates stages through a flat `intermediate: dict[str, Any]`. Each LLM stage emits a constrained IR; code stages normalize, assemble, and render.

### Worker-aware execution path

Stage 3.5 introduces `WorkerPlanIR` with per-worker ownership. Stages 4–10 consume worker-scoped IRs (`WorkerFlowPlanIR`, `WorkerBlockPlanIR`, `WorkerStepPlanIR`) and Stage 10 assembles the final `WorkerIR` with child workers where source evidence supports delegation.

### Pipeline stages

| Stage | Name | Kind | Key output |
|-------|------|------|------------|
| 0 | InputAdapter | Code / LLM | `CanonicalCompileInput` (hard facts, hints, evidence) |
| 1 | SpanSlicer | LLM | `List[SpanIR]` — text spans with section/field routing |
| 2 | FieldRouter | LLM | `FieldRouteIR` — span-to-construct routing |
| 3 | AmbiguityResolver | LLM | Resolved spans and routes |
| **3.5** | **WorkerBoundaryPlanner** | **LLM + Code** | **`WorkerPlanIR`** — worker ownership, handoffs, candidates |
| 4 | FlowAssembler | LLM | `WorkerFlowPlanIR` |
| 5 | BlockAssembler | LLM | `WorkerBlockPlanIR` |
| 6 | ResourceExtractor | LLM | `SymbolTable` + resource registry |
| 7 | StepExtractor | LLM | `WorkerStepPlanIR` |
| 8 | ProfileExtractor | LLM | `AgentProfileIR` — persona, constraints |
| 9 | ConstraintExtractor | LLM | `List[ConstraintIR]` |
| 9.5 | IRNormalizer | Code | Normalized IRs, `INVOKE_WORKER` materialization, diagnostics |
| 10 | WorkerAssembler | Code | `WorkerIR` AST with child worker definitions |
| 11 | SPLRenderer | Code | SPL text + validation diagnostics |

**Stage 3.5** is the most architecturally significant LLM stage. It splits into sub-phases: 3.5a (candidate extraction via LLM), 3.5b (boundary decisions via LLM), then a deterministic materializer (3.5c) building `WorkerPlanIR`. The orchestrator provides defensive repair for unassigned behavior spans.

### IRS — Information Requirements Specification

IRS is the rule engine that sits between LLM inference and deterministic code. It defines **per-construct slot contracts** and runs with post-normalize final authority:

**1. Data model** (`compiler/construct_registry.py`) — `SPLConstructRegistry` holds the default construct definitions:

```
EXCEPTION_FLOW
├── condition         [required_for_partial, evidence: failure_mode]
├── handler_action    [renderable_without, missing → missing_handler]
└── trigger_step      [post-MVP]

GENERAL_COMMAND
├── action_text       [syntax_required]
├── source_evidence   [missing → assumed_command_not_renderable]
└── result_variable   [optional]

REQUEST_INPUT
├── prompt_text       [syntax_required]
└── value_target      [missing → type_or_contract_ambiguity]

CALL_API
├── api_name          [syntax_required]
├── call_action       [distinguishes mention from executable]
└── integration_evidence

INVOKE_WORKER
├── target_worker     [syntax_required]
├── handoff_id
├── input_bindings
└── output_bindings

CHILD_WORKER, WORKER_CANDIDATE, REQUIRED_OUTPUT ...
```

Each slot specifies: whether it's syntax-required, required for partial/complete rendering, what evidence kinds prove it, what diagnostic kind to emit when missing, and whether it can be inferred or suggested.

**2. Final authority** (`compiler/irs/checkers/post_normalize.py`) — After normalized worker-scoped IR is assembled, post-normalize IRS emits authoritative construct diagnostics through `IRSRunner` and `DiagnosticProjector`, such as `missing_handler`, `missing_output_producer`, `type_or_contract_ambiguity`, and `assumed_command_not_renderable`.

Output feeds into the Executable Gate (below), provenance aggregation, and the final compile report.

### Fact bridges

Deterministic bridges in `pipeline/fact_bridges.py` convert adapter hard facts into partial IR skeletons **without inventing executable behavior**:

- **`bridge_failure_modes_worker_scoped()`**: Creates worker-scoped `ExceptionFlow` skeletons from `FailureModeFact` objects when route annotations have not already materialized them. No handler blocks or steps are created — the `missing_handler` diagnostic surfaces the gap.
- **`bridge_delegation_intents()`**: Emits `type_or_contract_ambiguity` diagnostics for delegation intents without valid handoff contracts.

### Executable Gate

`pipeline/executable_gate.py` prevents unsourced commands from entering the rendered SPL. It checks:
- Step has source evidence → passes
- Step is compiler scaffolding (e.g., `INVOKE_WORKER` from a valid handoff) → passes
- Step lacks source evidence → blocked, `assumed_command_not_renderable` diagnostic

### Provenance

`pipeline/provenance.py` aggregates `TraceRecord` entries linking every materialized SPL element back to its source spans, sections, and packets. Structural NL inputs produce richer provenance chains; generic NL inputs produce span-level traces. Assumed or inferred traces are marked `needs_confirmation`.

### Output artifacts

Each run produces:

| File | Description |
|------|-------------|
| `final_spl.txt` | Rendered SPL text |
| `compile_report.txt` | Compact compilation summary with completeness and diagnostic counts |
| `feedback_report.md` | User-facing report explaining partial status, missing slots, blocked commands, assumptions, and provenance |

### Configuration surface

`PipelineConfig` now keeps operational settings only: LLM connection, output paths, logging, validation, and retry behavior. Migration feature flags and compatibility fallback switches have been removed; worker-aware execution, split Stage 3.5 planning, Stage 6 structured resource context, resource name filtering, Stage 2 fail-fast route refinement, and post-normalize IRS are the default behavior.

## SPL Output Shape

Generated SPL follows the grammar in `docs/spl_grammar.txt`. The output is source-backed: only constructs with source evidence are rendered as executable SPL; missing evidence produces partial skeletons with diagnostics.

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent links or unseen facts
        Evidence: Require evidence for sourced claims
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "A user request" user_request: text
        "Optional known topics" known_topics: List [text]
        "A draft communication artifact" draft_communication_artifact: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Source retrieval." Worker_retrieve_sources]
        [INPUTS]
            OPTIONAL <REF>connectors_or_source_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>source_evidence_set</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            ...
        [END_MAIN_FLOW]
    [END_WORKER]
    [DEFINE_WORKER: "Main worker" MainWorker]
        [INPUTS]
            REQUIRED <REF>user_request</REF>
            OPTIONAL <REF>known_topics</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Determine the type of communication requested ...]
                COMMAND-2 [INVOKE Worker_retrieve_sources WITH ... RESPONSE ... SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [EXCEPTION_FLOW: Missing timeframe]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```

Note: Exception flows without handler actions are rendered as partial skeletons — the `missing_handler` diagnostic is emitted separately.

## Project Structure

```text
nl2spl/
├── src/nl2spl/
│   ├── adapters/              # InputAdapter — raw text → CanonicalCompileInput
│   │   ├── base.py            #   Abstract adapter interface
│   │   ├── registry.py        #   Adapter registry + routing
│   │   ├── structural_nl.py   #   Rule-based structural NL parser
│   │   ├── generic_nl.py      #   Freeform input adapter
│   │   ├── llm_engine.py      #   Adapter fact parser utilities
│   │   └── fact_verifier.py   #   Adapter fact verification
│   ├── canonical/             # CanonicalCompileInput contract
│   │   └── compile_input.py   #   HardFacts, FailureModeFact, DelegationIntentFact, hints
│   ├── ir/                    # Pydantic v2 dataclass IRs
│   │   ├── span_ir.py         #   SpanIR
│   │   ├── field_route_ir.py  #   FieldRouteIR
│   │   ├── flow_structure_ir.py  # FlowStructureIR, ExceptionFlow
│   │   ├── block_structure_ir.py # BlockStructureIR
│   │   ├── step_ir.py         #   StepIR
│   │   ├── symbol_table.py    #   SymbolTable (flat + worker-scoped composite key)
│   │   ├── worker_plan_ir.py  #   WorkerPlanIR, WorkerSpecIR, WorkerFlowPlanIR, etc.
│   │   ├── worker_ir.py       #   WorkerIR AST (Stage 10 output)
│   │   ├── constraint_ir.py   #   ConstraintIR
│   │   ├── agent_profile_ir.py #  AgentProfileIR
│   │   ├── resource_registry_ir.py
│   │   └── diagnostics.py     #   CompileDiagnostic
│   ├── compiler/              # Deterministic compiler components
│   │   ├── construct_registry.py  # SPLConstructRegistry + ConstructIRS
│   │   ├── irs_prompt_builder.py  # IRS checklist utilities
│   │   ├── diagnostic_registry.py # Standard diagnostic kinds
│   │   ├── diagnostic_analyzer.py # Diagnostic analysis + consolidation
│   │   ├── producer_index.py      # Producer/consumer index for Gate
│   │   ├── completeness.py        # Completeness assessment
│   │   ├── assumptions.py         # Assumption tracking
│   │   ├── compile_result.py      # PipelineResult
│   │   ├── report_renderer.py     # Compile report rendering
│   │   ├── feedback_report_renderer.py  # User-facing feedback report
│   │   ├── spl_formatter.py       # SPL formatting
│   │   └── analyzers/
│   │       └── semantic_conflict.py  # LLM conflict analyzer
│   ├── llm/                   # LLM client
│   │   ├── client.py          #   LLMClient (OpenAI SDK, JSON mode)
│   │   └── prompts.py         #   Prompt file loader
│   ├── pipeline/              # Pipeline orchestration + stages
│   │   ├── orchestrator.py    #   PipelineOrchestrator — full pipeline coordinator
│   │   ├── executable_gate.py #   Gate that blocks unsourced commands
│   │   ├── fact_bridges.py    #   FailureModeFact → ExceptionFlow bridges
│   │   ├── provenance.py      #   ProvenanceAggregator — TraceRecord chains
│   │   ├── worker_plan_validator.py  # Worker plan structural validation
│   │   └── stages/            #   Stage 1 through Stage 11
│   │       ├── stage1_span_slicer.py
│   │       ├── stage2_field_router.py
│   │       ├── stage3_ambiguity_resolver.py
│   │       ├── stage3_5_worker_boundary_planner/  # Multi-file stage
│   │       │   ├── executor.py        # Stage entry + LLM orchestration
│   │       │   ├── planner.py         # 3.5a/3.5b LLM call logic
│   │       │   ├── plan_parser.py     # LLM output parser
│   │       │   ├── materializer.py    # 3.5c deterministic materializer
│   │       │   ├── prompt_builder.py  # Prompt construction
│   │       │   └── decision_validator.py
│   │       ├── stage4_flow_assembler/
│   │       │   ├── executor.py        # Worker-scoped flow assembly entry
│   │       │   ├── assembler.py
│   │       │   ├── flow_parser.py
│   │       │   ├── span_filter.py
│   │       │   ├── prompt_builder.py
│   │       │   └── irs_checker.py     # Stage 4 IRS post-hoc check
│   │       ├── stage5_block_assembler/
│   │       ├── stage6_resource_extractor/
│   │       │   ├── extractor.py
│   │       │   ├── legacy.py          # Compatibility helpers for direct stage tests
│   │       │   ├── worker_scoped.py   # Worker-scoped entry
│   │       │   └── resource_name_filter.py
│   │       ├── stage7_step_extractor/
│   │       │   ├── extractor.py
│   │       │   ├── legacy.py          # Compatibility helpers for direct stage tests
│   │       │   ├── worker_scoped.py   # Worker-scoped entry
│   │       │   └── irs_checker.py     # IRS framework test helper
│   │       ├── stage8_profile_extractor.py
│   │       ├── stage9_constraint_extractor.py
│   │       ├── stage9_5_normalizer/
│   │       │   ├── normalizer.py      # Normalizer facade
│   │       │   ├── worker_scoped.py   # Worker-scoped path
│   │       │   ├── worker_handoffs.py # INVOKE_WORKER materialization
│   │       │   ├── normalization.py
│   │       │   ├── helpers.py
│   │       │   ├── flow_classification.py
│   │       │   └── validation.py
│   │       ├── stage10_worker_assembler/
│   │       │   ├── assembler.py
│   │       │   ├── child_worker_builder.py
│   │       │   ├── step_resolver.py
│   │       │   └── block_utils.py
│   │       └── stage11_spl_renderer/
│   │           ├── renderer.py
│   │           ├── block_renderer.py
│   │           ├── clause_builder.py
│   │           ├── text_utils.py
│   │           └── formatting.py
│   ├── errors/                # Custom exceptions
│   ├── utils/                 # Logging and persistence
│   └── main.py                # CLI entry point
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── multi_worker/      # Deterministic WorkerPlanIR fixtures
├── prompts/                   # LLM system prompt .txt files
├── docs/                      # Design docs, implementation plans, reports
├── examples/
│   ├── usage.py               # Demo script with env-based LLM config
│   └── output/                # Example run outputs (internal-comms, etc.)
├── pyproject.toml
└── README.md
```

## Development

### Testing

```bash
pytest                                    # All tests
pytest tests/unit                         # Unit tests only
pytest tests/integration -v               # Integration tests
pytest tests/integration/test_multi_worker_pipeline.py -q  # Multi-worker rollout
```

The multi-worker rollout suite uses deterministic `WorkerPlanIR` fixtures under `tests/fixtures/multi_worker/` and checks golden SPL invariants without making LLM calls. It covers Stage 9.5–11 IR-level paths plus mocked-LLM `PipelineOrchestrator.run()` regressions.

### Code Quality

```bash
ruff check src tests     # Lint
ruff format src tests    # Format
mypy src                 # Strict type check
```

### Conventions

- Python 3.11+ with `from __future__ import annotations` in every file
- Pydantic v2 dataclass IRs (NOT BaseModel) in `src/nl2spl/ir/`
- Line length 100, `ruff` with rules `E, F, W, I, N, UP, B`
- `mypy` strict mode
- All stage modules use a `PipelineStage` subclass with `name` property and `execute()` method
- LLM stages under `pipeline/stages/`; code-only stages (9.5, 10, 11) follow the same base class
- Production orchestration uses worker-scoped stage paths; direct `execute()` helpers exist only where unit tests still cover stage-local parsing.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI-compatible API key |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | API base URL |
| `LLM_MODEL` | No | `gpt-4o` | Model name for LLM calls |
| `LLM_MAX_TOKENS` | No | `4096` | Max tokens per LLM response |
| `LLM_TEMPERATURE` | No | `0.0` | LLM sampling temperature |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_FILE` | No | — | Optional log file path |

Each run writes intermediate checkpoints (when `save_intermediate=True`) and `final_spl.txt` into `output/<run_name>/`.

## Documentation

Core design documents:

- `docs/spl_nl_to_spl_design_document_v4.md` — v4 compiler and IR design
- `docs/nl_2_spl_compiler_architecture_irs_v_5.md` — v5 IRS architecture overview
- `docs/spl_grammar.txt` — SPL grammar reference
- `docs/prompt_design_document.md` — LLM prompt contracts by stage
- `docs/multi_worker_system_design.md` — Multi-worker architecture and WorkerPlanIR
- `docs/migration-worker-aware-pipeline.md` — Worker-aware migration plan

Input adapter:

- `docs/InputAdapter/nl_2_spl_input_adapter_design.md` — Adapter architecture
- `docs/InputAdapter/input_adapter_api_contract.md` — CanonicalCompileInput API
- `docs/InputAdapter/input_adapter_progress.md` — Implementation status

IRS (v5):

- `docs/implementation/v5-irs/` — Phase-by-phase IRS implementation reports
- `docs/nl_2_spl_compiler_architecture_irs_v_5.md` — IRS architecture

Implementation plans and reports:

- `docs/implementation/partial_spl_mvp_design.md` — Partial SPL MVP design
- `docs/implementation/worker-aware-migration/` — Worker-aware migration task breakdown

## License

This project is licensed under the MIT License.
