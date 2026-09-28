"""Resolve AdvancedSkeleton 6.925 FK segment scale defaults from Fit data."""
from __future__ import annotations

import re

from .fit_metadata import FitJointMetadata


def fit_segment_scale_compensate(
    metadata: FitJointMetadata,
    build_name: str,
    parent_build_name: str,
    *,
    use_offset_parent_matrix: bool,
    is_finger: bool = False,
) -> bool:
    """Return the FK segment setting; an explicit Fit value wins."""
    if metadata.seg_scale_comp is not None:
        return metadata.seg_scale_comp
    return not (
        is_finger
        or any(token in build_name for token in ("Finger", "Cup", "Toes"))
        or "Head" in parent_build_name
        or (use_offset_parent_matrix
            and re.search(r"Part[0-9]", build_name) is not None)
    )
