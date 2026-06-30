# Repair Runtime Closure

For every editable slot, verify the complete chain:

    SlotSpec.repair_affordances
    -> RepairCatalog entry
    -> RepairStrategySpec
    -> target resolver
    -> structured context builder
    -> selectable-reference policy
    -> typed intent schema
    -> handler or suggestion orchestration
    -> registered patch adapter
    -> materialization plan and declared stage authority
    -> preview and user confirmation
    -> apply evidence
    -> compiler-authority verification
    -> E2E test

The strategy is the semantic source. Patch types are transitional execution
adapters and must not define the final construct shape.

Missing strategy linkage, unregistered runtime IDs, absent materialization
plans, or non-user-facing derived catalog entries are runtime closure gaps.
Do not treat presentation copy or diagnostic messages as materialization facts.