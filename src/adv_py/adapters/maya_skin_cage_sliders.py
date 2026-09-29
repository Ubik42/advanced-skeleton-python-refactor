"""Maya graph for AdvancedSkeleton 6.925 SkinCage Sliders."""
from __future__ import annotations

from adv_py.core.skin_cage_sliders import SkinCageSlider
from .maya_adv_icons import create_adv_icon
from .maya_skin_cage import MayaSkinCageHost


class MayaSkinCageSliderHost(MayaSkinCageHost):
    def _leaf(self, node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _parent_joint(self, joint: str) -> str:
        parents = self.cmds.listRelatives(joint, parent=True, type="joint",
                                          fullPath=True) or []
        if not parents:
            raise ValueError("变形关节缺少父关节：" + joint)
        return parents[0]

    def capture_slider_rows(self) -> tuple[tuple[str, str, str, int], ...]:
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
            if parts[2].startswith("twistProfile") and parts[2] != "twistProfile1":
                raise ValueError("多段 Twist 截面需先确定末端关节映射：" + leaf)
            joint = self._name(parts[0] + "_" + parts[1])
            if not c.objExists(joint) or c.nodeType(joint) != "joint":
                raise ValueError("截面缺少对应变形关节：" + leaf)
            if parts[2].startswith("endProfile"):
                restore = joint
            elif parts[2] == "twistProfile1":
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
            rows.append((profile, joint, restore, bend_axis))
        return tuple(rows)

    def preflight_sliders(self, plan: tuple[SkinCageSlider, ...], *,
                          creating: bool, include_controller: bool) -> None:
        c = self.cmds
        for leaf in ("skinCage", "skinClusterSkinCage", "MotionSystem",
                     "DeformSet"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SkinCage Sliders 缺少原版节点：" + leaf)
        if include_controller:
            for leaf in ("ControlSet", "Main"):
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
                         slider: str, parent: str) -> None:
        c = self.cmds
        prefix = f"{spec.stem}{spec.segment}Slide"
        suffix = f"{index}_{spec.side}"
        start = c.createNode("decomposeMatrix", name=self._name(
            prefix + "StartMatrix" + suffix))
        end = c.createNode("decomposeMatrix", name=self._name(
            prefix + "EndMatrix" + suffix))
        distance = c.createNode("distanceBetween", name=self._name(
            prefix + "Dist" + suffix))
        c.connectAttr(parent + ".worldMatrix[0]",
                      start + ".inputMatrix")
        c.connectAttr(spec.deform_joint + ".worldMatrix[0]",
                      end + ".inputMatrix")
        c.connectAttr(start + ".outputTranslate", distance + ".point1")
        c.connectAttr(end + ".outputTranslate", distance + ".point2")
        baseline = float(c.getAttr(distance + ".distance"))
        if baseline < 1e-6:
            raise ValueError("Slider 驱动距离为零：" + spec.profile)
        normalize = c.createNode("multiplyDivide", name=self._name(
            prefix + "Normalize" + suffix))
        c.setAttr(normalize + ".operation", 2)
        c.connectAttr(distance + ".distance", normalize + ".input1X")
        c.setAttr(normalize + ".input2X", baseline)
        offset = c.createNode("plusMinusAverage", name=self._name(
            prefix + "Offset" + suffix))
        c.setAttr(offset + ".operation", 2)
        c.connectAttr(normalize + ".outputX", offset + ".input1D[0]")
        c.setAttr(offset + ".input1D[1]", 1)
        gain = c.createNode("multiplyDivide", name=self._name(
            prefix + "Gain" + suffix))
        c.connectAttr(offset + ".output1D", gain + ".input1X")
        c.connectAttr(slider + ".slide", gain + ".input2X")
        axis = "X" if spec.segment != "middle" else (
            "Y" if index in (0, 2) else "Z")
        value = float(c.getAttr(slider + ".translate" + axis))
        if spec.segment == "start":
            value *= -1
        scale = c.createNode("multiplyDivide", name=self._name(
            prefix + "Scale" + suffix))
        c.connectAttr(gain + ".outputX", scale + ".input1X")
        c.setAttr(scale + ".input2X", value)
        # The original graph uses per-corner distance normalization. Preserve
        # the rest-pose offset while the ratio drives displacement.
        final = c.createNode("plusMinusAverage", name=self._name(
            prefix + "PlusOffset" + suffix))
        c.setAttr(final + ".input1D[0]", float(c.getAttr(
            slider + ".translate" + axis)))
        c.connectAttr(scale + ".outputX", final + ".input1D[1]")
        c.connectAttr(final + ".output1D", slider + ".translate" + axis)

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
        c.parentConstraint(control, slider, maintainOffset=True)
        driver = self._name("FK" + self._leaf(spec.deform_joint))
        rotate = "rotateZ" if index in (0, 2) else "rotateY"
        axis = "translateX" if spec.segment != "middle" else (
            "translateY" if index in (0, 2) else "translateZ")
        rest = float(c.getAttr(control + "." + axis))
        span = abs(float(c.getAttr(slider + ".translateY")) if index in (0, 2)
                   else float(c.getAttr(slider + ".translateZ"))) / 4.0
        for angle, displacement in ((-90, -span), (0, 0), (90, span)):
            c.setDrivenKeyframe(control + "." + axis,
                                currentDriver=driver + "." + rotate,
                                driverValue=angle,
                                value=rest + displacement)
        c.setAttr(slider + ".segmentScaleCompensate", False)

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
                self._distance_driver(spec, index, joint, first_parent)
            c.skinCluster(self._name("skinClusterSkinCage"), edit=True,
                          addInfluence=joint, weight=0, lockWeights=False)
            vertex = self._sample_vertex(spec, index, 0.833)
            c.skinPercent(self._name("skinClusterSkinCage"), vertex,
                          transformValue=[(joint, 1.0)])
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
                if joint in influences:
                    c.skinCluster(skin, edit=True, removeInfluence=joint)
                c.delete(joint)
            control = self._name("FKOffset" + leaf)
            if c.objExists(control):
                c.delete(control)
            prefix = f"{spec.stem}{spec.segment}Slide"
            suffix = f"{index}_{spec.side}"
            for part in ("StartMatrix", "EndMatrix", "Dist", "Normalize",
                         "Offset", "Gain", "Scale", "PlusOffset"):
                node = self._name(prefix + part + suffix)
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
        return all((c.objExists(self._name(spec.joint(index))) and
                    spec.joint(index) in influences) == present
                   for index in spec.indices)
