"""Template-dependent Unreal Mannequin operations behind a scene host."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.unreal_mannequin import JointMatch, MannequinPlan, plan_mannequin


class MannequinHost(Protocol):
    def transaction(self, label: str): ...
    def preflight(self, plan: MannequinPlan, template_path: str) -> None: ...
    def preflight_mannequin_creation(self, plan: MannequinPlan, template_path: str) -> None: ...
    def confirm_original_control_build_pose(self) -> int: ...
    def clear_mannequin_export_assets(self) -> None: ...
    def import_template(self, plan: MannequinPlan, template_path: str) -> None: ...
    def fit_scale(self, plan: MannequinPlan) -> None: ...
    def connect_root_scale(self, plan: MannequinPlan) -> None: ...
    def finish_mannequin(self) -> None: ...
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
              match_template_pose: bool = True) -> MannequinPlan | None:
        plan = plan_mannequin(template,
                              scale_adv_to_template=scale_adv_to_template,
                              match_template_pose=match_template_pose)
        self.host.preflight_mannequin_creation(plan, template_path)
        with self.host.transaction("创建 Unreal Mannequin 骨架"):
            if not self.host.confirm_original_control_build_pose():
                return None
            self.host.clear_mannequin_export_assets()
            self.host.preflight(plan, template_path)
            build_mannequin(self.host, plan, template_path)
        return plan


def build_mannequin(host: MannequinHost, plan: MannequinPlan,
                    template_path: str) -> None:
    """Native creation passes inside the caller's single scene transaction."""
    host.import_template(plan, template_path)
    host.fit_scale(plan)
    host.capture_template_pose(plan)
    for match in plan.matches[:2]:
        host.constrain_match(match)
    host.connect_root_scale(plan)
    host.match_spine()
    for match in plan.matches[2:]:
        host.constrain_match(match)
    host.copy_custom_joints()
    host.match_template_pose(plan)
    host.copy_face_joints()
    host.finish_mannequin()
    if not host.has_mannequin():
        raise RuntimeError("Unreal Mannequin 骨架创建失败")


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
