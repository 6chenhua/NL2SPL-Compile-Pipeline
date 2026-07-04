from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier
from nl2spl.compiler.spl_editing.resolution import validate_promotion_resolution_marker


class DefineChildWorkerClosureVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, verification_artifacts):
        failures = []
        directive = getattr(patch.payload, "payload", None)
        markers = [
            marker
            for marker in patched_snapshot.promotion_resolution_markers
            if marker.normalized_directive_id == getattr(directive, "directive_id", None)
        ]
        if len(markers) != 1 or markers[0].resolution_kind != "defined_child_worker":
            failures.append("Missing defined_child_worker resolution marker")
            return tuple(failures)
        marker = markers[0]
        marker_validity = validate_promotion_resolution_marker(
            marker,
            patch.target_ref,
            expected_repair_patch_id=patch.patch_id,
        )
        if not marker_validity.valid:
            failures.append(
                "Invalid defined_child_worker resolution marker: "
                + ",".join(marker_validity.reasons)
            )
            return tuple(failures)
        plan = patched_snapshot.worker_plan
        child_ids = {
            worker.worker_id
            for worker in plan.workers
            if worker.kind == "child" and worker.purpose == directive.delegated_responsibility
        }
        if len(child_ids) != 1:
            failures.append("Child identity/purpose is not unique")
            return tuple(failures)
        child_id = next(iter(child_ids))
        child = next(worker for worker in plan.workers if worker.worker_id == child_id)
        expected_inputs = tuple(item.ref.canonical_name for item in directive.selected_input_refs)
        expected_outputs = tuple(item.canonical_name for item in directive.admitted_outputs)
        usage = {item.output_id: item for item in directive.result_usage}
        expected_parent_outputs = tuple(
            _parent_output_name(usage[output.output_id])
            for output in directive.admitted_outputs
        )
        if any(not value for value in expected_parent_outputs):
            failures.append("Result usage contains an empty parent result binding")
        if len(expected_parent_outputs) != len(set(expected_parent_outputs)):
            failures.append("Parent result bindings must be unique")
        invalid_required_targets = [
            output.output_id
            for output in directive.admitted_outputs
            if _is_required_output_ref(usage[output.output_id])
        ]
        if invalid_required_targets:
            failures.append("Parent required output is not a valid result binding target")
        if tuple(field.name for field in child.input_contract) != expected_inputs:
            failures.append("Child input contract does not match selected refs")
        if tuple(field.name for field in child.output_contract) != expected_outputs:
            failures.append("Child output contract does not match admitted outputs")
        flow = patched_snapshot.worker_flow_plan.worker_flows.get(child_id)
        if flow is None:
            failures.append("Child main flow is missing")
        blocks = patched_snapshot.worker_block_plan.worker_blocks.get(child_id)
        child_blocks = blocks.main_flow_blocks if blocks is not None else []
        if len(child_blocks) != 1 or child_blocks[0].block_type != "SEQUENTIAL":
            failures.append("Child closure requires exactly one sequential block")
        child_steps = patched_snapshot.worker_step_plan.worker_steps.get(child_id, [])
        if len(child_steps) != 1:
            failures.append("Child closure must contain exactly one command")
        else:
            command = child_steps[0]
            if (
                command.command_type != "GENERAL_COMMAND"
                or command.text != directive.delegated_responsibility
                or tuple(command.inputs) != expected_inputs
                or tuple(command.outputs) != expected_outputs
            ):
                failures.append("Child command does not match the normalized directive")
            if child_blocks and command.block_ref != child_blocks[0].block_id:
                failures.append("Child command is not owned by the child block")
            if set(command.outputs) != set(expected_outputs):
                failures.append("Child command does not produce all admitted outputs")
        handoffs = [item for item in plan.handoffs if item.to_worker == child_id]
        if len(handoffs) != 1:
            failures.append("Child closure requires one handoff")
        else:
            handoff = handoffs[0]
            expected_input_bindings = tuple((name, name) for name in expected_inputs)
            actual_input_bindings = tuple(
                (item.parent_variable, item.child_input) for item in handoff.input_bindings
            )
            if actual_input_bindings != expected_input_bindings:
                failures.append("Handoff input bindings do not match selected refs")
            expected_output_bindings = tuple(
                (
                    output.canonical_name,
                    _parent_output_name(usage[output.output_id]),
                )
                for output in directive.admitted_outputs
            )
            actual_output_bindings = tuple(
                (item.child_output, item.parent_variable) for item in handoff.output_bindings
            )
            if actual_output_bindings != expected_output_bindings:
                failures.append("Handoff output bindings do not match result usage")
            if handoff.materialization_status != "materialized":
                failures.append("Handoff is not fully materialized")
            invokes = [
                step
                for steps in patched_snapshot.worker_step_plan.worker_steps.values()
                for step in steps
                if step.command_type == "INVOKE_WORKER"
                and step.handoff_id == handoffs[0].handoff_id
            ]
            if len(invokes) != 1:
                failures.append("Handoff requires one matching parent invocation")
            else:
                invoke = invokes[0]
                if (
                    invoke.flow_ref != "main"
                    or tuple(invoke.inputs) != expected_inputs
                    or tuple(invoke.outputs) != expected_parent_outputs
                    or invoke.integration_ref != child.worker_name
                ):
                    failures.append("Parent invocation does not match the handoff plan")
                failures.extend(
                    _result_binding_failures(
                        patched_snapshot,
                        directive,
                        handoff,
                        invoke,
                        expected_parent_outputs,
                    )
                )
        expected_closure_refs = {
            f"worker:{child_id}",
            f"flow:{child_id}:main",
            (
                f"block:{child_id}:{child_blocks[0].block_id}"
                if len(child_blocks) == 1
                else "block:missing"
            ),
            (
                f"step:{child_id}:{child_steps[0].step_id}"
                if len(child_steps) == 1
                else "step:missing"
            ),
            f"handoff:{handoffs[0].handoff_id}" if handoffs else "handoff:missing",
            (
                f"step:{plan.main_worker_id}:{invokes[0].step_id}"
                if handoffs and len(invokes) == 1
                else "invoke:missing"
            ),
        }
        marker_refs = tuple(marker.materialized_construct_refs)
        if len(marker_refs) != len(set(marker_refs)) or set(marker_refs) != expected_closure_refs:
            failures.append(
                "Resolution marker and materialized closure refs are not bidirectionally exact"
            )
        rendered = verification_artifacts.rendered_spl or ""
        if directive.delegated_responsibility not in rendered:
            failures.append("Rendered SPL does not contain child responsibility")
        return tuple(failures)


