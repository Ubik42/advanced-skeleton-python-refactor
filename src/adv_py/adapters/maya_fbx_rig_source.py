"""Read a bound FBX hierarchy and its bind pose without retaining scene edits."""
from __future__ import annotations

from adv_py.application.fbx_rig_import import (FBXRigBuildAudit,
                                               FBXRigGeneratedTargets,
                                               FBXRigSourceCapture)
from adv_py.application.fit_container import CreateFitSkeleton
from adv_py.application.oriented_fit_template import BuildOrientedFitTemplate
from adv_py.application.oriented_body_skeleton import BuildOrientedBodySkeleton
from adv_py.application.registered_body_build import _JoinedTransactionHost
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fbx_rig_import import FBXRigImportPlan, FBXRigSourceJoint
from adv_py.core.fbx_rig_import import (FBXRigControlTransferPlan,
                                        FBXRigFitGuideState)
from adv_py.core.fbx_rig_fk import plan_fbx_rig_fk_controls
from adv_py.core.body_root_motion import plan_body_root_motion
from adv_py.core.fit_orientation import (FitOrientationChildSelection,
                                         FitOrientationRequest)
from adv_py.core.fit_template import FitJointSpec, FitTemplateSpec
from adv_py.core.joint_labels import JointLabel

from .maya_source_skeleton_fit import MayaSourceSkeletonFitHost
from .maya_fbx_rig_transfer import MayaFBXRigTransferMixin


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
        skin_boundary = []
        for skin in c.ls(type="skinCluster") or ():
            influences = set(c.ls(c.skinCluster(skin, query=True,
                                                influence=True) or (),
                                  long=True) or ())
            if not influences.intersection(paths):
                continue
            geometry_ids = []
            for geometry in c.skinCluster(skin, query=True,
                                           geometry=True) or ():
                mesh = (c.listRelatives(geometry, parent=True,
                                        fullPath=True) or (None,))[0]
                if mesh is not None and mesh not in meshes:
                    meshes.append(mesh)
                if mesh is not None:
                    geometry_ids.extend(c.ls(mesh, uuid=True) or ())
            influence_ids = tuple(sorted(
                item for path in influences
                for item in (c.ls(path, uuid=True) or ())))
            skin_boundary.append((
                (c.ls(skin, uuid=True) or (None,))[0],
                tuple(sorted(geometry_ids)), influence_ids))
        if not getattr(self, "_transaction_active", False):
            self._fbx_skin_boundary = tuple(sorted(skin_boundary))
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


