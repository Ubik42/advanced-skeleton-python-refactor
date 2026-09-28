"""Read a bound FBX hierarchy and its bind pose without retaining scene edits."""
from __future__ import annotations

from adv_py.application.fbx_rig_import import FBXRigSourceCapture
from adv_py.core.fbx_rig_import import FBXRigImportPlan, FBXRigSourceJoint

from .maya_source_skeleton_fit import MayaSourceSkeletonFitHost


class MayaFBXRigSourceReader:
    def __init__(self, cmds=None) -> None:
        if cmds is None:
            from maya import cmds as maya_cmds
            cmds = maya_cmds
        self._cmds = cmds

    def existing_advanced_skeleton_nodes(self) -> tuple[str, ...]:
        c = self._cmds
        names = ("Group", "AllSet", "ControlSet", "DeformSet")
        return tuple(name for name in names if c.objExists(name))

    def _source_paths(self) -> tuple[str, ...]:
        c = self._cmds
        joints = tuple(c.ls(type="joint", long=True) or ())
        if not joints:
            raise ValueError("FBX rig 场景没有来源关节")
        depth = min(path.count("|") for path in joints)
        roots = tuple(path for path in joints if path.count("|") == depth)
        if len(roots) != 1:
            raise ValueError("FBX rig 需要唯一顶层来源骨架")
        root = roots[0]
        paths = (root, *(c.listRelatives(root, allDescendents=True,
                 type="joint", fullPath=True) or ()))
        return tuple(sorted(set(paths), key=lambda path: (path.count("|"), path)))

    def _joint_states(self, paths: tuple[str, ...]) -> tuple[FBXRigSourceJoint, ...]:
        c = self._cmds
        included = set(paths)
        result = []
        for path in paths:
            parent = (c.listRelatives(path, parent=True, fullPath=True)
                      or (None,))[0]
            while parent is not None and parent not in included:
                parent = (c.listRelatives(parent, parent=True,
                                          fullPath=True) or (None,))[0]
            position = tuple(float(value) for value in c.xform(
                path, query=True, worldSpace=True, translation=True))
            result.append(FBXRigSourceJoint(
                path, path.rsplit("|", 1)[-1], parent, position))
        return tuple(result)

    def capture_fbx_rig_source(self) -> FBXRigSourceCapture:
        c = self._cmds
        paths = self._source_paths()
        joints = self._joint_states(paths)
        times = tuple(sorted(set(float(value) for value in (
            c.keyframe(paths, query=True, timeChange=True) or ()))))
        descendants = c.listRelatives(paths[0], allDescendents=True,
                                       type="transform", fullPath=True) or ()
        highest_y = max((float(c.xform(path, query=True, worldSpace=True,
                                       translation=True)[1])
                         for path in (*paths, *descendants)), default=0.0)
        meshes = []
        for skin in c.ls(type="skinCluster") or ():
            influences = set(c.ls(c.skinCluster(skin, query=True,
                                                influence=True) or (),
                                  long=True) or ())
            if not influences.intersection(paths):
                continue
            for geometry in c.skinCluster(skin, query=True,
                                           geometry=True) or ():
                mesh = (c.listRelatives(geometry, parent=True,
                                        fullPath=True) or (None,))[0]
                if mesh is not None and mesh not in meshes:
                    meshes.append(mesh)
        return FBXRigSourceCapture(
            joints, times, highest_y, None, tuple(meshes),
            float(c.currentTime(query=True)),
            float(c.playbackOptions(query=True, minTime=True)),
            float(c.playbackOptions(query=True, maxTime=True)),
            bool(c.autoKeyframe(query=True, state=True)))

    def capture_fbx_bind_pose_joints(
        self, source: FBXRigSourceCapture,
    ) -> tuple[FBXRigSourceJoint, ...]:
        """Restore dagPose inside one undo chunk, then undo that whole probe."""
        c = self._cmds
        if not c.undoInfo(query=True, state=True):
            raise ValueError("FBX rig 绑定姿态预检需要启用 Maya Undo")
        if tuple(joint.path for joint in source.joints) != self._source_paths():
            raise ValueError("FBX rig 来源骨架在预检前已变化")
        captured = None
        marker = None
        c.undoInfo(openChunk=True, chunkName="AdvPy FBX bind pose probe")
        try:
            # The marker guarantees an undoable chunk even when -1 is already
            # current and no dagPose needs restoring.
            marker = c.createNode("transform")
            c.currentTime(-1)
            for pose in c.ls(type="dagPose") or ():
                c.dagPose(pose, restore=True)
            captured = self._joint_states(tuple(
                joint.path for joint in source.joints))
        finally:
            c.undoInfo(closeChunk=True)
            c.undo()
        if marker is not None and c.objExists(marker):
            raise RuntimeError("FBX rig 绑定姿态预检未撤销临时节点")
        if abs(float(c.currentTime(query=True)) - source.current_time) > 1e-6:
            raise RuntimeError("FBX rig 绑定姿态预检未恢复原场景时间")
        restored = self._joint_states(tuple(
            joint.path for joint in source.joints))
        if any(any(abs(a - b) > 1e-4 for a, b in zip(
                current.world_position, before.world_position))
               for current, before in zip(restored, source.joints)):
            raise RuntimeError("FBX rig 绑定姿态预检未恢复原骨架")
        assert captured is not None
        return captured


