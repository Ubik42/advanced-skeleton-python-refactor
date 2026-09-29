"""Maya implementation of the original SkinCage copy/delete/reuse actions."""
from __future__ import annotations

from contextlib import contextmanager

from adv_py.core.skin_cage import (
    SKIN_CAGE_NODES, SkinCageBuildPlan, SkinCageCopyTarget,
)


class MayaSkinCageHost:
    def __init__(self, namespace: str = "") -> None:
        from maya import cmds
        self.cmds = cmds
        self.namespace = namespace.strip(":")
        self._source_skin = ""
        self._source_mesh = ""
        self._influences: tuple[str, ...] = ()
        self._selection: tuple[str, ...] = ()

    def _name(self, leaf: str) -> str:
        return self.namespace + ":" + leaf if self.namespace else leaf

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            c.undoInfo(closeChunk=True)
            c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)

    def capture_build_input(self):
        c = self.cmds
        system = self._name("DeformationSystem")
        if not c.objExists(system):
            raise ValueError("当前角色没有 DeformationSystem")
        roots = c.listRelatives(system, children=True, type="joint",
                                fullPath=True) or []
        if len(roots) != 1:
            raise ValueError("DeformationSystem 应有唯一的根关节")
        children = {}
        positions = {}
        pending = [roots[0]]
        while pending:
            joint = pending.pop()
            kids = tuple(c.listRelatives(joint, children=True,
                                         type="joint", fullPath=True) or ())
            children[joint] = kids
            positions[joint] = tuple(c.xform(
                joint, query=True, worldSpace=True, translation=True))
            pending.extend(kids)
        return roots[0], children, positions

    def preflight_build(self, plan: SkinCageBuildPlan) -> None:
        c = self.cmds
        if len(plan.influences) < 2:
            raise ValueError("至少需要两个变形关节创建 SkinCage")
        geometry = self._name("Geometry")
        if not c.objExists(geometry):
            raise ValueError("当前角色没有 Geometry 组")
        occupied = [self._name(leaf) for leaf in SKIN_CAGE_NODES
                    if c.objExists(self._name(leaf))]
        if occupied:
            raise ValueError("SkinCage 已存在或有残留节点，请先删除：" +
                             ", ".join(occupied))

    def _profile(self, joint: str, suffix: str, radius: float,
                 parent: str, layer: str,
                 anchors: tuple[str, ...] = ()) -> str:
        c = self.cmds
        leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        tail = ("_twistProfile" + suffix[5:] if suffix.startswith("twist")
                else "_" + suffix + "Profile")
        hidden_tail = tail.replace("Profile", "Curve")
        name = self._name(leaf + tail)
        profile = c.curve(name=name, degree=1, point=[
            (0, -1, 1), (0, 1, 1), (0, 1, -1),
            (0, -1, -1), (0, -1, 1)])
        c.parent(profile, parent)
        c.xform(profile, worldSpace=True, matrix=c.xform(
            joint, query=True, worldSpace=True, matrix=True))
        fit_name = self._name(leaf.rsplit("_", 1)[0])
        fat = float(c.getAttr(joint + ".fat")) if c.objExists(
            joint + ".fat") else 1.0
        front = float(c.getAttr(joint + ".fatFront")) if c.objExists(
            joint + ".fatFront") else 1.0
        width = float(c.getAttr(joint + ".fatWidth")) if c.objExists(
            joint + ".fatWidth") else 1.0
        if c.objExists(fit_name + ".fat"):
            fat = float(c.getAttr(fit_name + ".fat"))
            front = float(c.getAttr(fit_name + ".fatFront")) if c.objExists(
                fit_name + ".fatFront") else front
            width = float(c.getAttr(fit_name + ".fatWidth")) if c.objExists(
                fit_name + ".fatWidth") else width
        c.setAttr(profile + ".scaleY", radius * 1.2 * fat * front)
        c.setAttr(profile + ".scaleZ", radius * 1.2 * fat * width)
        c.setAttr(profile + ".scaleX", radius * 1.2)
        if anchors:
            constraints = c.pointConstraint(
                *anchors, profile, maintainOffset=False) or []
            if len(anchors) == 2 and constraints:
                aliases = c.pointConstraint(constraints[0], query=True,
                                            weightAliasList=True) or []
                if len(aliases) == 2:
                    c.setAttr(constraints[0] + "." + aliases[0], 0.75)
                    c.setAttr(constraints[0] + "." + aliases[1], 0.25)
            c.orientConstraint(joint, profile, maintainOffset=True)
        else:
            c.parentConstraint(joint, profile, maintainOffset=True)
        hidden = c.duplicate(profile,
                             name=self._name(leaf + hidden_tail),
                             parentOnly=False, returnRootsOnly=True)[0]
        for constraint in c.listRelatives(hidden, children=True,
                                          type="constraint") or ():
            c.delete(constraint)
        c.parent(hidden, profile)
        c.setAttr(hidden + ".visibility", 0)
        c.sets(profile, add=self._name("SkinCageCurvesSet"))
        c.editDisplayLayerMembers(layer, profile, noRecurse=True)
        return profile

    def _loft_chain(self, profiles: list[str], leaf: str,
                    nurbs_group: str, mesh_group: str) -> tuple[str, str]:
        c = self.cmds
        if len(profiles) < 2:
            raise ValueError("SkinCage 链需要至少两个截面：" + leaf)
        surface = c.loft(*profiles, name=self._name(leaf + "_surface"),
                         constructionHistory=True, uniform=True,
                         close=False, autoReverse=True, degree=1,
                         sectionSpans=1)[0]
        c.parent(surface, nurbs_group)
        mesh = c.nurbsToPoly(surface, name=self._name(leaf + "_poly"),
                             constructionHistory=True, format=3,
                             polygonType=0, uNumber=3, vNumber=3)[0]
        c.parent(mesh, mesh_group)
        copy = c.duplicate(mesh, name=self._name(leaf + "_poly_copy"),
                           upstreamNodes=False)[0]
        c.delete(copy, constructionHistory=True)
        return mesh, copy

    def _branch_profile(self, joint: str, suffix: str) -> str:
        c = self.cmds
        current = joint
        for _ in range(100):
            leaf = current.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            profile = self._name(leaf + "_" + suffix + "Profile")
            if c.objExists(profile):
                return profile
            middle = self._name(leaf + "_middleProfile")
            if c.objExists(middle):
                return middle
            relatives = (c.listRelatives(current, children=True,
                                         type="joint", fullPath=True) or ()
                         if suffix == "start" else
                         c.listRelatives(current, parent=True,
                                         type="joint", fullPath=True) or ())
            if not relatives:
                break
            current = relatives[0]
        raise ValueError("SkinCage 分叉缺少截面曲线：" + joint)

    def _branch_panels(self, parent: str, child: str) -> str:
        """Connect the four corner spans of a side branch to its parent ring."""
        c = self.cmds
        parent_curve = self._branch_profile(parent, "end")
        child_curve = self._branch_profile(child, "start")
        parent_points = [c.xform(f"{parent_curve}.cv[{i}]", query=True,
                                 worldSpace=True, translation=True)
                         for i in range(4)]
        child_points = [c.xform(f"{child_curve}.cv[{i}]", query=True,
                                worldSpace=True, translation=True)
                        for i in range(4)]
        parent_leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        child_leaf = child.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        base = self._name(parent_leaf + "_" + child_leaf + "_branch")
        facets = []
        for index in range(4):
            next_index = (index + 1) % 4
            points = [parent_points[index], parent_points[next_index],
                      child_points[next_index], child_points[index]]
            facets.append(c.polyCreateFacet(
                point=points, constructionHistory=False,
                name=base + "Face" + str(index))[0])
        bridge = c.polyUnite(facets, constructionHistory=False,
                             name=base)[0]
        c.polyMergeVertex(bridge, distance=0.0001,
                          constructionHistory=False)
        return bridge

    def _weight_tweaks(self, cage: str, skin: str) -> None:
        """Match the original Chest_M parent blend at its profile corners."""
        c = self.cmds
        chest = self._name("Chest_M")
        curve = self._name("Chest_M_middleProfile")
        if not c.objExists(chest) or not c.objExists(curve):
            return
        parent = c.listRelatives(chest, parent=True, type="joint",
                                 fullPath=True) or []
        if not parent:
            return
        influences = c.ls(c.skinCluster(skin, query=True,
                                        influence=True) or [], long=True) or []
        if parent[0] not in influences:
            c.skinCluster(skin, edit=True, addInfluence=parent[0],
                          weight=0.0, lockWeights=False)
        shape = (c.listRelatives(cage, shapes=True,
                                 noIntermediate=True, type="mesh",
                                 fullPath=True) or [])[0]
        sampler = c.createNode("closestPointOnMesh",
                                name=self._name("skinCageClosestSampler"))
        try:
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh",
                          force=True)
            for index in range(5):
                point = c.xform(f"{curve}.cv[{index}]", query=True,
                                worldSpace=True, translation=True)
                c.setAttr(sampler + ".inPosition", *point,
                          type="double3")
                vertex = int(c.getAttr(sampler + ".closestVertexIndex"))
                c.skinPercent(skin, f"{cage}.vtx[{vertex}]",
                              transformValue=[(parent[0], 0.5)],
                              normalize=True)
        finally:
            c.delete(sampler)

    def create_cage(self, plan: SkinCageBuildPlan) -> None:
        from maya import mel

        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        geometry = self._name("Geometry")
        groups = {}
        for leaf in ("Cages", "MeshGeometry", "MeshCurves", "NurbsGeometry"):
            groups[leaf] = c.group(empty=True, name=self._name(leaf),
                                   parent=geometry)
        c.setAttr(groups["NurbsGeometry"] + ".visibility", 0)
        c.setAttr(groups["MeshGeometry"] + ".overrideEnabled", 1)
        c.sets(empty=True, name=self._name("SkinCageCurvesSet"))
        if c.objExists(self._name("Sets")):
            c.sets(self._name("SkinCageCurvesSet"), add=self._name("Sets"))
        for leaf, color, visible in (("SkinCage", 0, True),
                                     ("SkinCurves1", 14, True),
                                     ("SkinCurves2", 13, False)):
            layer = c.createDisplayLayer(empty=True, name=self._name(leaf))
            c.setAttr(layer + ".visibility", visible)
            if color:
                c.setAttr(layer + ".color", color)
            if leaf == "SkinCage":
                c.setAttr(layer + ".displayType", 2)
        ys = [c.xform(j, query=True, worldSpace=True, translation=True)[1]
              for j in plan.influences]
        height = max(max(ys) - min(ys), 1.0)
        pieces = []
        copies = []
        chain_influences = []
        for chain in plan.chains:
            leaf = chain.joints[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            profiles = []
            influences = list(chain.joints)
            for index, joint in enumerate(chain.joints):
                joint_leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                divisor = (140 if "Finger" in joint_leaf else 80
                           if "Wrist" in joint_leaf else 60
                           if "Elbow" in joint_leaf else 15
                           if joint_leaf.startswith(("Root", "Spine", "Chest"))
                           else 40)
                radius = height / divisor
                if (joint != plan.root and
                        (index == 0 or not chain.parts[index - 1])):
                    previous = (chain.joints[index - 1] if index else
                                (c.listRelatives(joint, parent=True,
                                                 type="joint",
                                                 fullPath=True) or [joint])[0])
                    profiles.append(self._profile(
                        joint, "start", radius, groups["MeshCurves"],
                        self._name("SkinCurves2"),
                        (joint, previous)))
                profiles.append(self._profile(
                    joint, "middle", radius, groups["MeshCurves"],
                    self._name("SkinCurves1")))
                if index < len(chain.joints) - 1:
                    if not chain.parts[index]:
                        profiles.append(self._profile(
                            joint, "end", radius,
                            groups["MeshCurves"], self._name("SkinCurves2"),
                            (joint, chain.joints[index + 1])))
                    for part_number, part in enumerate(chain.parts[index], 1):
                        profiles.append(self._profile(
                            joint, "twist" + str(part_number), radius,
                            groups["MeshCurves"],
                            self._name("SkinCurves2"), (part,)))
                        influences.append(part)
            if len(profiles) == 1:
                end = self._profile(
                    chain.joints[0], "end", height / 40,
                    groups["MeshCurves"], self._name("SkinCurves2"))
                c.move(-height / 250, 0, 0, end + ".cv[0:4]",
                       relative=True, objectSpace=True)
                profiles.append(end)
            mesh, copy = self._loft_chain(
                profiles, leaf, groups["NurbsGeometry"],
                groups["MeshGeometry"])
            skin = c.skinCluster(influences, mesh, toSelectedBones=True,
                                 maximumInfluences=3, dropoffRate=4)[0]
            chain_influences.extend(c.skinCluster(
                skin, query=True, influence=True) or ())
            pieces.append(mesh)
            copies.append(copy)
        if not pieces:
            raise ValueError("变形系统没有可生成笼体的关节链")
        for branch in plan.branches:
            copies.append(self._branch_panels(branch.parent, branch.child))
        if len(copies) == 1:
            cage = c.rename(copies[0], self._name("skinCage"))
        else:
            cage = c.polyUnite(copies, constructionHistory=False,
                               name=self._name("skinCage"))[0]
        c.polyMergeVertex(cage, distance=0.0001, constructionHistory=False)
        c.polyAutoProjection(cage, constructionHistory=False,
                             planes=6, percentageSpace=0.2)
        c.parent(cage, groups["Cages"])
        c.editDisplayLayerMembers(self._name("SkinCage"), cage,
                                  noRecurse=True)
        joints = tuple(dict.fromkeys(chain_influences))
        if not joints:
            raise ValueError("SkinCage 管体没有有效的蒙皮关节")
        cage_skin = c.skinCluster(
            list(joints), cage, toSelectedBones=True, maximumInfluences=3,
            dropoffRate=4, name=self._name("skinClusterSkinCage"))[0]
        c.select(pieces, replace=True)
        c.select(cage, add=True)
        c.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint",
                          influenceAssociation="closestJoint")
        self._weight_tweaks(cage, cage_skin)
        for mesh in pieces:
            skin = self._skin(mesh)
            if skin:
                c.delete(skin)
            c.setAttr(mesh + ".visibility", 0)
        old_wraps = set(node for node in c.listHistory(cage) or ()
                        if c.nodeType(node) == "wrap")
        c.select(cage, replace=True)
        c.select(pieces[0], add=True)
        mel.eval('doWrapArgList 7 {"1","0","1","2","0","1","1","0"}')
        new_wraps = [node for node in c.listHistory(cage) or ()
                     if c.nodeType(node) == "wrap" and node not in old_wraps]
        if len(new_wraps) != 1:
            raise RuntimeError("SkinCage Wrap 创建后未找到唯一变形器")
        wrap = c.rename(new_wraps[0], self._name("wrapSkinCage"))
        for mesh in pieces[1:]:
            c.select(cage, replace=True)
            c.select(mesh, add=True)
            mel.eval("AddWrapInfluence")
        c.reorderDeformers(cage_skin, wrap, cage)
        c.select(selection, replace=True) if selection else c.select(clear=True)

    def capture_build(self, plan: SkinCageBuildPlan) -> bool:
        c = self.cmds
        return (all(c.objExists(self._name(leaf)) for leaf in (
            "Cages", "MeshGeometry", "MeshCurves", "NurbsGeometry",
            "SkinCageCurvesSet", "skinCage", "skinClusterSkinCage"))
            and self._skin(self._name("skinCage")) ==
            self._name("skinClusterSkinCage")
            and bool(c.listRelatives(self._name("MeshCurves"),
                                     allDescendents=True,
                                     type="nurbsCurve")))

    def _skin(self, mesh: str) -> str:
        c = self.cmds
        skins = [node for node in c.listHistory(mesh, pruneDagObjects=True) or ()
                 if c.nodeType(node) == "skinCluster"]
        if len(skins) > 1:
            raise ValueError("网格存在多个 skinCluster，请先明确变形链：" + mesh)
        return skins[0] if skins else ""

    def _mesh(self, node: str) -> str:
        c = self.cmds
        shape = node.split(".", 1)[0]
        if c.nodeType(shape) == "mesh":
            parents = c.listRelatives(shape, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("网格 Shape 没有唯一父节点：" + shape)
            return parents[0]
        if c.nodeType(shape) != "transform" or not c.listRelatives(
                shape, shapes=True, noIntermediate=True, type="mesh"):
            raise ValueError("选择项不是多边形网格：" + node)
        return (c.ls(shape, long=True) or [shape])[0]

    def capture_copy_input(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        c = self.cmds
        self._selection = tuple(c.ls(selection=True, flatten=True, long=True) or ())
        if not self._selection:
            raise ValueError("请选择要复制 SkinCage 权重的网格或顶点")
        components = tuple(item for item in self._selection if "." in item)
        if components and len(components) != len(self._selection):
            raise ValueError("请只选择网格对象，或只选择同一网格的顶点")
        if components and any(".vtx[" not in item for item in components):
            raise ValueError("组件复制目前只接受网格顶点")
        meshes = tuple(dict.fromkeys(self._mesh(item) for item in self._selection))
        return meshes, components

    def preflight_copy(self, targets: tuple[SkinCageCopyTarget, ...]) -> None:
        c = self.cmds
        self._source_mesh = self._name("skinCage")
        self._source_skin = self._name("skinClusterSkinCage")
        if not c.objExists(self._source_mesh) or not c.objExists(self._source_skin):
            raise ValueError("当前角色没有完整 SkinCage；需先创建笼体")
        if self._skin(self._source_mesh) != self._source_skin:
            raise ValueError("SkinCage 的蒙皮连接与原版结构不一致")
        self._influences = tuple(c.skinCluster(
            self._source_skin, query=True, influence=True) or ())
        if not self._influences:
            raise ValueError("SkinCage 蒙皮没有变形关节")
        for target in targets:
            if target.mesh == (c.ls(self._source_mesh, long=True) or [""])[0]:
                raise ValueError("不能把 SkinCage 权重复制回笼体本身")
            self._skin(target.mesh)

    def copy_weights(self, target: SkinCageCopyTarget) -> None:
        c = self.cmds
        skin = self._skin(target.mesh)
        if skin:
            current = set(c.skinCluster(skin, query=True, influence=True) or ())
            for joint in self._influences:
                if joint not in current:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  weight=0.0, lockWeights=False)
        else:
            skin = c.skinCluster(list(self._influences), target.mesh,
                                 toSelectedBones=True, maximumInfluences=3,
                                 dropoffRate=4.0)[0]
        try:
            c.select(self._source_mesh, replace=True)
            c.select(list(target.components) if target.components else
                     target.mesh, add=True)
            c.copySkinWeights(noMirror=True,
                              surfaceAssociation="closestPoint",
                              influenceAssociation="closestJoint")
            c.setAttr(skin + ".skinningMethod",
                      c.getAttr(self._source_skin + ".skinningMethod"))
            c.skinCluster(skin, edit=True, removeUnusedInfluence=True)
        finally:
            c.select(list(self._selection), replace=True)

    def capture_copy(self, target: SkinCageCopyTarget) -> bool:
        return bool(self._skin(target.mesh))

    def delete_cage(self) -> tuple[str, ...]:
        c = self.cmds
        existing = tuple(self._name(leaf) for leaf in SKIN_CAGE_NODES
                         if c.objExists(self._name(leaf)))
        if existing:
            c.delete(list(existing))
        if any(c.objExists(node) for node in existing):
            raise RuntimeError("SkinCage 删除后仍有残留节点")
        return existing

    def print_reuse_commands(self, *, transforms: bool = True,
                             shapes: bool = True, catch: bool = False) -> int:
        c = self.cmds
        root = self._name("MeshCurves")
        if not c.objExists(root):
            raise ValueError("当前角色没有 MeshCurves")
        commands = []
        if transforms:
            for constraint in c.listRelatives(
                    root, allDescendents=True, type="constraint",
                    fullPath=True) or ():
                for attr in c.listAttr(constraint, userDefined=True) or ():
                    value = c.getAttr(constraint + "." + attr)
                    if isinstance(value, (int, float)):
                        commands.append(f"setAttr {constraint}.{attr} {value}")
        for curve in c.listRelatives(root, allDescendents=True,
                                     type="transform", fullPath=True) or ():
            shape = c.listRelatives(curve, shapes=True,
                                    noIntermediate=True, type="nurbsCurve") or []
            if not shape or not c.getAttr(curve + ".visibility"):
                continue
            if transforms:
                pos = c.xform(curve, query=True, objectSpace=True,
                              translation=True)
                rot = c.xform(curve, query=True, objectSpace=True,
                              rotation=True)
                scale = c.xform(curve, query=True, objectSpace=True,
                                scale=True)
                commands.append("xform -os -t {} {} {} -ro {} {} {} -s {} {} {} {}".format(
                    *pos, *rot, *scale, curve))
            if shapes:
                count = int(c.getAttr(shape[0] + ".spans")) + int(
                    c.getAttr(shape[0] + ".degree"))
                for index in range(count):
                    xyz = c.getAttr(f"{shape[0]}.controlPoints[{index}]")[0]
                    if any(xyz):
                        commands.append("setAttr {}.controlPoints[{}] {} {} {}".format(
                            shape[0], index, *xyz))
        for command in commands:
            print("catch (`" + command + "`);" if catch
                  else command + ";")
        return len(commands)
