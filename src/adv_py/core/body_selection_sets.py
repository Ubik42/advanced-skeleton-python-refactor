"""Selection-set membership for a newly built Body character."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodySelectionSetsPlan:
    controls: tuple[str, ...]
    deform_joints: tuple[str, ...]
    pose_channels: tuple[tuple[str, str], ...] = ()
    control_set: str = "ControlSet"
    deform_set: str = "DeformSet"
    all_set: str = "AllSet"
    root_set: str = "Sets"
    build_pose: str = "buildPose"
    motion_system: str = "MotionSystem"
    character_group: str = "Group"
    main_system: str = "MainSystem"

    def __post_init__(self) -> None:
        for label, members in (("ControlSet", self.controls),
                               ("DeformSet", self.deform_joints)):
            # ADV removes terminal joints even for a one-Root prop. Its
            # empty DeformSet is valid; the prop binds Root_M explicitly.
            if ((label == 'ControlSet' and not members) or len(members) != len(set(members))
                    or any(not isinstance(path, str) or not path
                           for path in members)):
                raise ValueError(label + " 成员为空或重复")
        if set(self.controls) & set(self.deform_joints):
            raise ValueError("控制器与变形关节不能共用选择集成员")
        if (any(not isinstance(item, tuple) or len(item) != 2
                       or not all(
                    isinstance(value, str) and value for value in item)
                    for item in self.pose_channels)
                or len(self.pose_channels) != len(set(self.pose_channels))):
            raise ValueError("构建姿态附加通道重复或无效")
        if len({self.control_set, self.deform_set,
                self.all_set, self.root_set, self.build_pose,
                self.motion_system, self.character_group,
                self.main_system}) != 8:
            raise ValueError("角色选择集名称重复")


def plan_body_selection_sets(
    controls: tuple[str, ...], deform_joints: tuple[str, ...],
    pose_channels: tuple[tuple[str, str], ...] = (),
) -> BodySelectionSetsPlan:
    return BodySelectionSetsPlan(tuple(dict.fromkeys(controls)),
                                 tuple(dict.fromkeys(deform_joints)),
                                 pose_channels)
