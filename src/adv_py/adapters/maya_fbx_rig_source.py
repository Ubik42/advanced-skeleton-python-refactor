"""Read a bound FBX hierarchy and its bind pose without retaining scene edits."""
from __future__ import annotations

from adv_py.application.fbx_rig_import import (FBXRigBuildAudit,
                                               FBXRigGeneratedTargets,
                                               FBXRigSourceCapture)
from adv_py.application.fit_container import CreateFitSkeleton
from adv_py.application.oriented_fit_template import BuildOrientedFitTemplate
from adv_py.application.oriented_body_skeleton import BuildOrientedBodySkeleton
from adv_py.application.registered_body_build import _JoinedTransactionHost
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot, plan_body_non_deform_markers,
)
from adv_py.core.body_all_set import BodyAllSetNode, plan_body_all_set
from adv_py.core.fbx_rig_import import (FBXRigImportPlan, FBXRigSourceJoint,
                                        detect_fbx_source_application,
                                        plan_fbx_game_root_motion)
from adv_py.core.fbx_rig_import import (FBXRigControlTransferPlan,
                                        FBXRigFitGuideState)
from adv_py.core.fbx_rig_fk import plan_fbx_rig_fk_controls
from adv_py.core.fbx_rig_ik import FBXRigIKLimb, plan_fbx_rig_ik_limbs
from adv_py.core.fit_orientation import (FitOrientationChildSelection,
                                         FitOrientationRequest)
from adv_py.core.fit_template import FitJointSpec, FitTemplateSpec
from adv_py.core.joint_labels import JointLabel

