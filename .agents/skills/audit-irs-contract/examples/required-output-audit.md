# Required Output Audit Example

REQUIRED_OUTPUT.output_name is source-defined and non-repairable.
REQUIRED_OUTPUT.producer is editable.

The producer slot passes only when:

- its affordance derives a user-facing RepairCatalog entry;
- required_output.materialize_producer.v1 resolves;
- InsertProducerStep and the Stage 7 materialization plan are registered;
- selected refs are validated;
- preview/apply and compiler-authority verification are tested.