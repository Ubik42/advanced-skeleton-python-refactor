"""Maya graph for AdvancedSkeleton 6.925 SkinCage Sliders."""
from __future__ import annotations

from adv_py.core.skin_cage_sliders import SkinCageSlider
from .maya_adv_icons import create_adv_icon
from .maya_skin_cage import MayaSkinCageHost


class MayaSkinCageSliderHost(MayaSkinCageHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._include_controller = False

    def _leaf(self, node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _parent_joint(self, joint: str) -> str:
        parents = self.cmds.listRelatives(joint, parent=True, type="joint",
                                          fullPath=True) or []
        if not parents:
            raise ValueError("变形关节缺少父关节：" + joint)
        return parents[0]

    def _twist_child(self, joint: str) -> str:
        c = self.cmds
        visited = set()
        current = joint
        while current not in visited:
            visited.add(current)
            children = c.listRelatives(current, children=True,
                                       type="joint", fullPath=True) or []
            candidates = [child for child in children
                          if "Slider" not in self._leaf(child)]
            ranked = sorted(candidates, key=lambda child: (
                not c.objExists(self._name("FK" + self._leaf(child))),
                "Part" not in self._leaf(child), self._leaf(child)))
            if not ranked:
                break
            current = ranked[0]
            if "Part" not in self._leaf(current):
                return current
        raise ValueError("末段 Twist 截面缺少后继关节：" + joint)

    def capture_slider_rows(self) -> tuple[tuple[str, str, str, int, str], ...]:
        c = self.cmds
        selection = c.ls(selection=True, long=True, transforms=True) or []
        if not selection:
            raise ValueError("请选择 SkinCage 截面曲线")
        rows = []
        for profile in selection:
            leaf = self._leaf(profile)
            parts = leaf.split("_")
            if len(parts) != 3 or not parts[2].startswith((
                    "startProfile", "middleProfile", "endProfile",
                    "twistProfile")):
                raise ValueError("请选择 SkinCage 截面曲线：" + leaf)
            if not c.listRelatives(profile, shapes=True,
                                   type="nurbsCurve"):
                raise ValueError("所选截面不是 NURBS 曲线：" + leaf)
            joint = self._name(parts[0] + "_" + parts[1])
            if not c.objExists(joint) or c.nodeType(joint) != "joint":
                raise ValueError("截面缺少对应变形关节：" + leaf)
            kind = parts[2]
            if kind.startswith("twistProfile") and kind != "twistProfile1":
                ordinal = int(kind.removeprefix("twistProfile"))
                next_profile = self._name(
                    f"{parts[0]}_{parts[1]}_twistProfile{ordinal + 1}")
                if c.objExists(next_profile):
                    continue
                joint = self._twist_child(joint)
                segment = "start"
            else:
                segment = ("end" if kind.startswith("twistProfile")
                           else kind.removesuffix("Profile"))
            if kind.startswith("endProfile"):
                restore = joint
            elif kind == "twistProfile1":
                part = self._name(parts[0] + "Part1_" + parts[1])
                restore = part if c.objExists(part) else joint
            else:
                restore = self._parent_joint(joint)
            bend_axis = 0
            if "Elbow" in parts[0] or "Knee" in parts[0]:
                orient = c.getAttr(joint + ".jointOrient")[0]
                if abs(orient[1]) > abs(orient[2]):
                    bend_axis = 1
                elif abs(orient[2]) > abs(orient[1]):
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
            for leaf in ("ControlSet", "Main", "buildPose"):
                if not c.objExists(self._name(leaf)):
                    raise ValueError("带控制器的 Sliders 缺少：" + leaf)
            for spec in plan:
                if not c.objExists(self._name("FK" +
                                               self._leaf(spec.deform_joint))):
                    raise ValueError("Sliders 缺少 FK 驱动控制器："
                                     + spec.deform_joint)
        for spec in plan:
            if len(c.ls(spec.profile + ".cv[*]", flatten=True) or []) < 5:
                raise ValueError("SkinCage 截面至少需要五个 CV：" + spec.profile)
            existing = [c.objExists(self._name(spec.joint(i)))
                        for i in spec.indices]
            if creating and any(existing):
                raise ValueError("Sliders 已存在：" + spec.profile)
            if not creating and not any(existing):
                raise ValueError("所选截面没有 Sliders：" + spec.profile)

    def ensure_partial_joints(self,
                              plan: tuple[SkinCageSlider, ...]) -> None:
        from adv_py.adapters.maya_partial_joints import MayaPartialJointsHost
        from adv_py.application.partial_joints import CreatePartialJoints

        c = self.cmds
        original = c.ls(selection=True, long=True) or []
        try:
            for joint in dict.fromkeys(spec.deform_joint for spec in plan):
                leaf = self._leaf(joint)
                stem, side = leaf.rsplit("_", 1)
                if c.objExists(self._name(stem + "Partial_" + side)):
                    continue
                c.select(joint, replace=True)
                CreatePartialJoints(MayaPartialJointsHost(
                    namespace=self.namespace)).apply()
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

    def _closest_vertex(self, position: tuple[float, ...]) -> str:
        c = self.cmds
        sampler = c.createNode("closestPointOnMesh")
        try:
            c.connectAttr(self._name("skinCage") + ".outMesh",
                          sampler + ".inMesh", force=True)
            c.setAttr(sampler + ".inPosition", *position, type="double3")
            index = int(c.getAttr(sampler + ".closestVertexIndex"))
            return self._name("skinCage") + f".vtx[{index}]"
        finally:
            c.delete(sampler)

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
        return self._closest_vertex(sample)

    def _distance_driver(self, spec: SkinCageSlider, index: int,
                         slider: str, parent: str, system: str,
                         midpoint: tuple[float, ...]) -> None:
        c = self.cmds
        shared = f"{spec.stem}Slide"
        suffix = f"{index}_{spec.side}"
        distance = self._name(shared + "Dist" + suffix)
        normalize = self._name(shared + "DistNormalize" + suffix)
        if not c.objExists(distance):
            start = c.createNode("transform", name=self._name(
                shared + "Start" + suffix), parent=parent, skipSelect=True)
            end = c.createNode("transform", name=self._name(
                shared + "End" + suffix), parent=parent, skipSelect=True)
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
            distance = c.createNode("distanceBetween", name=distance)
            c.connectAttr(end + ".translate", distance + ".point2")
            normalize = c.createNode("multiplyDivide", name=normalize)
            c.setAttr(normalize + ".operation", 2)
            c.connectAttr(distance + ".distance", normalize + ".input1X")
            baseline = float(c.getAttr(distance + ".distance"))
            if baseline < 1e-6:
                raise ValueError("Slider 初始距离为零：" + spec.profile)
            c.setAttr(normalize + ".input2X", baseline)
        prefix = f"{spec.stem}{spec.segment}Slide"
        reducer = c.createNode("multiplyDivide", name=self._name(
            prefix + "Reducer" + suffix))
        slide = c.createNode("multiplyDivide", name=self._name(
            prefix + "Multiply" + suffix))
        plus = c.createNode("plusMinusAverage", name=self._name(
            prefix + "PlusOffset" + suffix))
        c.connectAttr(reducer + ".outputX", slide + ".input1X")
        c.connectAttr(slider + ".slide", slide + ".input2X")
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
            axis = "Y" if index in (0, 2) else "Z"
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
        c = self.cmds
        leaf = spec.joint(index)
        offset = c.createNode("transform", name=self._name("FKOffset" + leaf),
                              parent=system, skipSelect=True)
        c.xform(offset, worldSpace=True,
                matrix=c.xform(slider, query=True, worldSpace=True,
                               matrix=True))
        extra = c.createNode("transform", name=self._name("FKExtra" + leaf),
                             parent=offset, skipSelect=True)
        bounds = c.exactWorldBoundingBox(self._name("skinCage"))
        height = max(bounds[4] - bounds[1], 0.001)
        control = create_adv_icon(
            c, name=self._name("FK" + leaf), parent=extra,
            template="Bend_icon", radius=0.01 * height,
            fallback_normal=(1.0, 0.0, 0.0))
        c.sets(control, add=self._name("ControlSet"))
        c.sets(extra, add=self._name("ControlSet"))
        c.parentConstraint(parent, offset, maintainOffset=True)
        fkx = c.createNode("transform", name=self._name("FKX" + leaf),
                           parent=control, skipSelect=True)
        c.parentConstraint(fkx, slider, maintainOffset=True)
        marker = c.createNode("transform", parent=slider, skipSelect=True)
        marker = c.parent(marker, spec.deform_joint)[0]
        local = c.getAttr(marker + ".translate")[0]
        c.delete(marker)
        driver = self._name("FK" + self._leaf(spec.deform_joint))
        rotate = ("rotateZ" if spec.bend_axis or index in (0, 2)
                  else "rotateY")
        axis = "translateX" if spec.segment != "middle" else (
            "translateY" if index in (0, 2) else "translateZ")
        rest = float(c.getAttr(control + "." + axis))
        c.setDrivenKeyframe(control + "." + axis,
                            currentDriver=driver + "." + rotate,
                            driverValue=0, value=rest)
        for alternate in (False, True):
            angle = -90 if index in (1, 2) else 90
            if alternate:
                angle *= -1
            if spec.segment == "end":
                angle *= -1
            displacement = (local[1] if index in (0, 2) else local[2]) / 4.0
            if alternate and spec.segment != "middle":
                displacement *= -1
            if spec.segment != "middle" and index in (0, 1):
                displacement *= -1
            c.setDrivenKeyframe(control + "." + axis,
                                currentDriver=driver + "." + rotate,
                                driverValue=angle,
                                value=rest + displacement)
        curves = c.listConnections(control + "." + axis,
                                   source=True, destination=False,
                                   type="animCurve") or []
        if len(curves) != 1:
            raise RuntimeError("Slider 控制器 SDK 曲线创建失败：" + leaf)
        sdk_name = self._name("SDKFK" + leaf + "_" + axis)
        curve = c.rename(curves[0], sdk_name)
        if spec.bend_axis:
            c.setAttr(curve + ".preInfinity", 1)
            c.setAttr(curve + ".postInfinity", 1)
            c.keyTangent(curve, index=(0, 0),
                         inTangentType="spline", outTangentType="spline")
            c.keyTangent(curve, index=(2, 2),
                         inTangentType="spline", outTangentType="spline")
        self._record_slider_build_pose(leaf)
        c.setAttr(slider + ".segmentScaleCompensate", False)

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

    def _remove_slider_build_pose(self, leaf: str) -> None:
        c = self.cmds
        pose = self._name("buildPose")
        if not c.objExists(pose) or not c.attributeQuery(
                "udExtraAttr", node=pose, exists=True):
            return
        plug = pose + ".udExtraAttr"
        existing = c.getAttr(plug) or ""
        updated = existing
        for command in self._slider_pose_commands(leaf):
            updated = updated.replace(command, "")
        if updated != existing:
            c.setAttr(plug, updated, type="string")

    def create_slider(self, spec: SkinCageSlider, *,
                      include_controller: bool) -> None:
        c = self.cmds
        system = self._system("SlideSystem", self._name("MotionSystem"))
        scale = self._name("MainScaleMultiplyDivide")
        if c.objExists(scale) and not c.isConnected(
                scale + ".output", system + ".scale"):
            c.connectAttr(scale + ".output", system + ".scale",
                          force=True)
        group = self._system(f"{spec.stem}SlideSystem_{spec.side}", system)
        partial = self._name(f"{spec.stem}Partial_{spec.side}")
        first_parent = self._parent_joint(spec.deform_joint)
        parent = (first_parent if spec.segment == "start" else partial
                  if spec.segment == "middle" else spec.deform_joint)
        for index in spec.indices:
            cv, next_cv = self._slider_indices(spec, index)
            a, b = self._cv(spec, cv), self._cv(spec, next_cv)
            midpoint = tuple((a[axis] + b[axis]) / 2 for axis in range(3))
            joint = c.createNode("joint", name=self._name(spec.joint(index)),
                                 parent=parent, skipSelect=True)
            c.xform(joint, worldSpace=True, translation=midpoint)
            c.sets(joint, add=self._name("DeformSet"))
            c.addAttr(joint, longName="slide", attributeType="double",
                      defaultValue=1, keyable=True)
            if include_controller:
                self._controller_driver(spec, index, joint, parent, group)
            else:
                self._distance_driver(spec, index, joint, first_parent,
                                      group, midpoint)
            c.skinCluster(self._name("skinClusterSkinCage"), edit=True,
                          addInfluence=joint, weight=0, lockWeights=False)
            vertex = self._sample_vertex(spec, index, 0.833)
            c.skinPercent(self._name("skinClusterSkinCage"), vertex,
                          transformValue=[(joint, 1.0)])
        skin = self._name("skinClusterSkinCage")
        if len(spec.indices) == 4:
            for index in spec.indices:
                vertex = self._sample_vertex(spec, index, 0.833)
                current = self._name(spec.joint(index))
                previous = self._name(spec.joint((index - 1) % 4))
                c.skinPercent(skin, vertex, transformValue=[
                    (current, 0.5), (previous, 0.5)])
        else:
            extra = ((2, 1), (4, 3)) if spec.indices == (1, 3) else (
                (1, 0), (3, 2))
            for cv, index in extra:
                flipped = (2, 3, 0, 1, 2)[cv] if spec.side == "L" else cv
                vertex = self._closest_vertex(self._cv(spec, flipped))
                c.skinPercent(skin, vertex, transformValue=[
                    (self._name(spec.joint(index)), 1.0)])
        if include_controller:
            main = self._name("Main")
            if not c.attributeQuery("slideSysVis", node=main, exists=True):
                c.addAttr(main, longName="slideSysVis",
                          attributeType="bool", defaultValue=True,
                          keyable=True)
            if not c.isConnected(main + ".slideSysVis", system + ".visibility"):
                c.connectAttr(main + ".slideSysVis", system + ".visibility",
                              force=True)

    def delete_slider(self, spec: SkinCageSlider) -> None:
        c = self.cmds
        skin = self._name("skinClusterSkinCage")
        center = self._profile_center(spec)
        for index in range(4):
            point = self._cv(spec, index)
            sample = tuple(center[axis] + 0.832 * (
                point[axis] - center[axis]) for axis in range(3))
            vertex = self._closest_vertex(sample)
            weights = ([(spec.deform_joint, 0.5),
                        (spec.restore_joint, 0.5)]
                       if spec.segment == "middle" else
                       [(spec.restore_joint, 1.0)])
            c.skinPercent(skin, vertex, transformValue=weights)
        for index in spec.indices:
            leaf = spec.joint(index)
            joint = self._name(leaf)
            if c.objExists(joint):
                influences = c.skinCluster(skin, query=True,
                                           influence=True) or []
                if any(self._leaf(value) == leaf for value in influences):
                    c.skinCluster(skin, edit=True, removeInfluence=joint)
                c.delete(joint)
            control = self._name("FKOffset" + leaf)
            if c.objExists(control):
                self._remove_slider_build_pose(leaf)
                c.delete(control)
            sdk = self._name("SDKFK" + leaf + "_" + (
                "translateX" if spec.segment != "middle" else
                "translateY" if index in (0, 2) else "translateZ"))
            if c.objExists(sdk):
                c.delete(sdk)
            prefix = f"{spec.stem}{spec.segment}Slide"
            suffix = f"{index}_{spec.side}"
            for part in ("Reducer", "Multiply", "PlusOffset", "MinusOne",
                         "Reverse", "Absolutor", "TimesMinusOne"):
                node = self._name(prefix + part + suffix)
                if c.objExists(node):
                    c.delete(node)
            if not any(c.objExists(self._name(
                    f"{spec.stem}{segment}Slider{index}_{spec.side}"))
                    for segment in ("start", "middle", "end")):
                shared = f"{spec.stem}Slide"
                for part in ("Start", "End", "Dist", "DistNormalize"):
                    node = self._name(shared + part + suffix)
                    if c.objExists(node):
                        c.delete(node)
        group = self._name(f"{spec.stem}SlideSystem_{spec.side}")
        if c.objExists(group) and not c.listRelatives(group, children=True):
            c.delete(group)

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
            elif (any(c.objExists(node) for node in control_names)
                  or c.objExists(sdk)
                  or any(c.objExists(node) for node in distance_nodes)
                  or any(command in pose_script for command in
                         self._slider_pose_commands(leaf))):
                return False
        return True
