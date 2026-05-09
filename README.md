# NL2SPL

Natural Language to Structured Prompt Language Compiler

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

NL2SPL converts natural language descriptions into SPL (Structured Prompt Language) code. It uses a multi-stage pipeline with LLM-powered semantic analysis and code-based compilation.

**Current Version**: v0.1.0 (Sprint 5 - Integration Complete)

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd nl2spl

# Install in development mode
pip install -e ".[dev]"
```

### 2. Configuration

Create a `.env` file in the project root:

```bash
# Required: LLM API configuration
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1  # Or your custom endpoint

# Optional: Model selection
LLM_MODEL=gpt-4o  # Default: gpt-4o

# Optional: Logging
LOG_LEVEL=INFO
LOG_FILE=logs/nl2spl.log
```

Or copy from the example:
```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Usage

#### Python API

```python
from pathlib import Path
from dotenv import load_dotenv
from nl2spl.config import load_config
from nl2spl.pipeline.orchestrator import PipelineOrchestrator

# Load environment variables
load_dotenv(Path(".env"))

# Load configuration
config = load_config()

# Create orchestrator
orchestrator = PipelineOrchestrator(config)

# Run pipeline
raw_text = """
Task family: Internal newsletters and announcements.
Inputs for each run: A user request, optional known topics.
Required outputs: A draft communication, completion status.
Reusable process: First determine communication type. Then identify missing fields.
Policies: Do not invent facts. Require evidence for claims.
Failure handling: Missing timeframe, evidence shortage.
Delegation policy: Optional source gathering if bounded.
"""

result = orchestrator.run(raw_text)
print(result.spl_text)
```

#### Command Line

```bash
# Run with default settings
python -m nl2spl.main input.txt

# Run with a custom output directory and run name
python -m nl2spl.main input.txt --output-dir output --run-name example
```

## Architecture

The pipeline consists of 12 stages organized in a top-down decomposition approach:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Input Text                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: SpanSlicer (LLM)                                      │
│  Split text into semantic spans                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: FieldRouter (LLM)                                     │
│  Route spans to 6 semantic fields                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: AmbiguityResolver (LLM)                               │
│  Resolve ambiguous spans                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: FlowAssembler (LLM)                                   │
│  Determine flow structure (main/alternative/exception)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 5: BlockAssembler (LLM)                                  │
│  Organize blocks within flows (sequential/if/for/while)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 6: ResourceExtractor (LLM)                               │
│  Extract variables, files, APIs                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 7: StepExtractor (LLM)                                   │
│  Extract atomic actions (steps)                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 8: ProfileExtractor (LLM)                                │
│  Extract persona, audience, concepts                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 9: ConstraintExtractor (LLM)                             │
│  Extract constraints (prohibitions, requirements, gates, etc.)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 9.5: IRNormalizer (Code)                                 │
│  Normalize and validate all IRs                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 10: WorkerAssembler (Code)                               │
│  Assemble worker structure                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 11: SPLRenderer (Code)                                   │
│  Render final SPL text                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        SPL Output                               │
└─────────────────────────────────────────────────────────────────┘
```

### Stage Types

- **LLM Stages** (1-9): Use Large Language Models for semantic analysis
- **Code Stages** (9.5-11): Pure code logic for compilation and rendering

## SPL Output Example

```spl
[DEFINE_AGENT: NewsletterAgent "Internal communications specialist"]

[DEFINE_PERSONA:]
    ROLE: Internal communications specialist
    STYLE: Professional and clear
[END_PERSONA]

[DEFINE_AUDIENCE:]
    TARGET: Internal teams
[END_AUDIENCE]

[DEFINE_VARIABLES:]
    "User request" user_request: string
    "Draft communication" draft: string
    "Completion status" status: boolean
[END_VARIABLES]

[DEFINE_CONSTRAINTS:]
    [PROHIBITION]
        Do not invent facts
        TARGETS: global
    [END_PROHIBITION]
    [EVIDENCE]
        Require evidence for claims
        TARGETS: global
    [END_EVIDENCE]
[END_CONSTRAINTS]

