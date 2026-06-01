"""IRS v6 Checker Registry — registration and lookup for pluggable checkers."""

from __future__ import annotations

from nl2spl.compiler.irs.checker import IRSChecker


class IRSCheckerRegistry:
    """Registry for IRS v6 checkers with stage and construct type filtering.
    
    Design notes:
        - Checkers are registered explicitly, no auto-discovery
        - Duplicate checker_id is rejected to prevent conflicts
        - Query results preserve registration order for determinism
        - Empty queries return empty lists, never None
    """
    
    def __init__(self) -> None:
        """Initialize empty registry."""
        self._checkers: list[IRSChecker] = []
        self._checker_ids: set[str] = set()
    
    def register(self, checker: IRSChecker) -> None:
        """Register a checker.
        
        Args:
            checker: Checker to register
        
        Raises:
            ValueError: If checker_id already registered
        """
        if checker.checker_id in self._checker_ids:
            raise ValueError(
                f"Checker with id '{checker.checker_id}' is already registered"
            )
        self._checkers.append(checker)
        self._checker_ids.add(checker.checker_id)
    
    def get_for_stage(self, stage_name: str) -> list[IRSChecker]:
        """Get all checkers that support a given stage.
        
        Args:
            stage_name: Pipeline stage name (e.g., "stage4", "stage7")
        
        Returns:
            List of checkers supporting this stage, in registration order
        """
        return [
            checker
            for checker in self._checkers
            if stage_name in checker.supported_stages
        ]
    
    def get_for_construct_type(self, construct_type: str) -> list[IRSChecker]:
        """Get all checkers that support a given construct type.
        
        Args:
            construct_type: SPL construct type (e.g., "GENERAL_COMMAND", "WORKER")
        
        Returns:
            List of checkers supporting this construct type, in registration order
        """
        return [
            checker
            for checker in self._checkers
            if construct_type in checker.supported_construct_types
        ]
    
    def get_for_stage_and_construct_type(
        self,
        stage_name: str,
        construct_type: str,
    ) -> list[IRSChecker]:
        """Get checkers that support both a stage and construct type.
        
        Args:
            stage_name: Pipeline stage name
            construct_type: SPL construct type
        
        Returns:
            List of checkers supporting both filters, in registration order
        """
        return [
            checker
            for checker in self._checkers
            if stage_name in checker.supported_stages
            and construct_type in checker.supported_construct_types
        ]
