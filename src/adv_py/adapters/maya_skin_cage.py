"""Maya implementation of the original SkinCage copy/delete/reuse actions."""
from __future__ import annotations

from contextlib import contextmanager
from fnmatch import fnmatchcase

from adv_py.core.skin_cage import (
    SKIN_CAGE_NODES, SkinCageBranchLayout, SkinCageBuildPlan,
    SkinCageCopyTarget, SkinCageCurveDeletePlan,
    SkinCageGroinAdjustment,
    SkinCageGroinLocators, SkinCageMirrorPair, SkinCageProfileShape,
    SkinCageWidthInput,
    SkinCageWidthSpec, special_skin_cage_branch,
)


from .maya_skin_cage_source import MayaSkinCageSourceMixin


class MayaSkinCageHost(MayaSkinCageSourceMixin):
    def __init__(self, namespace: str = "", *, slider_include_controller: bool = False) -> None:
        from maya import cmds
        self.cmds = cmds
        self.namespace = namespace.strip(":")
        self.slider_include_controller = slider_include_controller
        self._source_skin = ""
        self._source_mesh = ""
        self._influences: tuple[str, ...] = ()
        self._selection: tuple[str, ...] = ()
        self._mirror_state = {}
        self._mirror_slider_expected = {}
        self._groin_expected_pos = None

    def _name(self, leaf: str) -> str:
        return self.namespace + ":" + leaf if self.namespace else leaf

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        previous_namespace = c.namespaceInfo(currentNamespace=True, absoluteName=True)
        if previous_namespace != ":":
            c.namespace(set=":")
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            c.undoInfo(closeChunk=True)
            if c.undoInfo(query=True, undoName=True) == label:
                c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        finally:
            if previous_namespace != ":":
                c.namespace(set=previous_namespace)

    def capture_build_input(self):
        c = self.cmds
        system = self._name("DeformationSystem")
        if not c.objExists(system):
            raise ValueError("当前角色没有 DeformationSystem")
        roots = c.listRelatives(system, children=True, type="joint",
                                fullPath=True) or []
        if not roots:
            raise ValueError("DeformationSystem 没有根关节")
        # asCreateSkinCage uses the first native child, even in a system
        # containing more than one top-level joint.
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
        geometry = self._name("Geometry")
        if not c.objExists(geometry):
            raise ValueError("当前角色没有 Geometry 组")

    def cage_exists(self) -> bool:
        return bool(self.cmds.objExists(self._name("MeshGeometry")))

    def preflight_rebuild(self, plan: SkinCageBuildPlan) -> None:
        # asRebuildSkinCage records whichever profiles survive, deletes the
        # named cage nodes if present, and creates again. Deleted curves or
        # an absent skinCluster must not prevent this recovery path.
        self.preflight_build(plan)

    def capture_profile_shapes(self) -> tuple[SkinCageProfileShape, ...]:
        """asRebuildSkinCage saves Shape names, including twistProfileShape1."""
        c = self.cmds
        profiles = []
        for shape in c.ls(self._name("*ProfileShape*"), type="nurbsCurve") or []:
            spans = int(c.getAttr(shape + ".spans"))
            count = spans if int(c.getAttr(shape + ".form")) == 2 else spans + int(c.getAttr(shape + ".degree"))
            points = tuple(tuple(c.xform(f"{shape}.cv[{index}]", query=True,
                                         worldSpace=True, translation=True))
                           for index in range(count + 1))
            profiles.append(SkinCageProfileShape(shape, points))
        return tuple(profiles)

    def restore_profile_shapes(self, profiles: tuple[SkinCageProfileShape, ...]) -> None:
        c = self.cmds
        self._restored_profile_points = []
        self._profile_restore_failures = []
        for profile in profiles:
            for index, point in enumerate(profile.points):
                component = f"{profile.name}.cv[{index}]"
                try:
                    c.xform(component, worldSpace=True, translation=point)
                except RuntimeError:
                    # The source catchQuiet is per CV, not per entire profile.
                    self._profile_restore_failures.append(component)
                else:
                    self._restored_profile_points.append((component, point))

    def capture_restored_profiles(self, profiles: tuple[SkinCageProfileShape, ...]) -> bool:
        c = self.cmds
        for component, expected in self._restored_profile_points:
            actual = c.xform(component, query=True, worldSpace=True, translation=True)
            if max(abs(actual[i] - expected[i]) for i in range(3)) > 1e-4:
                return False
        if self._profile_restore_failures:
            c.warning("SkinCage 原版逐 CV 恢复跳过了 %d 项；请检查重建后的截面。" %
                      len(self._profile_restore_failures))
        return True

    def capture_curve_delete_input(self) -> tuple[str, ...]:
        c = self.cmds
        leaves = ("SkinCurves1", "SkinCurves2", "MeshGeometry",
                  "MeshCurves", "NurbsGeometry")
        return tuple(leaf for leaf in leaves
                     if c.objExists(self._name(leaf)))

    def preflight_curve_delete(
            self, plan: SkinCageCurveDeletePlan) -> bool:
        c = self.cmds
        skin = self._name("skinClusterSkinCage")
        return bool(c.objExists(self._name("skinCageShape")) and c.objExists(skin))

    def delete_curves(self, plan: SkinCageCurveDeletePlan) -> None:
        """asDeleteSkinCurves: temporary undeformed mesh and deferred delete."""
        c = self.cmds
        skin = self._name("skinClusterSkinCage")
        visible_shape = self._name("skinCageShape")
        if not c.objExists(visible_shape) or not c.objExists(skin):
            return
        c.setAttr(skin + ".envelope", 0)
        try:
            temporary = c.duplicate(visible_shape, name=self._name("asTempMesh"))[0]
        finally:
            c.setAttr(skin + ".envelope", 1)
        for leaf in plan.nodes:
            if c.objExists(self._name(leaf)):
                c.delete(self._name(leaf))
        self._curve_delete_input = ""
        for mesh in c.listRelatives(self._name("skinCage"), shapes=True, type="mesh") or []:
            if mesh == visible_shape:
                continue
            c.connectAttr(temporary + ".outMesh", mesh + ".inMesh")
            self._curve_delete_input = mesh
            # Native Maya deferred command matches the source's graph bake.
            c.evalDeferred(lambda node=temporary: c.delete(node) if c.objExists(node) else None,
                           lowestPriority=True)
            break

    def capture_curves_deleted(self, plan: SkinCageCurveDeletePlan) -> bool:
        c = self.cmds
        return (all(not c.objExists(self._name(leaf)) for leaf in plan.nodes)
                and c.objExists(self._name("skinCageShape"))
                and self._skin(self._name("skinCage")) == self._name("skinClusterSkinCage")
                and c.getAttr(self._name("skinClusterSkinCage") + ".envelope") == 1)

    def _special_branch_panels(self, parent: str,
                               layout: SkinCageBranchLayout) -> str:
        c = self.cmds
        leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        base = self._name(leaf + "_branch")
        wrist_curves = [self._name(stem + "_L_" + suffix + "Curve")
                        for stem, suffix in (("Wrist", "end"), ("ThumbFinger2", "start"),
                                             ("IndexFinger1", "start"), ("MiddleFinger1", "start"),
                                             ("RingFinger1", "start"), ("PinkyFinger1", "start"))]
        if leaf == "Wrist_L":
            for curve in wrist_curves:
                c.setAttr(curve + ".s", -.833, -.833, -.833, type="float3")
        for index, face in enumerate(layout.faces):
            points = []
            for curve, cv in face:
                profile = self._name(curve + "Curve")
                if not c.objExists(profile):
                    raise ValueError("SkinCage 专用分叉缺少截面：" + profile)
                points.append(c.xform(f"{profile}.cv[{cv}]", query=True,
                                      worldSpace=True, translation=True))
            facet = c.polyCreateFacet(
                point=points, constructionHistory=False, texture=1, subdivisions=1,
                name=self._name("tempPolyPlane" + str(
                    1 if leaf == "Chest_M" and index < 6 else
                    index - 3 if leaf == "Chest_M" else index + 1)))[0]
            if index in layout.reverse_faces:
                c.polyNormal(facet, normalMode=0, userNormalMode=0,
                             constructionHistory=False)
        bridge = c.polyUnite(
            [self._name("tempPolyPlane" + str(index + 1))
             for index in range(len(layout.faces))],
            constructionHistory=False, mergeUVSets=1,
                             centerPivot=True, name=base)[0]
        if leaf == "Wrist_L":
            for curve in wrist_curves:
                c.setAttr(curve + ".s", .833, .833, .833, type="float3")
            c.polyNormal(bridge, normalMode=0, userNormalMode=0,
                         constructionHistory=False)
        return bridge

    def _weight_tweaks(self, cage: str, skin: str) -> None:
        """asSkinCageWeightTweaks, including sampler lifetime without Chest."""
        c = self.cmds
        sampler = self._name("closestSampler")
        if c.objExists(sampler):
            c.delete(sampler)
        sampler = c.createNode("closestPointOnMesh", name=sampler)
        try:
            c.connectAttr(cage + ".outMesh", sampler + ".inMesh", force=True)
            curve = self._name("Chest_M_middleCurve")
            if c.objExists(curve):
                for index in range(5):
                    point = c.xform(f"{curve}.cv[{index}]", query=True,
                                    worldSpace=True, translation=True)
                    c.setAttr(sampler + ".inPosition", *point, type="double3")
                    vertex = int(c.getAttr(sampler + ".closestVertexIndex"))
                    parent = c.listRelatives(self._name("Chest_M"), parent=True) or []
                    c.skinPercent(skin, f"{cage}.vtx[{vertex}]",
                                  transformValue=[(parent[0], 0.5)])
        finally:
            c.delete(sampler)

    def _profile_tweaks(self, plan: SkinCageBuildPlan) -> None:
        """asProfileTweaks: labels, Fit axis and native component scale."""
        c = self.cmds
        for profile in c.ls(self._name("*Ankle*_*endProfile"), type="transform") or []:
            ankle = profile.removesuffix("_endProfile")
            fit = ankle[:-2]
            factor = -1 if ankle.endswith("_L") else 1
            heel = ""
            for child in c.listRelatives(fit, children=True, type="joint") or []:
                label = self._cage_label(child)
                if fnmatchcase(label or "", "*Heel*"):
                    heel = child
            if not heel:
                continue
            center = c.xform(profile, query=True, worldSpace=True, translation=True)
            heel_position = c.xform(heel, query=True, worldSpace=True, translation=True)
            axis = self._cage_axis(fit, "tertiary")[-1].lower()
            axis_index = "xyz".index(axis)
            indices = (0, 1, 4) if "_R_" in profile else (2, 3)
            for index in indices:
                cv = f"{profile}.cv[{index}]"
                local = c.getAttr(cv)[0]
                c.xform(cv, worldSpace=True,
                        translation=(heel_position[0] * factor, *heel_position[1:]))
                c.setAttr(cv + "." + axis + "Value", local[axis_index])
                c.scale(1.2, 1.2, 1, cv, relative=True, pivot=center)
        for profile in c.ls(self._name("*Toes*Profile"), type="transform") or []:
            center = c.xform(profile, query=True, worldSpace=True, translation=True)
            indices, opposite = ((0, 1, 4), (2, 3)) if "_R_" in profile else ((2, 3), (0, 1, 4))
            for index in indices:
                cv = f"{profile}.cv[{index}]"
                position = c.xform(cv, query=True, worldSpace=True, translation=True)
                c.xform(cv, worldSpace=True, translation=(position[0], 0, position[2]))
                c.scale(1, 1.2, 1, cv, worldSpace=True, relative=True, pivot=center)
            if "_start" in profile:
                for index in opposite:
                    c.scale(1, .5, 1, f"{profile}.cv[{index}]",
                            worldSpace=True, relative=True, pivot=center)
        start = self._name("Neck_M_startProfile")
        middle = self._name("Neck_M_middleProfile")
        chest = self._name("Chest_M_middleProfile")
        if c.objExists(self._name("Neck_M_startCurve")) and c.objExists(chest):
            chest_scale = c.getAttr(chest + ".s")[0]
            neck_scale = c.getAttr(middle + ".s")[0]
            for index in range(5):
                cv = f"{middle}.cv[{index}]"
                regular = c.xform(cv, query=True, worldSpace=True, translation=True)
                c.setAttr(middle + ".s", *chest_scale, type="float3")
                wide = c.xform(cv, query=True, worldSpace=True, translation=True)
                c.setAttr(middle + ".s", *neck_scale, type="float3")
                c.xform(f"{start}.cv[{index}]", worldSpace=True,
                        translation=(regular[0] * 1.1,
                                     (regular[1] + wide[1]) / 2,
                                     (regular[2] + wide[2]) / 2))

    def create_cage(self, plan: SkinCageBuildPlan) -> None:
        """asCreateSkinCage: source curve graph, weights, wrap and final edits."""
        c = self.cmds
        if c.softSelect(query=True, softSelectEnabled=True):
            c.softSelect(edit=True, softSelectEnabled=False)
        if c.symmetricModelling(query=True, symmetry=True):
            c.symmetricModelling(edit=True, symmetry=False)
        original_axis = c.upAxis(query=True, axis=True)
        if original_axis == "z":
            self._cage_flip_axis("y")
        from .maya_original_fit_attributes import ensure_original_fit_attributes
        ensure_original_fit_attributes(c, self._name("FitSkeleton"),
                                       self._name("DeformationSystem"), self._cage_rla_child)
        for leaf in ("Cages", "MeshGeometry", "MeshCurves", "NurbsGeometry"):
            node = c.createNode("transform", name=self._name(leaf))
            c.parent(node, self._name("Geometry"))
        c.setAttr(self._name("MeshGeometry") + ".overrideEnabled", 1)
        c.setAttr(self._name("NurbsGeometry") + ".v", 0)
        curve_set = c.sets(empty=True, name=self._name("SkinCageCurvesSet"))
        c.sets(curve_set, add=self._name("Sets"))
        c.select(clear=True)
        for number, leaf in enumerate(("SkinCage", "SkinCurves1", "SkinCurves2"), 1):
            c.createDisplayLayer(empty=True, name=self._name(leaf), number=number,
                                 noRecurse=True)
        for leaf, color, visible in (("SkinCurves2", 13, 0), ("SkinCurves1", 14, 1)):
            c.setAttr(self._name(leaf) + ".v", visible)
            c.setAttr(self._name(leaf) + ".displayType", 0)
            c.setAttr(self._name(leaf) + ".color", color)
        c.setAttr(self._name("SkinCage") + ".displayType", 2)
        root = self._name(self._cage_leaf(plan.root))
        self._cage_main_box(root)
        face_set = self._name("FaceAllSet")
        for joint in reversed(self._cage_descendants(root)):
            if c.objExists(face_set) and c.sets(joint, isMember=face_set):
                continue
            if self._cage_children(joint) and not c.objExists(joint + "_middleCurve"):
                self._cage_main_box(joint)
        for joint in self._cage_descendants(self._name("DeformationSystem")):
            if c.objExists(face_set) and c.sets(joint, isMember=face_set):
                continue
            children = self._cage_children(joint)
            leaf = self._cage_leaf(joint)
            layout = special_skin_cage_branch(leaf, tuple(self._cage_leaf(child) for child in children))
            if leaf == "Chest_M" and not c.objExists(self._name("Neck_M_startCurve")):
                layout = None
            if layout:
                self._special_branch_panels(joint, layout)
            else:
                self._cage_generic_branch(joint, children)
        copies = c.ls(self._name("*_copy"), self._name("*_branch"), assemblies=True) or []
        cage = c.polyUnite(copies, ch=0, name=self._name("skinCage"))[0]
        c.setAttr(cage + ".keepBorder", 0)
        c.polyMergeVertex(cage, d=.0001, am=1, ch=1)
        c.delete(cage, constructionHistory=True)
        c.parent(cage, self._name("Cages"))
        c.editDisplayLayerMembers(self._name("SkinCage"), cage, noRecurse=True)
        middle_curves = c.ls(self._name("*_middleCurve"), type="transform") or []
        c.polyAutoProjection(cage, ch=0, lm=0, pb=0, ibd=0, cm=0, l=2,
                             sc=1, o=1, p=6, ps=.2, ws=0)
        c.select(clear=True)
        for curve in middle_curves:
            joint = curve.replace("_middleCurve", "")
            name, side = self._cage_leaf(joint).split("_")[:2]
            partial = self._name(name + "Partial_" + side)
            if c.objExists(partial): c.select(partial, add=True)
            c.select(joint, add=True)
            for n in range(1, 99):
                twist = self._name(name + "Part" + str(n) + "_" + side)
                if not c.objExists(twist): break
                c.select(twist, add=True)
            parent = self._cage_parent(joint)
            if parent and not c.objExists(parent + "_middleCurve") and not fnmatchcase(parent, "*Part[0-9]*"):
                c.select(parent, add=True)
            if c.objExists(partial): c.select(partial, add=True)
            if not c.listRelatives(joint, children=True, type="joint"):
                c.select(joint, deselect=True)
        c.select(cage, add=True)
        from .maya_original_skin_history import new_original_skin_clusters
        skin = new_original_skin_clusters(commands=c, namespace=self.namespace)[0]
        skin = c.rename(skin, self._name("skinClusterSkinCage"))
        cylinders = c.listRelatives(self._name("MeshGeometry"), children=True) or []
        c.select(cylinders, replace=True)
        c.select(cage, add=True)
        c.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint",
                          influenceAssociation="closestJoint")
        cylinders = c.ls(self._name("*_poly"), type="transform") or []
        for mesh in cylinders:
            shape = c.listRelatives(mesh, shapes=True, noIntermediate=True, type="mesh")[0]
            c.delete(c.listConnections(shape + ".inMesh") or [])
            c.setAttr(mesh + ".v", 0, lock=True)
        c.select([cage, cylinders[0]], replace=True)
        from .maya_face_deformer_sets import original_face_deformer_sets
        with original_face_deformer_sets(c):
            self._cage_native('doWrapArgList 7 {"1","0","1","2","0","1","1","0"}')
        for mesh in cylinders[1:]:
            c.select([cage, mesh], replace=True)
            self._cage_native("AddWrapInfluence")
        shape = c.listRelatives(cage, shapes=True, noIntermediate=True, type="mesh")[0]
        wrap = c.rename((c.listConnections(shape + ".inMesh") or [""])[0],
                        self._name("wrapSkinCage"))
        c.reorderDeformers(skin, wrap, cage)
        fit = self._name("FitSkeleton")
        from .maya_original_fit_attributes import original_fit_scale
        tolerance = .01 * original_fit_scale(c, fit)
        fit_joints = c.listRelatives(fit, allDescendents=True, type="joint") or []
        for b in (1, -1):
            for joint in fit_joints:
                x = c.xform(joint, query=True, worldSpace=True, translation=True)[0]
                side = "_M" if -tolerance < x < tolerance else "_R"
                if b == -1:
                    if side == "_M": continue
                    side = "_L"
                profile = joint + side + "_middleProfile"
                if not c.objExists(profile) or not c.objExists(joint + ".fat"):
                    continue
                fat = c.getAttr(joint + side + ".fat")
                front = c.getAttr(joint + side + ".fatFront")
                width = c.getAttr(joint + side + ".fatWidth")
                c.setAttr(profile + ".scale" + self._cage_axis(joint, "secondary")[-1], fat * front)
                c.setAttr(profile + ".scale" + self._cage_axis(joint, "tertiary")[-1], fat * width)
                c.refresh()
        self._profile_tweaks(plan)
        pairs = self._cage_source_mirror_pairs()
        if pairs:
            self.preflight_mirror(pairs)
            for pair in pairs:
                self.mirror_profiles(pair)
                self.sync_mirrored_sliders(pair)
        if original_axis == "z":
            self._cage_flip_axis("z")
        self._weight_tweaks(cage, skin)
        c.select(clear=True)

    def _cage_flip_axis(self, axis):
        c = self.cmds
        group = self._name("Group")
        attributes = ("rx", "ry", "rz", "r")
        locked = [bool(c.getAttr(group + "." + attr, lock=True)) for attr in attributes]
        for attr, was_locked in zip(attributes, locked):
            if was_locked:
                c.setAttr(group + "." + attr, lock=False)
        try:
            c.setAttr(group + ".r", 90 if axis == "z" else 0, 0, 0, type="float3")
        finally:
            for attr, was_locked in zip(attributes, locked):
                if was_locked:
                    c.setAttr(group + "." + attr, lock=True)
        c.upAxis(axis=axis)

    def _cage_source_mirror_pairs(self):
        profiles = self.capture_mirror_input()
        pairs = []
        by_leaf = {node.rsplit("|", 1)[-1]: node for node in profiles}
        for source in profiles:
            leaf = source.rsplit("|", 1)[-1]
            if "_R_" in leaf:
                target = by_leaf.get(leaf.replace("_R_", "_L_", 1))
                if target: pairs.append(SkinCageMirrorPair(source, target))
        return tuple(pairs)

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

    def preflight_mirror(self, pairs: tuple[SkinCageMirrorPair, ...]) -> None:
        c = self.cmds
        self._mirror_state.clear()
        self._mirror_slider_expected.clear()
        for pair in pairs:
            source_shapes = c.listRelatives(pair.source, shapes=True) or []
            target_shapes = c.listRelatives(pair.target, shapes=True) or []
            if not source_shapes or not target_shapes:
                raise ValueError("SkinCage 镜像截面缺少 Shape")
            shape = source_shapes[0]
            spans = int(c.getAttr(shape + ".spans"))
            count = spans if int(c.getAttr(shape + ".form")) == 2 else spans + int(c.getAttr(shape + ".degree"))
            points = tuple(tuple(c.xform(f"{shape}.cv[{index}]", query=True,
                                         worldSpace=True, translation=True))
                           for index in range(count + 1))
            expected = {}
            mapped = 2
            for index, point in enumerate(points):
                if index < 5:
                    mapped = (2, 3, 0, 1, 2)[index]
                reflected = (-point[0], point[1], point[2])
                expected[mapped] = reflected
                if index == 2:
                    expected[4] = reflected
            # Source tokens use short control names, not a DAG parent's name.
            stem = pair.source.rsplit("|", 1)[-1].split("_")[0]
            asymmetric = c.objExists(stem + "_NonSymmetry")
            local = tuple(tuple(c.getAttr(f"{shape}.cv[{index}]")[0])
                          for index in range(count + 1)) if asymmetric else ()
            self._mirror_state[pair.target] = {
                "points": expected, "source_shape": shape, "target_shape": target_shapes[0],
                "translation": tuple(c.xform(pair.source, query=True,
                                              worldSpace=True, translation=True)),
                "scale": tuple(c.getAttr(pair.source + ".s")[0]),
                "stem": stem, "local": local,
            }

    def mirror_profiles(self, pair: SkinCageMirrorPair) -> None:
        c = self.cmds
        state = self._mirror_state[pair.target]
        translation = state["translation"]
        c.xform(pair.target, worldSpace=True,
                translation=(-translation[0], translation[1], translation[2]))
        c.setAttr(pair.target + ".s", *state["scale"], type="float3")
        shape = state["target_shape"]
        for index, point in state["points"].items():
            c.xform(f"{shape}.cv[{index}]", worldSpace=True, translation=point)
        if state["local"]:
            temporary = self._name("tempXform")
            if c.objExists(temporary):
                c.delete(temporary)
            temporary = c.createNode("transform", name=temporary, parent=pair.source)
            try:
                temporary = c.parent(temporary, state["stem"])[0]
                temporary = c.parent(temporary, state["stem"] + "_NonSymmetry", relative=True)[0]
                for axis in "xyz":
                    c.setAttr(temporary + ".t" + axis, -c.getAttr(temporary + ".t" + axis))
                matrix = c.xform(temporary, query=True, worldSpace=True, matrix=True)
                state["matrix"] = tuple(matrix)
                c.xform(pair.target, worldSpace=True, matrix=matrix)
            finally:
                c.delete(temporary)
            for index, point in enumerate(state["local"]):
                for axis, value in zip("xyz", point):
                    c.setAttr(f"{shape}.cv[{index}].{axis}Value", value)

    def _slider_spec_for_profile(self, profile: str):
        from adv_py.adapters.maya_skin_cage_sliders import MayaSkinCageSliderHost
        from adv_py.core.skin_cage_sliders import plan_skin_cage_sliders

        c = self.cmds
        selected = c.ls(selection=True, long=True) or []
        try:
            c.select(profile, replace=True)
            host = MayaSkinCageSliderHost(self.namespace)
            rows = host.capture_slider_rows()
            return (host, plan_skin_cage_sliders(rows)[0]) if rows else (
                host, None)
        finally:
            c.select(selected, replace=True) if selected else c.select(clear=True)

    def sync_mirrored_sliders(self, pair: SkinCageMirrorPair) -> None:
        """SkinCage branch of asMirrorControlCurves: partial slots are legal."""
        c = self.cmds
        _, source = self._slider_spec_for_profile(pair.source)
        target_host, target = self._slider_spec_for_profile(pair.target)
        if source is None or target is None:
            return
        source_present = tuple(c.objExists(self._name(source.joint(index))) for index in range(4))
        target_present = tuple(c.objExists(self._name(target.joint(index))) for index in range(4))
        expected = {}
        if any(source_present):
            # The original calls asCreateSliders even when existing: its
            # first two name checks decide whether the operation is skipped.
            target_host.preflight_sliders((target,), creating=True, include_controller=self.slider_include_controller)
            with target_host.slider_sampling_scope():
                target_host.create_slider(target, include_controller=self.slider_include_controller)
            for index, opposite in enumerate((2, 3, 0, 1)):
                source_joint = self._name(source.joint(index))
                target_joint = self._name(target.joint(opposite))
                if c.objExists(source_joint) and c.objExists(target_joint):
                    value = float(c.getAttr(source_joint + ".slide"))
                    c.setAttr(target_joint + ".slide", value)
                    expected[target_joint] = value
        elif any(target_present):
            with target_host.slider_delete_time_scope(), target_host.slider_sampling_scope():
                target_host.delete_slider(target)
            target_host.finish_slider_delete()
            expected = {self._name(target.joint(index)): None for index in range(4)}
        self._mirror_slider_expected[pair.target] = expected

    def capture_mirror(self, pair: SkinCageMirrorPair) -> bool:
        c = self.cmds
        state = self._mirror_state[pair.target]
        shape = state["target_shape"]
        if state["local"]:
            for index, expected in enumerate(state["local"]):
                actual = c.getAttr(f"{shape}.cv[{index}]")[0]
                if max(abs(actual[axis] - expected[axis]) for axis in range(3)) > .0001:
                    return False
            actual_matrix = c.xform(pair.target, query=True, worldSpace=True, matrix=True)
            if max(abs(actual_matrix[i] - state["matrix"][i]) for i in range(16)) > .0001:
                return False
        else:
            for index, point in state["points"].items():
                actual = c.xform(f"{shape}.cv[{index}]", query=True,
                                 worldSpace=True, translation=True)
                if max(abs(actual[axis] - point[axis]) for axis in range(3)) > .0001:
                    return False
        for joint, expected_slide in self._mirror_slider_expected.get(
                pair.target, {}).items():
            if expected_slide is None:
                if c.objExists(joint):
                    return False
            elif (not c.objExists(joint)
                  or abs(float(c.getAttr(joint + ".slide"))
                         - expected_slide) > 1e-6):
                return False
        return True

    def set_source_width(self) -> tuple[SkinCageWidthSpec, ...]:
        """asSkinCurvesToWidth with native read/write ordering inside undo."""
        from math import dist
        c = self.cmds
        for leaf in ("SkinCurves1", "SkinCurves2"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SkinCurves not found. Create SkinCage first")
        c.listConnections(self._name("SkinCurves2") + ".drawInfo")
        main_profiles = c.listConnections(self._name("SkinCurves1") + ".drawInfo") or []
        written = []
        for main in main_profiles:
            joint = main.rsplit("_", 1)[0]
            if not c.objExists(joint):
                continue
            parent = self._cage_parent(joint)
            while parent and fnmatchcase(parent, "*Part[0-9]*"):
                parent = self._cage_parent(parent)
            if not parent or not c.objExists(parent):
                continue
            children = c.listRelatives(joint, children=True, type="joint") or []
            if not children or not c.objExists(children[0]):
                continue
            immediate_parent = self._cage_parent(joint)
            if any(fnmatchcase(node, "*Part[0-9]*") and not c.objExists(node + ".twistAmount")
                   for node in (children[0], immediate_parent) if node):
                continue
            for end in (False, True):
                profile = joint + ("_endProfile" if end else "_startProfile")
                if not c.objExists(profile):
                    stem = joint if end else parent
                    indices = range(1, 21) if end else range(20, 0, -1)
                    profile = next((stem + "_twistProfile" + str(index) for index in indices
                                    if c.objExists(stem + "_twistProfile" + str(index))), "")
                if not profile or fnmatchcase(self._cage_leaf(profile), "Neck*"):
                    continue
                offset = c.listRelatives(profile, parent=True)[0]
                pc, sc = offset + "_pointConstraint1", offset + "_scaleConstraint1"
                aliases = c.listAttr(pc, userDefined=True) or []
                c.setAttr(pc + ".offset", 0, 0, 0, type="float3")
                targets = c.listConnections(pc + ".target[0].targetParentMatrix") or []
                other_index, main_index = 0, 1
                if targets and targets[0] == main.replace("Profile", "Curve"):
                    other_index, main_index = 1, 0
                    targets = c.listConnections(pc + ".target[1].targetParentMatrix") or []
                    if not targets:
                        continue
                position = c.xform(main, query=True, worldSpace=True, translation=True)
                other_position = c.xform(targets[0], query=True, worldSpace=True, translation=True)
                distance = dist(position, other_position)
                inner = c.listRelatives(main, children=True)[0]
                points = [c.xform(f"{inner}.cv[{index}]", query=True,
                                   worldSpace=True, translation=True) for index in range(3)]
                height, width = dist(points[0], points[1]), dist(points[1], points[2])
                if len(aliases) < 2:
                    continue
                weight = min((height + width) / 4 / distance, .45)
                row = SkinCageWidthInput(profile, pc, sc, aliases[main_index], aliases[other_index],
                                         aliases[main_index], aliases[other_index], height, width, distance)
                for constraint in (pc, sc):
                    c.setAttr(constraint + "." + aliases[other_index], weight)
                    c.setAttr(constraint + "." + aliases[main_index], 1 - weight)
                written.append(SkinCageWidthSpec(row, weight))
        cage = self._name("skinCage")
        if not c.objExists(cage + ".deformationWidth"):
            c.addAttr(cage, longName="deformationWidth", attributeType="bool", defaultValue=1, keyable=False)
        return tuple(written)

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
        cage_root = self._name("Root_M_middleCurve")
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

    def preflight_groin_adjustment(self) -> bool:
        c = self.cmds
        return all(c.objExists(self._name(leaf)) for leaf in (
            "Root_M_middleCurve", "Hip_R_startProfileShape"))

    def finish_groin_adjustment(self, *, skipped: bool = False) -> None:
        c = self.cmds
        for leaf in ("GroinStart", "GroinSide"):
            if c.objExists(self._name(leaf)):
                c.delete(self._name(leaf))
        if skipped:
            c.warning("Skipped, because required profile-curves not found")

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
        root_position = c.xform(root, query=True, worldSpace=True,
                                translation=True)
        c.xform(root, worldSpace=True,
                translation=(0, plan.side_y, root_position[2]))
        for source_leaf, source_index, target_indices, target_leaf, factor in (
                ("Root_M_middleCurve", 2, (3,), "Hip_R_startProfileShape", 1.0),
                ("Root_M_middleProfileShape", 2, (3,), "Hip_R_middleProfileShape", .95),
                ("Root_M_middleCurve", 1, (0, 4), "Hip_R_startProfileShape", 1.0),
                ("Root_M_middleProfileShape", 1, (0, 4), "Hip_R_middleProfileShape", .95)):
            point = c.xform(f"{self._name(source_leaf)}.cv[{source_index}]",
                            query=True, worldSpace=True, translation=True)
            for index in target_indices:
                self._groin_set_cv(target_leaf, index,
                                   source=(point[0], point[1] * factor, point[2]))
        for index in (2, 1):
            self._groin_set_cv("Hip_R_middleProfileShape", index,
                               y=plan.start_y * 0.95)
            self._groin_set_cv("Hip_R_startProfileShape", index,
                               x=0.0, y=plan.start_y)
        hip_start = self._name("Hip_R_startProfile")
        c.scale(1.2, 1.2, 1.2, hip_start, relative=True)
        twist_count = int(c.getAttr(self._name("Hip") + ".twistJoints"))
        for index in range(1, twist_count + 1):
            curve = self._name(f"Hip_R_twistProfileShape{index}")
            pos = c.xform(f"{curve}.cv[1]", query=True,
                          worldSpace=True, translation=True)
            if pos[1] > plan.start_y:
                c.move(0, (pos[1] - plan.start_y) * -1.2, 0,
                       f"{curve}.cv[1:2]", relative=True)
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
        for leaf in ("Root_M", "LegLockConstrained"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("创建 Groin_M 前需要完整 SkinCage：" + leaf)
        if c.objExists(self._name("Groin_M")):
            raise ValueError("当前角色已有 Groin_M")

    def create_groin_joint(self) -> None:
        """asCreateGroinJoint uses inner curves and the source OPM helper."""
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        root = self._name("Root_M")
        c.select(root, replace=True)
        groin = c.joint(name=self._name("Groin_M"))
        position = c.xform(root, query=True, worldSpace=True, translation=True)
        c.xform(groin, worldSpace=True,
                translation=(0, position[1] - position[1] / 20, position[2]))
        if c.objExists(self._name("Hip_R_middleProfile")):
            point = c.xform(self._name("Hip_R_startCurveShape") + ".cv[1]",
                            query=True, worldSpace=True, translation=True)
            c.xform(groin, worldSpace=True, translation=(0, point[1], position[2]))
            skin = self._name("skinClusterSkinCage")
            c.skinCluster(skin, edit=True, lockWeights=False, weight=0,
                          addInfluence=groin)
            sampler = self._name("closestSampler")
            if c.objExists(sampler): c.delete(sampler)
            sampler = c.createNode("closestPointOnMesh", name=sampler)
            cage = self._name("skinCage")
            shape = c.listRelatives(cage, shapes=True, noIntermediate=True, type="mesh")[0]
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh", force=True)
            try:
                for side, indices in (("R", (1, 2)), ("L", (0, 3))):
                    for kind in ("start", "middle"):
                        profile = self._name(f"Hip_{side}_startProfile")
                        saved_z = None
                        if kind == "start":
                            saved_z = c.getAttr(profile + ".tz")
                            # posA is overwritten for every sampled CV in MEL;
                            # the left start uses the last right middle's Y.
                            c.setAttr(profile + ".tz", position[1] / 50)
                        try:
                            curve = self._name(f"Hip_{side}_{kind}Curve")
                            for index in indices:
                                position = c.xform(f"{curve}.cv[{index}]", query=True,
                                                    worldSpace=True, translation=True)
                                c.setAttr(sampler + ".inPosition", *position, type="double3")
                                vertex = int(c.getAttr(sampler + ".closestVertexIndex"))
                                component = f"{cage}.vtx[{vertex}]"
                                c.skinPercent(skin, component, transformValue=(groin, 1))
                                if kind == "middle":
                                    c.skinPercent(skin, component,
                                                  transformValue=(self._name("Hip_" + side), .5))
                        finally:
                            if saved_z is not None: c.setAttr(profile + ".tz", saved_z)
            finally:
                c.delete(sampler)
        self._cage_parent_constraint(self._name("LegLockConstrained"), groin)
        if not (c.objExists(self._name("FitSkeleton") + ".useOffsetParentMatrix")
                and c.getAttr(self._name("FitSkeleton") + ".useOffsetParentMatrix")):
            c.parent(groin + "_parentConstraint1", groin + "_scaleConstraint1",
                     self._name("ConstraintSystem"))
        c.select(selection, replace=True) if selection else c.select(clear=True)

    def capture_groin_joint(self) -> bool:
        c = self.cmds
        groin = self._name("Groin_M")
        if not c.objExists(groin): return False
        # Without middleProfile the original deliberately creates only a
        # constrained joint. It does not add a skin influence in that branch.
        if not c.objExists(self._name("Hip_R_middleProfile")):
            return bool(c.listConnections(groin, source=True, destination=False))
        influences = c.ls(c.listConnections(
            self._name("skinClusterSkinCage") + ".matrix") or [], long=True) or []
        return (c.ls(groin, long=True) or [groin])[0] in influences

    def _skin(self, mesh: str) -> str:
        c = self.cmds
        skins = [node for node in c.listHistory(mesh, pruneDagObjects=True) or ()
                 if c.nodeType(node) == "skinCluster"]
        return skins[-1] if skins else ""

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
        self._influences = tuple(c.listConnections(
            self._source_skin + ".matrix") or ())
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
            current = set(c.listConnections(skin + ".matrix") or ())
            for joint in self._influences:
                if joint not in current:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  weight=0.0, lockWeights=False)
        else:
            c.select(list(self._influences), replace=True)
            c.select(target.mesh, add=True)
            from .maya_original_skin_history import new_original_skin_clusters
            skin = new_original_skin_clusters(commands=c, namespace=self.namespace)[0]
        try:
            c.select(self._source_mesh, replace=True)
            c.select(list(target.components) if target.components else
                     target.mesh, add=True)
            c.copySkinWeights(noMirror=True,
                              surfaceAssociation="closestPoint",
                              influenceAssociation="closestJoint")
            c.setAttr(skin + ".skinningMethod",
                      c.getAttr(self._source_skin + ".skinningMethod"))
            from .maya_original_skin_history import remove_unused_for_skin
            remove_unused_for_skin(c, skin)
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
        profiles = []
        for curve in c.listRelatives(root, allDescendents=True, type="transform") or []:
            curve_shapes = c.listRelatives(curve, shapes=True, type="nurbsCurve") or []
            if curve_shapes and c.getAttr(curve + ".v"):
                profiles.append(curve)
        if transforms:
            for curve in profiles:
                position = c.xform(curve, query=True, relative=True, objectSpace=True, translation=True)
                rotation = c.xform(curve, query=True, relative=True, objectSpace=True, rotation=True)
                scale = c.xform(curve, query=True, relative=True, objectSpace=True, scale=True)
                commands.append("xform -os -t {} {} {} -ro {} {} {} -s {} {} {} {}".format(
                    *position, *rotation, *scale, curve))
        if shapes:
            for curve in profiles:
                count = int(c.getAttr(curve + ".spans")) + int(c.getAttr(curve + ".degree"))
                for index in range(count):
                    point = c.getAttr(f"{curve}.controlPoints[{index}]")[0]
                    if any(point):
                        commands.append("setAttr {}.controlPoints[{}] {} {} {}".format(curve, index, *point))
        for command in commands:
            print("catch (`" + command + "`);" if catch
                  else command + ";")
        return len(commands)
