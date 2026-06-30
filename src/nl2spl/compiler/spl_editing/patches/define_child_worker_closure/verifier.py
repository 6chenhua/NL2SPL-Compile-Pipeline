from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


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
        plan = patched_snapshot.worker_plan
        child_ids = {
            worker.worker_id
            for worker in plan.workers
            if worker.kind == "child"
            and worker.purpose == directive.delegated_responsibility
        }
        if len(child_ids) != 1:
            failures.append("Child identity/purpose is not unique")
            return tuple(failures)
        child_id = next(iter(child_ids))
        child_steps = patched_snapshot.worker_step_plan.worker_steps.get(child_id, [])
        if len(child_steps) != 1:
            failures.append("Child closure must contain exactly one command")
        else:
            expected_outputs = {item.canonical_name for item in directive.admitted_outputs}
            if set(child_steps[0].outputs) != expected_outputs:
                failures.append("Child command does not produce all admitted outputs")
        handoffs = [item for item in plan.handoffs if item.to_worker == child_id]
        if len(handoffs) != 1:
            failures.append("Child closure requires one handoff")
        else:
            invokes = [
                step
                for steps in patched_snapshot.worker_step_plan.worker_steps.values()
                for step in steps
                if step.command_type == "INVOKE_WORKER"
                and step.handoff_id == handoffs[0].handoff_id
            ]
            if len(invokes) != 1:
                failures.append("Handoff requires one matching parent invocation")
        if not set(marker.materialized_construct_refs):
            failures.append("Resolution marker has no materialized closure refs")
        rendered = verification_artifacts.rendered_spl or ""
        if directive.delegated_responsibility not in rendered:
            failures.append("Rendered SPL does not contain child responsibility")
        return tuple(failures)
