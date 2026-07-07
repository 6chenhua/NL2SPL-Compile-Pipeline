"""
CompositeOutputPlan IR model for lowering multiple output intents into a single structured result.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputIntent:
    variable_name: str
    data_type: str
    source_span_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "variable_name": self.variable_name,
            "data_type": self.data_type,
            "source_span_ids": list(self.source_span_ids),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> OutputIntent:
        for f in ("variable_name", "data_type", "source_span_ids"):
            if f not in payload:
                raise ValueError(f"Missing field in OutputIntent: {f}")
        return cls(
            variable_name=str(payload["variable_name"]),
            data_type=str(payload["data_type"]),
            source_span_ids=tuple(str(s) for s in payload["source_span_ids"]),  # type: ignore
        )


@dataclass(frozen=True)
class CompositeFieldMapping:
    original_field_name: str
    original_data_type: str
    composite_field_name: str

    def to_payload(self) -> dict[str, object]:
        return {
            "original_field_name": self.original_field_name,
            "original_data_type": self.original_data_type,
            "composite_field_name": self.composite_field_name,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> CompositeFieldMapping:
        for f in ("original_field_name", "original_data_type", "composite_field_name"):
            if f not in payload:
                raise ValueError(f"Missing field in CompositeFieldMapping: {f}")
        return cls(
            original_field_name=str(payload["original_field_name"]),
            original_data_type=str(payload["original_data_type"]),
            composite_field_name=str(payload["composite_field_name"]),
        )


@dataclass(frozen=True)
class DeclarationRewrite:
    remove_variable_name: str

    def to_payload(self) -> dict[str, object]:
        return {
            "remove_variable_name": self.remove_variable_name,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DeclarationRewrite:
        if "remove_variable_name" not in payload:
            raise ValueError("Missing field in DeclarationRewrite: remove_variable_name")
        return cls(remove_variable_name=str(payload["remove_variable_name"]))


@dataclass(frozen=True)
class ReferenceRewrite:
    original_ref: str
    rewritten_ref: str
    top_name: str
    field_path: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "original_ref": self.original_ref,
            "rewritten_ref": self.rewritten_ref,
            "top_name": self.top_name,
            "field_path": list(self.field_path),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ReferenceRewrite:
        for f in ("original_ref", "rewritten_ref", "top_name", "field_path"):
            if f not in payload:
                raise ValueError(f"Missing field in ReferenceRewrite: {f}")
        return cls(
            original_ref=str(payload["original_ref"]),
            rewritten_ref=str(payload["rewritten_ref"]),
            top_name=str(payload["top_name"]),
            field_path=tuple(str(x) for x in payload["field_path"]),  # type: ignore
        )


@dataclass(frozen=True)
class WorkerOutputRewrite:
    remove_output_names: tuple[str, ...]
    add_output_name: str
    add_output_type: str
    required: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "remove_output_names": list(self.remove_output_names),
            "add_output_name": self.add_output_name,
            "add_output_type": self.add_output_type,
            "required": self.required,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> WorkerOutputRewrite:
        for f in ("remove_output_names", "add_output_name", "add_output_type", "required"):
            if f not in payload:
                raise ValueError(f"Missing field in WorkerOutputRewrite: {f}")
        return cls(
            remove_output_names=tuple(str(x) for x in payload["remove_output_names"]),  # type: ignore
            add_output_name=str(payload["add_output_name"]),
            add_output_type=str(payload["add_output_type"]),
            required=bool(payload["required"]),
        )


@dataclass(frozen=True)
class FieldProjectionRelation:
    source_variable: str
    field_path: tuple[str, ...]
    target_variable: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source_variable": self.source_variable,
            "field_path": list(self.field_path),
            "target_variable": self.target_variable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> FieldProjectionRelation:
        for f in ("source_variable", "field_path", "target_variable"):
            if f not in payload:
                raise ValueError(f"Missing field in FieldProjectionRelation: {f}")
        return cls(
            source_variable=str(payload["source_variable"]),
            field_path=tuple(str(x) for x in payload["field_path"]),  # type: ignore
            target_variable=str(payload["target_variable"]),
        )


@dataclass(frozen=True)
class CompositeOutputPlan:
    plan_id: str
    worker_id: str
    step_id: str
    command_type: str
    original_output_intents: tuple[OutputIntent, ...]
    composite_variable_name: str
    composite_type_name: str
    field_mappings: tuple[CompositeFieldMapping, ...]
    declaration_rewrites: tuple[DeclarationRewrite, ...]
    reference_rewrites: tuple[ReferenceRewrite, ...]
    worker_output_rewrite: WorkerOutputRewrite | None
    projection_relations: tuple[FieldProjectionRelation, ...]
    naming_authority: str
    source_span_ids: tuple[str, ...]
    schema_version: str = "composite_output_plan.v1"

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "worker_id": self.worker_id,
            "step_id": self.step_id,
            "command_type": self.command_type,
            "original_output_intents": [x.to_payload() for x in self.original_output_intents],
            "composite_variable_name": self.composite_variable_name,
            "composite_type_name": self.composite_type_name,
            "field_mappings": [x.to_payload() for x in self.field_mappings],
            "declaration_rewrites": [x.to_payload() for x in self.declaration_rewrites],
            "reference_rewrites": [x.to_payload() for x in self.reference_rewrites],
            "worker_output_rewrite": self.worker_output_rewrite.to_payload()
            if self.worker_output_rewrite
            else None,
            "projection_relations": [x.to_payload() for x in self.projection_relations],
            "naming_authority": self.naming_authority,
            "source_span_ids": list(self.source_span_ids),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> CompositeOutputPlan:
        # Schema version validation
        schema = payload.get("schema_version")
        if not schema:
            raise ValueError("Missing schema_version in payload")
        if schema != "composite_output_plan.v1":
            raise ValueError(f"Invalid schema_version: {schema}")

        # Required fields check
        required_fields = (
            "plan_id",
            "worker_id",
            "step_id",
            "command_type",
            "original_output_intents",
            "composite_variable_name",
            "composite_type_name",
            "field_mappings",
            "declaration_rewrites",
            "reference_rewrites",
            "worker_output_rewrite",
            "projection_relations",
            "naming_authority",
            "source_span_ids",
        )
        for f in required_fields:
            if f not in payload:
                raise ValueError(f"Missing field in CompositeOutputPlan: {f}")

        worker_rewrite_payload = payload["worker_output_rewrite"]
        worker_output_rewrite = (
            WorkerOutputRewrite.from_payload(worker_rewrite_payload)  # type: ignore
            if worker_rewrite_payload
            else None
        )

        return cls(
            schema_version=str(schema),
            plan_id=str(payload["plan_id"]),
            worker_id=str(payload["worker_id"]),
            step_id=str(payload["step_id"]),
            command_type=str(payload["command_type"]),
            original_output_intents=tuple(
                OutputIntent.from_payload(x)
                for x in payload["original_output_intents"]  # type: ignore
            ),
            composite_variable_name=str(payload["composite_variable_name"]),
            composite_type_name=str(payload["composite_type_name"]),
            field_mappings=tuple(
                CompositeFieldMapping.from_payload(x)
                for x in payload["field_mappings"]  # type: ignore
            ),
            declaration_rewrites=tuple(
                DeclarationRewrite.from_payload(x)
                for x in payload["declaration_rewrites"]  # type: ignore
            ),
            reference_rewrites=tuple(
                ReferenceRewrite.from_payload(x)
                for x in payload["reference_rewrites"]  # type: ignore
            ),
            worker_output_rewrite=worker_output_rewrite,
            projection_relations=tuple(
                FieldProjectionRelation.from_payload(x)
                for x in payload["projection_relations"]  # type: ignore
            ),
            naming_authority=str(payload["naming_authority"]),
            source_span_ids=tuple(str(s) for s in payload["source_span_ids"]),  # type: ignore
        )
