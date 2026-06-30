from nl2spl.compiler.spl_editing.patches.base import PatchPreviewer


class DefineChildWorkerClosurePreviewer(PatchPreviewer):
    def preview(self, payload):
        return "Complete child worker closure preview"
