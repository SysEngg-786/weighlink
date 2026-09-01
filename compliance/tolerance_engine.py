# ==============================================================================
# weighlink/compliance/tolerance_engine.py
# Tolerance engine — evaluates each stable weighment against configurable
# min/max thresholds and stamps the result (PASS / FAIL / NO_RULE).
# Tolerance profiles are loaded from JSON config files.
# ==============================================================================

import json
import os


class ToleranceEngine:
    """
    Evaluates weighment records against a tolerance profile.
    
    The engine is stateless per evaluation — each call to evaluate()
    is independent. The tolerance profile is loaded once at init.
    
    Only stable readings are evaluated. Unstable readings are passed
    through unchanged with tolerance_result = 'NO_RULE'.
    """

    def __init__(self, tolerance_config_path):
        """
        Load a tolerance profile from a JSON config file.
        
        Args:
            tolerance_config_path: Path to the tolerance JSON file
                                   (e.g. config/tolerances/demo_product.json)
        """
        self._profile = None
        self._min_weight = None
        self._max_weight = None
        self._profile_name = "none"

        if not os.path.exists(tolerance_config_path):
            # No tolerance file = no rules applied. All readings get NO_RULE.
            # This is valid — not every deployment needs tolerance checking.
            return

        with open(tolerance_config_path, 'r') as f:
            self._profile = json.load(f)

        self._profile_name = self._profile.get("profile_name", "unknown")
        tolerance = self._profile.get("tolerance", {})
        self._min_weight = tolerance.get("min_weight")
        self._max_weight = tolerance.get("max_weight")

    @property
    def profile_name(self):
        """Name of the loaded tolerance profile."""
        return self._profile_name

    @property
    def has_rules(self):
        """True if a valid tolerance profile with min/max is loaded."""
        return self._min_weight is not None and self._max_weight is not None

    def evaluate(self, record):
        """
        Evaluate a WeighmentRecord against the tolerance profile.
        Modifies the record in place: sets tolerance_result, tolerance_min,
        tolerance_max.
        
        Rules:
        - Unstable readings are never evaluated (tolerance_result stays NO_RULE)
        - If no tolerance profile is loaded, result is NO_RULE
        - Weight within [min, max] inclusive = PASS
        - Weight outside [min, max] = FAIL
        
        Args:
            record: WeighmentRecord instance (modified in place)
        
        Returns:
            The same WeighmentRecord (for chaining convenience)
        """
        # Unstable readings are not evaluated — scale is still settling
        if not record.is_stable:
            record.tolerance_result = "NO_RULE"
            return record

        # No tolerance rules loaded — pass through without judgment
        if not self.has_rules:
            record.tolerance_result = "NO_RULE"
            return record

        # Apply tolerance bounds to the record
        record.tolerance_min = self._min_weight
        record.tolerance_max = self._max_weight

        # Evaluate: within bounds = PASS, outside = FAIL
        if self._min_weight <= record.weight <= self._max_weight:
            record.tolerance_result = "PASS"
        else:
            record.tolerance_result = "FAIL"

        return record
