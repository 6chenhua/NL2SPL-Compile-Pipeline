"""Run Stage 3.5 prompt against internal-comms intermediate files and diff."""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from common import make_client, make_config, normalize
from nl2spl.adapters.structural_nl import StructuralNLAdapter
from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBoundaryDecisionIR,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import WorkerBoundaryPlanner
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    WorkerPlanMaterializer,
)

INTERMEDIATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "output" / "internal-comms"
)

STAGE_NAME = "stage3_5_worker_boundary_planner"

RAW_TEXT = """
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


def build_canonical_input() -> CanonicalCompileInput:
    """Run the StructuralNLAdapter on the raw text to produce CanonicalCompileInput."""
    adapter = StructuralNLAdapter()
    return adapter.adapt(RAW_TEXT)


def load_json(filename: str) -> dict[str, Any]:
    path = INTERMEDIATE_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Intermediate file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_spans() -> list[SpanIR]:
    data = load_json("stage1_span_slicer.json")
    spans_data = data["result"]["spans"]
    return [
        SpanIR(
            span_id=s["span_id"],
            text=s["text"],
            ambiguity=AmbiguityInfo(
                is_ambiguous=s["ambiguity"]["is_ambiguous"],
                reasons=s["ambiguity"].get("reasons", []),
                needs_split=s["ambiguity"].get("needs_split", False),
            ),
            source_section_id=s.get("source_section_id"),
            source_packet_id=s.get("source_packet_id"),
        )
        for s in spans_data
    ]


def load_routes() -> FieldRouteIR:
    data = load_json("stage2_field_router.json")
    routes = data["result"]["routes"]
    return FieldRouteIR(
        identity=routes.get("identity", []),
        audience=routes.get("audience", []),
        rules=routes.get("rules", []),
        domain=routes.get("domain", []),
        integrations=routes.get("integrations", []),
        behavior=routes.get("behavior", []),
    )


def load_expected_candidates() -> list[dict[str, Any]]:
    return load_json("stage3_5a_candidate_task_units.json")["result"]["candidates"]


def load_expected_decisions() -> list[dict[str, Any]]:
    return load_json("stage3_5b_worker_boundary_decisions.json")["result"]["decisions"]


def load_expected_materializer_output() -> dict[str, Any]:
    return load_json("stage3_5c_worker_plan_materializer.json")["result"]


def run_full_split_path():
    """Run Stage 3.5 split path (3.5a → 3.5b → 3.5c) with real LLM and diff."""
    spans = load_spans()
    routes = load_routes()
    canonical_input = build_canonical_input()
    expected = load_expected_materializer_output()

    config = make_config(STAGE_NAME)
    client = make_client(config)
    planner = WorkerBoundaryPlanner(config, client)

    actual = planner.execute((spans, routes, canonical_input))
    actual_dict = asdict(actual)

    _print_comparison(STAGE_NAME, expected, actual_dict)

    actual_path = INTERMEDIATE_DIR / "stage3_5_worker_boundary_planner_actual.json"
    actual_path.write_text(
        json.dumps(actual_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nActual output saved to: {actual_path}")


def run_materializer_only():
    """Run the deterministic materializer (3.5c) with stored 3.5a/3.5b outputs."""
    candidates_raw = load_expected_candidates()
    decisions_raw = load_expected_decisions()
    canonical_input = build_canonical_input()
    expected = load_expected_materializer_output()

    candidates = [_build_candidate(c) for c in candidates_raw]
    decisions = [_build_decision(d) for d in decisions_raw]

    hard_inputs = [
        ContractFieldIR(f.name, f.data_type, f.required, f.description, "input")
        for f in canonical_input.hard_facts.inputs
    ]
    hard_outputs = [
        ContractFieldIR(f.name, f.data_type, f.required, f.description, "output")
        for f in canonical_input.hard_facts.outputs
    ]

    behavior_span_ids = set(load_routes().behavior)
    materializer = WorkerPlanMaterializer()
    plan, warnings = materializer.materialize(
        candidates=candidates,
        decisions=decisions,
        hard_fact_inputs=hard_inputs,
        hard_fact_outputs=hard_outputs,
        behavior_span_ids=behavior_span_ids,
    )
    actual = asdict(plan)

    print("=" * 80)
    print("MATERIALIZER ONLY (no LLM)")
    print("=" * 80)
    _print_comparison("stage3_5c_materializer", expected, actual)


def _build_candidate(c: dict[str, Any]) -> CandidateTaskUnitIR:
    return CandidateTaskUnitIR(
        candidate_id=c["candidate_id"],
        source_span_ids=c.get("source_span_ids", []),
        task_text=c.get("task_text", ""),
        purpose=c.get("purpose", ""),
        candidate_kind=c.get("candidate_kind", "bounded_subtask"),
        possible_inputs=[
            ContractFieldIR(
                name=f["name"],
                data_type=f.get("data_type", "text"),
                required=f.get("required", True),
                description=f.get("description", ""),
                source=f.get("source", "input"),
            )
            for f in c.get("possible_inputs", [])
        ],
        possible_outputs=[
            ContractFieldIR(
                name=f["name"],
                data_type=f.get("data_type", "text"),
                required=f.get("required", True),
                description=f.get("description", ""),
                source=f.get("source", "output"),
            )
            for f in c.get("possible_outputs", [])
        ],
        signals=c.get("signals", []),
        risks=c.get("risks", []),
    )


def _build_decision(d: dict[str, Any]) -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id=d["candidate_id"],
        decision=d.get("decision", "keep_in_main_worker"),
        boundary_strength=d.get("boundary_strength", "moderate"),
        boundary_kind=d.get("boundary_kind", "not_a_worker"),
        rejection_reason=d.get("rejection_reason"),
        reason=d.get("reason", ""),
        evidence=d.get("evidence", []),
    )


def _print_comparison(label: str, expected: Any, actual: Any) -> None:
    expected_text = json.dumps(
        normalize(expected), ensure_ascii=False, indent=2, sort_keys=True
    )
    actual_text = json.dumps(
        normalize(actual), ensure_ascii=False, indent=2, sort_keys=True
    )

    print("=" * 80)
    print(f"{label}: EXPECTED")
    print("=" * 80)
    print(expected_text)
    print("=" * 80)
    print(f"{label}: ACTUAL")
    print("=" * 80)
    print(actual_text)

    if expected_text == actual_text:
        print("=" * 80)
        print(f"{label}: MATCH")
        print("=" * 80)
        return

    print("=" * 80)
    print(f"{label}: DIFF expected -> actual")
    print("=" * 80)
    diff = difflib.unified_diff(
        expected_text.splitlines(),
        actual_text.splitlines(),
        fromfile="expected",
        tofile="actual",
        lineterm="",
    )
    print("\n".join(diff))


if __name__ == "__main__":
    import sys

    if "--materializer-only" in sys.argv:
        run_materializer_only()
    else:
        run_full_split_path()
