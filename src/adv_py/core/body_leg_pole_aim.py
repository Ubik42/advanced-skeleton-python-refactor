"""OPM Leg pole follow frame used by the character control spaces."""
from dataclasses import dataclass

from .fit_symmetry import FitBuildSide


@dataclass(frozen=True, slots=True)
class BodyLegPoleAimSpec:
    side: FitBuildSide
    parent_source: str
    ik_root: str
    ankle_control: str
    ankle_frame_parent: str
    pole_offset: str
    pole_position: tuple[float, float, float]
    swivel_plug: str
    handle_twist: str
    frame_name: str
    aligned_name: str
    aim_name: str
    target_name: str
    matrix_name: str
    swivel_name: str
    local_name: str
    follow_name: str | None = None

    @property
    def frame_path(self):
        return self.ik_root + '|' + self.frame_name

    @property
    def aligned_path(self):
        return self.ankle_frame_parent + '|' + self.aligned_name

    @property
    def aim_path(self):
        return self.ik_root + '|' + self.aim_name

    @property
    def target_path(self):
        return self.aim_path + '|' + self.target_name

    @property
    def node_names(self):
        return (self.frame_name, self.aligned_name, self.aim_name,
                self.target_name, self.matrix_name, self.swivel_name,
                self.local_name, self.frame_name + 'Constraint') + (
                    (self.follow_name,) if self.follow_name else ())


def plan_body_leg_pole_aim(ik, torso=None, *, foot=None,
                           parent_source=None, attach_pole=False):
    if (torso is None) == (parent_source is None):
        raise ValueError('PoleAim 需要唯一的父级来源')
    source = torso.leg_lock.path if torso is not None else parent_source
    eligible = ({side.side for side in foot.sides
                 if 'swivel' in side.attributes}
                if foot is not None else {limb.side for limb in ik.limbs})
    result = []
    for limb in ik.limbs:
        if limb.side not in eligible:
            continue
        suffix = limb.side.value
        result.append(BodyLegPoleAimSpec(
            side=limb.side,
            parent_source=source,
            ik_root=ik.root_path,
            ankle_control=limb.ankle_control_path,
            ankle_frame_parent=limb.ankle_sub_path or limb.ankle_control_path,
            pole_offset=limb.pole_offset_path,
            pole_position=limb.pole_position,
            swivel_plug=limb.ankle_control_path + '.swivel',
            handle_twist=limb.handle_name + '.twist',
            frame_name=f'AdvPy_PoleParentFrame_{suffix}',
            aligned_name=f'AdvPy_PoleAlignedOffset_{suffix}',
            aim_name=f'AdvPy_PoleAim_{suffix}',
            target_name=f'AdvPy_PoleAimTarget_{suffix}',
            matrix_name=f'AdvPy_PoleAimAM_{suffix}',
            swivel_name=f'AdvPy_PoleAimSwivelCM_{suffix}',
            local_name=f'AdvPy_PoleAimLocalMM_{suffix}',
            follow_name=(f'AdvPy_PoleAimFollow_{suffix}'
                         if attach_pole else None),
        ))
    return tuple(result)
