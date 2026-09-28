"""Maya host for ADV's Remove Unused Influences action."""
from __future__ import annotations

from adv_py.core.skin_optimize import (
    PRUNE_THRESHOLD, PruneSkinWeightsPlan, SkinInfluenceState, SkinOptimizePlan,
    SkinWeightState,
)

from .maya_body import MayaBodyBuildHost


class MayaSkinOptimizeHost(MayaBodyBuildHost):
    def _skin_shapes(self) -> tuple[tuple[str, str], ...]:
        c = self._cmds.raw if self.namespace else self._cmds
        geometry = (c.ls(self.scene_address("|Group|Geometry"),
                         long=True, type="transform") or [])
        if len(geometry) != 1:
            raise ValueError("当前角色缺少唯一的 Group|Geometry")
        root = geometry[0]
        shapes = c.listRelatives(root, allDescendents=True,
                                 fullPath=True, type="mesh") or []
        skin_shapes = set()
        for shape in shapes:
            if c.getAttr(shape + ".intermediateObject"):
                continue
            for node in c.listHistory(shape, pruneDagObjects=True) or []:
                if c.nodeType(node) == "skinCluster":
                    skin_shapes.add(((c.ls(node, long=True) or [node])[0],
                                     shape))
        for skin in {skin for skin, _ in skin_shapes}:
            for shape in c.skinCluster(skin, query=True, geometry=True) or []:
                matches = c.ls(shape, long=True) or []
                if len(matches) != 1 or not matches[0].startswith(root + "|"):
                    raise ValueError("Skin 同时影响当前角色 Geometry 以外的网格："
                                     + skin)
        return tuple(sorted(skin_shapes))

    def _skin_nodes(self) -> tuple[str, ...]:
        return tuple(sorted({skin for skin, _ in self._skin_shapes()}))

    def capture_skin_influences(self) -> tuple[SkinInfluenceState, ...]:
        c = self._cmds.raw if self.namespace else self._cmds
        return tuple(SkinInfluenceState(
            skin,
            len(c.skinCluster(skin, query=True, influence=True) or []),
            int(c.skinCluster(skin, query=True,
                              removeUnusedInfluence=True)),
        ) for skin in self._skin_nodes())

    def preflight_skin_optimize(self, plan: SkinOptimizePlan) -> None:
        c = self._cmds.raw if self.namespace else self._cmds
        if self.capture_skin_influences() != plan.before:
            raise ValueError("Skin 输入发生变化")
        for item in plan.before:
            if (c.referenceQuery(item.skin, isNodeReferenced=True)
                    or c.lockNode(item.skin, query=True, lock=True)[0]):
                raise ValueError("Skin 被引用或锁定，不能清理：" + item.skin)

    def remove_unused_skin_influences(self, plan: SkinOptimizePlan) -> None:
        self._require_transaction()
        self.preflight_skin_optimize(plan)
        c = self._cmds.raw if self.namespace else self._cmds
        for item in plan.before:
            if item.unused_count:
                self._transaction_changed = True
                c.skinCluster(item.skin, edit=True,
                              removeUnusedInfluence=True)

    def capture_skin_weights(self) -> tuple[SkinWeightState, ...]:
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma

        c = self._cmds.raw if self.namespace else self._cmds
        states = []
        for skin, shape in self._skin_shapes():
            selection = om.MSelectionList()
            selection.add(skin)
            skin_fn = oma.MFnSkinCluster(selection.getDependNode(0))
            selection = om.MSelectionList()
            selection.add(shape)
            dag = selection.getDagPath(0)
            vertices = int(om.MFnMesh(dag).numVertices)
            component_fn = om.MFnSingleIndexedComponent()
            component = component_fn.create(om.MFn.kMeshVertComponent)
            component_fn.addElements(range(vertices))
            values, width = skin_fn.getWeights(dag, component)
            influences = skin_fn.influenceObjects()
            if width != len(influences) or len(values) != vertices * width:
                raise RuntimeError("Skin 权重矩阵维度无效：" + shape)
            locked = tuple(bool(c.getAttr(path.fullPathName()
                                           + ".lockInfluenceWeights"))
                           if c.objExists(path.fullPathName()
                                          + ".lockInfluenceWeights") else False
                           for path in influences)
            weak = 0
            locked_weak = 0
            for index, weight in enumerate(values):
                if 0.0 < weight < PRUNE_THRESHOLD:
                    weak += 1
                    if locked[index % width]:
                        locked_weak += 1
            states.append(SkinWeightState(skin, shape, vertices, width,
                                          weak, locked_weak))
        return tuple(states)

    def preflight_skin_prune(self, plan: PruneSkinWeightsPlan) -> None:
        c = self._cmds.raw if self.namespace else self._cmds
        if self.capture_skin_weights() != plan.before:
            raise ValueError("Skin 权重输入发生变化")
        for skin in {item.skin for item in plan.before}:
            if (c.referenceQuery(skin, isNodeReferenced=True)
                    or c.lockNode(skin, query=True, lock=True)[0]):
                raise ValueError("Skin 被引用或锁定，不能修剪：" + skin)

    def prune_skin_weights(self, plan: PruneSkinWeightsPlan) -> None:
        self._require_transaction()
        self.preflight_skin_prune(plan)
        c = self._cmds.raw if self.namespace else self._cmds
        for item in plan.before:
            if item.weak_count:
                parents = c.listRelatives(item.shape, parent=True,
                                          fullPath=True) or []
                if len(parents) != 1:
                    raise RuntimeError("蒙皮网格缺少唯一的父节点：" + item.shape)
                self._transaction_changed = True
                c.skinPercent(item.skin, parents[0],
                              pruneWeights=plan.threshold)
