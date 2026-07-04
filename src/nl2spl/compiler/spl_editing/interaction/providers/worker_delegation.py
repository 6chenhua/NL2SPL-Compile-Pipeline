"""Dynamic Worker Delegation repair interaction provider."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.interaction.model import (
    RepairInputFieldView,
    RepairInputOptionView,
    RepairInputSchemaView,
    RepairInteractionView,
    revision_token_string,
)


class WorkerDelegationInteractionProvider:
    provider_id = "worker_delegation.interaction_provider.v1"

    def build(self, *, spec, issue, option, subject, refset, snapshot) -> RepairInteractionView:
        if option.option_id == "keep_in_main_flow":
            return self._keep_main(spec, issue, option, subject, refset, snapshot)
        return self._define_child(spec, issue, option, subject, refset, snapshot)

    def _define_child(self, spec, issue, option, subject, refset, snapshot):
        ref_options = tuple(
            RepairInputOptionView(ref.ref_id, ref.display_label, ref.ref_id)
            for ref in (refset.refs if refset is not None else ())
            if ref.ref_role == "selectable_input"
        )
        placement_options = tuple(
            RepairInputOptionView(ref.ref_id, ref.display_label, ref.ref_id)
            for ref in (refset.refs if refset is not None else ())
            if ref.ref_role == "placement_anchor"
        )
        result_target_options = tuple(
            RepairInputOptionView(ref.ref_id, ref.display_label, ref.ref_id)
            for ref in (refset.refs if refset is not None else ())
            if ref.ref_role == "binding_target"
        )
        output_schema = RepairInputSchemaView(
            schema_id="worker_delegation.new_child_output.v1",
            schema_version="1",
            fields=(
                RepairInputFieldView("local_id", "Local ID", "short_text", True),
                RepairInputFieldView("display_name", "Result name", "short_text", True),
                RepairInputFieldView(
                    "semantic_description", "Result description", "long_text", True
                ),
                RepairInputFieldView("data_type_hint", "Data type", "short_text", False),
            ),
        )
        result_schema = RepairInputSchemaView(
            schema_id="worker_delegation.result_usage.v1",
            schema_version="1",
            fields=(
                RepairInputFieldView("output_local_id", "Child result", "short_text", True),
                RepairInputFieldView(
                    "parent_ref_id",
                    "Parent result target",
                    "reference_select",
                    False,
                    options=result_target_options,
                    ref_role="binding_target",
                ),
                RepairInputFieldView(
                    "create_parent_local_temporary",
                    "Create parent-local temporary result",
                    "single_choice",
                    True,
                    options=(
                        RepairInputOptionView("yes", "Yes", "yes"),
                        RepairInputOptionView("no", "No", "no"),
                    ),
                ),
            ),
        )
        fields = (
            RepairInputFieldView(
                "delegated_responsibility",
                "Delegated responsibility",
                "long_text",
                True,
                value=subject.summary,
            ),
            RepairInputFieldView(
                "input_refs",
                "Required information",
                "reference_select",
                False,
                options=ref_options,
                ref_role="selectable_input",
            ),
            RepairInputFieldView(
                "input_empty_semantics",
                "No-input semantics",
                "single_choice",
                False,
                options=(
                    RepairInputOptionView("explicit_none", "No parent input", "explicit_none"),
                ),
            ),
            RepairInputFieldView(
                "returned_results",
                "Returned results",
                "new_fact_list",
                True,
                fact_schema_id=output_schema.schema_id,
            ),
            RepairInputFieldView(
                "invocation_timing",
                "Invocation timing",
                "single_choice",
                True,
                options=(
                    RepairInputOptionView("append", "Append to main flow", "append"),
                    RepairInputOptionView("before", "Before selected command", "before"),
                    RepairInputOptionView("after", "After selected command", "after"),
                ),
            ),
            RepairInputFieldView(
                "placement_ref",
                "Placement anchor",
                "reference_select",
                False,
                options=placement_options,
                ref_role="placement_anchor",
            ),
            RepairInputFieldView(
                "result_usage",
                "Result usage",
                "structured_object",
                True,
                object_schema_id=result_schema.schema_id,
            ),
            RepairInputFieldView(
                "additional_instruction", "Additional instruction", "long_text", False
            ),
        )
        return RepairInteractionView(
            issue_id=issue.issue_id,
            strategy_id=option.strategy_id,
            option_id=option.option_id,
            contract_id=spec.contract_id,
            contract_version=spec.contract_version,
            revision_token=revision_token_string(snapshot.revision_token),
            interaction_kind="structured_with_notes",
            availability="available",
            input_readiness="input_required",
            fields=fields,
            schemas=(output_schema, result_schema),
        )

    def _keep_main(self, spec, issue, option, subject, refset, snapshot):
        fields = (
            RepairInputFieldView(
                "task_selection",
                "Task boundary",
                "single_choice",
                True,
                options=(
                    RepairInputOptionView(
                        "source_gathering", "Source gathering", "source gathering"
                    ),
                    RepairInputOptionView(
                        "template_matching", "Template matching", "template matching"
                    ),
                    RepairInputOptionView("both", "Both", "source gathering and template matching"),
                ),
            ),
            RepairInputFieldView(
                "additional_instruction", "Additional instruction", "long_text", False
            ),
        )
        return RepairInteractionView(
            issue_id=issue.issue_id,
            strategy_id=option.strategy_id,
            option_id=option.option_id,
            contract_id=spec.contract_id,
            contract_version=spec.contract_version,
            revision_token=revision_token_string(snapshot.revision_token),
            interaction_kind="structured_with_notes",
            availability="available",
            input_readiness="input_required",
            fields=fields,
        )
