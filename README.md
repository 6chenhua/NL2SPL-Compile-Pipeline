# NL2SPL

Natural Language to Structured Prompt Language Compiler.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

NL2SPL converts natural-language process descriptions into SPL (Structured Prompt Language). The compiler uses LLM calls for semantic analysis, then code stages normalize, assemble, validate, and render executable SPL text.

The current implementation is intentionally not a one-shot "ask the model for SPL" flow. Each LLM stage emits a constrained IR, and later code stages enforce structural consistency.

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
Required outputs: A draft communication, source evidence set, assumptions log, completion status.
Reusable process: First determine communication type. Then identify missing fields.
If sources are needed and available, retrieve them using approved source recipes.
Maintain provenance for externally sourced facts.
When enough required information is available, produce a draft.
If the user asks for revision, revise while rechecking constraints.
Policies: Do not invent facts. Require evidence for claims.
Delegation policy: Optional source gathering may be delegated if bounded.
"""

result = orchestrator.run(raw_text)
print(result.spl_text)
print(result.validation_warnings)
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

The pipeline has 12 stages: 9 LLM stages, one code normalizer stage, and 2 code assembly/rendering stages.

| Stage | Name | Kind | Output |
|-------|------|------|--------|
| 1 | SpanSlicer | LLM | `List[SpanIR]` |
| 2 | FieldRouter | LLM | `FieldRouteIR` + ambiguity updates |
| 3 | AmbiguityResolver | LLM | resolved spans and routes |
| 4 | FlowAssembler | LLM | `FlowStructureIR` |
| 5 | BlockAssembler | LLM | `BlockStructureIR` |
| 6 | ResourceExtractor | LLM | `ResourceRegistryIR` + `SymbolTable` |
| 7 | StepExtractor | LLM | `List[StepIR]` + updated `SymbolTable` |
| 8 | ProfileExtractor | LLM | `AgentProfileIR` |
| 9 | ConstraintExtractor | LLM | `List[ConstraintIR]` |
| 9.5 | IRNormalizer | Code | normalized IRs + diagnostics |
| 10 | WorkerAssembler | Code | `WorkerIR` with child worker definitions |
| 11 | SPLRenderer | Code | SPL text + validation diagnostics |

Important implementation details:

- Stage 4 receives compact plain text in the form `span_id: span text`; it does not pass full `SpanIR` JSON or ambiguity metadata into the prompt.
- Stage 5 receives only flow JSON enriched with concrete span text (`span_id` + `text`), so block assembly has local context without a second behavior-span blob.
- `FlowStructureIR.delegation_candidates` is the current compatibility carrier for delegation. Stage 9.5 materializes concrete `INVOKE_WORKER` steps from child-worker candidates and rejects unresolved placeholder worker invocations.
- Stage 10 builds concrete `ChildWorkerIR` definitions, and Stage 11 renders them before the main worker.
- Multi-output delegated steps can be normalized into structured result variables and emitted under `[DEFINE_TYPES:]` when a structured SPL type is required.

## SPL Output Shape

Generated SPL follows the grammar conventions used by `docs/spl_grammar.txt`, including numbered commands, explicit blocks, concrete worker names, and `<REF>...</REF>` variable references.

```spl
[DEFINE_AGENT: MainWorker "Main worker"]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
    [DEFINE_VARIABLES:]
        "The communication request provided by the user." user_request: text
        "The draft communication artifact generated as output." draft_communication_artifact: text
        "Structured result for source retrieval." child_dc_1_result: ChildDc1Result
    [END_VARIABLES]
    [DEFINE_TYPES:]
        ChildDc1Result = { retrieved_sources: List [text], provenance_log: text }
    [END_TYPES]
    [DEFINE_WORKER: "Source retrieval and provenance maintenance can be modularized." child_dc_1]
        [INPUTS]
            REQUIRED <REF>available_connectors</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>child_dc_1_result</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Retrieve sources and maintain provenance RESULT child_dc_1_result: ChildDc1Result SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
    [DEFINE_WORKER: "Main worker" MainWorker]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-2 [COMMAND Determine what kind of communication is requested based on <REF>user_request</REF>]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
[END_AGENT]
```

## Documentation

- `docs/spl_nl_to_spl_design_document_v4.md`: compiler and IR design.
- `docs/prompt_design_document.md`: LLM prompt contracts by stage.
- `docs/delegation_plan_todo.md`: WorkerPlanIR migration plan for replacing the current delegation bridge.
- `docs/multi_worker_system_design.md`: detailed multi-worker architecture and implementation guidance.
- `docs/implementation/multi_worker_collaboration_plan.md`: multi-developer collaboration plan for the WorkerPlanIR migration.
- `docs/implementation/multi_worker_dev_e_tests_rollout.md`: regression fixture, golden SPL, and rollout QA ownership.
- `docs/input_adapter_implementation_plan.md`: InputAdapter implementation plan and rollout checklist.
- `docs/input_adapter_api_contract.md`: CanonicalCompileInput and adapter API contract.
- `docs/input_adapter_progress.md`: current InputAdapter MVP implementation status and remaining work.
- `docs/spl_grammar.txt`: SPL grammar reference.
- `docs/internal_comms_generation_review.md`: review notes and resolution status for the internal-comms example.

## Development

### Testing

```bash
pytest
pytest tests/unit
pytest tests/integration -v
pytest tests/integration/test_multi_worker_pipeline.py -q
```

The multi-worker rollout suite uses deterministic WorkerPlanIR fixtures under
`tests/fixtures/multi_worker/` and checks golden SPL invariants without making
LLM calls. It includes IR-level Stage 9.5 through Stage 11 coverage plus
mocked-LLM `PipelineOrchestrator.run(...)` feature-flag regressions. The current
multi-worker flag remains default-off while rollout coverage continues to expand.

### Code Quality

```bash
ruff check src tests
ruff format src tests
mypy src
```

### Project Structure

```text
nl2spl/
├── src/nl2spl/
│   ├── ir/                       # Span, route, flow, block, resource, step, profile, constraint, worker IRs
│   ├── llm/                      # LLM client and prompt loading
│   ├── pipeline/
│   │   ├── orchestrator.py       # End-to-end pipeline coordinator
│   │   └── stages/               # Stage 1 through Stage 11 implementations
│   ├── compiler/                 # SPL formatting helpers
│   ├── validator/                # Static validation
│   ├── errors/                   # Custom exceptions
│   └── utils/                    # Logging and persistence
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
├── examples/
├── output/
├── pyproject.toml
└── README.md
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | API base URL |
| `LLM_MODEL` | No | `gpt-4o` | LLM model name |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_FILE` | No | - | Optional log file path |

Each run writes intermediate checkpoints and `final_spl.txt` into the configured run directory.

## License

This project is licensed under the MIT License.
