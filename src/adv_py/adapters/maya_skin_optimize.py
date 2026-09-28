"""Maya host for ADV's Remove Unused Influences action."""
from __future__ import annotations

from adv_py.core.skin_optimize import SkinInfluenceState, SkinOptimizePlan

from .maya_body import MayaBodyBuildHost


class MayaSkinOptimizeHost(MayaBodyBuildHost):
    def _skin_nodes(self) -> tuple[str, ...]:
        c = self._cmds.raw if self.namespace else self._cmds
        geometry = (c.ls(self.scene_address("|Group|Geometry"),
                         long=True, type="transform") or [])
        if len(geometry) != 1:
            raise ValueError("当前角色缺少唯一的 Group|Geometry")
        root = geometry[0]
        shapes = c.listRelatives(root, allDescendents=True,
                                 fullPath=True, type="mesh") or []
        skins = set()
        for shape in shapes:
            if c.getAttr(shape + ".intermediateObject"):
                continue
            for node in c.listHistory(shape, pruneDagObjects=True) or []:
                if c.nodeType(node) == "skinCluster":
                    skins.add((c.ls(node, long=True) or [node])[0])
        for skin in skins:
            for shape in c.skinCluster(skin, query=True, geometry=True) or []:
                matches = c.ls(shape, long=True) or []
                if len(matches) != 1 or not matches[0].startswith(root + "|"):
                    raise ValueError("Skin 同时影响当前角色 Geometry 以外的网格："
                                     + skin)
        return tuple(sorted(skins))

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