def _parent_output_name(result_usage) -> str:
    parent_ref = getattr(result_usage, "parent_ref", None)
    if parent_ref is not None:
        return parent_ref.ref.canonical_name
    return getattr(result_usage, "parent_temporary_name", None) or ""


def _is_required_output_ref(result_usage) -> bool:
    parent_ref = getattr(result_usage, "parent_ref", None)
    if parent_ref is None:
        return False
    ref = getattr(parent_ref, "ref", None)
    ref_kind = getattr(ref, "ref_kind", "")
    ref_id = getattr(ref, "ref_id", "")
    return ref_kind == "required_output" or str(ref_id).startswith("required_output:")


def _result_binding_failures(
    snapshot,
    directive,
    handoff,
    invoke,
    expected_parent_outputs: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    symbols = getattr(snapshot.symbol_table, "_variables", {})
    main_worker_id = snapshot.worker_plan.main_worker_id
    for item in directive.result_usage:
        if item.parent_temporary_name is None:
            continue
        symbol = symbols.get(("worker", main_worker_id, item.parent_temporary_name))
        if symbol is None:
            failures.append("Parent temporary result is missing from parent worker scope")
            continue
        if symbol.declared:
            failures.append("Parent temporary result escaped its worker-local scope")
        if symbol.producer_step != invoke.step_id:
            failures.append("Parent temporary result producer does not match invoke step")

    child_ids = {
        worker.worker_id
        for worker in snapshot.worker_plan.workers
        if worker.kind == "child"
    }
    producer_index = ProducerIndex(
        steps=snapshot.worker_step_plan.get_all_steps(),
        handoffs=list(snapshot.worker_plan.handoffs),
        known_child_worker_ids=child_ids,
    )
    for parent_output in expected_parent_outputs:
        producers = producer_index.get_producers(parent_output)
        handoff_producers = [
            producer
            for producer in producers
            if producer.producer_kind == "handoff"
            and producer.producer_ref == handoff.handoff_id
            and producer.renderable
        ]
        if len(handoff_producers) != 1:
            failures.append(
                "Parent result binding is not backed by a renderable handoff producer"
            )
    return failures
