"""DCC-neutral rig description and validation."""

from .model import ConstraintSpec, NodeSpec, RigPlan
from .matrix import IDENTITY_MATRIX, Matrix44, almost_equal, matrix44, translation_matrix, transpose_flat
from .validation import PlanValidationError, validate_plan

__all__ = [
    "ConstraintSpec",
    "IDENTITY_MATRIX",
    "Matrix44",
    "NodeSpec",
    "PlanValidationError",
    "RigPlan",
    "almost_equal",
    "matrix44",
    "translation_matrix",
    "transpose_flat",
    "validate_plan",
]
