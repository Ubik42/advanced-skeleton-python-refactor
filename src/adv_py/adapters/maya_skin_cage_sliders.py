"""Maya graph for AdvancedSkeleton 6.925 SkinCage Sliders."""
from __future__ import annotations

import re
from contextlib import contextmanager

from adv_py.core.skin_cage_sliders import SkinCageSlider
from .maya_adv_icons import create_adv_icon
from .maya_skin_cage import MayaSkinCageHost


class MayaSkinCageSliderHost(MayaSkinCageHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._include_controller = False
        self._slider_sampler = ""

    def _leaf(self, node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _parent_joint(self, joint: str) -> str:
        parents = self.cmds.listRelatives(joint, parent=True, type="joint",
                                          fullPath=True) or []
        return parents[0] if parents else self._name("Root_M")

    def _twist_child(self, joint: str) -> str:
        """asSkinCurveSliderInfo preserves native child order and last match."""
        c = self.cmds
        seen = set()
        while joint and joint not in seen:
            seen.add(joint)
            child = ""
            for candidate in c.listRelatives(joint, children=True, type="joint") or []:
                leaf = self._leaf(candidate)
                if "Slider" in leaf:
                    continue
                if self._cage_fk(candidate):
                    child = candidate
                if re.search(r"Part[0-9]_", leaf):
                    child = candidate
            if not child or not re.search(r"Part[0-9]", self._leaf(child)):
                return child
            joint = child
        return ""

    def capture_slider_rows(self) -> tuple[tuple[str, str, str, int, str], ...]:
        c = self.cmds
        selection = c.ls(selection=True) or []
        if not selection:
            raise ValueError("请选择 SkinCage 截面曲线")
        rows = []
        for profile in selection:
            leaf = self._leaf(profile)
            parts = leaf.split("_")
            if len(parts) < 3 or "Profile" not in parts[2]:
                raise ValueError("请选择 SkinCage 截面曲线：" + leaf)
            joint = self._name(parts[0] + "_" + parts[1])
            kind = parts[2]
            segment = kind.removesuffix("Profile") if kind in (
                "startProfile", "middleProfile", "endProfile") else ""
            if kind == "twistProfile1":
                segment = "end"
            elif re.fullmatch(r"twistProfile[2-9]", kind):
                child = self._twist_child(joint)
                following = profile[:-1] + str(int(profile[-1]) + 1)
                if child and c.objExists(child) and not c.objExists(following):
                    joint, segment = child, "start"
            if not segment:
                continue
            if kind == "twistProfile1":
                part = self._name(parts[0] + "Part1_" + parts[1])
                restore = part if c.objExists(part) else joint
            elif kind == "endProfile":
                restore = joint
            else:
                restore = (c.listRelatives(joint, parent=True) or [""])[0]
            bend_axis = 0
            if "Elbow" in self._leaf(joint) or "Knee" in self._leaf(joint):
                orient = c.getAttr(joint + ".jointOrient")[0]
                opm = self._name("FitSkeleton") + ".useOffsetParentMatrix"
                if c.objExists(opm) and c.getAttr(opm):
                    from maya.api import OpenMaya as om
                    matrix = c.getAttr(joint + ".offsetParentMatrix")
                    if len(matrix) == 1:
                        matrix = matrix[0]
                    rotation = om.MTransformationMatrix(om.MMatrix(matrix)).rotation()
                    from math import degrees
                    orient = tuple(degrees(value) for value in (rotation.x, rotation.y, rotation.z))
                if abs(orient[1]) > abs(orient[2]):
                    bend_axis = 1
                if abs(orient[2]) > abs(orient[1]):
                    bend_axis = 2
            rows.append((profile, joint, restore, bend_axis, segment))
        return tuple(rows)

    def preflight_sliders(self, plan: tuple[SkinCageSlider, ...], *,
                          creating: bool, include_controller: bool) -> None:
        c = self.cmds
        self._include_controller = creating and include_controller
        for leaf in ("skinCage", "skinClusterSkinCage", "MotionSystem",
                     "DeformSet"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SkinCage Sliders 缺少原版节点：" + leaf)
        if include_controller:
            self._cage_main()
            for leaf in ("ControlSet", "buildPose"):
                if not c.objExists(self._name(leaf)):
                    raise ValueError("带控制器的 Sliders 缺少：" + leaf)
            for spec in plan:
                if not self._cage_fk(spec.deform_joint):
                    raise ValueError("Sliders 缺少 FK 驱动控制器："
                                     + spec.deform_joint)
        for spec in plan:
            if len(c.ls(spec.profile + ".cv[*]", flatten=True) or []) < 5:
                raise ValueError("SkinCage 截面至少需要五个 CV：" + spec.profile)

    def ensure_partial_joints(self,
                              plan: tuple[SkinCageSlider, ...]) -> None:
        from adv_py.adapters.maya_partial_joints import MayaPartialJointsHost
        from adv_py.core.partial_joints import plan_create_partial_joints

        c = self.cmds
        original = c.ls(selection=True, long=True) or []
        try:
            for joint in dict.fromkeys(
                    spec.deform_joint for spec in plan
                    if not any(c.objExists(self._name(spec.joint(index)))
                               for index in (0, 1))):
                leaf = self._leaf(joint)
                stem, side = leaf.rsplit("_", 1)
                if c.objExists(self._name(stem + "Partial_" + side)):
                    continue
                c.select(joint, replace=True)
                helper = MayaPartialJointsHost(namespace=self.namespace)
                plan = plan_create_partial_joints(
                    helper.capture_partial_candidates(),
                    helper.resolve_partial_selection(),
                    use_opm=helper.partial_uses_opm())
                # The SkinCage operation owns rollback. A second host opening
                # another undo chunk here splits a single source operation.
                helper._transaction_active = True
                try:
                    for spec in plan.specs:
                        helper.create_partial_joint(spec)
                finally:
                    helper._transaction_active = False
        finally:
            c.select(original, replace=True) if original else c.select(clear=True)

    def _system(self, leaf: str, parent: str) -> str:
        c = self.cmds
        name = self._name(leaf)
        if c.objExists(name):
            return name
        return c.createNode("transform", name=name, parent=parent,
                            skipSelect=True)

    def _profile_center(self, spec: SkinCageSlider) -> tuple[float, ...]:
        return tuple(self.cmds.xform(spec.profile, query=True,
                                     worldSpace=True, translation=True))

    def _cv(self, spec: SkinCageSlider, index: int) -> tuple[float, ...]:
        return tuple(self.cmds.xform(spec.profile + f".cv[{index}]",
                                     query=True, worldSpace=True,
                                     translation=True))

    @contextmanager
    def slider_sampling_scope(self):
        """The source uses one named closestSampler for the whole selection."""
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        sampler = self._name("closestSampler")
        if c.objExists(sampler):
            c.delete(sampler)
        self._slider_sampler = c.createNode("closestPointOnMesh", name=sampler)
        c.connectAttr(self._name("skinCage") + ".outMesh",
                      self._slider_sampler + ".inMesh", force=True)
        try:
            yield
        finally:
            if c.objExists(self._slider_sampler):
                c.delete(self._slider_sampler)
            self._slider_sampler = ""
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def _closest_vertex(self, position: tuple[float, ...]) -> str:
        if not self._slider_sampler:
            raise RuntimeError("Slider sampling requires its operation scope")
        c = self.cmds
        c.setAttr(self._slider_sampler + ".inPosition", *position, type="double3")
        index = int(c.getAttr(self._slider_sampler + ".closestVertexIndex"))
        return self._name("skinCage") + f".vtx[{index}]"

    def _slider_indices(self, spec: SkinCageSlider,
                        index: int) -> tuple[int, int]:
        cv = (2, 3, 0, 1)[index] if spec.side == "L" else index
        return cv, cv + 1

    def _sample_vertex(self, spec: SkinCageSlider, index: int,
                       factor: float) -> str:
        c = self.cmds
        cv, _ = self._slider_indices(spec, index)
        point = self._cv(spec, cv)
        joint = tuple(c.xform(spec.deform_joint, query=True,
                              worldSpace=True, translation=True))
        sample = tuple(joint[axis] + factor * (point[axis] - joint[axis])
                       for axis in range(3))
        # The original builder moves the opposite profile out of the cage
        # during closest-vertex lookup when both sides overlap closely.
        if spec.side not in ("L", "R"):
            return self._closest_vertex(sample)
        other_side = "R" if spec.side == "L" else "L"
        # For a twist profile the source still displaces the canonical
        # opposite start/end profile, rather than the opposite twist profile.
        opposite = self._name(f"{spec.stem}_{other_side}_{spec.segment}Profile")
        if not c.objExists(opposite):
            return self._closest_vertex(sample)
        c.move(0, 0, -999, opposite, relative=True, worldSpace=True)
        try:
            return self._closest_vertex(sample)
        finally:
            c.move(0, 0, 999, opposite, relative=True, worldSpace=True)

    def _distance_driver(self, spec: SkinCageSlider, index: int,
                         slider: str, parent: str, system: str,
                         midpoint: tuple[float, ...]) -> None:
        c = self.cmds
        shared = f"{spec.stem}Slide"
        suffix = f"{index}_{spec.side}"
        distance = self._name(shared + "Dist" + suffix)
        normalize = self._name(shared + "DistNormalize" + suffix)
        if not c.objExists(distance):
            distance = c.createNode("distanceBetween", name=distance)
            start = c.createNode("transform", name=self._name(
                shared + "Start" + suffix), skipSelect=True)
            end = c.createNode("transform", name=self._name(
                shared + "End" + suffix), skipSelect=True)
            c.connectAttr(end + ".translate", distance + ".point2", force=True)
            start = c.parent(start, parent)[0]
            end = c.parent(end, parent)[0]
            c.xform(start, worldSpace=True, translation=midpoint)
            c.xform(end, worldSpace=True, translation=midpoint)
            partial = self._name(f"{spec.stem}Partial_{spec.side}")
            end = c.parent(end, partial)[0]
            c.setAttr(end + ".translateX", 0)
            local = c.getAttr(end + ".translate")[0]
            side_factor = -1 if spec.side == "L" else 1
            magnitude = sum(component * component for component in local) ** 0.5
            length = float(c.getAttr(spec.deform_joint + ".translateX"))
            c.setAttr(start + ".translate", length - magnitude * side_factor,
                      0, 0, type="double3")
            start = c.parent(start, system)[0]
            end = c.parent(end, start)[0]
            c.parentConstraint(spec.deform_joint, start, maintainOffset=True)
            c.parentConstraint(partial, end, maintainOffset=True)
            normalize = c.createNode("multiplyDivide", name=normalize)
            c.setAttr(normalize + ".operation", 2)
            c.connectAttr(distance + ".distance", normalize + ".input1X")
            baseline = float(c.getAttr(distance + ".distance"))
            c.setAttr(normalize + ".input2X", baseline)
        prefix = f"{spec.stem}{spec.segment}Slide"
        reducer = c.createNode("multiplyDivide", name=self._name(
            prefix + "Reducer" + suffix))
        slide = c.createNode("multiplyDivide", name=self._name(
            prefix + "Multiply" + suffix))
        plus = c.createNode("plusMinusAverage", name=self._name(
            prefix + "PlusOffset" + suffix))
        c.addAttr(slider, longName="slide", attributeType="double", defaultValue=1, keyable=True)
        c.connectAttr(slider + ".slide", slide + ".input2X")
        c.connectAttr(reducer + ".outputX", slide + ".input1X")
        c.connectAttr(slide + ".outputX", plus + ".input1D[0]")
        width = max(abs(float(c.getAttr(slider + ".translateY"))),
                    abs(float(c.getAttr(slider + ".translateZ"))))
        side_factor = -1 if spec.side == "L" else 1
        if spec.segment != "middle":
            sign = (-1 if spec.segment == "start" else 1) * side_factor
            c.setAttr(reducer + ".input2X", width * sign)
            minus = c.createNode("plusMinusAverage", name=self._name(
                prefix + "MinusOne" + suffix))
            c.setAttr(minus + ".operation", 2)
            c.connectAttr(normalize + ".outputX", minus + ".input1D[0]")
            c.setAttr(minus + ".input1D[1]", 1)
            c.connectAttr(minus + ".output1D", reducer + ".input1X")
            axis = "X"
        else:
            axis = "Y" if spec.bend_axis == 2 or (spec.bend_axis == 0 and index in (0, 2)) else "Z"
            c.setAttr(reducer + ".input2X", width)
            reverse = c.createNode("reverse", name=self._name(
                prefix + "Reverse" + suffix))
            absolute = c.createNode("condition", name=self._name(
                prefix + "Absolutor" + suffix))
            negate = c.createNode("multiplyDivide", name=self._name(
                prefix + "TimesMinusOne" + suffix))
            value = float(c.getAttr(slider + ".translate" + axis))
            c.setAttr(absolute + ".operation", 4 if value > 0 else 2)
            c.connectAttr(normalize + ".outputX", reverse + ".inputX")
            c.connectAttr(reverse + ".outputX", absolute + ".firstTerm")
            c.connectAttr(reverse + ".outputX",
                          absolute + ".colorIfFalseR")
            # The MEL creates the same Reducer name twice in this branch;
            # Maya auto-names the second, unused node. Keep that graph behavior.
            c.createNode("multiplyDivide", name=self._name(prefix + "Reducer" + suffix))
            c.connectAttr(reverse + ".outputX", negate + ".input1X")
            c.setAttr(negate + ".input2X", -1)
            c.connectAttr(negate + ".outputX",
                          absolute + ".colorIfTrueR")
            c.connectAttr(absolute + ".outColorR",
                          reducer + ".input1X")
        c.setAttr(plus + ".input1D[1]", float(c.getAttr(
            slider + ".translate" + axis)))
        c.connectAttr(plus + ".output1D", slider + ".translate" + axis)

    def _controller_driver(self, spec: SkinCageSlider, index: int,
                           slider: str, parent: str, system: str) -> None:
        """asCreateSliders controller branch invokes the Python asDsCreate port."""
        from .maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.core.driving_systems import DrivingCreateOptions
        c = self.cmds
        leaf = spec.joint(index)
        offset = c.createNode("transform", name=self._name("FKOffset" + leaf), parent=system)
        extra = c.createNode("transform", name=self._name("FKExtra" + leaf), parent=offset)
        from .maya_original_transform_channels import lock_original_transform_channels
        lock_original_transform_channels(c,extra,False,False,True,True)
        height = float(c.getAttr(self._cage_main() + ".height"))
        control = create_adv_icon(c, name=self._name("FK" + leaf), parent=extra,
                                  template="Bend_icon", radius=.01 * height,
                                  fallback_normal=(1, 0, 0))
        c.setAttr(control + ".t", 0, 0, 0, type="float3")
        c.sets(control, extra, add=self._name("ControlSet"))
        self._cage_align(offset, slider)
        c.setAttr(offset + ".rotateOrder", c.getAttr(slider + ".rotateOrder"))
        fkx = c.createNode("transform", name=self._name("FKX" + leaf), parent=control)
        self._cage_parent_constraint(fkx, slider, maintain_offset=False)
        self._cage_parent_constraint(parent, offset, maintain_offset=True)
        c.setAttr(slider + ".segmentScaleCompensate", 0)
        self._record_slider_build_pose(leaf)
        temporary = self._name("tempTransform")
        if c.objExists(temporary):
            c.delete(temporary)
        temporary = c.createNode("transform", name=temporary, parent=slider)
        temporary = c.parent(temporary, spec.deform_joint)[0]
        local = c.getAttr(temporary + ".t")[0]
        c.delete(temporary)
        helper = MayaDrivingSystemsHost(namespace=self.namespace or None)
        helper._transaction_active = True
        helper._original_driving_from_build = True
        from maya import mel
        q_rotations = bool(mel.eval("global int $asDSQRotate; $asDSQRotate;"))
        if spec.bend_axis in (0, 2):
            q_rotations = spec.bend_axis == 0
            mel.eval("global int $asDSQRotate; $asDSQRotate=%d;" % int(q_rotations))
        try:
            rotate = "rotateY" if spec.bend_axis == 0 and index in (1, 3) else "rotateZ"
            driven_axis = "translateX" if spec.segment != "middle" else (
                "translateY" if index in (0, 2) else "translateZ")
            driver_control = self._cage_fk(spec.deform_joint)
            driver_leaf = self._leaf(driver_control)
            for alternate in (False, True):
                angle = -90 if index in (1, 2) else 90
                if alternate:
                    angle *= -1
                if spec.segment == "end":
                    angle *= -1
                value = local[1 if index in (0, 2) else 2] / 4
                if alternate and spec.segment != "middle":
                    value *= -1
                if spec.segment != "middle" and index in (0, 1):
                    value *= -1
                c.setAttr(driver_control + "." + rotate, angle)
                c.setAttr(control + "." + driven_axis, value)
                options = DrivingCreateOptions(driver_leaf, rotate, mirror=False,
                                               q_rotations=q_rotations)
                plan = helper.capture_original_driving_create(options)
                helper.create_original_driving_system(plan)
            if not q_rotations:
                curve = self._name("SDKFK" + leaf + "_" + driven_axis)
                c.setAttr(curve + ".preInfinity", 1)
                c.setAttr(curve + ".postInfinity", 1)
                for key in (0, 2):
                    c.keyTangent(curve, index=(key, key),
                                 inTangentType="spline", outTangentType="spline")
        finally:
            helper._transaction_active = False
        main = self._cage_main()
        if not c.objExists(main + ".slideSysVis"):
            c.addAttr(main, longName="slideSysVis", attributeType="bool", defaultValue=1, keyable=True)
            c.setAttr(main + ".slideSysVis", keyable=False, channelBox=True)
        system = self._name("SlideSystem")
        if not c.isConnected(main + ".slideSysVis", system + ".v"):
            c.connectAttr(main + ".slideSysVis", system + ".v")

    def _slider_pose_commands(self, leaf: str) -> tuple[str, str]:
        return tuple('xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 "%s";'
                     % self._name(prefix + leaf)
                     for prefix in ("FKExtra", "FK"))

    def _record_slider_build_pose(self, leaf: str) -> None:
        c = self.cmds
        pose = self._name("buildPose")
        if not c.attributeQuery("udExtraAttr", node=pose, exists=True):
            c.addAttr(pose, longName="udExtraAttr", dataType="string")
        plug = pose + ".udExtraAttr"
        existing = c.getAttr(plug) or ""
        c.setAttr(plug, existing + "".join(
            self._slider_pose_commands(leaf)), type="string")

    def create_slider(self, spec: SkinCageSlider, *,
                      include_controller: bool) -> bool:
        c = self.cmds
        if any(c.objExists(self._name(spec.joint(index))) for index in (0, 1)):
            return False
        system = self._system("SlideSystem", self._name("MotionSystem"))
        scale = self._name("MainScaleMultiplyDivide")
        if c.objExists(scale) and not c.isConnected(
                scale + ".output", system + ".scale"):
            c.connectAttr(scale + ".output", system + ".scale",
                          force=True)
        group = self._system(f"{spec.stem}SlideSystem_{spec.side}", system)
        self.ensure_partial_joints((spec,))
        partial = self._name(f"{spec.stem}Partial_{spec.side}")
        first_parent = self._parent_joint(spec.deform_joint)
        parent = (first_parent if spec.segment == "start" else partial
                  if spec.segment == "middle" else spec.deform_joint)
        vertices = {}
        if spec.segment == "end" and "Part1_" in self._leaf(spec.restore_joint):
            parent = self._cage_rla_child(spec.deform_joint)
        for index in spec.indices:
            cv, next_cv = self._slider_indices(spec, index)
            a, b = self._cv(spec, cv), self._cv(spec, next_cv)
            midpoint = tuple((a[axis] + b[axis]) / 2 for axis in range(3))
            c.select(spec.deform_joint, replace=True)
            joint = c.joint(name=self._name(spec.joint(index)))
            if parent != spec.deform_joint:
                joint = c.parent(joint, parent)[0]
            c.sets(joint, add=self._name("DeformSet"))
            c.delete(c.orientConstraint(spec.profile, joint))
            c.makeIdentity(joint, apply=True, translate=False, rotate=True, scale=False, normal=0)
            c.xform(joint, worldSpace=True, translation=midpoint)
            if include_controller:
                self._controller_driver(spec, index, joint, parent, group)
            else:
                self._distance_driver(spec, index, joint, first_parent,
                                      group, midpoint)
            c.skinCluster(self._name("skinClusterSkinCage"), edit=True,
                          addInfluence=joint, weight=0, lockWeights=False)
            vertex = self._sample_vertex(spec, index, .833)
            vertices[index] = vertex
            skin = self._name("skinClusterSkinCage")
            c.skinPercent(skin, vertex, transformValue=[(joint, 1)])
            if spec.bend_axis == 0:
                if index > 0:
                    c.skinPercent(skin, vertex, transformValue=[
                        (self._name(spec.joint(index - 1)), .5)])
                if index == 3:
                    c.skinPercent(skin, vertices[0], transformValue=[
                        (self._name(spec.joint(3)), .5)])
            if (spec.bend_axis == 1 and index == 3) or (spec.bend_axis == 2 and index == 2):
                extra = ((2, 1), (4, 3)) if spec.bend_axis == 1 else ((1, 0), (3, 2))
                for pickup, slider_index in extra:
                    cv_index = (2, 3, 0, 1, 2)[pickup] if spec.side == "L" else pickup
                    vertex = self._closest_vertex(self._cv(spec, cv_index))
                    c.skinPercent(skin, vertex, transformValue=[
                        (self._name(spec.joint(slider_index)), 1)])
        return True

    def delete_slider(self, spec: SkinCageSlider) -> None:
        c = self.cmds
        skin = self._name("skinClusterSkinCage")
        for index in range(4):
            # MEL reads the holder position BEFORE its .832 scale.
            vertex = self._closest_vertex(self._cv(spec, index))
            weights = ([(spec.deform_joint, .5), (spec.restore_joint, .5)]
                       if spec.segment == "middle" else [(spec.restore_joint, 1)])
            c.skinPercent(skin, vertex, transformValue=weights)
        for index in range(4):
            for name in (spec.joint(index), "FKOffset" + spec.joint(index),
                         f"{spec.stem}SlideStart{index}_{spec.side}"):
                node = self._name(name)
                if c.objExists(node):
                    c.delete(node)
        group = self._name(f"{spec.stem}SlideSystem_{spec.side}")
        if c.objExists(group) and not c.listRelatives(group, children=True):
            c.delete(group)

    @contextmanager
    def slider_delete_time_scope(self):
        c = self.cmds
        current = c.currentTime(query=True)
        c.currentTime(0)
        try:
            yield
        finally:
            c.currentTime(current)

    def finish_slider_delete(self) -> None:
        from .maya_driving_systems import MayaDrivingSystemsHost
        helper = MayaDrivingSystemsHost(namespace=self.namespace or None)
        helper._transaction_active = True
        try:
            helper.go_to_original_corrective_build_pose(face=False)
        finally:
            helper._transaction_active = False
        self.cmds.select(clear=True)

    def capture_sliders(self, spec: SkinCageSlider, *,
                        present: bool) -> bool:
        c = self.cmds
        influences = {self._leaf(node) for node in (c.skinCluster(
            self._name("skinClusterSkinCage"), query=True,
            influence=True) or [])}
        pose = self._name("buildPose")
        pose_script = (c.getAttr(pose + ".udExtraAttr") or ""
                       if c.objExists(pose + ".udExtraAttr") else "")
        for index in spec.indices:
            leaf = spec.joint(index)
            joint = self._name(leaf)
            if (c.objExists(joint) and leaf in influences) != present:
                return False
            control_names = tuple(self._name(prefix + leaf) for prefix in (
                "FKOffset", "FKExtra", "FK", "FKX"))
            axis = ("translateX" if spec.segment != "middle" else
                    "translateY" if index in (0, 2) else "translateZ")
            sdk = self._name("SDKFK" + leaf + "_" + axis)
            prefix = f"{spec.stem}{spec.segment}Slide"
            suffix = f"{index}_{spec.side}"
            distance_nodes = tuple(self._name(prefix + part + suffix)
                                   for part in ("Reducer", "Multiply",
                                                "PlusOffset"))
            if present and self._include_controller:
                if (not all(c.objExists(node) for node in control_names)
                        or not c.objExists(sdk)
                        or not all(command in pose_script for command in
                                   self._slider_pose_commands(leaf))):
                    return False
            elif present:
                if not all(c.objExists(node) for node in distance_nodes):
                    return False
            elif any(c.objExists(node) for node in control_names):
                return False
        return True
