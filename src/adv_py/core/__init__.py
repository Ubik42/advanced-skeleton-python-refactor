"""DCC-neutral rig description and validation."""

from .fit_metadata import (
    FitJointIssue,
    FitJointField,
    FitJointFieldEdit,
    FitJointMetadata,
    FitJointPatch,
    FitJointValidationError,
    audit_fit_joint,
    fit_joint_value,
    predict_fit_joint_metadata,
)
from .joint_labels import JointLabel, JointLabelValidationError
from .model import ConstraintSpec, LimbSpec, NodeSpec, RigPlan
from .matrix import (
    IDENTITY_MATRIX,
    Matrix44,
    almost_equal,
    frame_from_y,
    matrix44,
    multiply,
    rotation_y_matrix,
    rotation_z_matrix,
    rows,
    translation_matrix,
    transpose_flat,
    with_translation,
)
from .validation import PlanValidationError, validate_plan

__all__ = [
    "ConstraintSpec",
    "FitJointIssue",
    "FitJointField",
    "FitJointFieldEdit",
    "FitJointMetadata",
    "FitJointPatch",
    "FitJointValidationError",
    "IDENTITY_MATRIX",
    "JointLabel",
    "JointLabelValidationError",
    "LimbSpec",
    "Matrix44",
    "NodeSpec",
    "PlanValidationError",
    "RigPlan",
    "almost_equal",
    "audit_fit_joint",
    "frame_from_y",
    "fit_joint_value",
    "matrix44",
    "multiply",
    "predict_fit_joint_metadata",
    "rotation_y_matrix",
    "rotation_z_matrix",
    "rows",
    "translation_matrix",
    "transpose_flat",
    "validate_plan",
    "with_translation",
]