from .maya_source_skeleton_fit import MayaSourceSkeletonFitHost
from .maya_fbx_rig_transfer import MayaFBXRigTransferMixin
from .maya_adv_icons import create_adv_icon
from .maya_fbx_rig_autoscale import project_fbx_fk_controls


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

    def _source_transform_paths(self, top_joint: str) -> tuple[str, ...]:
        """Capture all transform descendants selected by asFBXRig."""
        c = self._cmds
        descendants = tuple(c.listRelatives(
            top_joint, allDescendents=True, fullPath=True) or ())
        paths = tuple(path for path in descendants
                      if c.nodeType(path) in ("joint", "transform"))
        return (*paths, top_joint)

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
        transforms = self._source_transform_paths(paths[0])
        times = tuple(sorted(set(float(value) for value in (
            c.keyframe(transforms, query=True, timeChange=True) or ()))))
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
        bound_skin_upper_y = (float(c.exactWorldBoundingBox(meshes[0])[4])
                              if meshes else None)
        return FBXRigSourceCapture(
            joints, times, highest_y,
            detect_fbx_source_application(tuple(
                c.ls(dagObjects=True, long=True) or ())), tuple(meshes),
            float(c.currentTime(query=True)),
            float(c.playbackOptions(query=True, minTime=True)),
            float(c.playbackOptions(query=True, maxTime=True)),
            bool(c.autoKeyframe(query=True, state=True)),
            bound_skin_upper_y)

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
        choice = self._cmds.confirmDialog(
            title="FBX rig", message="为场景中的已蒙皮 FBX 骨架创建控制器？",
            button=("继续", "取消"), defaultButton="取消",
            cancelButton="取消", dismissString="取消")
        if choice != "继续":
            return "cancel"
        if detected_application is None:
            return "fbx_rig"
        choice = self._cmds.confirmDialog(
            title="检测到来源骨架",
            message=("检测到 " + detected_application
                     + "。原版建议使用 NameMatcher 对齐外部骨架；请选择构建路径。"),
            button=("NameMatcher", "FBX rig", "取消"),
            defaultButton="NameMatcher", cancelButton="取消",
            dismissString="取消")
        return {"NameMatcher": "name_matcher",
                "FBX rig": "fbx_rig"}.get(choice, "cancel")

    def route_to_fbx_name_matcher(self, source_root: str) -> None:
        from adv_py.product.maya_panel import show_name_matcher_detail
        show_name_matcher_detail(source_root)

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
        source_transforms = self._source_transform_paths(plan.top_joint)
        if not set(joint.path for joint in source.joints) <= set(
                source_transforms):
            raise ValueError("FBX rig 来源骨架与 transform 层级不一致")
        planned_names = []
        for path in source_transforms:
            if (c.referenceQuery(path, isNodeReferenced=True)
                    or any(c.lockNode(path, query=True, lock=True) or ())):
                raise ValueError("FBX rig 来源 transform 被引用或锁定：" + path)
            leaf = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            planned_names.append((path.rsplit("|", 1)[0],
                leaf if path == plan.top_joint else leaf.replace("_", "")))
        if len(set(planned_names)) != len(planned_names):
            raise ValueError(
                "FBX rig 来源同级 transform 清除下划线后名称冲突")
        for mesh in source.bound_meshes:
            if not c.objExists(mesh):
                raise ValueError("FBX rig 来源蒙皮网格已丢失：" + mesh)

    def prepare_fbx_bind_pose(
        self, plan: FBXRigImportPlan, source: FBXRigSourceCapture,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        self._fbx_bind_positions = {
            joint.path: joint.world_position
            for joint in plan.bind_pose_joints}
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
        all_paths = self._source_transform_paths(plan.top_joint)
        identities = {
            path: ((c.ls(path, uuid=True) or (None,))[0], c.nodeType(path))
            for path in all_paths}
        if any(identifier is None for identifier, _ in identities.values()):
            raise RuntimeError("FBX rig 来源 transform 缺少节点身份")
        paths = {path: path for path in all_paths}
        for original in sorted(all_paths,
                               key=lambda path: path.count("|"),
                               reverse=True):
            current = paths[original]
            leaf = original.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            target = (leaf if original == plan.top_joint
                      else leaf.replace("_", ""))
            before_parent = current.rsplit("|", 1)[0]
            renamed = c.rename(current, ":FBXRig:" + target)
            new_path = before_parent + "|" + renamed.rsplit("|", 1)[-1]
            resolved = c.ls(new_path, long=True) or ()
            if len(resolved) != 1:
                raise RuntimeError("FBX rig 来源 transform 迁入命名空间失败："
                                   + original)
            paths[original] = resolved[0]
            for original, mapped in tuple(paths.items()):
                if mapped.startswith(current + "|"):
                    paths[original] = resolved[0] + mapped[len(current):]
        for original, mapped in paths.items():
            resolved = c.ls(mapped, long=True) or ()
            expected_id, expected_kind = identities[original]
            if (resolved != [mapped]
                    or (c.ls(mapped, uuid=True) or (None,))[0] != expected_id
                    or c.nodeType(mapped) != expected_kind):
                raise RuntimeError(
                    "FBX rig 来源 transform 在迁移后身份或类型改变："
                    + original)
            parent = original.rsplit("|", 1)[0]
            if parent in paths and not mapped.startswith(paths[parent] + "|"):
                raise RuntimeError(
                    "FBX rig 来源 transform 父链在迁移后断开："
                    + original)
        self._fbx_source_transform_paths = tuple(sorted(set(paths.values())))
        return {joint.path: paths[joint.path]
                for joint in plan.bind_pose_joints}

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
        CreateFitSkeleton(joined).apply(
            "FitSkeleton", display_radius=plan.fit_display_radius)
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

    def capture_fbx_fit_display_radius(self) -> float:
        c = self._cmds
        shapes = c.listRelatives("FitSkeleton", shapes=True,
                                 noIntermediate=True, fullPath=True,
                                 type="nurbsCurve") or ()
        if len(shapes) != 1:
            raise RuntimeError("FBX rig Fit 圆环曲线缺失或不唯一")
        bounds = c.exactWorldBoundingBox(shapes[0])
        return float(bounds[3] - bounds[0]) / 2.0

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
        fit_roots = c.ls("FitSkeleton", long=True, type="transform") or ()
        if len(fit_roots) != 1:
            raise RuntimeError("FBX rig Fit 根节点缺失或不唯一")
        result = []
        for guide in plan.fit_guides:
            path = (fit_roots[0] +
                    self._fbx_fit_guide_path(guide.name,
                                             by_name)[len("|FitSkeleton"):])
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
        self.parent_fit_skeleton_under_group("FitSkeleton")
        built = BuildOrientedBodySkeleton(
            _JoinedTransactionHost(self)).apply(
                "FitSkeleton",
                center_tolerance=plan.side_threshold_cm,
                root_parent_path=deformation)
        names = {joint.name for joint in built.snapshot.joints}
        if "Root_M" not in names or len(names) != len(built.snapshot.joints):
            raise RuntimeError("FBX rig Body 骨架创建后名称不完整")
        return built.snapshot

    def build_fbx_advanced_skeleton(self, plan: FBXRigImportPlan) -> None:
        """Build arbitrary FK plus labeled three-joint arm and leg IK limbs."""
        self._require_transaction()
        c = self._cmds
        if any(c.objExists(name) for name in (
                "MainSystem", "Main", "ControlSet", "DeformSet", "AllSet")):
            raise ValueError("FBX rig 主控或选择集名称已被占用")
        body = self.build_fbx_body_skeleton(plan)
        controls = plan_fbx_rig_fk_controls(body, plan)
        ik_limbs = plan_fbx_rig_ik_limbs(body, plan)
        ik_body_paths = {path for limb in ik_limbs
                         for path in limb.body_joint_paths}
        main_system = c.createNode("transform", name="MainSystem",
                                   parent="|Group|MotionSystem")
        main = create_adv_icon(c, name="Main", parent=main_system,
            template="Main_icon", radius=max(plan.scale * 2.5, .01),
            fallback_normal=(0, 1, 0))
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
            control = create_adv_icon(c, name=spec.control_name,
                parent=offset, template="FK_icon", radius=spec.radius,
                fallback_normal=(1, 0, 0), fallback_sections=12,
                mirror_left=spec.control_name.endswith("_L"))
            control_paths[spec.control_name] = (
                c.ls(control, long=True, type="transform") or [control])[0]
            c.setAttr(control + ".overrideEnabled", True)
            c.setAttr(control + ".overrideColor",
                      13 if spec.control_name.endswith("_R") else
                      6 if spec.control_name.endswith("_L") else 17)
            if spec.body_joint_path not in ik_body_paths:
                constraint = c.parentConstraint(control, spec.body_joint_path,
                    maintainOffset=False,
                    name="AdvPy_FBX_" + spec.control_name + "_Parent")
                if len(constraint) != 1:
                    raise RuntimeError("FBX rig FK 控制约束创建失败："
                                       + spec.control_name)
        ik_controls = self._build_fbx_ik_limbs(
            ik_limbs, controls, control_paths, main,
            plan.scale) if ik_limbs else ()
        control_paths = {name: (c.ls(name, long=True,
                                     type="transform") or [None])[0]
                         for name in control_paths}
        if None in control_paths.values():
            raise RuntimeError("FBX rig FK 控制器在 IK 改挂后丢失")
        temporary_markers = plan_body_non_deform_markers(body)
        temporary_paths = set(temporary_markers)
        self._fbx_removed_non_deform_names = frozenset(
            joint.name for joint in body.joints
            if joint.path in temporary_paths)
        if temporary_markers:
            body = self.remove_body_non_deform_markers(
                body.root, temporary_markers)
            for joint_name in self._fbx_removed_non_deform_names:
                control_name = "FK" + joint_name
                control = control_paths.pop(control_name, None)
                if control is None:
                    continue
                offset = (c.listRelatives(control, parent=True,
                                          fullPath=True) or (None,))[0]
                if offset is None or not offset.endswith(
                        "|" + control_name + "Offset"):
                    raise RuntimeError("FBX rig 临时 FK 控制层无效："
                                       + control_name)
                children = c.listRelatives(offset, children=True,
                                           type="transform",
                                           fullPath=True) or ()
                descendants = c.listRelatives(
                    control, allDescendents=True, type="transform",
                    fullPath=True) or ()
                if tuple(children) != (control,) or descendants:
                    raise RuntimeError("FBX rig 临时 FK 控制层仍有其他控制器："
                                       + control_name)
                c.delete(offset)
        c.sets(tuple(control_paths.values()) + (main, *ik_controls),
               name="ControlSet")
        c.sets(tuple(joint.path for joint in body.joints), name="DeformSet")
        c.sets(empty=True, name="AllSet")
        group = "|Group"
        c.addAttr(group, longName="advPyFbxRigMode", dataType="string")
        c.setAttr(group + ".advPyFbxRigMode",
                  "labeled_ik_fk_v1" if ik_limbs else "generic_fk_v1",
                  type="string", lock=True)
        if set(control_paths) != {
                spec.control_name for spec in controls
                if spec.control_name.removeprefix("FK") not in
                self._fbx_removed_non_deform_names}:
            raise RuntimeError("FBX rig FK 控制器写后数量不符")
        self._fbx_built_ik_limbs = ik_limbs
        self._transaction_changed = True

    def capture_fbx_generated_ownership_start(
        self,
    ) -> tuple[BodyAllSetNode, ...]:
        """Capture after Fit creation, before Body and transfer nodes exist."""
        return self.capture_body_scene_nodes()

    def finalize_fbx_generated_ownership(
        self, before: tuple[BodyAllSetNode, ...],
    ) -> None:
        self._require_transaction()
        after = self.capture_body_scene_nodes()
        plan = plan_body_all_set(before, after, "FitSkeleton")
        self.populate_body_all_set(plan)
        if set(self.capture_body_all_set_members()) != set(plan.members):
            raise RuntimeError("FBX rig AllSet 登记后成员不完整")
        # Maya parents a constraint under its constrained source joint.
        # Those FBXRig namespace ancestors make it appear foreign to the
        # root-character snapshot even though our build created the node.
        c = self._cmds
        outside = tuple(dict.fromkeys((
            *getattr(self, "_fbx_source_constraints", {}).values(),
            *((getattr(self, "_fbx_game_root_constraint", None),)
              if getattr(self, "_fbx_game_root_constraint", None) else ()),
        )))
        external = []
        for name in outside:
            paths = c.ls(name, long=True, type="parentConstraint") or ()
            if len(paths) != 1:
                raise RuntimeError("FBX rig 来源约束缺失或重名：" + name)
            external.append(paths[0])
        if external:
            c.sets(tuple(external), add="AllSet")
            registered = {identifier
                          for member in c.sets("AllSet", query=True) or ()
                          for identifier in (c.ls(member, uuid=True) or ())}
            expected = {identifier for path in external
                        for identifier in (c.ls(path, uuid=True) or ())}
            if not expected <= registered:
                raise RuntimeError("FBX rig 来源约束未登记到 AllSet")

    def _build_fbx_ik_limbs(
        self, limbs: tuple[FBXRigIKLimb, ...],
        specs, fk_controls: dict[str, str], main: str, scale: float,
    ) -> tuple[str, ...]:
        c = self._cmds
        names = ["AdvPy_FBX_IKSystem"]
        for limb in limbs:
            label = limb.kind + "_" + limb.side
            names.extend((limb.ik_control_name, limb.pole_control_name,
                          limb.ik_control_name + "Offset",
                          limb.pole_control_name + "Offset",
                          "AdvPy_FBX_" + label + "_IKHandle",
                          "AdvPy_FBX_" + label + "_PoleConstraint",
                          "AdvPy_FBX_" + label + "_Orient",
                          "AdvPy_FBX_" + label + "_Reverse",
                          "AdvPy_FBX_" + label + "_EndFollow",
                          "AdvPy_FBX_" + label + "_EndFollowConstraint"))
            names.extend("AdvPy_FBX_IK_" + name
                         for name in limb.body_joint_names)
            names.extend("AdvPy_FBX_" + name + "_Blend"
                         for name in limb.body_joint_names)
        if any(c.objExists(name) for name in names):
            raise ValueError("FBX rig IK 节点名称已被占用")
        system = c.createNode("transform", name="AdvPy_FBX_IKSystem",
                              parent=main)
        controls = []
        for limb in limbs:
            label = limb.kind + "_" + limb.side
            switch = main + "." + limb.switch_attribute
            c.addAttr(main, longName=limb.switch_attribute,
                      attributeType="double", minValue=0, maxValue=1,
                      defaultValue=0, keyable=True)
            reverse = c.createNode("reverse",
                                   name="AdvPy_FBX_" + label + "_Reverse")
            c.connectAttr(switch, reverse + ".inputX")
            for fk_name in limb.fk_control_names:
                fk = fk_controls.get(fk_name)
                if fk is None:
                    raise RuntimeError("FBX rig IK 链缺少 FK 控制：" + fk_name)
                shapes = c.listRelatives(
                    fk, shapes=True, noIntermediate=True,
                    type="nurbsCurve", fullPath=True) or ()
                if not shapes:
                    raise RuntimeError("FBX rig FK 控制曲线缺失：" + fk_name)
                for shape in shapes:
                    plug = shape + ".visibility"
                    if c.connectionInfo(plug, sourceFromDestination=True):
                        raise RuntimeError("FBX rig FK 曲线显隐已被占用："
                                           + shape)
                    c.connectAttr(reverse + ".outputX", plug)
            ik_joints = []
            parent = system
            for body_path, body_name in zip(limb.body_joint_paths,
                                            limb.body_joint_names):
                duplicate = c.duplicate(body_path, parentOnly=True,
                    name="AdvPy_FBX_IK_" + body_name)[0]
                duplicate = c.parent(duplicate, parent, absolute=True)[0]
                c.xform(duplicate, worldSpace=True,
                        matrix=c.xform(body_path, query=True,
                                       worldSpace=True, matrix=True))
                c.setAttr(duplicate + ".drawStyle", 2)
                ik_joints.append(duplicate)
                parent = duplicate
            end_offset = c.createNode("transform",
                name=limb.ik_control_name + "Offset", parent=main)
            c.xform(end_offset, worldSpace=True,
                    matrix=c.xform(limb.body_joint_paths[2], query=True,
                                   worldSpace=True, matrix=True))
            end_control = create_adv_icon(c, name=limb.ik_control_name,
                parent=end_offset, template="IK_icon",
                radius=max(scale * .8, .01),
                fallback_normal=(0, 1, 0),
                mirror_left=limb.side == "L")
            c.setAttr(end_control + ".overrideEnabled", True)
            c.setAttr(end_control + ".overrideColor",
                      13 if limb.side == "R" else 6)
            pole_offset = c.createNode("transform",
                name=limb.pole_control_name + "Offset", parent=main)
            c.xform(pole_offset, worldSpace=True,
                    translation=limb.pole_position)
            pole = create_adv_icon(c, name=limb.pole_control_name,
                parent=pole_offset, template="Pole_icon",
                radius=max(scale * .25, .01),
                fallback_normal=(0, 0, 1),
                mirror_left=limb.side == "L")
            c.setAttr(pole + ".overrideEnabled", True)
            c.setAttr(pole + ".overrideColor",
                      13 if limb.side == "R" else 6)
            handle = c.ikHandle(startJoint=ik_joints[0],
                endEffector=ik_joints[2], solver="ikRPsolver",
                name="AdvPy_FBX_" + label + "_IKHandle")
            if len(handle) < 2:
                raise RuntimeError("FBX rig IK Handle 创建失败：" + label)
            c.parent(handle[0], end_control, absolute=True)
            c.setAttr(handle[0] + ".visibility", False)
            c.poleVectorConstraint(pole, handle[0],
                name="AdvPy_FBX_" + label + "_PoleConstraint")
            c.orientConstraint(end_control, ik_joints[2],
                maintainOffset=False,
                name="AdvPy_FBX_" + label + "_Orient")
            for body_path, body_name, fk_name, ik_joint in zip(
                    limb.body_joint_paths, limb.body_joint_names,
                    limb.fk_control_names, ik_joints):
                fk = fk_controls.get(fk_name)
                if fk is None:
                    raise RuntimeError("FBX rig IK 链缺少 FK 控制：" + fk_name)
                constraint = c.parentConstraint(
                    fk, ik_joint, body_path, maintainOffset=False,
                    name="AdvPy_FBX_" + body_name + "_Blend")
                if len(constraint) != 1:
                    raise RuntimeError("FBX rig IK/FK 混合约束创建失败："
                                       + body_name)
                aliases = c.parentConstraint(constraint[0], query=True,
                                              weightAliasList=True) or ()
                if len(aliases) != 2:
                    raise RuntimeError("FBX rig IK/FK 混合权重数量无效："
                                       + body_name)
                c.connectAttr(reverse + ".outputX",
                              constraint[0] + "." + aliases[0])
                c.connectAttr(switch, constraint[0] + "." + aliases[1])
            # Toes and fingers are still FK. Parent their control offsets to
            # the blended end joint so they follow either IK or FK wrist/foot.
            children = tuple(spec for spec in specs
                             if spec.parent_control_name ==
                             limb.fk_control_names[2])
            if children:
                follow = c.createNode("transform",
                    name="AdvPy_FBX_" + label + "_EndFollow", parent=main)
                c.xform(follow, worldSpace=True,
                        matrix=c.xform(limb.body_joint_paths[2], query=True,
                                       worldSpace=True, matrix=True))
                c.parentConstraint(limb.body_joint_paths[2], follow,
                    maintainOffset=False,
                    name="AdvPy_FBX_" + label + "_EndFollowConstraint")
                for child in children:
                    control = fk_controls[child.control_name]
                    offset = (c.listRelatives(control, parent=True,
                                              fullPath=True) or [None])[0]
                    if offset is None:
                        raise RuntimeError("FBX rig 末端 FK 子控制层缺失："
                                           + child.control_name)
                    c.parent(offset, follow, absolute=True)
            for offset in (end_offset, pole_offset):
                c.connectAttr(switch, offset + ".visibility")
            controls.extend((end_control, pole))
        return tuple(controls)

    def capture_fbx_generated_targets(
        self, plan: FBXRigImportPlan,
    ) -> FBXRigGeneratedTargets:
        c = self._cmds
        removed = getattr(self, "_fbx_removed_non_deform_names", frozenset())
        deformation = "|Group|DeformationSystem"
        joints = c.listRelatives(deformation, allDescendents=True,
                                 type="joint", fullPath=True) or ()
        deform_names = tuple(path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                             for path in joints)
        if removed.intersection(deform_names):
            raise RuntimeError("FBX rig 临时脚部关节仍留在变形骨架中")
        if any(c.objExists("FK" + name) for name in removed):
            raise RuntimeError("FBX rig 临时脚部 FK 控制器仍留在场景中")
        candidates = tuple(link.control_name
                           for link in plan.candidate_control_links
                           if link.control_name.removeprefix("FK") not in removed)
        controls = tuple(name for name in candidates
                         if len(c.ls(name, long=True, type="transform") or ()) == 1)
        return FBXRigGeneratedTargets(controls, deform_names)

    def enlarge_small_fbx_fk_controls(
        self, plan: FBXRigImportPlan, bound_meshes: tuple[str, ...],
    ) -> None:
        """Fit FK shapes to the bound mesh when the user accepts the prompt."""
        self._require_transaction()
        c = self._cmds
        answer = c.confirmDialog(
            title="自动缩放控制器？", message="将 FK 控制曲线贴合角色模型？",
            button=("是", "否"), defaultButton="是",
            cancelButton="否", dismissString="否")
        if answer != "是":
            return
        current_meshes = self._current_fbx_bound_mesh_paths()
        if len(current_meshes) != len(bound_meshes):
            raise RuntimeError("FBX rig 来源蒙皮网格在命名空间迁移后数量改变")
        removed = getattr(self, "_fbx_removed_non_deform_names", frozenset())
        project_fbx_fk_controls(c,
            tuple(link.control_name for link in plan.candidate_control_links
                  if link.control_name.removeprefix("FK") not in removed),
            current_meshes)
        self._transaction_changed = True

    def _current_fbx_bound_mesh_paths(self) -> tuple[str, ...]:
        """Find originally bound meshes after optional hierarchy renaming."""
        c = self._cmds
        expected = getattr(self, "_fbx_skin_boundary", ())
        skin_ids = {row[0] for row in expected}
        mesh_ids = {identifier for row in expected
                    for identifier in row[1]}
        paths = {}
        for skin in c.ls(type="skinCluster") or ():
            if (c.ls(skin, uuid=True) or (None,))[0] not in skin_ids:
                continue
            for shape in c.skinCluster(skin, query=True, geometry=True) or ():
                parents = c.listRelatives(shape, parent=True,
                                          fullPath=True) or ()
                if len(parents) != 1:
                    raise RuntimeError("FBX rig 蒙皮网格父级在迁移后无效")
                identifier = (c.ls(parents[0], uuid=True) or (None,))[0]
                if identifier in mesh_ids:
                    paths[identifier] = parents[0]
        if set(paths) != mesh_ids:
            raise RuntimeError("FBX rig 来源蒙皮网格在迁移后缺失")
        return tuple(paths[identifier] for identifier in sorted(paths))

    def connect_fbx_game_root_motion(
        self, plan: FBXRigImportPlan, source_paths: dict[str, str],
    ) -> None:
        self._require_transaction()
        motion = plan_fbx_game_root_motion(plan)
        c = self._cmds
        body_root = self._only_fbx_node("Root_M", "joint")
        if body_root != "|Group|DeformationSystem|Root_M":
            raise ValueError("FBX rig Root Body 已被改挂")
        if any(c.objExists(name) for name in motion.node_names):
            raise ValueError("FBX rig Root Motion 名称已被占用")
        if any((c.ls(path, long=True, type="transform") or []) != [path]
               for path in ("|Group|DeformationSystem",
                            "|Group|MotionSystem|RootSystem",
                            "|Group|MotionSystem|ConstraintSystem",
                            "|Group|MotionSystem|MainSystem",
                            "|Group|MotionSystem|MainSystem|Main")):
            raise ValueError("FBX rig Root Motion 缺少主控系统")
        self._transaction_changed = True
        root_motion = c.createNode("joint", name="RootMotion_M",
            parent="|Group|DeformationSystem", skipSelect=True)
        c.setAttr(root_motion + ".segmentScaleCompensate", False)
        moved = c.parent(body_root, root_motion, absolute=True)[0]
        if (c.ls(root_motion, long=True, type="joint") or ()) != [motion.joint_path]:
            raise RuntimeError("FBX rig Root Motion 关节路径漂移")
        if (c.ls(moved, long=True, type="joint") or ()) != [motion.body_root_path]:
            raise RuntimeError("FBX rig Root Body 改挂失败")
        offset = c.createNode("transform", name="FKOffsetRootMotion_M",
            parent="|Group|MotionSystem|RootSystem", skipSelect=True)
        follow = c.createNode("transform", name="FKFollowRootMotion_M",
            parent=offset, skipSelect=True)
        extra = c.createNode("transform", name="FKExtraRootMotion_M",
            parent=follow, skipSelect=True)
        control = c.circle(name="FKRootMotion_M", normal=(0, 1, 0),
            radius=motion.radius, constructionHistory=False)[0]
        control = c.parent(control, extra, relative=True)[0]
        for node, expected in ((offset, motion.offset_path),
                               (follow, motion.follow_path),
                               (extra, motion.extra_path),
                               (control, motion.control_path)):
            if (c.ls(node, long=True, type="transform") or ()) != [expected]:
                raise RuntimeError("FBX rig Root Motion 控制层路径漂移")
        shapes = c.listRelatives(control, shapes=True,
            noIntermediate=True, fullPath=True, type="nurbsCurve") or ()
        if len(shapes) != 1:
            raise RuntimeError("FBX rig Root Motion 控制曲线缺失")
        c.setAttr(shapes[0] + ".overrideEnabled", True)
        c.setAttr(shapes[0] + ".overrideColor", 17)
        c.sets((control, extra), add="ControlSet")
        c.sets(root_motion, add="DeformSet")
        driven = c.parentConstraint(control, root_motion,
            maintainOffset=False, name=motion.body_constraint)
        if len(driven) != 1:
            raise RuntimeError("FBX rig Root Motion 控制约束创建失败")
        constraint_system = "|Group|MotionSystem|ConstraintSystem"
        moved_constraint = c.parent(driven[0], constraint_system,
                                    absolute=True)[0]
        if (c.ls(moved_constraint, long=True, type="parentConstraint")
                or []) != [constraint_system + "|" + motion.body_constraint]:
            raise RuntimeError("FBX rig Root Motion 约束未进入 ConstraintSystem")
        main = "|Group|MotionSystem|MainSystem|Main"
        main_system = "|Group|MotionSystem|MainSystem"
        follow_constraint = c.parentConstraint(main, main_system, follow,
            maintainOffset=False, name=motion.follow_constraint)
        if len(follow_constraint) != 1:
            raise RuntimeError("FBX rig Root Motion 跟随约束创建失败")
        aliases = c.parentConstraint(follow_constraint[0], query=True,
                                      weightAliasList=True) or ()
        if len(aliases) != 2:
            raise RuntimeError("FBX rig Root Motion 跟随权重不完整")
        c.addAttr(control, longName="followMain", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        value_range = c.createNode("setRange", name=motion.range_node,
                                    skipSelect=True)
        for attr, value in (("maxX", 1), ("minY", 1),
                            ("oldMaxX", 10), ("oldMaxY", 10)):
            c.setAttr(value_range + "." + attr, value)
        for axis in "XY":
            c.connectAttr(control + ".followMain",
                          value_range + ".value" + axis)
        c.connectAttr(value_range + ".outValueX",
                      follow_constraint[0] + "." + aliases[0])
        c.connectAttr(value_range + ".outValueY",
                      follow_constraint[0] + "." + aliases[1])
        source = self._only_fbx_node(
            source_paths[plan.game_root_joint], "joint")
        source_constraint = c.parentConstraint(root_motion, source,
            maintainOffset=True, name=motion.source_constraint)
        if len(source_constraint) != 1:
            raise RuntimeError("FBX rig 游戏根关节约束创建失败")
        self._fbx_game_root_constraint = motion.source_constraint

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

    def _audit_fbx_ik_limbs(self) -> int:
        c = self._cmds
        limbs = tuple(getattr(self, "_fbx_built_ik_limbs", ()))
        main = "|Group|MotionSystem|MainSystem|Main"
        for limb in limbs:
            label = limb.kind + "_" + limb.side
            switch = main + "." + limb.switch_attribute
            reverse = "AdvPy_FBX_" + label + "_Reverse"
            handle = "AdvPy_FBX_" + label + "_IKHandle"
            if (not c.objExists(switch) or not c.objExists(reverse)
                    or not c.objExists(handle)
                    or not c.objExists(limb.ik_control_name)
                    or not c.objExists(limb.pole_control_name)
                    or abs(float(c.getAttr(switch))) > 1e-6):
                raise RuntimeError("FBX rig IK 主控或求解器不完整：" + label)
            if not c.isConnected(switch, reverse + ".inputX"):
                raise RuntimeError("FBX rig IK/FK 反向权重未连接：" + label)
            for fk_name in limb.fk_control_names:
                fk = (c.ls(fk_name, long=True,
                           type="transform") or [None])[0]
                shapes = (c.listRelatives(
                    fk, shapes=True, noIntermediate=True,
                    type="nurbsCurve", fullPath=True) or ()) if fk else ()
                if (not shapes or any(not c.isConnected(
                        reverse + ".outputX", shape + ".visibility")
                        for shape in shapes)):
                    raise RuntimeError("FBX rig FK 控制曲线显隐未切换："
                                       + fk_name)
            for body_name, fk_name in zip(limb.body_joint_names,
                                          limb.fk_control_names):
                constraint = "AdvPy_FBX_" + body_name + "_Blend"
                aliases = c.parentConstraint(constraint, query=True,
                                              weightAliasList=True) or ()
                targets = c.parentConstraint(constraint, query=True,
                                              targetList=True) or ()
                resolved = tuple((c.ls(path, long=True) or [None])[0]
                                 for path in targets)
                ik_joint = (c.ls("AdvPy_FBX_IK_" + body_name,
                                 long=True, type="joint") or [None])[0]
                fk_control = (c.ls(fk_name, long=True,
                                    type="transform") or [None])[0]
                if (len(aliases) != 2 or resolved !=
                        (fk_control, ik_joint)
                        or not c.isConnected(reverse + ".outputX",
                                             constraint + "." + aliases[0])
                        or not c.isConnected(switch,
                                             constraint + "." + aliases[1])):
                    raise RuntimeError("FBX rig IK/FK 关节混合不完整："
                                       + body_name)
        return len(limbs)

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
            constraint_paths = c.ls(constraint, long=True,
                                    type="parentConstraint") or ()
            connected = (len(constraint_paths) == 1 and all(
                c.isConnected(
                    constraint_paths[0] + ".constraintTranslate" + axis,
                    source + ".translate" + axis)
                for axis in "XYZ"))
            if resolved == (driver,) and connected:
                connected_controls.append(link.control_name)
                connected_sources.append(source)
        source_nodes = tuple(getattr(
            self, "_fbx_source_transform_paths", source_paths.values()))
        source_animation_removed = not any(
            c.listConnections(path, source=True, destination=False,
                              type="animCurve") for path in source_nodes)
        baked = (plan.last_bake_frame is not None
                 and tuple(getattr(self, "_fbx_baked_control_names", ()))
                     == transfer.bake_control_names
                 and all(c.objExists(name)
                         for name in transfer.bake_control_names)
                 and any(c.keyframe(name, query=True, timeChange=True)
                         for name in transfer.bake_control_names))
        game_connected = False
        if plan.game_root_joint is not None:
            motion = plan_fbx_game_root_motion(plan)
            paths = ((motion.joint_path, "joint"),
                     (motion.body_root_path, "joint"),
                     (motion.offset_path, "transform"),
                     (motion.follow_path, "transform"),
                     (motion.extra_path, "transform"),
                     (motion.control_path, "transform"))
            present = all((c.ls(path, long=True, type=kind) or []) == [path]
                          for path, kind in paths)
            constraints = (motion.follow_constraint,
                           motion.body_constraint,
                           motion.source_constraint)
            if (present and all(c.objExists(name) for name in constraints)
                    and c.objExists(motion.range_node)):
                follow_targets = c.parentConstraint(
                    motion.follow_constraint, query=True,
                    targetList=True) or ()
                aliases = c.parentConstraint(
                    motion.follow_constraint, query=True,
                    weightAliasList=True) or ()
                source_targets = c.parentConstraint(
                    motion.source_constraint, query=True,
                    targetList=True) or ()
                driver_targets = c.parentConstraint(
                    motion.body_constraint, query=True,
                    targetList=True) or ()
                main = "|Group|MotionSystem|MainSystem|Main"
                system = "|Group|MotionSystem|MainSystem"
                game_source = source_paths[plan.game_root_joint]
                resolved = lambda names: tuple((c.ls(name, long=True)
                    or (None,))[0] for name in names)
                game_connected = (
                    resolved(follow_targets) == (main, system)
                    and resolved(source_targets) == (motion.joint_path,)
                    and resolved(driver_targets) == (motion.control_path,)
                    and (c.listRelatives(motion.source_constraint,
                        parent=True, fullPath=True) or []) == [game_source]
                    and (c.listRelatives(motion.body_constraint,
                        parent=True, fullPath=True) or []) == [
                            "|Group|MotionSystem|ConstraintSystem"]
                    and (c.listRelatives(motion.follow_constraint,
                        parent=True, fullPath=True) or []) == [motion.follow_path]
                    and len(aliases) == 2
                    and all(c.isConnected(
                        motion.control_path + ".followMain",
                        motion.range_node + ".value" + axis)
                        for axis in "XY")
                    and all(c.isConnected(
                        motion.range_node + ".outValue" + axis,
                        motion.follow_constraint + "." + alias)
                        for axis, alias in zip("XY", aliases))
                    and not bool(c.getAttr(motion.joint_path
                                           + ".segmentScaleCompensate")))
        ik_limb_count = self._audit_fbx_ik_limbs()
        owned_ids = {identifier
                     for member in c.sets("AllSet", query=True) or ()
                     for identifier in (c.ls(member, uuid=True) or ())}
        required_owned = (
            "|Group",
            *getattr(self, "_fbx_source_constraints", {}).values(),
            *((getattr(self, "_fbx_game_root_constraint", None),)
              if getattr(self, "_fbx_game_root_constraint", None) else ()),
        )
        ownership_complete = (
            (c.ls("FitSkeleton", long=True,
                  type="transform") or ()) == ["|Group|FitSkeleton"]
            and all((c.ls(name, uuid=True) or [None])[0] in owned_ids
                    for name in required_owned)
            and not any(path.startswith("|FBXRig:")
                        for member in c.sets("AllSet", query=True) or ()
                        for path in (c.ls(member, long=True,
                                          type="joint") or ())))
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
            connected_source_paths=tuple(connected_sources),
            ik_limb_count=ik_limb_count,
            ownership_complete=ownership_complete)
