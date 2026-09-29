"""Maya implementation of AdvancedSkeleton's Fit chain resampling."""
from __future__ import annotations

from uuid import uuid4

from adv_py.core.fit_resample import FitResamplePlan

from .maya_fit import MayaFitJointHost


class MayaFitResampleHost(MayaFitJointHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace)
        self._resample_end_matrix: tuple[float, ...] | None = None

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
            attrs = set(c.listAttr(path, userDefined=True) or ())
            if attrs - {"fat", "fatFront", "fatWidth"}:
                raise ValueError("Fit 重采样会丢失中间关节元数据：" + path)
            connected = c.listConnections(path, source=True,
                                          destination=True) or []
            if any(c.nodeType(node) in ("skinCluster", "constraint",
                                         "parentConstraint", "orientConstraint",
                                         "pointConstraint", "scaleConstraint")
                   for node in connected):
                raise ValueError("Fit 重采样中间关节已有变形或约束：" + path)
        for name in plan.new_names:
            matches = c.ls(self.scene_address(name), long=True) or []
            if any(path not in old for path in matches):
                raise ValueError("Fit 重采样新名称已被占用：" + name)
        for path in (plan.start, plan.end):
            if any(c.getAttr(path + "." + axis, lock=True)
                   for axis in ("tx", "ty", "tz", "rx", "ry", "rz")):
                raise ValueError("Fit 重采样端点变换通道已锁定：" + path)

    def _sample_spline(self, plan: FitResamplePlan) -> tuple[tuple[float, ...], ...]:
        c = self._cmds
        handle = curve = sampler = None
        try:
            created = c.ikHandle(startJoint=plan.start, endEffector=plan.end,
                                 solver="ikSplineSolver", createCurve=True,
                                 simplifyCurve=False, parentCurve=False)
            handle, curve = created[0], created[2]
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
            for node in (sampler, handle, curve):
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
            c.delete(plan.old_chain[1])
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
                          defaultValue=low + fraction * (high - low),
                          keyable=True)
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
