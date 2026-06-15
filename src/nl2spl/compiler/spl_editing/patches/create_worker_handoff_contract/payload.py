"""CreateWorkerHandoffContract payload."""

from dataclasses import dataclass, field

from nl2spl.compiler.spl_editing.patches.base import PatchPayload


@dataclass(frozen=True)
class CreateWorkerHandoffContractPayload(PatchPayload):
    worker_promotion_id: str
    parent_worker_id: str
    child_worker_id: str
    input_bindings: dict[str, str] = field(default_factory=dict)
    output_bindings: dict[str, str] = field(default_factory=dict)
    invocation_point: str = "main"
    result_handoff: str = ""
    source_signal_id: str | None = None
    input_binding_status: str = "known_present"
    output_binding_status: str = "known_present"
    input_binding_status_source: str | None = "user_confirmed_repair"
    output_binding_status_source: str | None = "user_confirmed_repair"
