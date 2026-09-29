"""Maya port of asDeleteAdvancedFace's owned graph and Skin cleanup."""
from __future__ import annotations

from adv_py.core.face_delete import FaceDeletePlan, FaceDeleteSkin
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFaceDeleteMixin:
    @property
    def _face_delete_cmds(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _face_delete_one(self, name: str, kind: str | None = None
                         ) -> str | None:
        c = self._face_delete_cmds
        paths = c.ls(self.scene_address(name), long=True,
                     **({"type": kind} if kind else {})) or ()
        if len(paths) > 1:
            raise FitSkeletonValidationError("Face 删除节点不唯一：" + name)
        return paths[0] if paths else None

    def _face_delete_id(self, path: str) -> str:
        ids = self._face_delete_cmds.ls(path, uuid=True) or ()
        if len(ids) != 1:
            raise FitSkeletonValidationError("Face 删除节点身份不唯一：" + path)
        return ids[0]

    def _face_delete_set_fit_value(self, plug: str, value,
                                   *, as_string: bool = False) -> None:
        c = self._face_delete_cmds
        locked = bool(c.getAttr(plug, lock=True))
        if locked:
            c.setAttr(plug, lock=False)
        try:
            if as_string:
                c.setAttr(plug, value, type="string")
            else:
                c.setAttr(plug, value)
        finally:
            if locked:
                c.setAttr(plug, lock=True)

    def plan_delete_face_advanced(self, *,
                                  keep_build_pose: bool = False
                                  ) -> FaceDeletePlan | None:
        c = self._face_delete_cmds
        motion = self._face_delete_one("FaceMotionSystem", "transform")
        if motion is None:
            return None
        face_set = self._face_delete_one("FaceAllSet", "objectSet")
        fit = self._face_delete_one("FaceFitSkeleton", "transform")
        if face_set is None or fit is None:
            raise FitSkeletonValidationError(
                "FaceSetup 缺少 FaceAllSet 或 FaceFitSkeleton，不能判定删除范围")
        owned = []
        for member in c.sets(face_set, query=True) or ():
            matches = c.ls(member, long=True) or ()
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    "FaceAllSet 成员缺失或重名：" + member)
            if matches[0] not in owned:
                owned.append(matches[0])
        if not owned or not any(
                motion == node or motion.startswith(node + "|")
                for node in owned):
            raise FitSkeletonValidationError(
                "FaceAllSet 没有包含 FaceMotionSystem")
        head_name = (c.getAttr(fit + ".HeadJoint")
                     if c.attributeQuery("HeadJoint", node=fit, exists=True)
                     else "") or ""
        head_matches = (c.ls(self.scene_address(head_name),
                             long=True, type="joint") if head_name else ())
        if not head_matches:
            face_joint = self._face_delete_one("FaceJoint_M", "joint")
            head_matches = (c.listRelatives(face_joint, parent=True,
                             fullPath=True, type="joint") or ()) if face_joint else ()
        if len(head_matches or ()) != 1:
            raise FitSkeletonValidationError("Face Fit 的 HeadJoint 缺失或重名")
        head = head_matches[0]
        for protected in (fit, head):
            if any(protected == node or protected.startswith(node + "|")
                   for node in owned):
                raise FitSkeletonValidationError(
                    "FaceAllSet 错误包含必须保留的节点：" + protected)
        skin_plans = []
        geometry_paths = set()
        for skin in c.ls(type="skinCluster") or ():
            skin_path = (c.ls(skin, long=True) or [None])[0]
            if skin_path is None:
                continue
            influences = []
            for influence in c.skinCluster(skin_path, query=True,
                                           influence=True) or ():
                matches = c.ls(influence, long=True, type="joint") or ()
                if len(matches) != 1:
                    raise FitSkeletonValidationError(
                        "Face Skin 影响关节缺失或重名：" + influence)
                influences.append(matches[0])
            generated = tuple(path for path in influences if any(
                path == node or path.startswith(node + "|")
                for node in owned))
            if not generated:
                continue
            geometry = []
            for shape in c.skinCluster(skin_path, query=True,
                                       geometry=True) or ():
                paths = c.ls(shape, long=True) or ()
                if len(paths) != 1:
                    raise FitSkeletonValidationError(
                        "Face Skin 几何体缺失或重名：" + shape)
                geometry.append(paths[0])
                geometry_paths.add(paths[0])
                geometry_paths.update(c.listRelatives(
                    paths[0], parent=True, fullPath=True) or ())
            if not geometry:
                raise FitSkeletonValidationError(
                    "Face Skin 缺少几何体：" + skin_path)
            skin_plans.append(FaceDeleteSkin(
                skin_path, self._face_delete_id(skin_path), generated,
                len(generated) == len(influences), tuple(geometry)))
        deletable = tuple(path for path in owned
                          if c.nodeType(path) not in (
                              "skinCluster", "mesh", "objectSet")
                          and path not in geometry_paths)
        if any(any(geometry.startswith(path + "|")
                   for geometry in geometry_paths)
               for path in deletable):
            raise FitSkeletonValidationError(
                "Face 删除范围包含蒙皮模型的父级")
        extra = tuple(node for name in ("asFaceBS", "asFaceDeltaMush",
                                       "FaceControlSet")
                      if (node := self._face_delete_one(name)) is not None)
        for path in (*owned, *extra, face_set, fit, head):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise FitSkeletonValidationError(
                    "Face 删除不能修改引用节点：" + path)
        return FaceDeletePlan(
            motion, self._face_delete_id(motion), face_set,
            self._face_delete_id(face_set), fit, self._face_delete_id(fit),
            head, self._face_delete_id(head), deletable,
            tuple(self._face_delete_id(path) for path in deletable),
            tuple(skin_plans), extra,
            tuple(self._face_delete_id(path) for path in extra),
            keep_build_pose)

    def delete_face_advanced(self, plan: FaceDeletePlan) -> None:
        self._require_transaction()
        c = self._face_delete_cmds
        for path, identifier in ((plan.motion, plan.motion_id),
                                 (plan.face_set, plan.face_set_id),
                                 (plan.fit, plan.fit_id),
                                 (plan.head, plan.head_id),
                                 *zip(plan.extra_nodes, plan.extra_ids)):
            if not c.objExists(path) or self._face_delete_id(path) != identifier:
                raise RuntimeError("Face 删除前关键节点已变化：" + path)
        current = tuple((c.ls(member, long=True) or [None])[0]
                        for member in c.sets(plan.face_set, query=True) or ())
        if (None in current or not set(plan.owned_ids) <= {
                self._face_delete_id(path) for path in current}):
            raise RuntimeError("FaceAllSet 成员在删除前已变化")
        self._transaction_changed = True
        for skin in plan.skins:
            if (not c.objExists(skin.path) or
                    self._face_delete_id(skin.path) != skin.identifier):
                raise RuntimeError("Face Skin 在删除前已变化：" + skin.path)
            if skin.add_head_before_removal:
                c.skinCluster(skin.path, edit=True,
                              addInfluence=plan.head, weight=1.0,
                              lockWeights=False)
            current_influences = tuple(
                (c.ls(path, long=True, type="joint") or [None])[0]
                for path in c.skinCluster(skin.path, query=True,
                                          influence=True) or ())
            if None in current_influences or not set(
                    skin.face_influences) <= set(current_influences):
                raise RuntimeError("Face Skin 影响关节在删除前已变化")
            locks = {}
            for joint in current_influences:
                plug = joint + ".lockInfluenceWeights"
                if c.objExists(plug):
                    locks[joint] = bool(c.getAttr(plug))
                    c.setAttr(plug, joint != plan.head)
            for joint in skin.face_influences:
                c.skinCluster(skin.path, edit=True, removeInfluence=joint)
            for joint, locked in locks.items():
                if c.objExists(joint + ".lockInfluenceWeights"):
                    c.setAttr(joint + ".lockInfluenceWeights", locked)
            for geometry in skin.geometry:
                if c.objExists(geometry):
                    c.skinPercent(skin.path, geometry, normalize=True)
        # Delete the independent DG nodes and only the outermost DAG roots.
        nodes = tuple(path for path in plan.owned_paths if c.objExists(path))
        node_set = set(nodes)
        roots = tuple(path for path in nodes if not (
            path.startswith("|") and any(
                path.startswith(parent + "|")
                for parent in node_set if parent != path)))
        if roots:
            c.delete(roots)
        for path in plan.extra_nodes:
            if c.objExists(path):
                c.delete(path)
        if c.objExists(plan.face_set):
            c.delete(plan.face_set)
        if not plan.keep_build_pose and c.attributeQuery(
                "run", node=plan.fit, exists=True):
            self._face_delete_set_fit_value(plan.fit + ".run", "",
                                            as_string=True)
        if not plan.keep_build_pose and c.attributeQuery(
                "advPyBuildPoseOverrides", node=plan.fit, exists=True):
            self._face_delete_set_fit_value(
                plan.fit + ".advPyBuildPoseOverrides", "[]",
                as_string=True)
        if c.attributeQuery("buildStep", node=plan.fit, exists=True):
            self._face_delete_set_fit_value(plan.fit + ".buildStep", 0)
        self._face_delete_set_fit_value(plan.fit + ".visibility", True)
        if (c.objExists(plan.motion) or c.objExists(plan.face_set)
                or self._face_delete_id(plan.fit) != plan.fit_id
                or self._face_delete_id(plan.head) != plan.head_id
                or any(not c.objExists(skin.path) or
                       self._face_delete_id(skin.path) != skin.identifier
                       for skin in plan.skins)):
            raise RuntimeError("Face 删除后 Fit、Head 或 Skin 未正确保留")
        for skin in plan.skins:
            remaining = {(c.ls(path, long=True, type="joint") or [None])[0]
                         for path in c.skinCluster(skin.path, query=True,
                                                   influence=True) or ()}
            if set(skin.face_influences) & remaining:
                raise RuntimeError("Face 删除后 Skin 仍保留面部生成关节："
                                   + skin.path)
        if not bool(c.getAttr(plan.fit + ".visibility")):
            raise RuntimeError("Face 删除后 Face Fit 没有重新显示")
