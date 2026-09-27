"""Template-dependent Unreal Mannequin operations behind a scene host."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.unreal_mannequin import JointMatch, MannequinPlan, plan_mannequin


class MannequinHost(Protocol):
    def transaction(self, label: str): ...
    def preflight(self, plan: MannequinPlan, template_path: str) -> None: ...
    def import_template(self, plan: MannequinPlan, template_path: str) -> None: ...
    def fit_scale(self, plan: MannequinPlan) -> None: ...
    def capture_template_pose(self, plan: MannequinPlan) -> None: ...
    def match_spine(self) -> None: ...
    def constrain_match(self, match: JointMatch) -> None: ...
    def copy_custom_joints(self) -> None: ...
    def match_template_pose(self, plan: MannequinPlan) -> None: ...
    def copy_face_joints(self) -> None: ...
    def has_mannequin(self) -> bool: ...
    def transfer_skin(self) -> int: ...
    def hide_original_geometry(self) -> None: ...
    def delete_mannequin(self) -> None: ...


class CreateMannequin:
    def __init__(self, host: MannequinHost):
        self.host = host

    def apply(self, template_path: str, *, template: str = "UE5 (Simple)",
              scale_adv_to_template: bool = True,
              match_template_pose: bool = True) -> MannequinPlan:
        plan = plan_mannequin(template,
                              scale_adv_to_template=scale_adv_to_template,
                              match_template_pose=match_template_pose)
        self.host.preflight(plan, template_path)
        with self.host.transaction("创建 Unreal Mannequin 骨架"):
            self.host.import_template(plan, template_path)
            self.host.fit_scale(plan)
            self.host.capture_template_pose(plan)
            self.host.match_spine()
            for match in plan.matches:
                self.host.constrain_match(match)
            self.host.copy_custom_joints()
            self.host.match_template_pose(plan)
            self.host.copy_face_joints()
            if not self.host.has_mannequin():
                raise RuntimeError("Unreal Mannequin 骨架创建失败")
        return plan


class TransferMannequinSkin:
    def __init__(self, host: MannequinHost):
        self.host = host

    def apply(self) -> int:
        if not self.host.has_mannequin():
            raise ValueError("须先创建 Unreal Mannequin 骨架")
        with self.host.transaction("转移蒙皮到 Unreal Mannequin"):
            count = self.host.transfer_skin()
            self.host.hide_original_geometry()
        return count


class DeleteMannequin:
    def __init__(self, host: MannequinHost):
        self.host = host

    def apply(self) -> None:
        with self.host.transaction("删除 Unreal Mannequin 骨架"):
            self.host.delete_mannequin()
            if self.host.has_mannequin():
                raise RuntimeError("Unreal Mannequin 骨架删除失败")
