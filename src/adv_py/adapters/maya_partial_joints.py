"""Maya node graph for ADV Body Partial Joints."""
from __future__ import annotations

from adv_py.core.partial_joints import (
    PartialDeleteSpec, PartialJointCandidate, PartialJointSpec,
)
from .maya_custom_controller import MayaCustomControllerHost


class MayaPartialJointsHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)

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
        for path in selection:
            leaf = self._leaf(path)
            if leaf.startswith("FK"):
                leaf = leaf[2:]
            if "Partial" in leaf:
                leaf = leaf.replace("Partial1_", "_", 1).replace(
                    "Partial_", "_", 1)
            joint = by_leaf.get(leaf)
            if joint and joint not in found:
                found.append(joint)
        return tuple(found)

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
        if auto_bind:
            for candidate in self.capture_partial_candidates():
                if c.referenceQuery(candidate.joint, isNodeReferenced=True):
                    raise ValueError("引用角色不能直接修改 Skin 影响关节")

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
        c = self._cmds
        root = self._unique("Root_M", "joint")
        joints = [root] + (c.listRelatives(root, allDescendents=True,
                                          fullPath=True, type="joint") or [])
        heights = [c.xform(node, query=True, worldSpace=True,
                           translation=True)[1] for node in joints]
        return max(max(heights) - min(heights), 0.001)

    def create_partial_joint(self, spec: PartialJointSpec) -> None:
        self._require_transaction()
        self._transaction_changed = True
        if spec.count == 1:
            self._create_single(spec)
        else:
            self._create_multi(spec)

    def _create_single(self, spec: PartialJointSpec) -> None:
        c = self._cmds
        source = self._unique(spec.joint, "joint")
        parent = self._unique(spec.parent, "joint")
        system = self._system("PartialJointsSystem",
                              self._unique("MotionSystem", "transform"))
        constraints = self._system("PartialJointsConstraints", system)
        stem_side = spec.stem + "_" + spec.side
        name = spec.stem + "Partial_" + spec.side
        world = c.xform(source, query=True, worldSpace=True, matrix=True)
        source_orient = c.getAttr(source + ".jointOrient")[0]
        joint = c.createNode("joint", name=self._node(name), parent=parent,
                             skipSelect=True)
        c.setAttr(joint + ".jointOrient", *source_orient)
        c.xform(joint, worldSpace=True, matrix=world)
        c.setAttr(joint + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
        c.setAttr(joint + ".segmentScaleCompensate", False)
        c.addAttr(joint, longName="partialJoint", attributeType="bool",
                  defaultValue=True)
        c.sets(joint, add=self._node("DeformSet"))
        offset = c.createNode("transform", name=self._node(stem_side + "_00Offset"),
                              parent=system, skipSelect=True)
        c.xform(offset, worldSpace=True, matrix=world)
        c.setAttr(offset + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
        zero = c.createNode("transform", name=self._node(stem_side + "_00"),
                            parent=offset, skipSelect=True)
        c.addAttr(zero, longName="partialJoint", attributeType="bool")
        parent_constraint = c.parentConstraint(
            parent, offset, maintainOffset=True,
            name=self._node(stem_side + "_00Offset_parentConstraint1"))[0]
        c.parent(parent_constraint, constraints)
        target = joint
        follow = joint
        if spec.include_controller:
            control_offset = c.createNode("transform", name=self._node(
                "FKOffset" + name), parent=system, skipSelect=True)
            c.xform(control_offset, worldSpace=True, matrix=world)
            extra = c.createNode("transform", name=self._node(
                "FKExtra" + name), parent=control_offset, skipSelect=True)
            control = self._create_control_icon(name, extra)
            c.sets((control, extra), add=self._node("ControlSet"))
            c.parentConstraint(control, joint, maintainOffset=False,
                               name=self._node(name + "_parentConstraint1"))
            c.scaleConstraint(control, joint, maintainOffset=False,
                              name=self._node(name + "_scaleConstraint1"))
            target, follow = control_offset, control
            main = self._node("Main")
            if c.objExists(main) and not c.attributeQuery("partialVis", node=main,
                                                          exists=True):
                c.addAttr(main, longName="partialVis", attributeType="bool",
                          defaultValue=True, keyable=True)
        side_factor = -1 if spec.side == "L" else 1
        delta = side_factor * self._height() / 5000.0
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
            c.parent((orient, point, scale), constraints)
        c.addAttr(follow, longName="follow", attributeType="double",
                  minValue=0.0, maxValue=10.0, defaultValue=5.0,
                  keyable=True)
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

    def _create_control_icon(self, name: str, parent: str) -> str:
        c = self._cmds
        icon = self._node("FaceA_icon")
        if c.objExists(icon):
            control = c.duplicate(icon, name=self._node("FK" + name),
                                  returnRootsOnly=True)[0]
        else:
            control = c.circle(name=self._node("FK" + name), normal=(1, 0, 0),
                               radius=self._height() / 20.0,
                               sections=8, constructionHistory=False)[0]
        c.parent(control, parent)
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
        group = self._system("PartialMultiJoints" + spec.stem + "_" + spec.side,
                             system)
        c.addAttr(group, longName="locatorVis", attributeType="bool",
                  defaultValue=False, keyable=True)
        radius = (float(c.getAttr(source + ".fat"))
                  if c.attributeQuery("fat", node=source, exists=True)
                  else self._height() / 100.0)
        direction = -1 if spec.side == "L" else 1
        step = 2.0 * radius * direction / spec.count
        world = c.xform(source, query=True, worldSpace=True, matrix=True)
        source_orient = c.getAttr(source + ".jointOrient")[0]
        joints = []
        for index in range(1, spec.count + 1):
            name = "%sPartial%d_%s" % (spec.stem, index, spec.side)
            ancestor = parent if index == 1 else joints[-1]
            joint = c.createNode("joint", name=self._node(name),
                                 parent=ancestor, skipSelect=True)
            c.setAttr(joint + ".jointOrient", *source_orient)
            c.setAttr(joint + ".rotateOrder", c.getAttr(source + ".rotateOrder"))
            c.setAttr(joint + ".segmentScaleCompensate", False)
            c.addAttr(joint, longName="partialJoint", attributeType="bool",
                      defaultValue=True)
            c.sets(joint, add=self._node("DeformSet"))
            if index == 1:
                c.xform(joint, worldSpace=True, matrix=world)
                c.move(-direction * radius + step, 0, 0, joint,
                       relative=True, objectSpace=True, worldSpaceDistance=True)
            else:
                c.setAttr(joint + ".translateX", step)
            joints.append(joint)
        handle, effector, curve = c.ikHandle(
            startJoint=joints[0], endEffector=joints[-1],
            solver="ikSplineSolver", numSpans=1,
            simplifyCurve=True, rootOnCurve=True,
            parentCurve=False, createCurve=True)
        suffix = spec.stem + "_" + spec.side
        handle = c.rename(handle, self._node("IkHandlePartial" + suffix))
        c.rename(effector, self._node("EffectorPartial" + suffix))
        curve = c.rename(curve, self._node("IKCurve" + suffix))
        curve_shape = (c.listRelatives(curve, shapes=True,
                                       fullPath=True, type="nurbsCurve") or [None])[0]
        if curve_shape is None:
            raise RuntimeError("Partial IK 曲线缺少 NURBS 形状")
        c.setAttr(handle + ".visibility", False, lock=True)
        c.parent((handle, curve), group)
        for index in range(4):
            transform = c.createNode("transform", name=self._node(
                "PMJX%d%s" % (index, suffix)), parent=group, skipSelect=True)
            position = c.xform("%s.cv[%d]" % (curve, index),
                               query=True, worldSpace=True, translation=True)
            c.xform(transform, worldSpace=True, translation=position)
            locator = c.spaceLocator(name=self._node(
                "PMJLoc%d%s" % (index, suffix)))[0]
            c.parent(locator, transform, relative=True)
            c.connectAttr(group + ".locatorVis", locator + ".visibility")
            c.setAttr(locator + ".overrideEnabled", True)
            c.setAttr(locator + ".overrideColor", 14 if index in (1, 2) else 13)
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
        tx = c.createNode("multiplyDivide", name=self._node(
            "IKCurveTxMultiply" + suffix), skipSelect=True)
        c.setAttr(normalize + ".operation", 2)
        c.setAttr(divisor + ".operation", 2)
        c.connectAttr(info + ".arcLength", normalize + ".input1X")
        c.setAttr(normalize + ".input2X", c.getAttr(info + ".arcLength"))
        c.connectAttr(normalize + ".outputX", divisor + ".input1X")
        c.connectAttr(self._node("MainScaleMultiplyDivide") + ".outputX",
                      divisor + ".input2X")
        c.setAttr(tx + ".input1X", step)
        c.connectAttr(divisor + ".outputX", tx + ".input2X")
        for joint in joints[1:]:
            c.connectAttr(tx + ".outputX", joint + ".translateX", force=True)
        if spec.auto_bind:
            clusters = set(c.listConnections(source, source=False,
                                             destination=True,
                                             type="skinCluster") or ())
            for cluster in sorted(clusters):
                if self._leaf(cluster) == "skinClusterSkinCage":
                    continue
                c.skinCluster(cluster, edit=True, addInfluence=joints,
                              dropoffRate=4.0)

    def delete_partial_joint(self, spec: PartialDeleteSpec) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        suffix = spec.stem + "_" + spec.side
        single = spec.stem + "Partial_" + spec.side
        if spec.single:
            control = self._node("FK" + single)
            if c.objExists(control):
                self._update_custom_build_pose(control, add=False)
            names = ("FKOffset" + single, single, suffix + "_00Offset",
                     "FK" + single + "SR",
                     suffix + "_00Offset_parentConstraint1",
                     single + "_orientConstraint1",
                     single + "_pointConstraint1",
                     single + "_scaleConstraint1",
                     "FKOffset" + single + "_orientConstraint1",
                     "FKOffset" + single + "_pointConstraint1",
                     "FKOffset" + single + "_scaleConstraint1")
            for name in names:
                node = self._node(name)
                if c.objExists(node):
                    c.delete(node)
        if spec.multi:
            names = ("IKCurveInfoAllMultiply" + suffix,
                     "IKCurveInfoNormalize" + suffix,
                     "IKCurveInfo" + suffix, "IKCurveTxMultiply" + suffix,
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
        candidates = self.capture_partial_candidates()
        if any(candidate.existing_single or candidate.existing_multi
               for candidate in candidates):
            return
        self._transaction_changed = True
        c.delete(system)
