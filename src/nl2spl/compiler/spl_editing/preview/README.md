# SPL Editing Preview Lifecycle

R12.4 uses Gate A Option A for the MVP lifecycle: preview stores the exact validated dry-run identity, including typed plan references and preview construct hashes. Confirmed apply must validate the stored preview against the apply candidate before creating `RepairEvidencePacket` or accepted overlay state.

The preview package owns stale detection. `PreviewStore` validates session, issue, snapshot, expiration, and scope. `validate_preview_not_stale()` validates the immutable identity fields: intent hash, directive hash, closure plan hash, selected refset id, typed plan hashes, preview construct hashes, and LLM generation config hash.

A mismatch means the preview is stale and must be regenerated. Apply code must not silently re-run generation or accept drift for the MVP path.