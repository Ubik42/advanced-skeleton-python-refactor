"""Procedure-local state of ADV 6.925 asFitAutoPlace.

The MEL procedure retains these locals across scan axes, finger retries and
the nCloth pass. Python loop variables must not silently reset them when the
procedure is split into modules. Only the axis maxima and index are reset by
the outer loop; the growth failure flag is deliberately persistent.
"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FitAutoPlaceScanState:
    host: Any
    c: Any
    minimum_y: float
    minimum_x: float
    minimum_z: float
    maximum_z: float
    maximum_y: float
    template: str
    orbit: Callable[[], None] = lambda: None
    axis: str = ''
    index: int = 0
    orbit_step: float = .2
    hits: int = 0
    previous_hits: int = 0
    width: float = 0.
    previous_width: float = 0.
    max_width: float = 0.
    max_z_width: float = 0.
    y_at_max_z: float = 0.
    hit_crotch: bool = False
    crotch_index: int = 0
    crotch_width: float = 0.
    hit_armpit: bool = False
    armpit_width: float = 0.
    hit_neck: bool = False
    hit_head: bool = False
    hit_ankle: bool = False
    ankle_rotation: float = 0.
    hit_arm_tip: bool = False
    hit_shoulder: bool = False
    arm_straight: bool = False
    first_split_x: float = 0.
    four_fingers: bool = False
    finger_grow_failed: bool = False
    max_finger_width: float = 0.
    average_finger_diameter: float = 0.
    previous_finger_box: tuple = (0.,) * 6
    has_ncloth: bool = False
    hit_thumb: bool = False
    nucleus: str = ''
    stop: bool = False
    break_axis: bool = False
    step_y: float = 0.
    step_z: float = 0.
    direction: tuple = (0., 0., 1.)
    project_on: str = 'CombinedSkin'
    projected: list = field(default_factory=list)
    center_curve: str = ''
    center_x: float = 0.
    bound_min: list = field(default_factory=list)
    bound_max: list = field(default_factory=list)