class MayaFBXRigPreparationHost(MayaSourceSkeletonFitHost,
                                MayaFBXRigSourceReader):
    """Prepare the imported source in the same undo transaction as rig build."""

    def __init__(self) -> None:
        MayaSourceSkeletonFitHost.__init__(self)

    def preflight_fbx_rig_import(
        self, plan: FBXRigImportPlan, source: FBXRigSourceCapture,
    ) -> None:
        c = self._cmds
        if (tuple(joint.path for joint in source.joints) != self._source_paths()
                or not c.objExists(plan.root_joint)):
            raise ValueError("FBX rig 来源骨架在规划后已变化")
        if c.namespace(exists="FBXRig"):
            raise ValueError("FBXRig 命名空间已存在，拒绝覆盖")
        if c.objExists("FitSkeleton"):
            raise ValueError("FitSkeleton 已存在，拒绝覆盖")
        names = []
        for joint in source.joints:
            if (c.referenceQuery(joint.path, isNodeReferenced=True)
                    or any(c.lockNode(joint.path, query=True,
                                      lock=True) or ())):
                raise ValueError("FBX rig 来源骨架被引用或锁定：" + joint.path)
            leaf = joint.name.rsplit(":", 1)[-1]
            names.append(leaf if joint.path == plan.top_joint
                         else leaf.replace("_", ""))
        if len(set(names)) != len(names):
            raise ValueError("FBX rig 清除下划线后来源关节名称冲突")
        for mesh in source.bound_meshes:
            if not c.objExists(mesh):
                raise ValueError("FBX rig 来源蒙皮网格已丢失：" + mesh)

    def prepare_fbx_bind_pose(
        self, plan: FBXRigImportPlan, source: FBXRigSourceCapture,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        if source.animation_key_times:
            self._transaction_changed = True
            c.playbackOptions(minTime=-1, animationStartTime=-1,
                              maxTime=plan.last_bake_frame,
                              animationEndTime=plan.last_bake_frame)
            c.currentTime(-1)
            c.autoKeyframe(state=True)
        poses = c.ls(type="dagPose") or ()
        if poses:
            self._transaction_changed = True
            for pose in poses:
                c.dagPose(pose, restore=True)

    def move_fbx_source_to_namespace(
        self, plan: FBXRigImportPlan,
    ) -> dict[str, str]:
        self._require_transaction()
        c = self._cmds
        if c.namespace(exists="FBXRig"):
            raise ValueError("FBXRig 命名空间在构建期间被占用")
        self._transaction_changed = True
        previous_namespace = c.namespaceInfo(currentNamespace=True)
        try:
            c.namespace(setNamespace=":")
            c.namespace(addNamespace="FBXRig")
        finally:
            c.namespace(setNamespace=previous_namespace)
        paths = {joint.path: joint.path for joint in plan.bind_pose_joints}
        for joint in sorted(plan.bind_pose_joints,
                            key=lambda item: item.path.count("|"),
                            reverse=True):
            current = paths[joint.path]
            leaf = joint.name.rsplit(":", 1)[-1]
            target = (leaf if joint.path == plan.top_joint
                      else leaf.replace("_", ""))
            before_parent = current.rsplit("|", 1)[0]
            renamed = c.rename(current, ":FBXRig:" + target)
            new_path = before_parent + "|" + renamed.rsplit("|", 1)[-1]
            resolved = c.ls(new_path, long=True, type="joint") or ()
            if len(resolved) != 1:
                raise RuntimeError("FBX rig 来源关节迁入命名空间失败："
                                   + joint.path)
            paths[joint.path] = resolved[0]
            for original, mapped in tuple(paths.items()):
                if mapped.startswith(current + "|"):
                    paths[original] = resolved[0] + mapped[len(current):]
        return paths