class MayaFBXRigPreparationHost(MayaFBXRigTransferMixin,
                                MayaSourceSkeletonFitHost,
                                MayaFBXRigSourceReader):
    """Prepare the imported source in the same undo transaction as rig build."""

    def __init__(self) -> None:
        MayaSourceSkeletonFitHost.__init__(self)

    def choose_fbx_rig_route(self,
                             detected_application: str | None) -> str:
        message = "为场景中的已蒙皮 FBX 骨架创建控制器？"
        if detected_application:
            message += "\n检测到 " + detected_application + "；请确认继续 FBX rig。"
        choice = self._cmds.confirmDialog(
            title="FBX rig", message=message,
            button=("继续", "取消"), defaultButton="取消",
            cancelButton="取消", dismissString="取消")
        return "fbx_rig" if choice == "继续" else "cancel"

    def route_to_fbx_name_matcher(self) -> None:
        raise NotImplementedError("NameMatcher 构建宿主尚未实现")

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

    def create_fbx_fit_guides(self, plan: FBXRigImportPlan) -> None:
        self._require_transaction()
        c = self._cmds
        by_name = {guide.name: guide for guide in plan.fit_guides}
        labels = dict(plan.inferred_labels)
        specs = []
        children: dict[str, list[str]] = {}
        for guide in plan.fit_guides:
            parent_position = ((0.0, 0.0, 0.0) if guide.parent is None
                               else by_name[guide.parent].world_position)
            local = tuple(value - parent for value, parent in zip(
                guide.world_position, parent_position))
            specs.append(FitJointSpec(guide.name, guide.parent, local,
                JointLabel.parse(labels.get(guide.name, guide.name))))
            if guide.parent is not None:
                children.setdefault(guide.parent, []).append(guide.name)
        template = FitTemplateSpec("fbx_rig", tuple(specs))
        selections = tuple(FitOrientationChildSelection(name, names[0])
                           for name, names in children.items()
                           if len(names) > 1)
        request = FitOrientationRequest(tuple(children), selections)
        joined = _JoinedTransactionHost(self)
        CreateFitSkeleton(joined).apply("FitSkeleton")
        c.setAttr("FitSkeleton.lockCenterJoints", False)
        BuildOrientedFitTemplate(joined).apply(template, request,
            "FitSkeleton", transaction_label="建立 FBX rig Fit 导向",
            error_context="FBX rig Fit 导向")
        for guide in plan.fit_guides:
            if not guide.end_control:
                continue
            path = self._fbx_fit_guide_path(guide.name, by_name)
            c.addAttr(path, longName="control", attributeType="bool",
                      defaultValue=True, keyable=True)
        self._transaction_changed = True

    @staticmethod
    def _fbx_fit_guide_path(name: str, by_name: dict) -> str:
        parts = [name]
        while (parent := by_name[parts[-1]].parent) is not None:
            parts.append(parent)
        return "|FitSkeleton|" + "|".join(reversed(parts))

    def capture_fbx_fit_guides(
        self, plan: FBXRigImportPlan,
    ) -> tuple[FBXRigFitGuideState, ...]:
        c = self._cmds
        by_name = {guide.name: guide for guide in plan.fit_guides}
        result = []
        for guide in plan.fit_guides:
            path = self._fbx_fit_guide_path(guide.name, by_name)
            matches = c.ls(path, long=True, type="joint") or ()
            if len(matches) != 1:
                raise RuntimeError("FBX rig Fit 导向缺失：" + guide.name)
            position = tuple(float(value) for value in c.xform(
                path, query=True, worldSpace=True, translation=True))
            label = self.read_joint_label(path)
            result.append(FBXRigFitGuideState(
                guide.name, guide.parent, position,
                bool(c.attributeQuery("control", node=path, exists=True)
                     and c.getAttr(path + ".control")),
                label.text if label is not None else None))
        return tuple(result)

    def build_fbx_body_skeleton(
        self, plan: FBXRigImportPlan,
    ) -> BodySkeletonSnapshot:
        """Build the mirrored deformation hierarchy without moving old Skin."""
        self._require_transaction()
        deformation = self.create_body_system_hierarchy()
        built = BuildOrientedBodySkeleton(
            _JoinedTransactionHost(self)).apply(
                "FitSkeleton",
                center_tolerance=plan.side_threshold_cm,
                infer_missing_labels=False,
                root_parent_path=deformation)
        names = {joint.name for joint in built.snapshot.joints}
        if "Root_M" not in names or len(names) != len(built.snapshot.joints):
            raise RuntimeError("FBX rig Body 骨架创建后名称不完整")
        return built.snapshot

    def build_fbx_advanced_skeleton(self, plan: FBXRigImportPlan) -> None:
        """Establish the generic Body/FK branch; IK labels are a later stage."""
        self._require_transaction()
        c = self._cmds
        if any(c.objExists(name) for name in (
                "MainSystem", "Main", "ControlSet", "DeformSet", "AllSet")):
            raise ValueError("FBX rig 主控或选择集名称已被占用")
        body = self.build_fbx_body_skeleton(plan)
        controls = plan_fbx_rig_fk_controls(body, plan)
        main_system = c.createNode("transform", name="MainSystem",
                                   parent="|Group|MotionSystem")
        main = c.circle(name="Main", normal=(0, 1, 0),
                        radius=max(plan.scale * 2.5, .01),
                        constructionHistory=False)[0]
        main = c.parent(main, main_system, relative=True)[0]
        c.setAttr(main + ".overrideEnabled", True)
        c.setAttr(main + ".overrideColor", 17)
        control_paths: dict[str, str] = {}
        for spec in controls:
            parent = (control_paths[spec.parent_control_name]
                      if spec.parent_control_name is not None else main)
            offset = c.createNode("transform",
                                  name=spec.control_name + "Offset",
                                  parent=parent)
            matrix = c.xform(spec.body_joint_path, query=True,
                             worldSpace=True, matrix=True)
            c.xform(offset, worldSpace=True, matrix=matrix)
            control = c.circle(name=spec.control_name, normal=(1, 0, 0),
                               radius=spec.radius,
                               constructionHistory=False)[0]
            control = c.parent(control, offset, relative=True)[0]
            control_paths[spec.control_name] = (
                c.ls(control, long=True, type="transform") or [control])[0]
            c.setAttr(control + ".overrideEnabled", True)
            c.setAttr(control + ".overrideColor",
                      13 if spec.control_name.endswith("_R") else
                      6 if spec.control_name.endswith("_L") else 17)
            constraint = c.parentConstraint(control, spec.body_joint_path,
                maintainOffset=False,
                name="AdvPy_FBX_" + spec.control_name + "_Parent")
            if len(constraint) != 1:
                raise RuntimeError("FBX rig FK 控制约束创建失败："
                                   + spec.control_name)
        c.sets(tuple(control_paths.values()) + (main,), name="ControlSet")
        c.sets(tuple(joint.path for joint in body.joints), name="DeformSet")
        c.sets("ControlSet", "DeformSet", name="AllSet")
        if set(control_paths) != {spec.control_name for spec in controls}:
            raise RuntimeError("FBX rig FK 控制器写后数量不符")
        self._transaction_changed = True

    def capture_fbx_generated_targets(
        self, plan: FBXRigImportPlan,
    ) -> FBXRigGeneratedTargets:
        c = self._cmds
        candidates = tuple(link.control_name
                           for link in plan.candidate_control_links)
        controls = tuple(name for name in candidates
                         if len(c.ls(name, long=True, type="transform") or ()) == 1)
        deformation = "|Group|DeformationSystem"
        joints = c.listRelatives(deformation, allDescendents=True,
                                 type="joint", fullPath=True) or ()
        deform_names = tuple(path.rsplit("|", 1)[-1] for path in joints)
        return FBXRigGeneratedTargets(controls, deform_names)

    def enlarge_small_fbx_fk_controls(self, plan: FBXRigImportPlan) -> None:
        """The generic FK plan creates final-size curves; verify each shape."""
        self._require_transaction()
        c = self._cmds
        for link in plan.candidate_control_links:
            controls = c.ls(link.control_name, long=True,
                            type="transform") or ()
            if len(controls) != 1:
                raise RuntimeError("FBX rig FK 控制器缺失：" + link.control_name)
            shapes = c.listRelatives(controls[0], shapes=True,
                                     noIntermediate=True, fullPath=True,
                                     type="nurbsCurve") or ()
            if not shapes:
                raise RuntimeError("FBX rig FK 控制器没有曲线："
                                   + link.control_name)

    def connect_fbx_game_root_motion(
        self, plan: FBXRigImportPlan, source_paths: dict[str, str],
    ) -> None:
        self._require_transaction()
        if plan.game_root_joint is None:
            raise ValueError("FBX rig 没有游戏根关节")
        c = self._cmds
        body_root = self._only_fbx_node("Root_M", "joint")
        root_motion = plan_body_root_motion(
            source_root_path=body_root,
            up_axis=self.scene_up_axis(),
            output_basename="RootMotion_M")
        if any(c.objExists(name) for name in root_motion.node_names):
            raise ValueError("FBX rig Root Motion 名称已被占用")
        self.create_body_root_motion(root_motion)
        source = self._only_fbx_node(
            source_paths[plan.game_root_joint], "joint")
        name = "AdvPy_FBX_GameRoot_Parent"
        self._transaction_changed = True
        c.parentConstraint(root_motion.output_path, source,
                           maintainOffset=True, name=name)
        self._fbx_game_root_constraint = name

    def restore_fbx_scene_time(self, source: FBXRigSourceCapture) -> None:
        c = self._cmds
        c.autoKeyframe(state=False)
        c.playbackOptions(minTime=source.playback_start,
                          animationStartTime=source.playback_start,
                          maxTime=source.playback_end,
                          animationEndTime=source.playback_end)
        c.currentTime(source.current_time)
        c.autoKeyframe(state=source.auto_key_enabled)

    def _current_fbx_skin_boundary(self) -> tuple:
        c = self._cmds
        expected_ids = {row[0] for row in getattr(
            self, "_fbx_skin_boundary", ())}
        result = []
        for skin in c.ls(type="skinCluster") or ():
            identifier = (c.ls(skin, uuid=True) or (None,))[0]
            if identifier not in expected_ids:
                continue
            geometry_ids = []
            for geometry in c.skinCluster(skin, query=True,
                                           geometry=True) or ():
                mesh = (c.listRelatives(geometry, parent=True,
                                        fullPath=True) or (None,))[0]
                if mesh is not None:
                    geometry_ids.extend(c.ls(mesh, uuid=True) or ())
            influence_ids = tuple(sorted(
                item for path in (c.skinCluster(skin, query=True,
                                                 influence=True) or ())
                for item in (c.ls(path, uuid=True) or ())))
            result.append((identifier, tuple(sorted(geometry_ids)),
                           influence_ids))
        return tuple(sorted(result))

    def capture_fbx_rig_audit(
        self, plan: FBXRigImportPlan,
        transfer: FBXRigControlTransferPlan,
        source_paths: dict[str, str],
    ) -> FBXRigBuildAudit:
        c = self._cmds
        connected_controls = []
        connected_sources = []
        for link in transfer.links:
            source = source_paths[link.source_joint]
            constraint = "AdvPy_FBX_Source_" + link.control_name
            if not c.objExists(constraint):
                continue
            targets = c.parentConstraint(constraint, query=True,
                                         targetList=True) or ()
            driver = (c.ls(link.deform_driver_name,
                           long=True) or (None,))[0]
            resolved = tuple((c.ls(target, long=True) or (None,))[0]
                             for target in targets)
            outputs = c.listConnections(source + ".translate",
                source=True, destination=False,
                type="parentConstraint") or ()
            if resolved == (driver,) and constraint in outputs:
                connected_controls.append(link.control_name)
                connected_sources.append(source)
        source_nodes = tuple(source_paths.values())
        source_animation_removed = not any(
            c.listConnections(path, source=True, destination=False,
                              type="animCurve") for path in source_nodes)
        baked = (plan.last_bake_frame is not None and all(
            c.keyframe(link.control_name, query=True,
                       timeChange=True)
            for link in transfer.links))
        game_connected = False
        if plan.game_root_joint is not None:
            name = getattr(self, "_fbx_game_root_constraint", "")
            game_connected = bool(name and c.objExists(name))
        return FBXRigBuildAudit(
            fit_guide_count=len(self.capture_fbx_fit_guides(plan)),
            paired_side_count=sum(
                c.objExists(source_paths[pair.right_joint])
                and c.objExists(source_paths[pair.left_joint])
                for pair in plan.mirror_pairs),
            connected_control_names=tuple(connected_controls),
            original_skeleton_constrained=(
                len(connected_sources) == len(transfer.links)),
            control_animation_baked=bool(baked),
            game_root_motion_connected=game_connected,
            bound_meshes_preserved=(
                self._current_fbx_skin_boundary()
                == getattr(self, "_fbx_skin_boundary", None)),
            temporary_bake_links_removed=not any(c.objExists(
                "AdvPy_FBX_Temp_" + link.control_name)
                for link in transfer.links),
            source_joint_animation_removed=source_animation_removed,
            connected_source_paths=tuple(connected_sources))
