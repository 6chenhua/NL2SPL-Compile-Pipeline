"""Integration characterization test for Stage 1.

Locks the E2E baseline behavior showing that the current pipeline config
produces a guard-only command 'When enough required information is available'.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nl2spl.config import LLMConfig, PipelineConfig, Stage1SegmentationConfig
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def test_stage1_llm_segmentation_characterization_e2e(tmp_path: Path) -> None:
    # 1. Setup config (default mode is legacy_packet_passthrough)
    config = PipelineConfig(
        llm=LLMConfig(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.0,
            api_key="test-api-key",
        ),
        output_dir=tmp_path / "output",
        save_intermediate=True,
        log_level="DEBUG",
        max_retries=1,
    )

    # 2. Load the real internal_comms text
    input_path = Path("examples/input/internal_comms.txt")
    assert input_path.exists(), "internal_comms.txt must exist"
    raw_text = input_path.read_text(encoding="utf-8")

    orchestrator = PipelineOrchestrator(config)

    # Mock stage-local LLM calls to match the current buggy pipeline execution of internal_comms.
    # Note: Stage 1 runs canonically (no LLM call).
    mock_llm_responses = {
        "stage2_adapter_guided": {
            "annotations": [
                {"span_id": "s15", "field": "behavior", "semantic_role": "process_step", "executable": True},
                {"span_id": "s16", "field": "behavior", "semantic_role": "process_step", "executable": True},
                {"span_id": "s17", "field": "behavior", "semantic_role": "process_step", "executable": True},
                {"span_id": "s18", "field": "behavior", "semantic_role": "process_step", "executable": True},
                {"span_id": "s19", "field": "behavior", "semantic_role": "process_step", "executable": True},
                {"span_id": "s20", "field": "rules", "semantic_role": "policy", "executable": False},
                {"span_id": "s21", "field": "rules", "semantic_role": "policy", "executable": False},
                {"span_id": "s22", "field": "rules", "semantic_role": "policy", "executable": False},
                {"span_id": "s23", "field": "rules", "semantic_role": "policy", "executable": False},
                {"span_id": "s24", "field": "rules", "semantic_role": "policy", "executable": False},
                {"span_id": "s25", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s26", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s27", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s28", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s29", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s30", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                {"span_id": "s31a", "field": "integrations", "semantic_role": "delegation_intent", "executable": True},
                {"span_id": "s31b", "field": "integrations", "semantic_role": "delegation_intent", "executable": True}
            ],
            "ambiguity_updates": [],
        },
        "stage3_ambiguity_resolver": {
            "resolved_spans": [],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": ["s20", "s21", "s22", "s23", "s24"],
                "domain": [],
                "integrations": ["s31a", "s31b"],
                "behavior": ["s15", "s16", "s17", "s18", "s19", "s25", "s26", "s27", "s28", "s29", "s30"],
            },
        },
        "stage3_5a_candidate_task_units": {
            "candidates": [
                {
                    "candidate_id": "candidate_retrieve_source_material",
                    "source_span_ids": ["s16"],
                    "task_text": "retrieve them using approved source recipes",
                    "purpose": "retrieve source materials",
                    "candidate_kind": "bounded_subtask",
                    "possible_inputs": [],
                    "possible_outputs": [],
                    "signals": []
                }
            ]
        },
        "stage3_5b_worker_boundary_decisions": {
            "decisions": [
                {
                    "candidate_id": "candidate_retrieve_source_material",
                    "decision": "compile_as_call_api",
                    "boundary_strength": "weak",
                    "boundary_kind": "call_api",
                    "rejection_reason": "single_api_call",
                    "reason": "API owned",
                    "evidence": []
                }
            ]
        },
        "stage4_flow_assembler": {
            "main_flow_spans": ["s15", "s16", "s17", "s19"],
            "alternative_flows": [
                {"flow_id": "alt_0", "condition_span_id": "s17", "spans": ["s18"]}
            ],
            "exception_flows": [],
            "delegation_candidates": [],
        },
        "stage5_block_assembler": {
            "main_flow_blocks": [
                {"block_id": "b_1", "block_type": "SEQUENTIAL", "spans": ["s15"]},
                {
                    "block_id": "b_2",
                    "block_type": "IF",
                    "condition_text": "sources are needed and available",
                    "spans": ["s16"],
                },
                {"block_id": "b_3", "block_type": "SEQUENTIAL", "spans": ["s17", "s19"]},
            ]
        },
        "stage6_resource_extractor": {
            "variables": [],
            "files": [],
            "apis": [],
            "types": [],
        },
        "stage7_step_extractor": {
            "steps": [
                {
                    "step_id": "st_15_1",
                    "text": "Determine the communication kind requested.",
                    "source_span_ids": ["s15"],
                    "command_type": "GENERAL_COMMAND",
                },
                {
                    "step_id": "st_16_1",
                    "text": "Maintain provenance for externally sourced facts.",
                    "source_span_ids": ["s16"],
                    "command_type": "GENERAL_COMMAND",
                },
                {
                    "step_id": "st_16_guard",
                    "text": "When enough required information is available.",
                    "source_span_ids": ["s16"],
                    "command_type": "GENERAL_COMMAND",
                },
                {
                    "step_id": "st_17_1",
                    "text": "Produce a draft.",
                    "source_span_ids": ["s17"],
                    "command_type": "GENERAL_COMMAND",
                },
                {
                    "step_id": "st_19_1",
                    "text": "Record unresolved items in assumptions log and set completion status.",
                    "source_span_ids": ["s19"],
                    "command_type": "GENERAL_COMMAND",
                },
            ],
            "new_variables": [],
        },
        "stage8_profile_extractor": {
            "persona": {"role": "Internal Communications Specialist"},
            "audience_aspects": [],
            "concepts": [],
        },
        "stage9_constraint_extractor": {
            "constraints": []
        },
    }

    with patch.object(orchestrator.client, "call_json") as mock_call:
        mock_call.side_effect = lambda stage_name, **kwargs: mock_llm_responses.get(
            stage_name, {}
        )

        result = orchestrator.run(raw_text)

        # Under legacy behavior:
        # 1. s16 has When enough... at tail
        # 2. Stage 7 materializes 'When enough required information is available' as a general command
        assert "[COMMAND When enough required information is available]" in result.spl_text or "COMMAND [COMMAND When enough required information is available]" in result.spl_text


def test_stage1_llm_segmentation_active_e2e(tmp_path: Path) -> None:
    # 1. Setup config (active mode opt-in)
    config = PipelineConfig(
        llm=LLMConfig(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.0,
            api_key="test-api-key",
        ),
        output_dir=tmp_path / "output",
        save_intermediate=True,
        log_level="DEBUG",
        max_retries=1,
    )
    config.stage1 = Stage1SegmentationConfig(mode="llm_source_constrained")

    # 2. Load the real internal_comms text
    input_path = Path("examples/input/internal_comms.txt")
    raw_text = input_path.read_text(encoding="utf-8")

    from nl2spl.adapters.registry import InputAdapterRegistry
    adapter_registry = InputAdapterRegistry()
    canonical_input = adapter_registry.adapt(raw_text)

    # Group authoritative packet IDs by section
    pkts_by_sec = {}
    for pkt in canonical_input.semantic_packets:
        pkts_by_sec.setdefault(pkt.source_section_id, []).append(pkt)

    rp_packets = pkts_by_sec.get("sec_reusable_process", [])
    rules_packets = pkts_by_sec.get("sec_policies", [])
    fm_packets = pkts_by_sec.get("sec_failure_handling", [])
    int_packets = pkts_by_sec.get("sec_delegation_policy", [])
    rp_pkts = [pkt.packet_id for pkt in rp_packets]
    rules_pkts = [pkt.packet_id for pkt in rules_packets]
    fm_pkts = [pkt.packet_id for pkt in fm_packets]
    int_pkts = [pkt.packet_id for pkt in int_packets]

    def packet_text(packets: list, *indices: int) -> str:
        return " ".join(
            " ".join(packets[index].text.split())
            for index in indices
        )

    orchestrator = PipelineOrchestrator(config)

    # 3. Setup mock LLM responses for all stages using dynamic packet IDs
    def mock_call_side_effect(stage_name: str, **kwargs: any) -> dict[str, any]:
        if stage_name == "stage1_source_constrained":
            user_prompt = kwargs.get("user_prompt", "")
            if "sec_reusable_process" in user_prompt:
                return {
                        "segments": [
                            {
                                "segment_text_exact": packet_text(rp_packets, 0),
                                "segmentation_kind": "atomic_action_candidate",
                                "source_packet_ids": [rp_pkts[0]],
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 1, 2),
                                "segmentation_kind": "atomic_action_candidate",
                                "source_packet_ids": [rp_pkts[1], rp_pkts[2]],
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 3),
                                "segmentation_kind": "guarded_action",
                                "guard_text_exact": "sources are needed and available",
                                "action_text_exact": "retrieve them using approved source recipes",
                                "source_packet_ids": [rp_pkts[3]],
                                "continuation_repaired": False,
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 4),
                                "segmentation_kind": "atomic_action_candidate",
                                "source_packet_ids": [rp_pkts[4]],
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 5),
                                "segmentation_kind": "guarded_action",
                                "guard_text_exact": "enough required information is available",
                                "action_text_exact": "produce a draft",
                                "source_packet_ids": [rp_pkts[5]],
                                "continuation_repaired": False,
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 6, 7),
                                "segmentation_kind": "guarded_action",
                                "guard_text_exact": "the user asks for revision",
                                "action_text_exact": (
                                    "revise while re checking constraints Do not finalize "
                                    "if required slots remain missing unless the draft is "
                                    "explicitly marked as assumption-bearing and the user "
                                    "confirms"
                                ),
                                "source_packet_ids": [rp_pkts[6], rp_pkts[7]],
                                "continuation_repaired": True,
                            },
                            {
                                "segment_text_exact": packet_text(rp_packets, 8),
                                "segmentation_kind": "atomic_action_candidate",
                                "source_packet_ids": [rp_pkts[8]],
                                "continuation_repaired": False,
                            },
                    ]
                }
            elif "sec_policies" in user_prompt:
                p20 = rules_pkts[0] if len(rules_pkts) > 0 else "s20"
                p21 = rules_pkts[1] if len(rules_pkts) > 1 else "s21"
                p22 = rules_pkts[2] if len(rules_pkts) > 2 else "s22"
                p23 = rules_pkts[3] if len(rules_pkts) > 3 else "s23"
                p24 = rules_pkts[4] if len(rules_pkts) > 4 else "s24"
                return {
                    "segments": [
                        {
                            "segment_text_exact": packet_text(rules_packets, 0),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": [p20],
                        },
                        {
                            "segment_text_exact": packet_text(rules_packets, 1),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": [p21],
                        },
                        {
                            "segment_text_exact": packet_text(rules_packets, 2),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": [p22],
                        },
                        {
                            "segment_text_exact": packet_text(rules_packets, 3),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": [p23],
                        },
                        {
                            "segment_text_exact": packet_text(rules_packets, 4),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": [p24],
                        },
                    ]
                }
            elif "sec_failure_handling" in user_prompt:
                return {
                    "segments": [
                        {
                            "segment_text_exact": packet_text(fm_packets, 0),
                            "segmentation_kind": "atomic_text_unit",
                            "source_packet_ids": [fm_pkts[0]],
                        }
                    ]
                }
            elif "sec_delegation_policy" in user_prompt:
                return {
                    "segments": [
                        {
                            "segment_text_exact": packet_text(int_packets, 0),
                            "segmentation_kind": "atomic_action_candidate",
                            "source_packet_ids": int_pkts,
                        }
                    ]
                }
            return {"segments": []}

        mock_stages = {
            "stage2_adapter_guided": {
                "annotations": [
                    {"span_id": "s1", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s2", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s3", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s4", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s5", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s6", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s7", "field": "behavior", "semantic_role": "process_step", "executable": True},
                    {"span_id": "s8", "field": "rules", "semantic_role": "policy", "executable": False},
                    {"span_id": "s9", "field": "rules", "semantic_role": "policy", "executable": False},
                    {"span_id": "s10", "field": "rules", "semantic_role": "policy", "executable": False},
                    {"span_id": "s11", "field": "rules", "semantic_role": "policy", "executable": False},
                    {"span_id": "s12", "field": "rules", "semantic_role": "policy", "executable": False},
                    {"span_id": "s13", "field": "behavior", "semantic_role": "failure_mode", "executable": False},
                        {"span_id": "s14", "field": "integrations", "semantic_role": "delegation_intent", "executable": True}
                ],
                "ambiguity_updates": [],
            },
            "stage3_ambiguity_resolver": {
                "resolved_spans": [],
                "resolved_routes": {
                    "identity": [],
                    "audience": [],
                    "rules": ["s8", "s9", "s10", "s11", "s12"],
                    "domain": [],
                        "integrations": ["s14"],
                        "behavior": ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s13"],
                },
            },
            "stage3_5a_candidate_task_units": {
                "candidates": [
                    {
                        "candidate_id": "candidate_retrieve_source_material",
                        "source_span_ids": ["s3"],
                        "task_text": "retrieve them using approved source recipes",
                        "purpose": "retrieve source materials",
                        "candidate_kind": "bounded_subtask",
                        "possible_inputs": [],
                        "possible_outputs": [],
                        "signals": []
                    }
                ]
            },
            "stage3_5b_worker_boundary_decisions": {
                "decisions": [
                    {
                        "candidate_id": "candidate_retrieve_source_material",
                        "decision": "compile_as_call_api",
                        "boundary_strength": "weak",
                        "boundary_kind": "call_api",
                        "rejection_reason": "single_api_call",
                        "reason": "API owned",
                        "evidence": []
                    }
                ]
            },
            "stage4_flow_assembler": {
                "main_flow_spans": ["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
                "alternative_flows": [],
                "exception_flows": [],
                "delegation_candidates": [],
            },
            "stage5_block_assembler": {
                "main_flow_blocks": [
                    {"block_id": "b_1", "block_type": "SEQUENTIAL", "spans": ["s1", "s2"]},
                    {
                        "block_id": "b_2",
                        "block_type": "IF",
                        "condition_text": "redundant condition text from Stage 5 LLM",
                        "spans": ["s3"],
                    },
                    {"block_id": "b_3", "block_type": "SEQUENTIAL", "spans": ["s4"]},
                    {
                        "block_id": "b_4",
                        "block_type": "IF",
                        "condition_text": "redundant condition text from Stage 5 LLM",
                        "spans": ["s5"],
                    },
                    {"block_id": "b_5", "block_type": "SEQUENTIAL", "spans": ["s6", "s7"]},
                ]
            },
            "stage6_resource_extractor": {
                "variables": [],
                "files": [],
                "apis": [],
                "types": [],
            },
            "stage7_step_extractor": {
                "steps": [
                    {
                        "step_id": "st_1",
                        "text": "Determine the communication kind requested.",
                        "source_span_ids": ["s1"],
                        "command_type": "GENERAL_COMMAND",
                    },
                    {
                        "step_id": "st_2",
                        "text": "Identify missing required fields.",
                        "source_span_ids": ["s2"],
                        "command_type": "GENERAL_COMMAND",
                    },
                    {
                        "step_id": "st_3",
                        "text": "Maintain provenance for externally sourced facts.",
                        "source_span_ids": ["s4"],
                        "command_type": "GENERAL_COMMAND",
                    },
                    {
                        "step_id": "st_4",
                        "text": "Produce a draft.",
                        "source_span_ids": ["s5"],
                        "command_type": "GENERAL_COMMAND",
                    },
                    {
                        "step_id": "st_5",
                        "text": "Record unresolved items in assumptions log and set completion status.",
                        "source_span_ids": ["s7"],
                        "command_type": "GENERAL_COMMAND",
                    },
                ],
                "new_variables": [],
            },
            "stage8_profile_extractor": {
                "persona": {"role": "Internal Communications Specialist"},
                "audience_aspects": [],
                "concepts": [],
            },
            "stage9_constraint_extractor": {
                "constraints": []
            },
        }
        return mock_stages.get(stage_name, {})

    with patch.object(orchestrator.client, "call_json") as mock_call:
        mock_call.side_effect = mock_call_side_effect

        result = orchestrator.run(raw_text)

        # In active mode:
        # 1. 'When enough required information is available' is successfully used as the condition for the IF block!
        # 2. It is NOT materialized as a standalone general command.
        assert "[IF enough required information is available]" in result.spl_text
        assert "[COMMAND Produce a draft]" in result.spl_text
        assert "When enough required information is available" not in result.spl_text or "[IF enough required information is available]" in result.spl_text
        assert "COMMAND When enough required information is available" not in result.spl_text
        assert "[COMMAND When enough required information is available]" not in result.spl_text
