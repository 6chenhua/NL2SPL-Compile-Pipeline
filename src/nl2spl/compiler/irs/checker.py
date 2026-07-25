"""IRS v6 Checker Protocol — pluggable construct-level IRS checker interface.

IRSChecker defines the contract for v6-style checkers that extract construct
instances from context and evaluate their information requirements satisfaction.
"""

from __future__ import annotations

from typing import Protocol

from nl2spl.compiler.constructs import ConstructIRS, ConstructSatisfactionReport
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance


class IRSChecker(Protocol):
    """Protocol for IRS v6 checkers.

    Attributes:
        checker_id: Unique identifier for this checker
        supported_construct_types: Tuple of construct types this checker handles
        supported_stages: Tuple of pipeline stages where this checker applies

    Methods:
        extract_instances: Extract construct instances from context
        check_instance: Evaluate IRS for a single construct instance

    Checker contract:
        1. Checkers MUST NOT call LLM APIs
        2. Checkers MUST NOT modify context or IR objects
        3. Checkers MUST NOT generate new SPL constructs
        4. Checkers MUST NOT fill missing slots with inferred values
        5. Checkers MUST NOT directly assemble CompileDiagnostic
        6. Checkers MUST NOT create reports for constructs without source demand
        7. Checkers SHOULD use ConstructIRS to determine slot requirements
        8. Checkers SHOULD populate ConstructSatisfactionReport with evidence

    Design notes:
        - Protocol allows structural typing, no base class required
        - extract_instances identifies what to check
        - check_instance evaluates one construct's IRS
        - Separation allows runner to batch/parallelize checking
        - Future: checkers may support incremental/cached checking
    """

    checker_id: str
    supported_construct_types: tuple[str, ...]
    supported_stages: tuple[str, ...]

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        """Extract construct instances from context for IRS checking.

        Args:
            context: Read-only pipeline artifacts at current stage

        Returns:
            List of construct instances to check

        Notes:
            - May return empty list if no relevant constructs found
            - Should not create instances for constructs without source demand
            - Instance extraction must not modify context
        """
        ...

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Evaluate IRS for a single construct instance.

        Args:
            instance: Construct instance to check
            irs: Information requirements spec for this construct type
            context: Read-only pipeline artifacts (for cross-construct queries)

        Returns:
            Satisfaction report with slot-level evidence and diagnostics

        Notes:
            - Must not modify instance, irs, or context
            - Should populate report with source evidence (spans, sections, packets)
            - Should use irs to determine required vs optional slots
            - Should set completeness based on slot satisfaction
            - Should set renderable based on minimum requirements
            - May populate v6 fields (parent, children, edges, frontier, cutline)
        """
        ...
