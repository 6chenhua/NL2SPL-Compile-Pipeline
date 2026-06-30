from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class DefineChildWorkerClosureApplier(PatchApplier):
    def apply(self, patch, snapshot):
        raise PatchValidationError(
            "DefineChildWorkerClosure must use RepairMaterializationService"
        )
