from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.interaction.model import NormalizedWorkerDelegationDirective
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class DefineChildWorkerClosureValidator(PatchValidator):
    def validate(self, patch, snapshot) -> None:
        intent = patch.payload
        directive = getattr(intent, "payload", None)
        if patch.patch_type != "DefineChildWorkerClosure":
            raise PatchValidationError("Wrong patch type")
        if not isinstance(directive, NormalizedWorkerDelegationDirective):
            raise PatchValidationError("Normalized worker delegation directive is required")
        if directive.verification_lane != "B" or not directive.admitted_outputs:
            raise PatchValidationError("Define-child closure requires Lane B and child outputs")
