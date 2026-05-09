# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-06

### Added

#### Core Architecture
- Project structure with `pyproject.toml`, `src/nl2spl/`, `tests/`, `docs/`
- Configuration management (`config.py`) with LLM and pipeline settings
- Entry point (`main.py`) for CLI usage
- Error handling hierarchy (`errors/exceptions.py`)
- Logging utilities (`utils/logger.py`)
- Persistence utilities (`utils/persistence.py`) for checkpoint saving

#### IR Models (11 data models)
- `SpanIR` - Semantic text spans with ambiguity info
- `FieldRouteIR` - Field routing for 6 semantic fields
- `FlowStructureIR` - Flow structure (main/alternative/exception)
- `BlockStructureIR` - Block structure (sequential/if/for/while)
- `ResourceRegistryIR` - Resources (variables, files, APIs)
- `SymbolTable` - Variable declaration and reference management
- `StepIR` - Atomic workflow steps
- `AgentProfileIR` - Agent persona, audience, concepts
- `ConstraintIR` - Constraints (prohibitions, requirements, gates)
- `WorkerIR` - Worker assembly structure

#### LLM Client
- OpenAI-compatible API wrapper (`llm/client.py`)
- JSON and text response modes
- Retry logic with configurable attempts

#### Pipeline Stages (12 stages)
- **Stage 1: SpanSlicer** - Split text into semantic spans
- **Stage 2: FieldRouter** - Route spans to 6 semantic fields
- **Stage 3: AmbiguityResolver** - Resolve ambiguous spans
- **Stage 4: FlowAssembler** - Determine flow structure
- **Stage 5: BlockAssembler** - Organize blocks within flows
- **Stage 6: ResourceExtractor** - Extract variables, files, APIs
- **Stage 7: StepExtractor** - Extract atomic actions
- **Stage 8: ProfileExtractor** - Extract persona, audience, concepts
- **Stage 9: ConstraintExtractor** - Extract constraints
- **Stage 9.5: IRNormalizer** - Normalize and validate IRs
- **Stage 10: WorkerAssembler** - Assemble worker structure
- **Stage 11: SPLRenderer** - Render final SPL text

#### Compiler & Validator
- `SPLFormatter` - SPL text formatting and indentation
- `StaticValidator` - Static SPL validation

#### Orchestrator
- `PipelineOrchestrator` - Pipeline coordination
- End-to-end pipeline execution
- Intermediate result saving

#### Testing
- 169 unit tests covering all stages
- Integration tests for end-to-end pipeline
- Test fixtures with sample inputs/outputs
- pytest configuration and fixtures

#### Documentation
- Comprehensive README.md
- Shared context document (`docs/shared_context.md`)
- Sprint plan (`docs/sprint_plan_v2.md`)
- Developer plans for each role
- SPL specification and examples

### Technical Details

- **Python**: 3.10+
- **Dependencies**: openai, pydantic, python-dotenv
- **Dev Tools**: pytest, mypy, ruff
- **Code Quality**: 100% mypy pass, ruff linting clean
- **Test Coverage**: >80%

### Known Issues

- Stage 6 variable parsing warnings (LLM response format)
- 6 non-critical mypy type warnings (runtime unaffected)
- 4 integration tests require API key

### Contributors

- Developer A (Tech Lead) - Architecture, code review, integration
- Developer B (Pipeline Engineer) - Stage 1-3 implementation
- Developer C (Flow Engineer) - Stage 4-5 implementation
- Developer D (Resource Engineer) - Stage 6-7 implementation
- Developer E (Compiler Engineer) - Stage 8-11, SPL formatter, validator

---

## [Unreleased]

### Planned for v0.2.0
- Prompt optimization for better LLM output
- Performance analysis and optimization
- Enhanced error handling
- More comprehensive integration tests
- Documentation improvements
