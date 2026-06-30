from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.applier import DefineChildWorkerClosureApplier
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.preview import DefineChildWorkerClosurePreviewer
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.validator import DefineChildWorkerClosureValidator
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.verifier import DefineChildWorkerClosureVerifier


def register_define_child_worker_closure_patch(runtime) -> None:
    from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
    from nl2spl.compiler.spl_editing.patches.registry import PatchBundle

    runtime.patches.register(
        "DefineChildWorkerClosure",
        PatchBundle(
            patch_type="DefineChildWorkerClosure",
            validator=DefineChildWorkerClosureValidator(),
            applier=DefineChildWorkerClosureApplier(),
            verifier=DefineChildWorkerClosureVerifier(),
            previewer=DefineChildWorkerClosurePreviewer(),
            contract=PatchTypeContract(
                patch_type="DefineChildWorkerClosure",
                produces_step_ir=True,
                produces_handoff_ir=True,
                evidence_targets=("worker", "flow", "block", "step", "handoff"),
            ),
        ),
    )

__all__ = [
    name
    for name in globals()
    if name.startswith("DefineChild") or name == "register_define_child_worker_closure_patch"
]
