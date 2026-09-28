"""Transfer imported FBX animation to FK controls and reconnect old Skin."""
from __future__ import annotations

from typing import Mapping

from adv_py.core.fbx_rig_import import (FBXRigControlTransferPlan,
                                        FBXRigImportPlan)


class MayaFBXRigTransferMixin:
    def _only_fbx_node(self, name: str, kind: str) -> str:
        nodes = self._cmds.ls(name, long=True, type=kind) or ()
        if len(nodes) != 1:
            raise ValueError("FBX rig 节点缺失或不唯一：" + name)
        return nodes[0]

    def connect_fbx_source_animation_to_controls(
        self, transfer: FBXRigControlTransferPlan,
        source_paths: Mapping[str, str],
    ) -> None:
        self._require_transaction()
        c = self._cmds
        constraints = []
        for link in transfer.links:
            source = self._only_fbx_node(
                source_paths[link.source_joint], "joint")
            control = self._only_fbx_node(link.control_name, "transform")
            name = "AdvPy_FBX_Temp_" + link.control_name
            if c.objExists(name):
                raise ValueError("FBX rig 临时约束名称已占用：" + name)
            self._transaction_changed = True
            built = c.parentConstraint(source, control,
                maintainOffset=True, name=name)
            if len(built) != 1:
                raise RuntimeError("FBX rig 临时控制约束创建失败："
                                   + link.control_name)
            constraints.append(built[0])
        self._fbx_temporary_constraints = tuple(constraints)

    def bake_fbx_control_animation(
        self, plan: FBXRigImportPlan,
        transfer: FBXRigControlTransferPlan,
        source_paths: Mapping[str, str],
    ) -> None:
        del source_paths
        self._require_transaction()
        if plan.first_bake_frame is None or plan.last_bake_frame is None:
            raise ValueError("FBX rig 没有可烘焙的动画范围")
        if len(getattr(self, "_fbx_temporary_constraints", ())) != len(
                transfer.links):
            raise RuntimeError("FBX rig 来源临时约束数量不符")
        controls = tuple(self._only_fbx_node(name, "transform")
                         for name in transfer.bake_control_names)
        self._transaction_changed = True
        self._cmds.bakeResults(controls, simulation=True,
            time=(plan.first_bake_frame, plan.last_bake_frame),
            sampleBy=1, disableImplicitControl=True,
            preserveOutsideKeys=False, sparseAnimCurveBake=False,
            removeBakedAttributeFromLayer=False,
            bakeOnOverrideLayer=False, controlPoints=False, shape=False)
        for control in controls:
            times = self._cmds.keyframe(control, query=True,
                                        timeChange=True) or ()
            if not times:
                raise RuntimeError("FBX rig 控制器烘焙后没有关键帧："
                                   + control)

    def remove_fbx_source_animation_and_bake_links(
        self, transfer: FBXRigControlTransferPlan,
        source_paths: Mapping[str, str],
    ) -> None:
        self._require_transaction()
        c = self._cmds
        constraints = tuple(getattr(self,
                                    "_fbx_temporary_constraints", ()))
        if len(constraints) != len(transfer.links):
            raise RuntimeError("FBX rig 临时约束记录不完整")
        self._transaction_changed = True
        c.delete(constraints)
        if any(c.objExists(name) for name in constraints):
            raise RuntimeError("FBX rig 临时约束未清除")
        self._fbx_temporary_constraints = ()
        source_nodes = {self._only_fbx_node(path, "joint")
                        for path in source_paths.values()}
        curves = set()
        for joint in source_nodes:
            curves.update(c.listConnections(joint, source=True,
                destination=False, type="animCurve") or ())
        for curve in curves:
            destinations = c.listConnections(curve + ".output",
                source=False, destination=True, plugs=True) or ()
            if any((c.ls(plug.rsplit(".", 1)[0], long=True)
                    or (None,))[0] not in source_nodes
                   for plug in destinations):
                raise ValueError("FBX rig 来源动画曲线被其他节点共用："
                                 + curve)
        if curves:
            c.delete(tuple(sorted(curves)))
        if any(c.listConnections(joint, source=True,
                destination=False, type="animCurve")
               for joint in source_nodes):
            raise RuntimeError("FBX rig 原骨架动画曲线未清除")
        for joint in source_nodes:
            for channel in ("translate", "rotate", "scale"):
                for axis in "XYZ":
                    plug = joint + "." + channel + axis
                    if c.listConnections(plug, source=True,
                                         destination=False, plugs=True):
                        raise ValueError("FBX rig 原骨架仍有外部通道驱动："
                                         + plug)

    def connect_fbx_controls_to_source(
        self, transfer: FBXRigControlTransferPlan,
        source_paths: Mapping[str, str],
    ) -> None:
        self._require_transaction()
        c = self._cmds
        constraints = {}
        for link in transfer.links:
            source = self._only_fbx_node(
                source_paths[link.source_joint], "joint")
            driver = self._only_fbx_node(link.deform_driver_name,
                "transform" if link.deform_driver_name == "FKRoot_M"
                else "joint")
            name = "AdvPy_FBX_Source_" + link.control_name
            if c.objExists(name):
                raise ValueError("FBX rig 来源约束名称已占用：" + name)
            self._transaction_changed = True
            built = c.parentConstraint(driver, source,
                maintainOffset=True, name=name)
            if len(built) != 1:
                raise RuntimeError("FBX rig 来源骨架约束创建失败："
                                   + source)
            constraints[source] = built[0]
        self._fbx_source_constraints = constraints
