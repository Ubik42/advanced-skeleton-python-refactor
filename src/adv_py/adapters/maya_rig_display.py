"""Maya scene operations used by the original Display panel."""
from __future__ import annotations

from adv_py.core.rig_display import RigDisplayPlan, RigDisplayState

from .maya_body import MayaBodyBuildHost


class MayaRigDisplayHost(MayaBodyBuildHost):
    def capture_rig_display(self) -> RigDisplayState:
        c = self._cmds
        motion = self.scene_address("MotionSystem")
        deformation = self.scene_address("DeformationSystem")
        motion_visibility = (bool(c.getAttr(motion + ".visibility"))
                             if c.objExists(motion) else None)
        driver = None
        for name in ("Main", "AdvPy_Global"):
            candidate = self.scene_address(name) + ".jointVis"
            if c.objExists(candidate):
                driver = candidate
                break
        if driver is None:
            for name in ("root", "Root_M"):
                candidate = self.scene_address(name) + ".visibility"
                if c.objExists(candidate):
                    driver = candidate
                    break
        legacy_root = self.scene_address("root")
        legacy_plug = (legacy_root + ".visibility"
                       if c.objExists(legacy_root + ".visibility") else None)
        fit = self.scene_address("FitSkeleton")
        fit_joints = (c.listRelatives(fit, allDescendents=True,
                                       type="joint", fullPath=True) or []
                      if c.objExists(fit) else [])
        joints = (c.listRelatives(deformation, allDescendents=True,
                                  type="joint", fullPath=True) or []
                  if c.objExists(deformation) else [])
        return RigDisplayState(
            motion_visibility,
            bool(c.getAttr(driver)) if driver else None,
            driver,
            tuple(sorted((path, bool(c.getAttr(path + ".displayLocalAxis")))
                         for path in joints)),
            float(c.jointDisplayScale(query=True)),
            legacy_root_visibility_plug=legacy_plug,
            legacy_root_visibility=(bool(c.getAttr(legacy_plug))
                                    if legacy_plug else None),
            legacy_root_settable=(bool(c.getAttr(legacy_plug, settable=True))
                                  if legacy_plug else False),
            hidden_fit_joints=tuple(sorted(
                path for path in fit_joints
                if int(c.getAttr(path + ".drawStyle")) == 2)),
        )

    def preflight_rig_display(self, plan: RigDisplayPlan) -> None:
        c = self._cmds
        if self.capture_rig_display() != plan.before:
            raise ValueError("Display 输入发生变化")
        plugs = ()
        if plan.operation == "motion":
            plugs = (self.scene_address("MotionSystem") + ".visibility",)
        elif plan.operation == "joints":
            plugs = (plan.before.joint_visibility_plug,)
            if plan.before.legacy_root_settable:
                plugs += (plan.before.legacy_root_visibility_plug,)
            if plan.value:
                plugs += tuple(path + ".drawStyle"
                               for path in plan.before.hidden_fit_joints)
        elif plan.operation == "axes":
            plugs = tuple(path + ".displayLocalAxis"
                          for path, _ in plan.before.joint_axes)
        for plug in plugs:
            if not plug or not c.objExists(plug) or not c.getAttr(
                    plug, settable=True):
                raise ValueError("Display 通道不可直接写入：" + str(plug))

    def apply_rig_display(self, plan: RigDisplayPlan) -> None:
        self._require_transaction()
        self.preflight_rig_display(plan)
        c = self._cmds
        self._transaction_changed = True
        if plan.operation == "motion":
            c.setAttr(self.scene_address("MotionSystem") + ".visibility",
                      plan.value)
        elif plan.operation == "joints":
            c.setAttr(plan.before.joint_visibility_plug, plan.value)
            if plan.before.legacy_root_settable:
                c.setAttr(plan.before.legacy_root_visibility_plug, plan.value)
            if plan.value:
                for path in plan.before.hidden_fit_joints:
                    c.setAttr(path + ".drawStyle", 0)
        elif plan.operation == "axes":
            for path, _ in plan.before.joint_axes:
                c.setAttr(path + ".displayLocalAxis", plan.value)
        else:
            c.jointDisplayScale(plan.value)
