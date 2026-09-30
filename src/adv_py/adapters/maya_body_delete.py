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

    def plan_delete_body_advanced(self, *,
                                  face_will_be_deleted: bool = False
                                  ) -> BodyDeletePlan | None:
        """Resolve ownership and preserved assets before opening Undo."""
        c = self._delete_cmds
        fit = self._delete_unique("FitSkeleton", node_type="transform")
        if fit is None:
            return None
        group = self._delete_unique("Group", node_type="transform")
        face = self._delete_unique("FaceGroup", node_type="transform")
        if (self._delete_unique("FaceMotionSystem", node_type="transform")
                is not None and not face_will_be_deleted):
            raise FitSkeletonValidationError(
                "此角色含 FaceSetup；须先移除 Face 绑定，再删除 Body Adv")
        geometry = self._delete_unique("Geometry", node_type="transform")
        if group is None:
            if geometry is not None:
                raise FitSkeletonValidationError(
                    "Body Group 缺失而 Geometry 仍存在，不能判定删除范围")
            return BodyDeletePlan(fit, self._delete_uuid(fit), None,
                                  (), (), (), (), (), (),
                                  c.upAxis(query=True, axis=True))
        if not fit.startswith(group + "|"):
            raise FitSkeletonValidationError(
                "FitSkeleton 不在当前 Body Group 内")
        if geometry is not None and not geometry.startswith(group + "|"):
            raise FitSkeletonValidationError(
                "Geometry 不在当前 Body Group 内")
        if face is not None and face.startswith(group + "|"):
            if face.rsplit("|", 1)[0] != group:
                raise FitSkeletonValidationError(
                    "Face Fit 嵌在 Body 子系统中，不能安全保留")
            face_fit = self._delete_unique(
                "FaceFitSkeleton", node_type="transform")
            if face_fit is None or not face_fit.startswith(face + "|"):
                raise FitSkeletonValidationError(
                    "FaceGroup 缺少 FaceFitSkeleton，不能判定保留范围")
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
        if face is not None and any(
                path == face or path.startswith(face + "|") for path in owned):
            raise FitSkeletonValidationError(
                "Body AllSet 错误包含需要保留的 Face Fit")
        geometry_children = (tuple(c.listRelatives(
            geometry, children=True, fullPath=True) or ())
            if geometry is not None else ())
        if any(c.nodeType(path) not in ('transform','joint')
               for path in geometry_children):
            raise FitSkeletonValidationError(
                'Delete Adv 的 Geometry 存在无法单独保留的直属 Shape')
        owned_set = set(owned)
        nested = []
        for root in geometry_children:
            if root not in owned_set:
                continue
            descendants = c.listRelatives(root, allDescendents=True,
                                          fullPath=True) or ()
            for path in sorted(descendants, key=lambda item:(item.count('|'),item)):
                if path in owned_set or any(path.startswith(item+'|')
                                             for item in nested):
                    continue
                parent=(c.listRelatives(path,parent=True,fullPath=True) or [None])[0]
                if parent not in owned_set:
                    continue
                if c.nodeType(path) not in ('transform','joint'):
                    raise FitSkeletonValidationError(
                        'Delete Adv 无法单独保留 Geometry 下的非变换子节点：'+path)
                nested.append(path)
        retained = tuple(self._delete_uuid(path) for path in
                         (*geometry_children,*nested) if path not in owned_set)
        fit_curves = tuple(dict.fromkeys(c.listConnections(
            fit, type="animCurve") or ()))
        preserved_animation = tuple(self._delete_uuid(curve)
                                    for curve in fit_curves)
        sets = tuple(path for name in ("ControlSet", "DeformSet",
                                            "AllSet", "Sets")
                     if (path := self._delete_unique(
                         name, node_type="objectSet")) is not None)
        for path in (fit, group, *((face,) if face else ()),
                     *geometry_children, *nested, *owned, *sets):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise FitSkeletonValidationError(
                    "Delete Adv 不修改引用节点：" + path)
        return BodyDeletePlan(
            fit, self._delete_uuid(fit), group, geometry_children,
            retained, preserved_animation, tuple(owned),
            tuple(self._delete_uuid(path) for path in owned), sets,
            c.upAxis(query=True, axis=True), face,
            self._delete_uuid(face) if face else None,
            tuple(nested),tuple(self._delete_uuid(path) for path in nested))

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
        if plan.face_fit_group is not None and (
                not c.objExists(plan.face_fit_group) or
                self._delete_uuid(plan.face_fit_group) !=
                plan.face_fit_group_id):
            raise RuntimeError("Delete Adv 执行前 Face Fit 已变化")
        if (len(plan.retained_nested_geometry_paths)
                != len(plan.retained_nested_geometry_ids)):
            raise RuntimeError('Delete Adv Geometry 用户子树记录不完整')
        for path,identifier in zip(plan.retained_nested_geometry_paths,
                                   plan.retained_nested_geometry_ids):
            if not c.objExists(path) or self._delete_uuid(path)!=identifier:
                raise RuntimeError('Delete Adv Geometry 用户子树已变化：'+path)
        self._transaction_changed = True
        if (plan.face_fit_group is not None and
                plan.face_fit_group.startswith(plan.group + "|")):
            c.parent(plan.face_fit_group, world=True, absolute=True)
        fit = c.parent(plan.fit, world=True, absolute=True)[0]
        if plan.scene_up_axis == "z":
            self.flip_character_scene_up_axis(fit, "z")
        for path in plan.retained_nested_geometry_paths:
            c.parent(path,world=True,absolute=True)
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
        if {self._delete_uuid(path) for path in resolved} != set(
                plan.owned_ids):
            raise RuntimeError("Delete Adv 执行期间 AllSet 成员身份变化")
        preserve_curves = set(plan.preserved_animation_ids)
        direct_children = tuple(c.listRelatives(
            group, children=True, fullPath=True) or ())
        owned = set(resolved)
        for child in direct_children:
            if child.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Geometry":
                if c.listRelatives(child, children=True, fullPath=True):
                    raise RuntimeError("Delete Adv Geometry 仍有未移出的模型")
            elif child not in owned:
                raise RuntimeError("Delete Adv Group 含未登记子节点：" + child)
        external_candidates = tuple(path for path in resolved
                                    if path != group
                                    and not path.startswith(group + "|")
                                    and self._delete_uuid(path)
                                    not in preserve_curves)
        external_set = set(external_candidates)
        external = tuple(path for path in external_candidates
                         if not (path.startswith("|") and any(
                             path.startswith(parent + "|")
                             for parent in external_set if parent != path)))
        for path in resolved:
            if path == group or path.startswith(group + "|"):
                continue
            if c.nodeType(path) == "multiplyDivide":
                plug = path + ".operation"
                if c.getAttr(plug, settable=True):
                    c.setAttr(plug, 0)
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
        remaining_curves = {self._delete_uuid(path)
                            for path in c.ls(type="animCurve") or ()}
        if not set(plan.preserved_animation_ids) <= remaining_curves:
            raise RuntimeError("Delete Adv 丢失了 Fit 驱动曲线")
        if plan.face_fit_group_id is not None:
            surviving = self._delete_unique("FaceGroup", node_type="transform")
            if (surviving is None or not surviving.startswith("|") or
                    surviving.count("|") != 1 or
                    self._delete_uuid(surviving) != plan.face_fit_group_id):
                raise RuntimeError("Delete Adv 丢失了 Face Fit")
