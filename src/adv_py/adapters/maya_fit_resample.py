"""Maya implementation of AdvancedSkeleton's Fit chain resampling."""
from __future__ import annotations

from uuid import uuid4

from adv_py.core.fit_resample import FitResamplePlan

from .maya_fit import MayaFitJointHost


class MayaFitResampleHost(MayaFitJointHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace)
        self._resample_end_matrix: tuple[float, ...] | None = None

    @staticmethod
    def _fat_node(joint: str) -> str:
        return joint.rsplit("|", 1)[-1] + "Fat"

    def _owned_fat_node(self, joint: str) -> str | None:
        c = self._cmds
        node = self._fat_node(joint)
        if not c.objExists(node):
            if any(c.attributeQuery(attr, node=joint, exists=True)
                   for attr in ("fatFrontAbs", "fatWidthAbs")):
                raise ValueError("Fit 体积输出存在但计算节点缺失：" + joint)
            return None
        expected = (
            (joint + ".fat", node + ".input1Y"),
            (joint + ".fat", node + ".input1Z"),
            (joint + ".fatFront", node + ".input2Y"),
            (joint + ".fatWidth", node + ".input2Z"),
            (node + ".outputY", joint + ".fatFrontAbs"),
            (node + ".outputZ", joint + ".fatWidthAbs"),
        )
        if (c.nodeType(node) != "multiplyDivide"
                or any(not c.attributeQuery(attr, node=joint, exists=True)
                       for attr in ("fat", "fatFront", "fatWidth",
                                    "fatFrontAbs", "fatWidthAbs"))
                or any(c.connectionInfo(destination,
                                        sourceFromDestination=True) != source
                       for source, destination in expected)):
            raise ValueError("Fit 体积计算节点与关节连接不匹配：" + joint)
        consumers = set(c.listConnections(node, source=False,
                                          destination=True) or ())
        if consumers - {joint}:
            raise ValueError("Fit 体积计算节点还驱动其他对象：" + node)
        return node

    def preflight_fit_resample(self, plan: FitResamplePlan) -> None:
        c = self._cmds
        old = set(plan.old_chain[1:-1])
        for path in plan.old_chain:
            if not c.objExists(path) or c.referenceQuery(path,
                                                        isNodeReferenced=True):
                raise ValueError("Fit 重采样关节不存在或被引用：" + path)
        for path, child in zip(plan.old_chain[1:-1],
                               plan.old_chain[2:]):
            children = set(c.listRelatives(path, children=True,
                                           fullPath=True) or ())
            if children != {child}:
                raise ValueError("Fit 重采样中间关节含其他子节点：" + path)
            fat_node = self._owned_fat_node(path)
            attrs = set(c.listAttr(path, userDefined=True) or ())
            if attrs - {"fat", "fatFront", "fatWidth",
                         "fatFrontAbs", "fatWidthAbs"}:
                raise ValueError("Fit 重采样会丢失中间关节元数据：" + path)
            connected = set(c.listConnections(path, source=True,
                                              destination=True) or ())
            if connected - ({fat_node} if fat_node else set()):
                raise ValueError("Fit 重采样中间关节有其他外部连接：" + path)
        for name in plan.new_names:
            matches = c.ls(self.scene_address(name), long=True) or []
            if any(path not in old for path in matches):
                raise ValueError("Fit 重采样新名称已被占用：" + name)
            fat_name = name + "Fat"
            if c.objExists(fat_name) and fat_name not in {
                    self._fat_node(path) for path in old}:
                raise ValueError("Fit 重采样体积节点名称已被占用：" + fat_name)
        for path in (plan.start, plan.end):
            if any(c.getAttr(path + "." + axis, lock=True)
                   for axis in ("tx", "ty", "tz", "rx", "ry", "rz")):
                raise ValueError("Fit 重采样端点变换通道已锁定：" + path)

    def _sample_spline(self, plan: FitResamplePlan) -> tuple[tuple[float, ...], ...]:
        c = self._cmds
        handle = effector = curve = sampler = None
        try:
            created = c.ikHandle(startJoint=plan.start, endEffector=plan.end,
                                 solver="ikSplineSolver", createCurve=True,
                                 simplifyCurve=False, parentCurve=False)
            handle, effector, curve = created[0], created[1], created[2]
            shape = (c.listRelatives(curve, shapes=True,
                                     noIntermediate=True, fullPath=True) or [])[0]
            sampler = c.createNode("pointOnCurveInfo",
                                   name=self.scene_address(
                                       "AdvPy_FitResampleSampler_" + uuid4().hex[:8]))
            c.setAttr(sampler + ".turnOnPercentage", True)
            c.connectAttr(shape + ".worldSpace[0]", sampler + ".inputCurve")
            positions = []
            for index in range(1, plan.joint_count - 1):
                c.setAttr(sampler + ".parameter",
                          index / (plan.joint_count - 1))
                positions.append(tuple(float(value) for value in
                                       c.getAttr(sampler + ".position")[0]))
            return tuple(positions)
        finally:
            for node in (sampler, handle, effector, curve):
                if node and c.objExists(node):
                    c.delete(node)

    def resample_fit_chain(self, plan: FitResamplePlan) -> tuple[str, ...]:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        positions = self._sample_spline(plan)
        old_labels = []
        for path in plan.old_chain[1:-1]:
            label = self.read_joint_label(path)
            if label is not None:
                old_labels.append((tuple(float(x) for x in c.xform(
                    path, query=True, worldSpace=True, translation=True)), label))
        volume = []
        for path in (plan.start, plan.end):
            volume.append(tuple(float(c.getAttr(path + "." + attr))
                                if c.attributeQuery(attr, node=path,
                                                    exists=True) else 1.0
                                for attr in ("fat", "fatFront", "fatWidth")))
        radius = float(c.getAttr(plan.start + ".radius"))
        end_matrix = tuple(float(x) for x in c.xform(
            plan.end, query=True, worldSpace=True, matrix=True))
        self._resample_end_matrix = end_matrix
        temporary = self.scene_address("AdvPy_FitResampleEnd_" + uuid4().hex[:8])
        endpoint = c.parent(plan.end, world=True, absolute=True)[0]
        endpoint = c.rename(endpoint, temporary)
        if len(plan.old_chain) > 2:
            old_fat_nodes = tuple(filter(None, (
                self._owned_fat_node(path)
                for path in plan.old_chain[1:-1])))
            c.delete(plan.old_chain[1])
            remaining_fat = tuple(node for node in old_fat_nodes
                                  if c.objExists(node))
            if remaining_fat:
                c.delete(remaining_fat)
        parent = plan.start
        created = []
        for index, (name, position) in enumerate(
                zip(plan.new_names, positions), 1):
            joint = c.createNode("joint", name=self.scene_address(name),
                                 parent=parent, skipSelect=True)
            c.setAttr(joint + ".radius", radius)
            c.xform(joint, worldSpace=True, translation=position)
            fraction = index / (plan.joint_count - 1)
            for attr, low, high in zip(
                    ("fat", "fatFront", "fatWidth"), *volume):
                c.addAttr(joint, longName=attr, attributeType="double",
                          minValue=0.0,
                          defaultValue=low + fraction * (high - low),
                          keyable=True)
            for attr in ("fatFrontAbs", "fatWidthAbs"):
                c.addAttr(joint, longName=attr, attributeType="double",
                          keyable=False)
            fat_node = c.createNode("multiplyDivide",
                                    name=self.scene_address(name + "Fat"))
            for source, destination in (
                    (joint + ".fat", fat_node + ".input1Y"),
                    (joint + ".fat", fat_node + ".input1Z"),
                    (joint + ".fatFront", fat_node + ".input2Y"),
                    (joint + ".fatWidth", fat_node + ".input2Z"),
                    (fat_node + ".outputY", joint + ".fatFrontAbs"),
                    (fat_node + ".outputZ", joint + ".fatWidthAbs")):
                c.connectAttr(source, destination)
            parent = (c.ls(joint, long=True, type="joint") or [joint])[0]
            created.append(parent)
        endpoint = c.rename(endpoint, plan.end.rsplit("|", 1)[-1])
        endpoint = c.parent(endpoint, parent, absolute=True)[0]
        endpoint = (c.ls(endpoint, long=True, type="joint") or [endpoint])[0]
        if any(abs(a - b) > 1e-4 for a, b in zip(
                c.xform(endpoint, query=True, worldSpace=True, matrix=True),
                end_matrix)):
            raise RuntimeError("Fit 重采样改变了终点世界变换")
        for position, label in old_labels:
            candidates = created + [endpoint]
            nearest = min(candidates, key=lambda path: sum(
                (a - b) ** 2 for a, b in zip(position, c.xform(
                    path, query=True, worldSpace=True,
                    translation=True))))
            self.set_joint_label(nearest, label)
        if created and plan.start.rsplit("|", 1)[-1].endswith("Root") \
                and plan.new_names[0] == "Spine1":
            c.reorder(created[0], front=True)
        return tuple((c.ls(self.scene_address(name), long=True,
                           type="joint") or [""])[0]
                     for name in plan.new_names)

    def finalize_fit_resample(self, plan: FitResamplePlan,
                              created: tuple[str, ...]) -> None:
        self._require_transaction()
        c = self._cmds
        if self._resample_end_matrix is None:
            raise RuntimeError("Fit 重采样终点姿态未记录")
        end = (created[-1] if created else plan.start) + "|" \
              + plan.end.rsplit("|", 1)[-1]
        if not c.objExists(end):
            raise RuntimeError("Fit 重采样终点已丢失")
        c.xform(end, worldSpace=True, matrix=self._resample_end_matrix)
        if any(abs(a - b) > 1e-4 for a, b in zip(
                c.xform(end, query=True, worldSpace=True, matrix=True),
                self._resample_end_matrix)):
            raise RuntimeError("Fit 重采样终点世界变换未能恢复")
        self._resample_end_matrix = None
