"""Maya implementation of the original SkinCage copy/delete/reuse actions."""
from __future__ import annotations

from contextlib import contextmanager

from adv_py.core.skin_cage import (
    SKIN_CAGE_NODES, SkinCageBranchLayout, SkinCageBuildPlan,
    SkinCageCopyTarget, SkinCageCurveDeletePlan,
    SkinCageGroinAdjustment,
    SkinCageGroinLocators, SkinCageMirrorPair, SkinCageProfileShape,
    SkinCageWidthInput,
    SkinCageWidthSpec, special_skin_cage_branch,
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
        self._mirror_state = {}
        self._groin_expected_pos = None

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
        face_set = self._name("FaceAllSet")
        while pending:
            joint = pending.pop()
            kids = tuple(c.listRelatives(joint, children=True,
                                         type="joint", fullPath=True) or ())
            if c.objExists(face_set):
                kids = tuple(child for child in kids
                             if not c.sets(child, isMember=face_set))
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

    def cage_exists(self) -> bool:
        c = self.cmds
        return c.objExists(self._name("MeshGeometry")) or c.objExists(
            self._name("skinCage"))

    def preflight_rebuild(self, plan: SkinCageBuildPlan) -> None:
        c = self.cmds
        for leaf in ("Geometry", "MeshGeometry", "MeshCurves",
                     "skinCage", "skinClusterSkinCage"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SkinCage 重建缺少原版节点：" + leaf)
        if len(plan.influences) < 2:
            raise ValueError("变形系统至少需要两个关节")

    def capture_profile_shapes(self) -> tuple[SkinCageProfileShape, ...]:
        c = self.cmds
        profiles = []
        for node in c.listRelatives(
                self._name("MeshCurves"), allDescendents=True,
                type="transform", fullPath=True) or ():
            leaf = node.rsplit("|", 1)[-1]
            if not leaf.endswith("Profile"):
                continue
            shape = c.listRelatives(node, shapes=True,
                                    noIntermediate=True,
                                    type="nurbsCurve") or []
            if len(shape) != 1:
                continue
            spans = int(c.getAttr(shape[0] + ".spans"))
            degree = int(c.getAttr(shape[0] + ".degree"))
            form = int(c.getAttr(shape[0] + ".form"))
            count = spans if form == 2 else spans + degree
            points = tuple(tuple(c.xform(
                f"{node}.cv[{index}]", query=True, worldSpace=True,
                translation=True)) for index in range(count))
            profiles.append(SkinCageProfileShape(leaf, points))
        return tuple(profiles)

    def restore_profile_shapes(
            self, profiles: tuple[SkinCageProfileShape, ...]) -> None:
        c = self.cmds
        restored = 0
        for profile in profiles:
            matches = c.ls(profile.name, long=True, type="transform") or []
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError("重建后的 SkinCage 截面名称不唯一：" +
                                 profile.name)
            node = matches[0]
            shape = c.listRelatives(node, shapes=True,
                                    noIntermediate=True,
                                    type="nurbsCurve") or []
            if len(shape) != 1:
                raise ValueError("重建后的 SkinCage 截面曲线无效：" +
                                 profile.name)
            count = int(c.getAttr(shape[0] + ".spans")) + int(
                c.getAttr(shape[0] + ".degree"))
            if count != len(profile.points):
                raise ValueError("SkinCage 重建前后截面控制点数不同：" +
                                 profile.name)
            for index, point in enumerate(profile.points):
                c.xform(f"{node}.cv[{index}]", worldSpace=True,
                        translation=point)
            restored += 1
        if not restored:
            raise RuntimeError("SkinCage 重建后没有可恢复的同名截面")

    def capture_restored_profiles(
            self, profiles: tuple[SkinCageProfileShape, ...]) -> bool:
        c = self.cmds
        count = 0
        for profile in profiles:
            matches = c.ls(profile.name, long=True, type="transform") or []
            if not matches:
                continue
            if len(matches) != 1:
                return False
            for index, expected in enumerate(profile.points):
                actual = c.xform(f"{matches[0]}.cv[{index}]",
                                 query=True, worldSpace=True,
                                 translation=True)
                if max(abs(actual[i] - expected[i]) for i in range(3)) > 1e-4:
                    return False
            count += 1
        return count > 0

    def capture_curve_delete_input(self) -> tuple[str, ...]:
        c = self.cmds
        leaves = ("SkinCurves1", "SkinCurves2", "MeshGeometry",
                  "MeshCurves", "NurbsGeometry")
        return tuple(leaf for leaf in leaves
                     if c.objExists(self._name(leaf)))

    def preflight_curve_delete(
            self, plan: SkinCageCurveDeletePlan) -> None:
        c = self.cmds
        cage = self._name("skinCage")
        skin = self._name("skinClusterSkinCage")
        if not c.objExists(cage) or not c.objExists(skin):
            raise ValueError("请先创建带蒙皮的 SkinCage")
        if self._skin(cage) != skin:
            raise ValueError("SkinCage 笼体没有原版 skinCluster 连接")
        if c.objExists(self._name("skinCageFrozenInput")):
            raise ValueError("SkinCage 已有冻结输入，请先检查旧曲线删除状态")

    def delete_curves(self, plan: SkinCageCurveDeletePlan) -> None:
        c = self.cmds
        cage = self._name("skinCage")
        skin = self._name("skinClusterSkinCage")
        envelope = c.getAttr(skin + ".envelope")
        c.setAttr(skin + ".envelope", 0)
        try:
            frozen = c.duplicate(
                cage, name=self._name("skinCageFrozenInput"),
                upstreamNodes=False)[0]
            c.delete(frozen, constructionHistory=True)
        finally:
            c.setAttr(skin + ".envelope", envelope)
        frozen_shape = (c.listRelatives(
            frozen, shapes=True, noIntermediate=True,
            type="mesh", fullPath=True) or [])[0]
        frozen_shape = c.parent(frozen_shape, cage, shape=True,
                                relative=True)[0]
        c.setAttr(frozen_shape + ".intermediateObject", 1)
        c.delete(frozen)
        wraps = tuple(node for node in c.listHistory(cage) or ()
                      if c.nodeType(node) == "wrap")
        if wraps:
            c.delete(wraps)
        input_shapes = c.listConnections(
            skin + ".input[0].inputGeometry", source=True,
            destination=False, shapes=True) or []
        input_shape = next((shape for shape in input_shapes
                            if c.nodeType(shape) == "mesh" and
                            (c.ls(shape, long=True) or [shape])[0] !=
                            frozen_shape), None)
        if input_shape is None:
            all_shapes = c.listRelatives(cage, shapes=True,
                                         type="mesh", fullPath=True) or []
            input_shape = next((shape for shape in all_shapes
                                if shape != frozen_shape and
                                c.getAttr(shape + ".intermediateObject")),
                               None)
        if input_shape is None:
            raise RuntimeError("SkinCage 缺少可冻结的蒙皮输入网格")
        c.connectAttr(frozen_shape + ".outMesh",
                      input_shape + ".inMesh", force=True)
        existing = [self._name(leaf) for leaf in plan.nodes
                    if c.objExists(self._name(leaf))]
        if existing:
            c.delete(existing)

    def capture_curves_deleted(
            self, plan: SkinCageCurveDeletePlan) -> bool:
        c = self.cmds
        cage = self._name("skinCage")
        skin = self._name("skinClusterSkinCage")
        shapes = c.listRelatives(cage, shapes=True, type="mesh",
                                 fullPath=True) or []
        return (all(not c.objExists(self._name(leaf))
                    for leaf in plan.nodes)
                and c.objExists(cage) and c.objExists(skin)
                and self._skin(cage) == skin
                and any("skinCageFrozenInput" in shape for shape in shapes))

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
            (0, -1, 1), (0, -1, -1), (0, 1, -1),
            (0, 1, 1), (0, -1, 1)])
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
            offset_name = self._name(
                leaf + ("_twistCurve" + suffix[5:] + "Offset"
                        if suffix.startswith("twist") else
                        "_" + suffix + "CurveOffset"))
            offset = c.group(empty=True, name=offset_name, parent=parent)
            c.xform(offset, worldSpace=True, matrix=c.xform(
                joint, query=True, worldSpace=True, matrix=True))
            c.parent(profile, offset)
            constraints = c.pointConstraint(
                *anchors, offset, maintainOffset=False) or []
            scale_constraints = c.scaleConstraint(
                *anchors, offset, maintainOffset=True) or []
            if len(anchors) == 2 and constraints:
                aliases = c.pointConstraint(constraints[0], query=True,
                                            weightAliasList=True) or []
                if len(aliases) == 2:
                    c.setAttr(constraints[0] + "." + aliases[0], 0.75)
                    c.setAttr(constraints[0] + "." + aliases[1], 0.25)
                if scale_constraints:
                    aliases = c.scaleConstraint(
                        scale_constraints[0], query=True,
                        weightAliasList=True) or []
                    if len(aliases) == 2:
                        c.setAttr(scale_constraints[0] + "." + aliases[0],
                                  0.75)
                        c.setAttr(scale_constraints[0] + "." + aliases[1],
                                  0.25)
            c.orientConstraint(joint, offset, maintainOffset=True)
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

    def _special_branch_panels(self, parent: str,
                               layout: SkinCageBranchLayout) -> str:
        c = self.cmds
        leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        base = self._name(leaf + "_branch")
        facets = []
        for index, face in enumerate(layout.faces):
            points = []
            for curve, cv in face:
                profile = self._name(curve + "Profile")
                if not c.objExists(profile):
                    raise ValueError("SkinCage 专用分叉缺少截面：" + profile)
                points.append(c.xform(f"{profile}.cv[{cv}]", query=True,
                                      worldSpace=True, translation=True))
            facet = c.polyCreateFacet(
                point=points, constructionHistory=False,
                name=base + "Face" + str(index))[0]
            if index in layout.reverse_faces:
                c.polyNormal(facet, normalMode=0, userNormalMode=0,
                             constructionHistory=False)
            facets.append(facet)
        bridge = c.polyUnite(facets, constructionHistory=False,
                             name=base)[0]
        c.polyMergeVertex(bridge, distance=0.0001,
                          constructionHistory=False)
        if leaf == "Wrist_L":
            c.polyNormal(bridge, normalMode=0, userNormalMode=0,
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

    def _profile_tweaks(self, plan: SkinCageBuildPlan) -> None:
        """Apply the ankle, toe and neck edits from asProfileTweaks."""
        c = self.cmds
        profiles = c.listRelatives(self._name("MeshCurves"),
                                   allDescendents=True, type="transform",
                                   fullPath=True) or []
        for profile in profiles:
            leaf = profile.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if leaf.startswith("Ankle") and leaf.endswith("_endProfile"):
                side = "_L" if "_L_" in leaf else "_R"
                fit = self._name(leaf.split("_", 1)[0])
                if not c.objExists(fit):
                    continue
                heel = next((joint for joint in (
                    c.listRelatives(fit, children=True, type="joint",
                                    fullPath=True) or ())
                    if "Heel" in joint.rsplit("|", 1)[-1]), None)
                if heel is None:
                    continue
                center = c.xform(profile, query=True, worldSpace=True,
                                 translation=True)
                heel_pos = c.xform(heel, query=True, worldSpace=True,
                                   translation=True)
                indices = (2, 3) if side == "_L" else (0, 1, 4)
                side_factor = -1 if side == "_L" else 1
                for index in indices:
                    cv = f"{profile}.cv[{index}]"
                    local_z = c.getAttr(cv)[0][2]
                    target = (heel_pos[0] * side_factor,
                              heel_pos[1], heel_pos[2])
                    c.xform(cv, worldSpace=True, translation=target)
                    c.setAttr(cv + ".zValue", local_z)
                    adjusted = c.xform(cv, query=True, worldSpace=True,
                                       translation=True)
                    c.xform(cv, worldSpace=True, translation=(
                        center[0] + (adjusted[0] - center[0]) * 1.2,
                        center[1] + (adjusted[1] - center[1]) * 1.2,
                        adjusted[2]))
            elif "Toes" in leaf and leaf.endswith("Profile"):
                center = c.xform(profile, query=True, worldSpace=True,
                                 translation=True)
                primary = (2, 3) if "_L_" in leaf else (0, 1, 4)
                opposite = (0, 1, 4) if "_L_" in leaf else (2, 3)
                for index in primary:
                    cv = f"{profile}.cv[{index}]"
                    pos = c.xform(cv, query=True, worldSpace=True,
                                  translation=True)
                    c.xform(cv, worldSpace=True, translation=(
                        pos[0], center[1] - 1.2 * center[1], pos[2]))
                if "_start" in leaf:
                    for index in opposite:
                        cv = f"{profile}.cv[{index}]"
                        pos = c.xform(cv, query=True, worldSpace=True,
                                      translation=True)
                        c.xform(cv, worldSpace=True, translation=(
                            pos[0], center[1] + (pos[1] - center[1]) * 0.5,
                            pos[2]))

        neck_start = self._name("Neck_M_startProfile")
        neck_middle = self._name("Neck_M_middleProfile")
        chest_middle = self._name("Chest_M_middleProfile")
        if not all(c.objExists(node) for node in (
                neck_start, neck_middle, chest_middle)):
            return
        chest_scale = c.getAttr(chest_middle + ".scale")[0]
        neck_scale = c.getAttr(neck_middle + ".scale")[0]
        for index in range(5):
            cv = f"{neck_middle}.cv[{index}]"
            c.setAttr(neck_middle + ".scale", *chest_scale,
                      type="double3")
            wide = c.xform(cv, query=True, worldSpace=True,
                           translation=True)
            c.setAttr(neck_middle + ".scale", *neck_scale,
                      type="double3")
            regular = c.xform(cv, query=True, worldSpace=True,
                              translation=True)
            c.xform(f"{neck_start}.cv[{index}]", worldSpace=True,
                    translation=(wide[0] * 1.1,
                                 (wide[1] + regular[1]) / 2,
                                 (wide[2] + regular[2]) / 2))

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
        chains_to_loft = []
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
            chains_to_loft.append((leaf, profiles, influences))
        self._profile_tweaks(plan)
        for leaf, profiles, influences in chains_to_loft:
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
        branches_by_parent = {}
        for branch in plan.branches:
            branches_by_parent.setdefault(branch.parent, []).append(
                branch.child)
        for parent, side_children in branches_by_parent.items():
            all_children = c.listRelatives(parent, children=True,
                                           type="joint", fullPath=True) or []
            parent_leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            child_leaves = tuple(child.rsplit("|", 1)[-1]
                                 .rsplit(":", 1)[-1]
                                 for child in all_children)
            layout = special_skin_cage_branch(parent_leaf, child_leaves)
            if layout:
                copies.append(self._special_branch_panels(parent, layout))
            else:
                for child in side_children:
                    copies.append(self._branch_panels(parent, child))
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
        surviving = [node for node in selection if c.objExists(node)]
        c.select(surviving, replace=True) if surviving else c.select(clear=True)

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

    def capture_mirror_input(self) -> tuple[str, ...]:
        c = self.cmds
        curve_set = self._name("SkinCageCurvesSet")
        if not c.objExists(curve_set):
            raise ValueError("当前角色没有 SkinCage 曲线集合")
        members = c.sets(curve_set, query=True) or []
        profiles = []
        for member in members:
            matches = c.ls(member, long=True, type="transform") or []
            if len(matches) == 1 and c.listRelatives(
                    matches[0], shapes=True, noIntermediate=True,
                    type="nurbsCurve"):
                profiles.append(matches[0])
        return tuple(dict.fromkeys(profiles))

    def preflight_mirror(self,
                         pairs: tuple[SkinCageMirrorPair, ...]) -> None:
        c = self.cmds
        self._mirror_state.clear()
        cv_map = (2, 3, 0, 1, 2)
        for pair in pairs:
            for profile in (pair.source, pair.target):
                shapes = c.listRelatives(
                    profile, shapes=True, noIntermediate=True,
                    type="nurbsCurve", fullPath=True) or []
                if len(shapes) != 1:
                    raise ValueError("SkinCage 截面须有唯一曲线 Shape：" + profile)
            source_points = tuple(tuple(c.xform(
                f"{pair.source}.cv[{index}]", query=True,
                worldSpace=True, translation=True)) for index in range(5))
            target_points = tuple(tuple(c.xform(
                f"{pair.target}.cv[{index}]", query=True,
                worldSpace=True, translation=True)) for index in range(5))
            expected = list(target_points)
            for source_index, target_index in enumerate(cv_map):
                pos = source_points[source_index]
                expected[target_index] = (-pos[0], pos[1], pos[2])
            pos = source_points[2]
            expected[4] = (-pos[0], pos[1], pos[2])
            self._mirror_state[pair.target] = (
                tuple(expected),
                tuple(c.xform(pair.source, query=True,
                              worldSpace=True, translation=True)),
                tuple(c.getAttr(pair.source + ".scale")[0]))

    def mirror_profiles(self, pair: SkinCageMirrorPair) -> None:
        c = self.cmds
        points, source_translation, source_scale = self._mirror_state[pair.target]
        if c.getAttr(pair.target + ".translateX", settable=True):
            c.xform(pair.target, worldSpace=True, translation=(
                -source_translation[0], source_translation[1],
                source_translation[2]))
        if all(c.getAttr(pair.target + ".scale" + axis, settable=True)
               for axis in "XYZ"):
            c.setAttr(pair.target + ".scale", *source_scale,
                      type="double3")
        for index, point in enumerate(points):
            c.xform(f"{pair.target}.cv[{index}]", worldSpace=True,
                    translation=point)

    def capture_mirror(self, pair: SkinCageMirrorPair) -> bool:
        c = self.cmds
        expected = self._mirror_state[pair.target][0]
        for index, point in enumerate(expected):
            actual = c.xform(f"{pair.target}.cv[{index}]", query=True,
                             worldSpace=True, translation=True)
            if max(abs(actual[axis] - point[axis])
                   for axis in range(3)) > 0.0001:
                return False
        return True

    def capture_width_input(self) -> tuple[SkinCageWidthInput, ...]:
        from math import dist

        c = self.cmds
        if not all(c.objExists(self._name(leaf)) for leaf in (
                "skinCage", "SkinCurves1", "SkinCurves2")):
            raise ValueError("请先创建当前角色的 SkinCage 和 SkinCurves")
        rows = []
        for main in self.capture_mirror_input():
            leaf = main.rsplit("|", 1)[-1]
            if not leaf.endswith("_middleProfile"):
                continue
            joint_name = leaf[:-len("_middleProfile")]
            joint = (c.ls(joint_name, long=True, type="joint") or [])
            if len(joint) != 1:
                continue
            cv = [tuple(c.xform(f"{main}.cv[{index}]", query=True,
                                worldSpace=True, translation=True))
                  for index in range(3)]
            edge_a = dist(cv[0], cv[1])
            edge_b = dist(cv[1], cv[2])
            for suffix in ("start", "end"):
                if joint_name.rsplit(":", 1)[-1].startswith("Neck"):
                    continue
                profile_name = joint_name + "_" + suffix + "Profile"
                profile = c.ls(profile_name, long=True,
                               type="transform") or []
                if len(profile) != 1:
                    continue
                offset = c.listRelatives(profile[0], parent=True,
                                         fullPath=True) or []
                if len(offset) != 1:
                    continue
                points = (c.listConnections(
                    offset[0] + ".translate", source=True,
                    destination=False, type="pointConstraint") or
                    c.listConnections(
                        offset[0] + ".translateX", source=True,
                        destination=False, type="pointConstraint") or [])
                scales = (c.listConnections(
                    offset[0] + ".scale", source=True,
                    destination=False, type="scaleConstraint") or
                    c.listConnections(
                        offset[0] + ".scaleX", source=True,
                        destination=False, type="scaleConstraint") or [])
                if len(points) != 1 or len(scales) != 1:
                    continue
                pc, sc = points[0], scales[0]
                point_targets = c.pointConstraint(
                    pc, query=True, targetList=True) or []
                scale_targets = c.scaleConstraint(
                    sc, query=True, targetList=True) or []
                if len(point_targets) != 2 or len(scale_targets) != 2:
                    continue
                canonical = lambda name: (c.ls(name, long=True) or [name])[0]
                main_path = canonical(joint[0])
                point_paths = tuple(map(canonical, point_targets))
                scale_paths = tuple(map(canonical, scale_targets))
                if main_path not in point_paths or main_path not in scale_paths:
                    continue
                pi = point_paths.index(main_path)
                si = scale_paths.index(main_path)
                point_aliases = c.pointConstraint(
                    pc, query=True, weightAliasList=True) or []
                scale_aliases = c.scaleConstraint(
                    sc, query=True, weightAliasList=True) or []
                if len(point_aliases) != 2 or len(scale_aliases) != 2:
                    continue
                other = point_paths[1 - pi]
                main_pos = c.xform(main, query=True, worldSpace=True,
                                   translation=True)
                other_pos = c.xform(other, query=True, worldSpace=True,
                                    translation=True)
                rows.append(SkinCageWidthInput(
                    profile[0], pc, sc,
                    point_aliases[pi], point_aliases[1 - pi],
                    scale_aliases[si], scale_aliases[1 - si],
                    edge_a, edge_b, dist(main_pos, other_pos)))
        return tuple(rows)

    def preflight_width(self,
                        specs: tuple[SkinCageWidthSpec, ...]) -> None:
        c = self.cmds
        for spec in specs:
            row = spec.source
            for constraint, aliases in (
                    (row.point_constraint, (row.main_point_alias,
                                            row.other_point_alias)),
                    (row.scale_constraint, (row.main_scale_alias,
                                            row.other_scale_alias))):
                if not c.objExists(constraint) or any(
                        not c.getAttr(constraint + "." + alias,
                                      settable=True) for alias in aliases):
                    raise ValueError("SkinCage 截面约束不可写：" + row.profile)

    def set_width(self, spec: SkinCageWidthSpec) -> None:
        c = self.cmds
        row = spec.source
        for constraint, main, other in (
                (row.point_constraint, row.main_point_alias,
                 row.other_point_alias),
                (row.scale_constraint, row.main_scale_alias,
                 row.other_scale_alias)):
            c.setAttr(constraint + "." + main,
                      1.0 - spec.other_weight)
            c.setAttr(constraint + "." + other,
                      spec.other_weight)
        cage = self._name("skinCage")
        if not c.attributeQuery("deformationWidth", node=cage,
                                exists=True):
            c.addAttr(cage, longName="deformationWidth",
                      attributeType="bool", defaultValue=True)

    def capture_width(self, spec: SkinCageWidthSpec) -> bool:
        c = self.cmds
        row = spec.source
        for constraint, main, other in (
                (row.point_constraint, row.main_point_alias,
                 row.other_point_alias),
                (row.scale_constraint, row.main_scale_alias,
                 row.other_scale_alias)):
            if abs(c.getAttr(constraint + "." + main) -
                   (1.0 - spec.other_weight)) > 1e-5:
                return False
            if abs(c.getAttr(constraint + "." + other) -
                   spec.other_weight) > 1e-5:
                return False
        return c.attributeQuery(
            "deformationWidth", node=self._name("skinCage"), exists=True)

    def capture_groin_locator_input(self):
        c = self.cmds
        fit_root = self._name("Root")
        cage_root = self._name("Root_M_middleProfile")
        if not c.objExists(fit_root) or not c.objExists(cage_root):
            raise ValueError("创建腹股沟定位器需要 Root 和 SkinCage 根截面")
        return (tuple(c.xform(fit_root, query=True, worldSpace=True,
                              translation=True)),
                tuple(c.xform(cage_root + ".cv[2]", query=True,
                              worldSpace=True, translation=True)))

    def create_groin_locators(self,
                              plan: SkinCageGroinLocators) -> None:
        c = self.cmds
        for leaf, pos in (("GroinStart", plan.start),
                          ("GroinSide", plan.side)):
            name = self._name(leaf)
            if c.objExists(name):
                c.delete(name)
            locator = c.spaceLocator(name=name)[0]
            c.xform(locator, worldSpace=True, translation=pos)
        c.select(clear=True)

    def capture_groin_locators(self,
                               plan: SkinCageGroinLocators) -> bool:
        c = self.cmds
        for leaf, expected in (("GroinStart", plan.start),
                               ("GroinSide", plan.side)):
            node = self._name(leaf)
            if not c.objExists(node):
                return False
            actual = c.xform(node, query=True, worldSpace=True,
                             translation=True)
            if max(abs(actual[i] - expected[i]) for i in range(3)) > 1e-5:
                return False
        return True

    def capture_groin_adjustment_input(self):
        c = self.cmds
        start, side = self._name("GroinStart"), self._name("GroinSide")
        if not c.objExists(start) or not c.objExists(side):
            raise ValueError("请先创建并调整 GroinStart、GroinSide 定位器")
        return (tuple(c.xform(start, query=True, worldSpace=True,
                              translation=True)),
                tuple(c.xform(side, query=True, worldSpace=True,
                              translation=True)))

    def preflight_groin_adjustment(self) -> None:
        c = self.cmds
        for leaf in ("Root_M_middleProfile", "Hip_R_startProfile",
                     "Hip_R_middleProfile"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("腹股沟调整缺少 SkinCage 截面：" + leaf)
        if not c.objExists(self._name("SkinCageCurvesSet")):
            raise ValueError("腹股沟调整需要 SkinCage 曲线集合")

    def _groin_set_cv(self, leaf: str, index: int, *, x: float | None = None,
                      y: float | None = None,
                      source: tuple[float, float, float] | None = None) -> None:
        c = self.cmds
        cv = f"{self._name(leaf)}.cv[{index}]"
        pos = source or c.xform(cv, query=True, worldSpace=True,
                                translation=True)
        c.xform(cv, worldSpace=True, translation=(
            pos[0] if x is None else x,
            pos[1] if y is None else y, pos[2]))

    def adjust_groin(self, plan: SkinCageGroinAdjustment) -> None:
        c = self.cmds
        root = self._name("Root_M_middleProfile")
        root_y = c.xform(root, query=True, worldSpace=True,
                         translation=True)[1]
        for index in range(5):
            cv = f"{root}.cv[{index}]"
            pos = c.xform(cv, query=True, worldSpace=True,
                          translation=True)
            c.xform(cv, worldSpace=True, translation=(
                pos[0], pos[1] + plan.side_y - root_y, pos[2]))
        for source_index, target_indices, target_leaf, factor in (
                (2, (3,), "Hip_R_startProfile", 1.0),
                (2, (3,), "Hip_R_middleProfile", 0.95),
                (1, (0, 4), "Hip_R_startProfile", 1.0),
                (1, (0, 4), "Hip_R_middleProfile", 0.95)):
            point = c.xform(f"{root}.cv[{source_index}]", query=True,
                            worldSpace=True, translation=True)
            for index in target_indices:
                self._groin_set_cv(target_leaf, index,
                                   source=(point[0], point[1] * factor,
                                           point[2]))
        for index in (1, 2):
            self._groin_set_cv("Hip_R_middleProfile", index,
                               y=plan.start_y * 0.95)
            self._groin_set_cv("Hip_R_startProfile", index,
                               x=0.0, y=plan.start_y)
        hip_start = self._name("Hip_R_startProfile")
        current = c.getAttr(hip_start + ".scale")[0]
        c.setAttr(hip_start + ".scale",
                  *(value * 1.2 for value in current), type="double3")
        index = 1
        while c.objExists(self._name(f"Hip_R_twistProfile{index}")):
            curve = self._name(f"Hip_R_twistProfile{index}")
            pos = c.xform(f"{curve}.cv[1]", query=True,
                          worldSpace=True, translation=True)
            if pos[1] > plan.start_y:
                delta = (pos[1] - plan.start_y) * -1.2
                for cv_index in (1, 2):
                    cv = f"{curve}.cv[{cv_index}]"
                    cv_pos = c.xform(cv, query=True, worldSpace=True,
                                     translation=True)
                    c.xform(cv, worldSpace=True, translation=(
                        cv_pos[0], cv_pos[1] + delta, cv_pos[2]))
            index += 1
        c.delete([self._name("GroinStart"), self._name("GroinSide")])
        self._groin_expected_pos = tuple(c.xform(
            hip_start + ".cv[1]", query=True, worldSpace=True,
            translation=True))

    def capture_groin_adjustment(self) -> bool:
        c = self.cmds
        if self._groin_expected_pos is None or any(c.objExists(
                self._name(leaf)) for leaf in ("GroinStart", "GroinSide")):
            return False
        cv = self._name("Hip_R_startProfile") + ".cv[1]"
        pos = c.xform(cv, query=True, worldSpace=True, translation=True)
        return max(abs(pos[i] - self._groin_expected_pos[i])
                   for i in range(3)) < 1e-4

    def preflight_groin_joint(self) -> None:
        c = self.cmds
        for leaf in ("Root_M", "skinCage", "skinClusterSkinCage"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("创建 Groin_M 前需要完整 SkinCage：" + leaf)
        if c.objExists(self._name("Groin_M")):
            raise ValueError("当前角色已有 Groin_M")

    def create_groin_joint(self) -> None:
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        root = self._name("Root_M")
        root_pos = c.xform(root, query=True, worldSpace=True,
                           translation=True)
        c.select(root, replace=True)
        groin = c.joint(name=self._name("Groin_M"))
        y = root_pos[1] * 0.95
        hip_start = self._name("Hip_R_startProfile")
        if c.objExists(hip_start):
            y = c.xform(hip_start + ".cv[1]", query=True,
                        worldSpace=True, translation=True)[1]
        c.xform(groin, worldSpace=True,
                translation=(0.0, y, root_pos[2]))
        skin = self._name("skinClusterSkinCage")
        c.skinCluster(skin, edit=True, addInfluence=groin,
                      weight=0.0, lockWeights=False)
        cage = self._name("skinCage")
        shape = (c.listRelatives(cage, shapes=True, noIntermediate=True,
                                 type="mesh", fullPath=True) or [])[0]
        sampler = c.createNode("closestPointOnMesh",
                                name=self._name("groinClosestSampler"))
        try:
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh",
                          force=True)
            for side, indices in (("R", (1, 2)), ("L", (0, 3))):
                for kind in ("start", "middle"):
                    profile = self._name(f"Hip_{side}_{kind}Profile")
                    if not c.objExists(profile):
                        continue
                    original_z = None
                    if kind == "start":
                        original_z = c.getAttr(profile + ".translateZ")
                        c.setAttr(profile + ".translateZ",
                                  root_pos[1] / 50.0)
                    try:
                        for index in indices:
                            point = c.xform(
                                f"{profile}.cv[{index}]", query=True,
                                worldSpace=True, translation=True)
                            c.setAttr(sampler + ".inPosition", *point,
                                      type="double3")
                            vertex = int(c.getAttr(
                                sampler + ".closestVertexIndex"))
                            component = f"{cage}.vtx[{vertex}]"
                            c.skinPercent(skin, component,
                                          transformValue=[(groin, 1.0)],
                                          normalize=True)
                            if kind == "middle":
                                c.skinPercent(skin, component,
                                              transformValue=[(
                                                  self._name("Hip_" + side),
                                                  0.5)], normalize=True)
                    finally:
                        if original_z is not None:
                            c.setAttr(profile + ".translateZ", original_z)
        finally:
            c.delete(sampler)
        leg_lock = self._name("LegLockConstrained")
        if c.objExists(leg_lock):
            constraints = (c.parentConstraint(
                leg_lock, groin, maintainOffset=True) or []) + (
                c.scaleConstraint(leg_lock, groin,
                                  maintainOffset=True) or [])
            system = self._name("ConstraintSystem")
            if c.objExists(system):
                for constraint in constraints:
                    c.parent(constraint, system)
        c.select(selection, replace=True) if selection else c.select(clear=True)

    def capture_groin_joint(self) -> bool:
        c = self.cmds
        groin = self._name("Groin_M")
        if not c.objExists(groin):
            return False
        influences = c.ls(c.skinCluster(
            self._name("skinClusterSkinCage"), query=True,
            influence=True) or [], long=True) or []
        path = (c.ls(groin, long=True) or [groin])[0]
        return path in influences

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