[DEFINE_WORKER: "Draft internal newsletter" NewsletterAgent]
    [INPUTS]
        REQUIRED <REF>user_request</REF>
        OPTIONAL <REF>known_topics</REF>
    [END_INPUTS]
    [OUTPUTS]
        REQUIRED <REF>draft</REF>
        REQUIRED <REF>status</REF>
    [END_OUTPUTS]
    [MAIN_FLOW]
        [SEQUENTIAL]
            COMMAND: Determine communication type
            COMMAND: Identify missing fields
            COMMAND: Draft communication
            COMMAND: Set completion status
    [END_MAIN_FLOW]
    [EXCEPTION_FLOW: Missing information]
        [SEQUENTIAL]
            REQUEST_INPUT: Request missing information
    [END_EXCEPTION_FLOW]
[END_WORKER]

[END_AGENT]
```

## Development

### Setup

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Create .env file
cp .env.example .env
# Edit .env with your API key
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=nl2spl --cov-report=html

# Run specific test file
pytest tests/unit/test_span_slicer.py

# Run integration tests (requires API key)
pytest tests/integration/ -v
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Auto-fix linting issues
ruff check src/ --fix

# Format code
ruff format src/
```

### Project Structure

```
nl2spl/
├── src/nl2spl/                  # Source code
│   ├── ir/                      # IR data models (11 files)
│   │   ├── span_ir.py           # Semantic span
│   │   ├── field_route_ir.py    # Field routing
│   │   ├── flow_structure_ir.py # Flow structure
│   │   ├── block_structure_ir.py# Block structure
│   │   ├── resource_registry_ir.py # Resources
│   │   ├── symbol_table.py      # Symbol table
│   │   ├── step_ir.py           # Step definition
│   │   ├── agent_profile_ir.py  # Agent profile
│   │   ├── constraint_ir.py     # Constraints
│   │   └── worker_ir.py         # Worker structure
│   ├── llm/                     # LLM client
│   │   ├── client.py            # OpenAI client wrapper
│   │   └── prompts.py           # Prompt templates
│   ├── pipeline/                # Pipeline stages
│   │   ├── orchestrator.py      # Pipeline coordinator
│   │   └── stages/              # 12 stage implementations
│   ├── compiler/                # SPL compiler
│   │   └── spl_formatter.py     # SPL formatting
│   ├── validator/               # Validation
│   │   └── static_validator.py  # Static validation
│   ├── errors/                  # Error handling
│   │   └── exceptions.py        # Custom exceptions
│   └── utils/                   # Utilities
│       ├── logger.py            # Logging setup
│       └── persistence.py       # Checkpoint saving
├── tests/                       # Tests
│   ├── unit/                    # Unit tests (169 tests)
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test fixtures
├── docs/                        # Documentation
├── output/                      # Intermediate results
├── .env.example                 # Environment template
├── pyproject.toml               # Project configuration
└── README.md                    # This file
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | API base URL |
| `LLM_MODEL` | No | `gpt-4o` | LLM model name |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_FILE` | No | - | Log file path |

### Pipeline Configuration

```python
from nl2spl.config import PipelineConfig, LLMConfig

config = PipelineConfig(
    llm=LLMConfig(
        model="gpt-4o",
        max_tokens=4096,
        temperature=0.0,
    ),
    output_dir=Path("output"),
    run_name="example",
    save_intermediate=True,
    log_level="INFO",
)
```

Each run writes all artifacts into one run directory. With the example above,
intermediate JSON checkpoints are saved under stable names such as
`output/example/stage1_span_slicer.json`, and the final SPL is saved separately
as `output/example/final_spl.txt`.

## Testing

### Test Coverage

- **Unit Tests**: 169 tests covering all stages
- **Integration Tests**: End-to-end pipeline tests
- **Coverage**: >80% code coverage

### Running Tests

```bash
# Quick test run
pytest -q

# Verbose output
pytest -v

# With coverage report
pytest --cov=nl2spl --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=nl2spl --cov-report=html
# Open htmlcov/index.html in browser
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings (Google style)
- Run `ruff check` and `mypy` before committing

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenAI for GPT models
- The SPL specification authors
- All contributors to this project

## Support

- **Issues**: GitHub Issues
- **Documentation**: See `docs/` directory
- **Examples**: See `tests/fixtures/` for sample inputs/outputs
