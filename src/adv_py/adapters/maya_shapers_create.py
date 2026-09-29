"""Maya implementation of the FK-loop branch of 6.925 Shapers Create."""
from __future__ import annotations

import json
from math import dist

from adv_py.core.shapers_create import ShapersFkLoop, ShapersFkLoopOptions
from .maya_shapers import _cmds, _python_shapers


class MayaShapersCreateHost:
    def __init__(self, namespace: str):
        self.cmds = _cmds()
        self.prefix = "" if namespace in ("", ":") else namespace.strip(":") + ":"

    def selected_fk_controls(self) -> tuple[str, ...]:
        return tuple(self.cmds.ls(selection=True, long=True,
                                  transforms=True) or ())

    def _one(self, name: str) -> str:
        matches = self.cmds.ls(name, long=True) or []
        if len(matches) != 1:
            raise ValueError("Shapers 节点不存在或名称不唯一：" + name)
        return matches[0]

    def _skin_cluster(self, mesh: str) -> str | None:
        clusters = [node for node in self.cmds.listHistory(mesh) or []
                    if self.cmds.nodeType(node) == "skinCluster"]
        if len(clusters) > 1:
            raise ValueError("Shapers Skin 网格存在多个 SkinCluster")
        return clusters[0] if clusters else None

    def preflight_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                           mesh: str) -> None:
        c = self.cmds
        mesh = self._one(mesh)
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("Shapers Skin 必须是单一多边形网格")
        loaded = [name for name in c.pluginInfo(query=True,
                                                 listPlugins=True) or []
                  if "shapersDeformer" in (
                      c.pluginInfo(name, query=True, dependNode=True) or [])]
        if len(loaded) != 1:
            raise ValueError("请先设置并加载 Shapers 插件")
        self._skin_cluster(mesh)
        for loop in loops:
            control = self._one(loop.control)
            joint = self._one(loop.deform_joint)
            if c.nodeType(joint) != "joint":
                raise ValueError("Shapers 对应变形关节不是 joint：" + joint)
            if (self.prefix and not control.rsplit("|", 1)[-1].startswith(self.prefix)):
                raise ValueError("FK 控制器不属于当前角色")
            for component, neutral in (("translate", (0, 0, 0)),
                                       ("rotate", (0, 0, 0)),
                                       ("scale", (1, 1, 1))):
                value = c.getAttr(control + "." + component)[0]
                if any(abs(float(a) - b) > 1e-4
                       for a, b in zip(value, neutral)):
                    raise ValueError("请先把 FK 控制器返回构建姿态：" + control)

    def _ensure_skin(self, mesh: str) -> str:
        c = self.cmds
        existing = self._skin_cluster(mesh)
        if existing:
            return existing
        joint = self.prefix + "ShapesJoint"
        if not c.objExists(joint):
            c.select(clear=True)
            joint = c.joint(name=joint)
        return c.skinCluster(joint, mesh, toSelectedBones=True,
                             maximumInfluences=3, dropoffRate=4,
                             removeUnusedInfluence=False)[0]

    def _controls_root(self) -> str:
        c = self.cmds
        root = self.prefix + "ShaperControls"
        if not c.objExists(root):
            motion = self.prefix + "MotionSystem"
            if c.objExists(motion):
                root = c.createNode("transform", name=root, parent=motion)
            else:
                root = c.createNode("transform", name=root)
        main = self.prefix + "Main"
        if not c.objExists(main):
            main = c.createNode("transform", name=main)
        for attribute, default in (("shaperVis", 1), ("shaperDisable", 0)):
            if not c.attributeQuery(attribute, node=main, exists=True):
                c.addAttr(main, longName=attribute, attributeType="bool",
                          defaultValue=default, keyable=False)
                c.setAttr(main + "." + attribute, channelBox=True)
        if not c.isConnected(main + ".shaperVis", root + ".visibility"):
            c.connectAttr(main + ".shaperVis", root + ".visibility",
                          force=True)
        return root

    def _unique_name(self, loop: ShapersFkLoop) -> tuple[str, str]:
        c = self.cmds
        for index in range(99):
            suffix = (chr(65 + index) if index < 26 else
                      chr(64 + index // 26) + chr(65 + index % 26))
            name = self.prefix + "Shaper" + loop.fit_stem + suffix + loop.side
            if not c.objExists(name):
                return name, suffix
        raise ValueError("Shapers 同名闭环数量超过 99")

    def _nearest_vertex(self, sampler: str, mesh: str,
                        position: tuple[float, ...]) -> tuple[int, tuple[float, ...]]:
        c = self.cmds
        c.setAttr(sampler + ".inPosition", *position, type="double3")
        index = int(c.getAttr(sampler + ".closestVertexIndex"))
        vertex = tuple(c.xform(f"{mesh}.vtx[{index}]", query=True,
                               worldSpace=True, translation=True))
        return index, vertex

    def _make_curve(self, loop: ShapersFkLoop, mesh: str,
                    options: ShapersFkLoopOptions, parent: str,
                    sampler: str) -> tuple[str, float, int]:
        c = self.cmds
        from maya import mel

        joint_pos = tuple(c.xform(loop.deform_joint, query=True,
                                  worldSpace=True, translation=True))
        control_pos = tuple(c.xform(loop.control + ".ep[0]", query=True,
                                    worldSpace=True, translation=True))
        radius = max(dist(joint_pos, control_pos) * 0.7, 1e-4)
        curve = c.circle(name=self.prefix + "AdvPy_ShaperTemp#",
                         center=(0, 0, 0), normal=(1, 0, 0),
                         sweep=360, radius=radius, degree=3,
                         sections=4, constructionHistory=False)[0]
        c.xform(curve, worldSpace=True,
                matrix=c.xform(loop.deform_joint, query=True,
                               worldSpace=True, matrix=True))
        for index in range(4):
            point = curve + f".ep[{index}]"
            locator = c.createNode("transform", name=self.prefix + "AdvPy_ShaperSnap#")
            try:
                c.xform(locator, worldSpace=True, translation=c.xform(
                    point, query=True, worldSpace=True, translation=True))
                constraint = c.geometryConstraint(mesh, locator)[0]
                c.delete(constraint)
                c.xform(point, worldSpace=True, translation=c.xform(
                    locator, query=True, worldSpace=True, translation=True))
            finally:
                c.delete(locator)
        c.rebuildCurve(curve, constructionHistory=False,
                       replaceOriginal=True, rebuildType=0,
                       endKnots=1, keepRange=0, keepControlPoints=False,
                       keepEndPoints=True, keepTangents=False,
                       spans=options.loop_controls, degree=3,
                       tolerance=0.01)
        c.select(curve, replace=True)
        mel.eval("nurbsCurveToBezier")
        curve_name = parent.rsplit("|", 1)[-1].replace(
            "Shaper", "ShaperCurve", 1)
        curve = c.rename(curve, curve_name)
        c.parent(curve, parent)
        c.setAttr(curve + ".displayCV", 1)
        c.setAttr(curve + ".overrideEnabled", 1)
        c.setAttr(curve + ".overrideColor", 16)
        c.setAttr(curve + ".overrideDisplayType", 2)
        shape = (c.listRelatives(curve, shapes=True, fullPath=True) or [])[0]
        spans = int(c.getAttr(shape + ".spans"))
        degree = int(c.getAttr(shape + ".degree"))
        return curve, radius, spans + degree - 1

    def _add_loop(self, loop: ShapersFkLoop, mesh: str,
                  options: ShapersFkLoopOptions, root: str,
                  sampler: str, skin: str) -> str:
        c = self.cmds
        group_name, letter = self._unique_name(loop)
        group = c.createNode("transform", name=group_name, parent=root)
        control_group = c.createNode(
            "transform", name=self.prefix + "ShaperControls" +
            loop.fit_stem + letter + loop.side, parent=group)
        for attribute, value in (("deformJoint", loop.deform_joint),
                                 ("skin", mesh)):
            c.addAttr(group, longName=attribute, dataType="string")
            c.setAttr(group + "." + attribute, value, type="string")
        c.addAttr(group, longName="loop", attributeType="bool",
                  defaultValue=True)
        curve, radius, count = self._make_curve(loop, mesh, options,
                                                group, sampler)
        if count < 9 or count % 3:
            raise RuntimeError("Shapers Bezier 闭环控制点数无效")
        positions = [tuple(c.xform(curve + f".cv[{index}]", query=True,
                                   worldSpace=True, translation=True))
                     for index in range(count)]
        vertices: list[int] = []
        for index, position in enumerate(positions):
            if index % 3:
                vertices.append(-1)
                continue
            vertex, snap = self._nearest_vertex(sampler, mesh, position)
            vertices.append(vertex)
            if options.snap_vertices:
                c.xform(curve + f".cv[{index}]", worldSpace=True,
                        translation=snap)
                positions[index] = snap
        os_curve = c.duplicate(curve, name=curve.replace(
            "ShaperCurve", "ShaperOSCurve", 1))[0]
        c.setAttr(os_curve + ".visibility", 0, lock=True)
        controls = []
        offsets = []
        for index, position in enumerate(positions):
            suffix = str(index) + loop.fit_stem + letter + loop.side
            name = self.prefix + "Shaper" + suffix
            control = c.sphere(name=name, pivot=(0, 0, 0),
                               axis=(0, 1, 0), radius=1, degree=3,
                               sections=8, spans=4,
                               constructionHistory=False)[0]
            size = radius / (10 if index % 3 == 0 else 20)
            c.scale(size, size, size, control + ".cv[*]", relative=True)
            if vertices[index] >= 0:
                c.addAttr(control, longName="vtxNr", attributeType="long",
                          defaultValue=vertices[index])
            attach = c.createNode("transform", name=self.prefix +
                                  "Shaper" + str(index) + "Attach" +
                                  loop.fit_stem + letter + loop.side,
                                  parent=control_group)
            offset = c.createNode("transform", name=self.prefix +
                                  "Shaper" + str(index) + "Offset" +
                                  loop.fit_stem + letter + loop.side,
                                  parent=attach)
            c.xform(offset, worldSpace=True, translation=position)
            c.parent(control, offset)
            if vertices[index] >= 0:
                weights = c.skinPercent(skin,
                                        f"{mesh}.vtx[{vertices[index]}]",
                                        query=True, value=True) or []
                influences = c.skinCluster(skin, query=True,
                                           influence=True) or []
                driver = influences[max(range(len(weights)),
                                        key=lambda n: weights[n])]
                c.parentConstraint(driver, attach, maintainOffset=True)
            dm = c.createNode("decomposeMatrix", name=self.prefix +
                              "Shaper" + str(index) + "DM" +
                              loop.fit_stem + letter + loop.side)
            c.connectAttr(control + ".worldMatrix[0]", dm + ".inputMatrix")
            controls.append((control, dm))
            offsets.append(offset)
            control_set = self.prefix + "ControlSet"
            if c.objExists(control_set):
                c.sets(control, add=control_set)
        for index, (control, dm) in enumerate(controls):
            if index % 3:
                anchor = index - 1 if index % 3 == 1 else (index + 1) % count
                c.parent(offsets[index], controls[anchor][0])
            c.connectAttr(dm + ".outputTranslate",
                          curve + f".cv[{index}]", force=True)
        c.connectAttr(controls[0][1] + ".outputTranslate",
                      curve + f".cv[{count}]", force=True)
        c.xform(curve, worldSpace=True, translation=(0, 0, 0),
                rotation=(0, 0, 0))
        for index, (control, _) in enumerate(controls):
            anchor = index if index % 3 == 0 else (
                index - 1 if index % 3 == 1 else (index + 1) % count)
            mm = c.createNode("multMatrix", name=self.prefix +
                              "Shaper" + str(index) + "MM" +
                              loop.fit_stem + letter + loop.side)
            c.connectAttr(control + ".worldMatrix[0]", mm + ".matrixIn[0]")
            c.connectAttr(offsets[anchor] + ".worldInverseMatrix[0]",
                          mm + ".matrixIn[1]")
            c.setAttr(mm + ".matrixIn[2]", *c.getAttr(offsets[anchor] +
                                                        ".matrix")[0], type="matrix")
            dm2 = c.createNode("decomposeMatrix", name=self.prefix +
                               "Shaper" + str(index) + "DM2" +
                               loop.fit_stem + letter + loop.side)
            c.connectAttr(mm + ".matrixSum", dm2 + ".inputMatrix")
            c.connectAttr(dm2 + ".outputTranslate",
                          os_curve + f".cv[{index}]", force=True)
            if index == 0:
                c.connectAttr(dm2 + ".outputTranslate",
                              os_curve + f".cv[{count}]", force=True)
        pose = self.prefix + "buildPose"
        if c.objExists(pose + ".advPyPoseData"):
            plug = pose + ".advPyPoseData"
            rows = json.loads(c.getAttr(plug) or "[]")
            for control, _ in controls:
                for attribute, value in (("translateX", 0),
                                         ("translateY", 0),
                                         ("translateZ", 0),
                                         ("rotateX", 0),
                                         ("rotateY", 0),
                                         ("rotateZ", 0),
                                         ("scaleX", 1),
                                         ("scaleY", 1),
                                         ("scaleZ", 1)):
                    rows.append([control, attribute, float(value)])
            c.setAttr(plug, json.dumps(rows, separators=(",", ":")),
                      type="string")
        elif c.objExists(pose):
            plug = pose + ".udExtraAttr"
            if not c.objExists(plug):
                c.addAttr(pose, longName="udExtraAttr", dataType="string")
            script = c.getAttr(plug) or ""
            script += "".join(
                'xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 "' +
                control + '";' for control, _ in controls)
            c.setAttr(plug, script, type="string")
        return os_curve

    def create_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                        mesh: str, options: ShapersFkLoopOptions) -> int:
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        c.undoInfo(openChunk=True, chunkName="创建 Shapers FK 闭环")
        failed = False
        try:
            mesh = self._one(mesh)
            skin = self._ensure_skin(mesh)
            root = self._controls_root()
            sampler = c.createNode("closestPointOnMesh",
                                   name=self.prefix + "AdvPy_ShaperSampler#")
            shape = (c.listRelatives(mesh, shapes=True,
                                     noIntermediate=True, fullPath=True,
                                     type="mesh") or [])[0]
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh")
            curves = [self._add_loop(loop, mesh, options, root, sampler, skin)
                      for loop in loops]
            c.delete(sampler)
            existing = [node for node in c.listHistory(mesh) or []
                        if c.nodeType(node) == "shapersDeformer"]
            c.select([mesh, *curves], replace=True)
            native = getattr(c, "shapersAddCurve" if existing else
                             "shapersCreate", None)
            if native:
                native()
            else:
                module = _python_shapers(c)
                (module.add_curve if existing else module.create)()
            deformers = [node for node in c.listHistory(mesh) or []
                         if c.nodeType(node) == "shapersDeformer"]
            if not deformers:
                raise RuntimeError("Shapers 插件未创建变形器")
            for curve in curves:
                connected = c.listConnections(
                    curve + ".worldSpace[0]", source=False,
                    destination=True, type="shapersDeformer") or []
                if not set(connected).intersection(deformers):
                    raise RuntimeError("Shapers 插件未绑定控制曲线：" + curve)
            main = self.prefix + "Main"
            for node in deformers:
                if not c.isConnected(main + ".shaperDisable",
                                     node + ".nodeState"):
                    c.connectAttr(main + ".shaperDisable",
                                  node + ".nodeState", force=True)
            return len(curves)
        except Exception:
            failed = True
            raise
        finally:
            c.undoInfo(closeChunk=True)
            if failed:
                c.undo()
            else:
                existing = [node for node in selection if c.objExists(node)]
                c.select(existing, replace=True) if existing else c.select(clear=True)
