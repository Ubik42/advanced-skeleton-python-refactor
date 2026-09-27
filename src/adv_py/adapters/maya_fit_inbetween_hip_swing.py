"""Maya graph for the Root Inbetween HipSwingReverse OPM branch."""
from __future__ import annotations

from math import sqrt

from adv_py.core.fit_inbetween_hip_swing import HipSwingReversePlan


class MayaHipSwingReverseMixin:
    def preflight_hip_swing_reverse(
        self, plan: HipSwingReversePlan,
    ) -> None:
        c = self._cmds
        for path, kind in (
            (plan.start_fk_offset_path, "transform"),
            (plan.start_fk_control_path, "transform"),
            (plan.start_body_path, "joint"),
            (plan.end_body_path, "joint"),
            (plan.part1_name, "joint"),
        ):
            if (c.ls(path, long=True, type=kind) or []) != [path]:
                raise ValueError("HipSwingReverse 来源不唯一：" + path)
        names = [plan.control_offset_name, plan.control_name,
                 plan.reverse_name, plan.blend_name,
                 plan.decompose_name]
        for part in plan.parts:
            names.extend((part.name, part.aligned_name,
                          part.aligned_matrix_name))
            if part.correction_name:
                names.append(part.correction_name)
        if len(set(names)) != len(names) or any(
                c.objExists(name) for name in names):
            raise ValueError("HipSwingReverse 节点名称冲突")
        matrices = ((plan.root_inbetween_matrix_name, 2),) + tuple(
            (part.fk_matrix_name, 3) for part in plan.parts[1:])
        for name, count in matrices:
            if (c.ls(name, type="multMatrix") or []) != [name]:
                raise ValueError("HipSwingReverse 接收矩阵不存在：" + name)
            if any(not c.connectionInfo(
                    f"{name}.matrixIn[{index}]",
                    sourceFromDestination=True)
                   for index in range(count)):
                raise ValueError("HipSwingReverse 接收矩阵输入不完整："
                                 + name)

    def _insert_hip_swing_matrix(
        self, name: str, index: int, count: int,
        source: str,
    ) -> None:
        c = self._cmds
        for slot in range(count - 1, index - 1, -1):
            old = c.connectionInfo(
                f"{name}.matrixIn[{slot}]",
                sourceFromDestination=True)
            if not old:
                raise ValueError("HipSwingReverse 原矩阵输入已变化："
                                 + name)
            c.connectAttr(old, f"{name}.matrixIn[{slot + 1}]",
                          force=True)
        c.connectAttr(source, f"{name}.matrixIn[{index}]",
                      force=True)

    def create_hip_swing_reverse(
        self, plan: HipSwingReversePlan,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        # The Root and all Part bind matrices must remain unchanged.
        observed = (plan.start_body_path,) + tuple(
            self._unique_fit_part_joint(
                f"RootPart{index}_M")
            for index in range(1, plan.count + 1))
        before = {node: c.xform(node, query=True,
                                worldSpace=True, matrix=True)
                  for node in observed}
        start = c.xform(plan.start_body_path, query=True,
                        worldSpace=True, translation=True)
        part1 = c.xform(plan.part1_name, query=True,
                        worldSpace=True, translation=True)
        step = sqrt(sum((float(b) - float(a)) ** 2
                        for a, b in zip(start, part1)))
        if step <= 1e-6:
            raise ValueError("HipSwingReverse Root Part 段长为零")
        end_matrix = c.xform(plan.end_body_path, query=True,
                             worldSpace=True, matrix=True)
        offset = c.createNode("transform",
                              name=plan.control_offset_name,
                              parent=plan.start_fk_control_path,
                              skipSelect=True)
        c.xform(offset, worldSpace=True, matrix=end_matrix)
        selection = c.ls(selection=True, long=True) or []
        try:
            control = c.circle(name=plan.control_name,
                               normal=(1.0, 0.0, 0.0),
                               radius=plan.radius, degree=3,
                               sections=16,
                               constructionHistory=False)[0]
            control = c.parent(control, offset, relative=True)[0]
        finally:
            if selection:
                c.select(selection, replace=True)
            else:
                c.select(clear=True)
        c.addAttr(control, longName="advPyHipSwingOwner",
                  dataType="string")
        c.setAttr(control + ".advPyHipSwingOwner",
                  "adv_py.hip_swing.v1", type="string", lock=True)
        for channel in ("translate", "scale"):
            for axis in "XYZ":
                c.setAttr(control + "." + channel + axis,
                          lock=True, keyable=False)
        reverse = c.createNode("transform", name=plan.reverse_name,
                               parent=plan.start_fk_offset_path,
                               skipSelect=True)
        c.xform(reverse, worldSpace=True, matrix=end_matrix)
        blend = c.createNode("blendMatrix", name=plan.blend_name)
        decompose = c.createNode("decomposeMatrix",
                                 name=plan.decompose_name)
        self._transaction_changed = True
        c.connectAttr(control + ".matrix",
                      blend + ".target[0].targetMatrix")
        c.setAttr(blend + ".target[0].weight",
                  1.0 / plan.count)
        c.setAttr(decompose + ".inputRotateOrder",
                  plan.rotate_order)
        c.connectAttr(blend + ".outputMatrix",
                      decompose + ".inputMatrix")
        parent = reverse
        for part in reversed(plan.parts):
            node = c.createNode("transform", name=part.name,
                                parent=parent, skipSelect=True)
            c.setAttr(node + ".rotateOrder", plan.rotate_order)
            c.setAttr(node + ".translateX", -step)
            c.connectAttr(decompose + ".outputRotate",
                          node + ".rotate")
            parent = node
        for part in plan.parts:
            aligned = c.createNode("transform",
                                   name=part.aligned_name,
                                   parent=part.name,
                                   skipSelect=True)
            matrix = c.createNode("multMatrix",
                                  name=part.aligned_matrix_name)
            local = c.xform(part.name, query=True,
                            objectSpace=True, matrix=True)
            c.setAttr(matrix + ".matrixIn[0]", *local,
                      type="matrix")
            upstream = (plan.reverse_name if part.index == plan.count
                        else plan.parts[part.index + 1].name)
            c.connectAttr(upstream + ".worldMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(part.name + ".worldInverseMatrix[0]",
                          matrix + ".matrixIn[2]")
            c.connectAttr(matrix + ".matrixSum",
                          aligned + ".offsetParentMatrix")
        local_zero = c.xform(plan.parts[0].name,
                             query=True, objectSpace=True,
                             matrix=True)
        for part in plan.parts[1:]:
            matrix = c.createNode("multMatrix",
                                  name=part.correction_name)
            previous = plan.parts[part.index - 1]
            c.connectAttr(part.aligned_name + ".worldMatrix[0]",
                          matrix + ".matrixIn[0]")
            c.connectAttr(previous.aligned_name
                          + ".worldInverseMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.setAttr(matrix + ".matrixIn[2]", *local_zero,
                      type="matrix")
            self._insert_hip_swing_matrix(
                part.fk_matrix_name, 0, 3,
                matrix + ".matrixSum")
        self._insert_hip_swing_matrix(
            plan.root_inbetween_matrix_name, 0, 2,
            plan.reverse_root_name + ".worldMatrix[0]")
        self._insert_hip_swing_matrix(
            plan.root_inbetween_matrix_name, 1, 3,
            plan.start_fk_offset_path + ".worldInverseMatrix[0]")
        for node, original in before.items():
            after = c.xform(node, query=True,
                            worldSpace=True, matrix=True)
            if max(abs(float(a) - float(b)) for a, b in zip(
                    original, after)) > 1e-4:
                raise RuntimeError("HipSwingReverse 改变绑定姿态：" + node)

    def capture_hip_swing_reverse(
        self, plan: HipSwingReversePlan,
    ) -> bool:
        c = self._cmds
        if (not c.objExists(plan.control_path + ".advPyHipSwingOwner")
                or c.getAttr(plan.control_path + ".advPyHipSwingOwner")
                != "adv_py.hip_swing.v1"
                or c.connectionInfo(
                    plan.blend_name + ".target[0].targetMatrix",
                    sourceFromDestination=True)
                != plan.control_path + ".matrix"
                or abs(float(c.getAttr(
                    plan.blend_name + ".target[0].weight"))
                    - 1.0 / plan.count) > 1e-8
                or c.connectionInfo(
                    plan.root_inbetween_matrix_name + ".matrixIn[0]",
                    sourceFromDestination=True)
                != plan.reverse_root_name + ".worldMatrix[0]"
                or c.connectionInfo(
                    plan.root_inbetween_matrix_name + ".matrixIn[1]",
                    sourceFromDestination=True)
                != plan.start_fk_offset_path
                + ".worldInverseMatrix[0]"):
            return False
        return all(c.connectionInfo(
            part.fk_matrix_name + ".matrixIn[0]",
            sourceFromDestination=True)
            == part.correction_name + ".matrixSum"
            for part in plan.parts[1:])
