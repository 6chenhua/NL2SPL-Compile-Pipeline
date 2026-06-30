"""Stage 6: ResourceExtractor - Extract variables, files, APIs, types."""

from nl2spl.pipeline.stages.stage6_resource_extractor.extractor import ResourceExtractor
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
    APIMaterializationRecordIR,
    materialize_api_declaration_skeletons,
)

__all__ = [
    "APICallBindingIR",
    "APIMaterializationPlanIR",
    "APIMaterializationRecordIR",
    "ResourceExtractor",
    "materialize_api_declaration_skeletons",
]
