"""Maya node graph for ADV Body Partial Joints."""
from __future__ import annotations
from dataclasses import replace
import json

from adv_py.core.character_registry import REGISTRY_NAME
from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from adv_py.core.partial_joints import (
    PartialDeleteSpec, PartialJointCandidate, PartialJointSpec,
)
from .maya_original_transform_channels import (
    align_original_transform,lock_original_transform_channels,
)
from .maya_adv_icons import create_adv_icon
from .maya_custom_controller import MayaCustomControllerHost


class MayaPartialJointsHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)
        self._multi_partial_radius = None

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    def _leaf(self, path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _members(self, set_name: str) -> tuple[str, ...]:
        c = self._cmds
        obj_set = self._node(set_name)
        if not c.objExists(obj_set):
            raise ValueError("ADV 角色缺少 " + set_name)
        return tuple(c.ls(c.sets(obj_set, query=True) or [],
                          long=True, type="joint") or ())

    def capture_partial_candidates(self) -> tuple[PartialJointCandidate, ...]:
        c = self._cmds
        result = []
        for joint in self._members("DeformSet"):
            leaf = self._leaf(joint)
            if "Partial" in leaf:
                continue
            stem, separator, side = leaf.rpartition("_")
            parent = (c.listRelatives(joint, parent=True, fullPath=True,
                                      type="joint") or [None])[0]
            child_count = len(c.listRelatives(joint, children=True,
                                              fullPath=True,
                                              type="joint") or ())
            result.append(PartialJointCandidate(
                joint, parent, child_count,
                bool(separator and c.objExists(self._node(
                    stem + "Partial_" + side))),
                bool(separator and c.objExists(self._node(
                    stem + "Partial1_" + side)))))
        return tuple(result)

    def _partial_fk_sources(self):
        c=self._cmds
        if not c.objExists(self._node(REGISTRY_NAME)+".advPyRegistryDocument"):
            return {}
        registration=self.read_character_registration()
        from .maya_original_control_identity import fk_bindings
        return {control:joint for joint,control in fk_bindings(registration).items()}

    def resolve_partial_selection(self) -> tuple[str, ...]:
        c = self._cmds
        selection = c.ls(selection=True, long=True) or []
        if not selection:
            return ()
        candidates = self.capture_partial_candidates()
        by_leaf: dict[str, str] = {}
        for candidate in candidates:
            leaf = self._leaf(candidate.joint)
            if leaf in by_leaf:
                raise ValueError("DeformSet 存在同名关节：" + leaf)
            by_leaf[leaf] = candidate.joint
        found = []
        sources=self._partial_fk_sources()
        for path in selection:
            leaf = sources.get(self._leaf(path),self._leaf(path))
            if leaf.startswith("FK"):
                leaf = leaf[2:]
            if "Partial" in leaf:
                leaf = leaf.replace("Partial1_", "_", 1).replace(
                    "Partial_", "_", 1)
            joint = by_leaf.get(leaf)
            if joint and joint not in found:
                found.append(joint)
        return tuple(found)

    def partial_uses_opm(self) -> bool:
        c = self._cmds
        fit = self._node("FitSkeleton")
        return bool(c.objExists(fit) and c.attributeQuery(
            "useOffsetParentMatrix", node=fit, exists=True)
            and c.getAttr(fit + ".useOffsetParentMatrix"))

    def preflight_partial_scene(self, *, include_controller: bool,
                                multi: bool, auto_bind: bool) -> None:
        c = self._cmds
        for name in ("MotionSystem", "DeformSet"):
            self._unique(name, "objectSet" if name == "DeformSet"
                         else "transform")
        if include_controller:
            self._unique("ControlSet", "objectSet")
        if multi:
            self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        self._unique("Root_M", "joint")

    def find_name_collisions(self, name: str) -> tuple[str, ...]:
        return tuple(self._cmds.ls(self._node(name), long=True) or ())

    def capture_partial_presence(self, joint: str) -> tuple[bool, bool]:
        leaf = self._leaf(joint)
        stem, separator, side = leaf.rpartition("_")
        if not separator:
            return False, False
        c = self._cmds
        return (bool(c.objExists(self._node(stem + "Partial_" + side))),
                bool(c.objExists(self._node(stem + "Partial1_" + side))))

    def _system(self, name: str, parent: str) -> str:
        c = self._cmds
        address = self._node(name)
        if c.objExists(address):
            return self._unique(address, "transform")
        return c.createNode("transform", name=address, parent=parent,
                            skipSelect=True)

    def _height(self) -> float:
        from .maya_original_control_identity import original_character_height
        return original_character_height(self._cmds)

    def create_partial_joint(self, spec: PartialJointSpec) -> None:
        self._require_transaction()
        self._transaction_changed = True
        if spec.count == 1:
            self._create_single(spec)
        else:
            self._create_multi(spec)

    def _mark_partial_influence(self, joint: str) -> None:
        c = self._cmds
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind", dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind", "original-partial-v1",
                  type="string", lock=True)

    def _create_single(self, spec: PartialJointSpec) -> None:
        c = self._cmds
        source = self._unique(spec.joint, "joint")
        parent = self._unique(spec.parent, "joint")
        system = self._system("PartialJointsSystem",
                              self._unique("MotionSystem", "transform"))
        constraints = (None if spec.use_opm else self._system(
            "PartialJointsConstraints", system))
        stem_side = spec.stem + "_" + spec.side
        name = spec.stem + "Partial_" + spec.side
        c.select(source, replace=True)
        joint = c.joint(name=self._node(name))
        c.setAttr(joint + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
        c.setAttr(joint + ".segmentScaleCompensate", False)
        joint = c.parent(joint, parent)[0]
        c.addAttr(joint, longName="partialJoint", attributeType="bool",
                  defaultValue=True)
        self._mark_partial_influence(joint)
        c.sets(joint, add=self._node("DeformSet"))
        joint = self._unique(joint, "joint")
        zero = None
        if not spec.use_opm:
            offset = c.createNode("transform", name=self._node(
                stem_side + "_00Offset"), parent=source, skipSelect=True)
            c.setAttr(offset + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
            offset = c.parent(offset, system)[0]
            zero = c.duplicate(offset, name=self._node(stem_side + "_00"))[0]
            zero = c.parent(zero, offset)[0]
            parent_constraint = c.parentConstraint(
                parent, offset, maintainOffset=True,
                name=self._node(stem_side + "_00Offset_parentConstraint1"))[0]
            c.addAttr(zero, longName="partialJoint", attributeType="bool")
        target = joint
        follow = joint
        if spec.include_controller:
            control_offset = c.createNode("transform", name=self._node(
                "FKOffset" + name), parent=system, skipSelect=True)
            extra = c.createNode("transform", name=self._node(
                "FKExtra" + name), parent=control_offset, skipSelect=True)
            lock_original_transform_channels(c,extra,False,False,True,True)
            control = self._create_control_icon(name, extra)
            control_offset=align_original_transform(c,control_offset,source,
                                                    True,True,False,True)
            fkx = c.createNode("transform", name=self._node(
                "FKX" + name), parent=control, skipSelect=True)
            c.sets((control, extra), add=self._node("ControlSet"))
            plan = plan_body_parent_constraint(replace(
                self.capture_parent_constraint_input(
                    self._unique(fkx, "transform"), joint, False),
                use_offset_parent_matrix=spec.use_opm))
            self.preflight_parent_constraint(plan)
            self.create_parent_constraint(plan)
            if not spec.use_opm:
                for kind in ("parent", "scale"):
                    constraint = self._unique(name + "_" + kind + "Constraint1",
                                              kind + "Constraint")
                    c.parent(constraint, system)
            target, follow = control_offset, control
            self._connect_partial_visibility(system)
        side_factor = -1 if spec.side == "L" else 1
        delta = side_factor * self._height() / 5000.0
        c.addAttr(follow, longName="follow", attributeType="double",
                  minValue=0.0, maxValue=10.0, defaultValue=5.0,
                  keyable=True)
        if spec.use_opm:
            self._connect_partial_opm(spec, source, parent, target,
                                      follow, delta)
            if spec.include_controller:
                self._update_custom_build_pose(control, base=extra, add=True)
                self._verify_single_control_layer(name, use_opm=True)
            return
        target_name = self._leaf(target)
        orient = c.orientConstraint(
            zero, source, target, maintainOffset=False,
            name=self._node(target_name + "_orientConstraint1"))[0]
        c.setAttr(orient + ".interpType", 2)
        point = c.pointConstraint(
            source, target, maintainOffset=False,
            name=self._node(target_name + "_pointConstraint1"))[0]
        c.setAttr(point + ".offsetX", delta)
        scale = c.scaleConstraint(
            source, target, maintainOffset=False,
            name=self._node(target_name + "_scaleConstraint1"))[0]
        if not spec.include_controller:
            c.parent((parent_constraint, orient, point, scale), constraints)
        aliases = c.orientConstraint(orient, query=True, weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("Partial Joints 双目标约束未建立")
        weight = c.createNode("setRange", name=self._node("FK" + name + "SR"),
                              skipSelect=True)
        for attribute in ("maxX", "minY"):
            c.setAttr(weight + "." + attribute, 1.0)
        for attribute in ("oldMaxX", "oldMaxY"):
            c.setAttr(weight + "." + attribute, 10.0)
        for axis in ("X", "Y"):
            c.connectAttr(follow + ".follow", weight + ".value" + axis)
        c.connectAttr(weight + ".outValueY", orient + "." + aliases[0])
        c.connectAttr(weight + ".outValueX", orient + "." + aliases[1])
        if spec.include_controller:
            self._update_custom_build_pose(control, base=extra, add=True)
            self._verify_single_control_layer(name)

    def _verify_single_control_layer(self, name: str, *, use_opm=False) -> None:
        c = self._cmds
        control = self._unique("FK" + name, "transform")
        fkx = self._unique("FKX" + name, "transform")
        if (c.listRelatives(fkx, parent=True, fullPath=True) or []) != [control]:
            raise RuntimeError("Partial FKX 控制层父级不一致：" + name)
        for attribute, expected in (("translate", (0., 0., 0.)),
                                    ("rotate", (0., 0., 0.)),
                                    ("scale", (1., 1., 1.))):
            actual = c.getAttr(fkx + "." + attribute)[0]
            if any(abs(float(value) - target) > 1e-6
                   for value, target in zip(actual, expected)):
                raise RuntimeError("Partial FKX 中性通道不一致：" + name)
        if use_opm:
            joint = self._unique(name, "joint")
            stem, side = name.rsplit("_", 1)
            matrix = self._unique(stem + "MM_" + side, "multMatrix")
            if not (c.isConnected(fkx + ".worldMatrix[0]", matrix + ".matrixIn[0]")
                    and c.isConnected(matrix + ".matrixSum", joint + ".offsetParentMatrix")):
                raise RuntimeError("Partial FKX OPM 连接不一致：" + name)
            return
        for kind in ("parent", "scale"):
            constraint = self._unique(name + "_" + kind + "Constraint1",
                                      kind + "Constraint")
            targets = getattr(c, kind + "Constraint")(
                constraint, query=True, targetList=True) or []
            resolved = [c.ls(target, long=True) or [] for target in targets]
            if resolved != [[fkx]]:
                raise RuntimeError("Partial FKX 约束来源不一致：" + name)

    def _connect_partial_visibility(self, system: str) -> None:
        c = self._cmds
        main = next((self._node(name) for name in ("Main", "AdvPy_Global")
                     if c.objExists(self._node(name))), None)
        if main is None:
            raise ValueError("Partial Joints 缺少角色总控")
        plug = main + ".partialVis"
        if not c.objExists(plug):
            c.addAttr(main, longName="partialVis", attributeType="bool",
                      defaultValue=True, keyable=False)
            c.setAttr(plug, channelBox=True)
        elif c.getAttr(plug, type=True) != "bool":
            raise ValueError("角色总控 partialVis 属性类型不匹配")
        target = system + ".visibility"
        inputs = c.listConnections(target, source=True,
                                   destination=False, plugs=True) or []
        if inputs and not c.isConnected(plug, target):
            raise ValueError("PartialJointsSystem 可见性已有其他来源")
        if not inputs:
            c.connectAttr(plug, target)
        if not c.isConnected(plug, target):
            raise RuntimeError("Partial Joints 可见性连接读回不一致")

    def _connect_partial_opm(self, spec: PartialJointSpec, source: str,
                             parent: str, target: str, follow: str,
                             delta: float) -> None:
        c = self._cmds
        if not spec.include_controller:
            c.setAttr(target + ".jointOrient", 0, 0, 0)
        c.setAttr(target + ".translate", 0, 0, 0)
        c.setAttr(target + ".rotate", 0, 0, 0)
        temporary_name = self._node("tempXform")
        if c.objExists(temporary_name):
            c.delete(temporary_name)
        blend = c.createNode("blendMatrix", name=self._node(
            spec.stem + "PartialBM_" + spec.side), skipSelect=True)
        temporary = c.createNode("transform", name=temporary_name, parent=source,
                                 skipSelect=True)
        try:
            c.setAttr(temporary + ".translateX", delta)
            temporary = c.parent(temporary, parent)[0]
            matrix = c.getAttr(temporary + ".matrix")
        finally:
            if c.objExists(temporary):
                c.delete(temporary)
        c.setAttr(blend + ".inputMatrix", *matrix, type="matrix")
        c.connectAttr(source + ".offsetParentMatrix",
                      blend + ".target[0].targetMatrix")
        output = blend + ".outputMatrix"
        if spec.include_controller:
            multiply = c.createNode("multMatrix", name=self._node(
                spec.stem + "PartialMM2_" + spec.side), skipSelect=True)
            c.connectAttr(output, multiply + ".matrixIn[0]")
            c.connectAttr(parent + ".worldMatrix[0]",
                          multiply + ".matrixIn[1]")
            output = multiply + ".matrixSum"
        c.connectAttr(output, target + ".offsetParentMatrix", force=True)
        kind = ("multDL" if int(str(c.about(version=True)).split('.')[0]) >= 2026
                else "multDoubleLinear")
        multiplier = c.createNode(kind, name=self._node(
            self._leaf(follow) + "FollowMDL_" + spec.side), skipSelect=True)
        c.setAttr(multiplier + ".input2", 0.1)
        c.connectAttr(follow + ".follow", multiplier + ".input1")
        c.connectAttr(multiplier + ".output",
                      blend + ".target[0].weight")

    def _create_control_icon(self, name: str, parent: str) -> str:
        c = self._cmds
        icon = self._node("FaceA_icon")
        if c.objExists(icon):
            control = c.duplicate(icon, name=self._node("FK" + name))[0]
            c.setAttr(control + ".translate", 0, 0, 0, type="float3")
            c.scale(0.834, 0.834, 0.834, control + ".cv[0:99]",
                    relative=True)
            control = c.parent(control, parent)[0]
        else:
            control = create_adv_icon(
                c, name=self._node("FK" + name), parent=parent,
                template="FaceA_icon", radius=0.834,
                fallback_normal=(1.0, 0.0, 0.0))
        for shape in c.listRelatives(control, shapes=True, fullPath=True) or []:
            c.setAttr(shape + ".overrideEnabled", True)
            c.setAttr(shape + ".overrideColor", 16)
        return control

    def _create_multi(self, spec: PartialJointSpec) -> None:
        c = self._cmds
        source = self._unique(spec.joint, "joint")
        parent = self._unique(spec.parent, "joint")
        system = self._system("PartialJointsSystem",
                              self._unique("MotionSystem", "transform"))
        if spec.include_controller:
            self._connect_partial_visibility(system)
        self._system("PartialJointsConstraints", system)
        if self._multi_partial_radius is None:
            self._multi_partial_radius = self._height() / 100.0
        if c.attributeQuery("fat", node=source, exists=True):
            self._multi_partial_radius = float(c.getAttr(source + ".fat"))
        radius = self._multi_partial_radius
        direction = -1 if spec.side == "L" else 1
        step = 2.0 * radius * direction / spec.count
        # MEL duplicates the temporary sibling and reparents each duplicate
        # absolutely. Maya adjusts jointOrient during that reparent; copying
        # the source orient onto every child creates a different spline chain.
        c.select(source, replace=True)
        seed = c.joint(name=self._node(spec.stem + "Partial_" + spec.side))
        c.setAttr(seed + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
        c.setAttr(seed + ".segmentScaleCompensate", False)
        seed = c.parent(seed, parent, absolute=True)[0]
        c.addAttr(seed, longName="partialJoint", attributeType="bool", defaultValue=True)
        self._mark_partial_influence(seed)
        c.sets(seed, add=self._node("DeformSet"))
        suffix = spec.stem + "_" + spec.side
        zero_offset = c.createNode("transform", name=self._node(suffix + "_00Offset"),
                                   parent=source, skipSelect=True)
        c.setAttr(zero_offset + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
        zero_offset = c.parent(zero_offset, system)[0]
        zero = c.duplicate(zero_offset, name=self._node(suffix + "_00"))[0]
        zero = c.parent(zero, zero_offset)[0]
        c.parentConstraint(parent, zero_offset, maintainOffset=True)
        c.addAttr(zero, longName="partialJoint", attributeType="bool")
        c.move(-direction * radius + step, 0, 0, seed,
               relative=True, objectSpace=True, worldSpaceDistance=True)
        joints = []
        for index in range(1, spec.count + 1):
            name = "%sPartial%d_%s" % (spec.stem, index, spec.side)
            joint = c.duplicate(seed, name=self._node(name))[0]
            c.sets(joint, add=self._node("DeformSet"))
            if index > 1:
                joint = c.parent(joint, joints[-1], absolute=True)[0]
                c.setAttr(joint + ".translateX", step)
            joints.append(joint)
        handle, effector, curve = c.ikHandle(
            startJoint=joints[0], endEffector=joints[-1],
            solver="ikSplineSolver", numSpans=1,
            simplifyCurve=True, rootOnCurve=True,
            parentCurve=False, createCurve=True)
        handle = c.rename(handle, self._node("IkHandlePartial" + suffix))
        c.rename(effector, self._node("EffectorPartial" + suffix))
        curve = c.rename(curve, self._node("IKCurve" + suffix))
        c.setAttr(handle + ".visibility", False, lock=True)
        group_name = self._node("PartialMultiJoints" + suffix)
        if not c.objExists(group_name):
            group = self._system("PartialMultiJoints" + suffix, system)
            c.addAttr(group, longName="locatorVis", attributeType="bool",
                      defaultValue=False, keyable=True)
        else:
            group = self._unique(group_name, "transform")
        c.parent((handle, curve), group)
        curve_shape = (c.listRelatives(curve, shapes=True,
                                       fullPath=True, type="nurbsCurve") or [None])[0]
        if curve_shape is None:
            raise RuntimeError("Partial IK 曲线缺少 NURBS 形状")
        for index in range(4):
            transform = c.createNode("transform", name=self._node(
                "PMJX%d%s" % (index, suffix)), parent=group, skipSelect=True)
            position = c.xform("%s.cv[%d]" % (curve, index),
                               query=True, worldSpace=True, translation=True)
            c.xform(transform, worldSpace=True, translation=position)
            locator = c.spaceLocator(name=self._node(
                "PMJLoc%d%s" % (index, suffix)))[0]
            c.connectAttr(group + ".locatorVis", locator + ".visibility")
            c.setAttr(locator + ".overrideEnabled", True)
            c.setAttr(locator + ".overrideColor", 14 if index in (1, 2) else 13)
            c.parent(locator, transform, relative=True)
            shape = (c.listRelatives(locator, shapes=True, fullPath=True) or [None])[0]
            if shape is None:
                raise RuntimeError("Partial 曲线定位器缺少形状")
            c.connectAttr(shape + ".worldPosition[0]",
                          curve_shape + ".controlPoints[%d]" % index)
            driver = parent if index < 2 else source
            c.parentConstraint(driver, transform, maintainOffset=True)
            c.scaleConstraint(driver, transform, maintainOffset=False)
        for child_index, parent_index in ((1, 0), (2, 3)):
            child = self._node("PMJLoc%d%s" % (child_index, suffix))
            holder = self._node("PMJLoc%d%s" % (parent_index, suffix))
            c.parent(child, holder)
            c.delete(self._node("PMJX%d%s" % (child_index, suffix)))
        info = c.createNode("curveInfo", name=self._node("IKCurveInfo" + suffix),
                            skipSelect=True)
        c.connectAttr(curve_shape + ".worldSpace[0]", info + ".inputCurve")
        normalize = c.createNode("multiplyDivide", name=self._node(
            "IKCurveInfoNormalize" + suffix), skipSelect=True)
        divisor = c.createNode("multiplyDivide", name=self._node(
            "IKCurveInfoAllMultiply" + suffix), skipSelect=True)
        c.setAttr(normalize + ".operation", 2)
        c.setAttr(divisor + ".operation", 2)
        c.connectAttr(info + ".arcLength", normalize + ".input1X")
        c.setAttr(normalize + ".input2X", c.getAttr(info + ".arcLength"))
        c.connectAttr(normalize + ".outputX", divisor + ".input1X")
        c.connectAttr(self._node("MainScaleMultiplyDivide") + ".outputX",
                      divisor + ".input2X")
        tx = c.createNode("multiplyDivide", name=self._node(
            "IKCurveTxMultiply" + suffix), skipSelect=True)
        c.setAttr(tx + ".input1X", step)
        c.connectAttr(divisor + ".outputX", tx + ".input2X")
        for joint in joints[1:]:
            c.connectAttr(tx + ".outputX", joint + ".translateX")
        c.delete(seed, zero_offset)
        if spec.auto_bind:
            clusters = dict.fromkeys(c.listConnections(source, source=False,
                                             destination=True,
                                             type="skinCluster") or ())
            for cluster in clusters:
                if self._leaf(cluster) == "skinClusterSkinCage":
                    continue
                c.skinCluster(cluster, edit=True, addInfluence=joints,
                              dropoffRate=4.0)
        self._verify_multi_chain(spec)

    def _update_custom_build_pose(self, control: str, *,
                                  base: str | None = None, add: bool) -> None:
        if not add or base is None:
            super()._update_custom_build_pose(control, base=base, add=add)
            return
        # asCreatePartialJoints appends exactly Extra reset, FK reset, follow=5.
        # The generic custom-controller writer captures other current user
        # attributes and reverses those reset commands, which is not this proc.
        c = self._cmds
        pose = self._node("buildPose")
        plug = pose + ".udExtraAttr"
        if not c.objExists(plug):
            c.addAttr(pose, longName="udExtraAttr", dataType="string")
        command = "".join(
            'xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 "%s";' % node
            for node in (base, control))
        command += 'setAttr "%s.follow" 5;' % control
        c.setAttr(plug, (c.getAttr(plug) or "") + command, type="string")
        values = []
        for node in (base, control):
            for kind, neutral in (("translate", 0.), ("rotate", 0.), ("scale", 1.)):
                for axis in "XYZ":
                    attribute = kind + axis
                    if c.getAttr(node + "." + attribute, settable=True):
                        values.append((node, attribute, neutral))
        values.append((control, "follow", 5.))
        for attribute, value in (
                ("advPyBuildPoseCommand", command),
                ("advPyBuildPoseValues", json.dumps(values, separators=(",", ":")))):
            c.addAttr(control, longName=attribute, dataType="string")
            c.setAttr(control + "." + attribute, value, type="string", lock=True)

    def _verify_multi_chain(self, spec: PartialJointSpec) -> None:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        suffix = spec.stem + "_" + spec.side
        group = self._unique("PartialMultiJoints" + suffix, "transform")
        handle = self._unique("IkHandlePartial" + suffix, "ikHandle")
        curve = self._unique("IKCurve" + suffix, "transform")
        joints = tuple(self._unique(
            "%sPartial%d_%s" % (spec.stem, index, spec.side), "joint")
            for index in range(1, spec.count + 1))
        source_parent = self._unique(spec.parent, "joint")
        for index, joint in enumerate(joints):
            expected_parent = source_parent if index == 0 else joints[index - 1]
            actual_parent = c.listRelatives(joint, parent=True,
                                            fullPath=True) or []
            if (actual_parent != [expected_parent]
                    or not c.sets(joint, isMember=self.scene_address(
                        "DeformSet"))):
                raise RuntimeError("多段 Partial 关节层级或 DeformSet 不一致："
                                   + joint)
        for node in (handle, curve):
            if (c.listRelatives(node, parent=True,
                                fullPath=True) or []) != [group]:
                raise RuntimeError("多段 Partial IK 系统层级不一致：" + node)
        shape = c.listRelatives(curve, shapes=True, fullPath=True,
                                type="nurbsCurve") or []
        if len(shape) != 1:
            raise RuntimeError("多段 Partial IK 曲线形状不完整")
        info = self._unique("IKCurveInfo" + suffix, "curveInfo")
        normalize = self._unique("IKCurveInfoNormalize" + suffix,
                                 "multiplyDivide")
        divisor = self._unique("IKCurveInfoAllMultiply" + suffix,
                               "multiplyDivide")
        tx = self._unique("IKCurveTxMultiply" + suffix, "multiplyDivide")
        connections = (
            (shape[0] + ".worldSpace[0]", info + ".inputCurve"),
            (info + ".arcLength", normalize + ".input1X"),
            (normalize + ".outputX", divisor + ".input1X"),
            (self.scene_address("MainScaleMultiplyDivide") + ".outputX",
             divisor + ".input2X"),
            (divisor + ".outputX", tx + ".input2X"),
            *((tx + ".outputX", joint + ".translateX")
              for joint in joints[1:]),
        )
        if any(not c.isConnected(source, destination)
               for source, destination in connections):
            raise RuntimeError("多段 Partial 曲线伸缩连接不完整")
        if spec.auto_bind:
            source = self._unique(spec.joint, "joint")
            clusters = set(c.listConnections(
                source, source=False, destination=True,
                type="skinCluster") or ())
            for cluster in clusters:
                if self._leaf(cluster) == "skinClusterSkinCage":
                    continue
                influences = set(c.ls(
                    c.skinCluster(cluster, query=True,
                                  influence=True) or [],
                    long=True, type="joint") or ())
                if not set(joints) <= influences:
                    raise RuntimeError("多段 Partial Skin 影响关节不完整："
                                       + cluster)

    def delete_partial_joint(self, spec: PartialDeleteSpec) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        suffix = spec.stem + "_" + spec.side
        single = spec.stem + "Partial_" + spec.side
        if spec.single:
            # Literal asDeletePartialJoints list and order (61991–61999).
            # Do not rewrite buildPose or purge auxiliary DG nodes that the
            # original procedure leaves alive after deleting its DAG objects.
            names = (single, suffix + "_00", suffix + "_00Offset",
                     suffix + "_00Offset_parentConstraint1",
                     single + "_pointConstraint1", single + "_orientConstraint1",
                     "FKOffset" + single)
            for name in names:
                node = self._node(name)
                if c.objExists(node):
                    c.delete(node)
        if spec.multi:
            names = ("IKCurveInfoAllMultiply" + suffix,
                     spec.stem + "Partial1_" + spec.side,
                     "PartialMultiJoints" + suffix)
            for name in names:
                node = self._node(name)
                if c.objExists(node):
                    c.delete(node)

    def remove_empty_partial_system(self) -> None:
        self._require_transaction()
        c = self._cmds
        system = self._node("PartialJointsSystem")
        if not c.objExists(system):
            return
        self._transaction_changed = True
        c.delete(system)
