"""Remove the generated Body rig while retaining its authored Fit tree."""
from __future__ import annotations

from adv_py.core.body_delete import BodyDeletePlan
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyDeleteMixin:
    @property
    def _delete_cmds(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _delete_unique(self, leaf: str, *, node_type: str | None = None
                       ) -> str | None:
        c = self._delete_cmds
        paths = c.ls(self.scene_address(leaf), long=True,
                     **({"type": node_type} if node_type else {})) or ()
        if len(paths) > 1:
            raise FitSkeletonValidationError(
                "Delete Adv 节点名称不唯一：" + leaf)
        return paths[0] if paths else None

    def _delete_uuid(self, path: str) -> str:
        ids = self._delete_cmds.ls(path, uuid=True) or ()
        if len(ids) != 1:
            raise RuntimeError("Delete Adv 节点身份不唯一：" + path)
        return ids[0]

    def plan_delete_body_advanced(self) -> BodyDeletePlan | None:
        """Resolve ownership and preserved assets before opening Undo."""
        c = self._delete_cmds
        fit = self._delete_unique("FitSkeleton", node_type="transform")
        if fit is None:
            return None
        group = self._delete_unique("Group", node_type="transform")
        face = self._delete_unique("FaceGroup", node_type="transform")
        if face is not None:
            raise FitSkeletonValidationError(
                "此角色含 FaceSetup；须先移除 Face 绑定，再删除 Body Adv")
        geometry = self._delete_unique("Geometry", node_type="transform")
        if group is None:
            if geometry is not None:
                raise FitSkeletonValidationError(
                    "Body Group 缺失而 Geometry 仍存在，不能判定删除范围")
            return BodyDeletePlan(fit, self._delete_uuid(fit), None,
                                  (), (), (), (),
                                  c.upAxis(query=True, axis=True))
        if not fit.startswith(group + "|"):
            raise FitSkeletonValidationError(
                "FitSkeleton 不在当前 Body Group 内")
        if geometry is not None and not geometry.startswith(group + "|"):
            raise FitSkeletonValidationError(
                "Geometry 不在当前 Body Group 内")
        all_set = self._delete_unique("AllSet", node_type="objectSet")
        if all_set is None:
            raise FitSkeletonValidationError(
                "Body AllSet 缺失，不能确认生成节点的删除范围")
        owned = []
        for item in c.sets(all_set, query=True) or ():
            paths = c.ls(item, long=True) or ()
            if len(paths) != 1:
                raise FitSkeletonValidationError(
                    "AllSet 成员缺失或重名：" + item)
            if paths[0] not in owned:
                owned.append(paths[0])
        if not owned:
            raise FitSkeletonValidationError(
                "Body AllSet 为空，不能确认生成节点的删除范围")
        if any(path == fit or path.startswith(fit + "|")
               for path in owned):
            raise FitSkeletonValidationError(
                "Body AllSet 错误包含需要保留的 FitSkeleton")
        geometry_children = (tuple(c.listRelatives(
            geometry, children=True, type="transform", fullPath=True) or ())
            if geometry is not None else ())
        retained = tuple(self._delete_uuid(path) for path in geometry_children
                         if path not in owned)
        sets = tuple(path for name in ("ControlSet", "DeformSet",
                                            "AllSet", "Sets")
                     if (path := self._delete_unique(
                         name, node_type="objectSet")) is not None)
        for path in (fit, group, *geometry_children, *owned, *sets):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise FitSkeletonValidationError(
                    "Delete Adv 不修改引用节点：" + path)
        return BodyDeletePlan(
            fit, self._delete_uuid(fit), group, geometry_children,
            retained, tuple(owned), sets,
            c.upAxis(query=True, axis=True))

    def delete_body_advanced(self, plan: BodyDeletePlan) -> None:
        """Port asDeleteAdvanced's unparent, Z-up and Sets removal sequence."""
        self._require_transaction()
        c = self._delete_cmds
        if not c.objExists(plan.fit) or self._delete_uuid(plan.fit) != plan.fit_id:
            raise RuntimeError("Delete Adv 执行前 FitSkeleton 已变化")
        if plan.group is None:
            return
        if not c.objExists(plan.group):
            raise RuntimeError("Delete Adv 执行前 Group 已消失")
        self._transaction_changed = True
        fit = c.parent(plan.fit, world=True, absolute=True)[0]
        if plan.scene_up_axis == "z":
            self.flip_character_scene_up_axis(fit, "z")
        if plan.geometry_children:
            c.parent(*plan.geometry_children, world=True, absolute=True)
        # AllSet is the build's authoritative ownership list. Query it again
        # after reparenting, because DAG paths have changed in this undo chunk.
        all_set = self._delete_unique("AllSet", node_type="objectSet")
        if all_set is None:
            raise RuntimeError("Delete Adv 执行期间 AllSet 已消失")
        members = c.sets(all_set, query=True) or ()
        if len(members) != len(plan.owned_nodes):
            raise RuntimeError("Delete Adv 执行期间 AllSet 成员数变化")
        # A rig root contains many descendants also listed in AllSet. Delete
        # only independent DG / external DAG members first, then the root.
        group = plan.group
        resolved = []
        for item in members:
            paths = c.ls(item, long=True) or ()
            if len(paths) != 1:
                raise RuntimeError("Delete Adv AllSet 成员丢失：" + item)
            resolved.append(paths[0])
        direct_children = tuple(c.listRelatives(
            group, children=True, fullPath=True) or ())
        owned = set(resolved)
        for child in direct_children:
            if child.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Geometry":
                if c.listRelatives(child, children=True, fullPath=True):
                    raise RuntimeError("Delete Adv Geometry 仍有未移出的模型")
            elif child not in owned:
                raise RuntimeError("Delete Adv Group 含未登记子节点：" + child)
        external = tuple(path for path in resolved
                         if path != group and not path.startswith(group + "|"))
        if external:
            c.delete(external)
        if c.objExists(group):
            c.delete(group)
        for path in plan.set_nodes:
            if c.objExists(path):
                c.delete(path)
        remaining_fit = c.ls(fit, long=True, type="transform") or ()
        if (len(remaining_fit) != 1 or self._delete_uuid(remaining_fit[0])
                != plan.fit_id or c.objExists(group)):
            raise RuntimeError("Delete Adv 没有保留 Fit 或未移除 Body Group")
        remaining_geometry = {
            identifier for path in c.ls(assemblies=True, long=True) or ()
            for identifier in (c.ls(path, uuid=True) or ())}
        if not set(plan.retained_geometry_ids) <= remaining_geometry:
            raise RuntimeError("Delete Adv 丢失了应保留的模型")
