from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from nl2spl.rendering.model import RenderMode, RenderWarning
from nl2spl.rendering.spl.construct_renderer import render_spl_construct

if TYPE_CHECKING:
    from nl2spl.compiler.spl_editing.preview.artifact import TypedRepairPreviewArtifact
    from nl2spl.rendering.context import SPLRenderContext


@dataclass(frozen=True)
class RenderedPreview:
    preview_id: str
    renderer_id: str
    format: Literal["spl_text", "markdown", "json_tree"]
    text: str
    warnings: tuple[RenderWarning, ...] = ()


def render_repair_preview_spl(
    typed_artifact: TypedRepairPreviewArtifact,
    context: SPLRenderContext,
) -> RenderedPreview:
    """Render a TypedRepairPreviewArtifact into a RenderedPreview using construct renderers."""
    from nl2spl.rendering.spl.preview_deserializer import deserialize_construct_from_dict

    rendered_parts = []
    render_warnings = []

    for node in typed_artifact.construct_nodes:
        if node.ir_payload.get("display") is False:
            continue

        ir_obj = None
        if (
            node.node_kind == "spl_construct"
            and node.spl_construct_type is not None
        ):
            try:
                ir_obj = deserialize_construct_from_dict(
                    node.spl_construct_type, dict(node.ir_payload)
                )
            except Exception:
                ir_obj = None

        if ir_obj is not None:
            # We have a valid construct to render
            fragment = render_spl_construct(
                node.spl_construct_type,
                ir_obj,
                context,
                RenderMode.REPAIR_PREVIEW,
            )
            rendered_parts.append(fragment.text)
            for diag in fragment.render_diagnostics:
                render_warnings.append(RenderWarning(message=diag.message, code=diag.kind))
        else:
            # Structured fallback
            action = node.ir_payload.get("action", "materialize")
            ctype = node.ir_payload.get("construct_type", "UNKNOWN")
            role = node.role
            fallback = f"Will {action} {ctype} for role {role}"
            rendered_parts.append(fallback)

    return RenderedPreview(
        preview_id=typed_artifact.preview_id,
        renderer_id="repair_preview_renderer",
        format="spl_text",
        text="\n".join(rendered_parts),
        warnings=tuple(render_warnings),
    )
