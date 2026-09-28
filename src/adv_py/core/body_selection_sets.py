"""Selection-set membership for a newly built Body character."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodySelectionSetsPlan:
    controls: tuple[str, ...]
    deform_joints: tuple[str, ...]
    control_set: str = "ControlSet"
    deform_set: str = "DeformSet"

    def __post_init__(self) -> None:
        for label, members in (("ControlSet", self.controls),
                               ("DeformSet", self.deform_joints)):
            if (not members or len(members) != len(set(members))
                    or any(not isinstance(path, str) or not path
                           for path in members)):
                raise ValueError(label + " 成员为空或重复")
        if set(self.controls) & set(self.deform_joints):
            raise ValueError("控制器与变形关节不能共用选择集成员")


def plan_body_selection_sets(
    controls: tuple[str, ...], deform_joints: tuple[str, ...]
) -> BodySelectionSetsPlan:
    return BodySelectionSetsPlan(tuple(dict.fromkeys(controls)),
                                 tuple(dict.fromkeys(deform_joints)))
