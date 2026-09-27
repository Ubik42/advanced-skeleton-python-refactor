"""Exercise bilateral eyelid fitting on an imported triangulated head mesh.

Pass a local head OBJ and a two-shell eye OBJ. Neither asset is modified or
copied into this repository.
"""
from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om

from adv_py.adapters.maya_face_pre import MayaFacePreHost
from adv_py.adapters.maya_face_build import MayaFaceBuildHost
from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
from adv_py.application.face_pre import EyeLidLayer, FaceSide
from adv_py.core.face_build_requirements import FaceInclude
from adv_py.core.face_eyelid_fit import order_eye_lid_loop
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.product.maya_panel_controller import MayaPanelController


def mesh_topology(mesh: str):
    selected = om.MSelectionList()
    selected.add(mesh)
    fn = om.MFnMesh(selected.getDagPath(0))
    poly_it = om.MItMeshPolygon(selected.getDagPath(0))
    face_edges = []
    while not poly_it.isDone():
        face_edges.append(tuple(poly_it.getEdges()))
        poly_it.next()
    edge_it = om.MItMeshEdge(selected.getDagPath(0))
    edge_faces = []
    while not edge_it.isDone():
        edge_faces.append(tuple(edge_it.getConnectedFaces()))
        edge_it.next()
    return fn, face_edges, edge_faces


def geodesic_eye_rings(mesh: str, eye: str, side: FaceSide):
    fn, face_edges, edge_faces = mesh_topology(mesh)
    bounds = cmds.exactWorldBoundingBox(eye)
    target = tuple((bounds[index] + bounds[index + 3]) / 2
                   for index in range(3))
    def closed_components(edge_ids):
        edge_ids = tuple(edge_ids)
        vertex_edges = {}
        for edge in edge_ids:
            for vertex in fn.getEdgeVertices(edge):
                vertex_edges.setdefault(vertex, set()).add(edge)
        remaining = set(edge_ids)
        loops = []
        while remaining:
            pending = [next(iter(remaining))]
            component = set()
            while pending:
                edge = pending.pop()
                if edge not in remaining:
                    continue
                remaining.remove(edge)
                component.add(edge)
                for vertex in fn.getEdgeVertices(edge):
                    pending.extend(vertex_edges[vertex] & remaining)
            edges = tuple((index, *fn.getEdgeVertices(index))
                          for index in sorted(component))
            vertices = {vertex for _, first, second in edges
                        for vertex in (first, second)}
            positions = {index: tuple(fn.getPoint(index, om.MSpace.kWorld)[axis]
                                      for axis in range(3)) for index in vertices}
            try:
                order_eye_lid_loop(edges, positions, eye_center_y=target[1],
                                   side=side.value)
            except ValueError:
                continue
            loops.append((tuple(sorted(component)), frozenset(vertices)))
        return loops

    def distance(loop):
        points = [fn.getPoint(index, om.MSpace.kWorld)
                  for index in loop[1]]
        center = tuple(sum(point[axis] for point in points) / len(points)
                       for axis in range(3))
        return sum((center[axis] - target[axis]) ** 2
                   for axis in range(3))
    eye_width = bounds[3] - bounds[0]
    apertures = [loop for loop in closed_components(
        index for index, adjacent in enumerate(edge_faces)
        if len(adjacent) == 1) if distance(loop) < eye_width ** 2]
    if apertures:
        inner = min(apertures, key=distance)
        selected = {face for edge in inner[0] for face in edge_faces[edge]}
        front = set(selected)
        rings = []
        for depth in range(1, 25):
            border = (index for index, adjacent in enumerate(edge_faces)
                      if len(adjacent) == 2
                      and sum(face in selected for face in adjacent) == 1)
            loops = closed_components(border)
            if loops:
                loop = min(loops, key=distance)
                if not (loop[1] & inner[1]):
                    rings.append((depth, *loop))
            next_front = {face for face in front for edge in face_edges[face]
                          for face in edge_faces[edge]} - selected
            if not next_front:
                break
            selected.update(next_front)
            front = next_front
        options = [(outer, main) for outer in rings for main in rings
                   if main[0] >= 2 and outer[0] >= main[0] + 2
                   and not (outer[2] & main[2])]
        if not options:
            raise RuntimeError("眼眶开口向外找不到两圈不相交的眼睑边环")
        outer, main = min(options, key=lambda rows: (
            rows[0][0], rows[1][0]))
        return target, ((outer[0], outer[1]), (main[0], main[1]),
                        (0, inner[0]))
    centers = []
    for face in range(fn.numPolygons):
        vertices = fn.getPolygonVertices(face)
        points = [fn.getPoint(index, om.MSpace.kWorld) for index in vertices]
        center = tuple(sum(point[axis] for point in points) / len(points)
                       for axis in range(3))
        centers.append(center)
    seed = min(range(len(centers)), key=lambda index:
        sum((centers[index][axis] - target[axis]) ** 2
            for axis in range(3)))
    selected = {seed}
    front = {seed}
    candidates = []
    for depth in range(1, 10):
        next_front = set()
        for face in front:
            for edge in face_edges[face]:
                next_front.update(edge_faces[edge])
        next_front -= selected
        selected.update(next_front)
        front = next_front
        if not front:
            break
        border = tuple(sorted(index for index, adjacent in
            enumerate(edge_faces) if sum(face in selected for face in adjacent)
            == 1))
        edges = tuple((index, *fn.getEdgeVertices(index)) for index in border)
        vertices = {vertex for _, first, second in edges
                    for vertex in (first, second)}
        positions = {index: tuple(fn.getPoint(index, om.MSpace.kWorld)[axis]
                                   for axis in range(3)) for index in vertices}
        try:
            order_eye_lid_loop(edges, positions, eye_center_y=target[1],
                               side=side.value)
        except ValueError:
            continue
        if len(edges) >= 8:
            candidates.append((depth, border, frozenset(vertices)))
    if len(candidates) < 3:
        raise RuntimeError("头部眼区找不到三圈可拆分的闭合边环")
    chosen = (candidates[-1], candidates[len(candidates)//2], candidates[0])
    if any(left[2] & right[2] for left, right in
           ((chosen[0], chosen[1]), (chosen[1], chosen[2]),
            (chosen[0], chosen[2]))):
        options = [(outer, main, inner)
                   for outer in candidates for main in candidates
                   for inner in candidates
                   if outer[0] > main[0] > inner[0]
                   and not (outer[2] & main[2] or main[2] & inner[2]
                            or outer[2] & inner[2])]
        if not options:
            raise RuntimeError("眼区找不到三条互不相交的闭合边环："
                               + ", ".join(str(row[0]) for row in candidates))
        chosen = max(options, key=lambda rows: (
            rows[0][0] - rows[2][0],
            min(rows[0][0] - rows[1][0],
                rows[1][0] - rows[2][0])))
    return target, tuple((depth, border) for depth, border, _ in chosen)


def original_eye_rings(mesh: str, eye: str, side: FaceSide,
                       manifest: dict):
    """Map an original right-side Face Fit edge selection to static OBJ edges."""
    fn, _, _ = mesh_topology(mesh)
    positions = [tuple(fn.getPoint(index, om.MSpace.kWorld)[axis]
                       for axis in range(3)) for index in range(fn.numVertices)]
    edge_lookup = {frozenset(fn.getEdgeVertices(index)): index
                   for index in range(fn.numEdges)}
    rings = []
    for layer in ("Outer", "Main", "Inner"):
        selected = []
        for first_point, second_point in manifest["layers"][layer][
                "edge_points_cm"]:
            points = (first_point, second_point)
            candidates = []
            for point in points:
                x, y, z = point
                if side is FaceSide.LEFT:
                    x = -x
                candidates.append({index for index, position in
                    enumerate(positions) if sum((a - b) ** 2 for a, b in
                    zip(position, (x, y, z))) < 1e-6})
            matching = {edge_lookup[frozenset((a, b))]
                        for a in candidates[0] for b in candidates[1]
                        if frozenset((a, b)) in edge_lookup}
            if len(matching) != 1:
                raise RuntimeError("原版 " + layer
                                   + " Fit 边无法映射到静态头部")
            selected.append(next(iter(matching)))
        if len(set(selected)) != len(selected):
            raise RuntimeError("原版 " + layer + " Fit 映射后边重复")
        rings.append((-1, tuple(selected)))
    bounds = cmds.exactWorldBoundingBox(eye)
    target = tuple((bounds[index] + bounds[index + 3]) / 2
                   for index in range(3))
    return target, tuple(rings)


def main() -> None:
    head_source = Path(sys.argv[1]).resolve()
    eyes_source = Path(sys.argv[2]).resolve()
    output = Path(sys.argv[3]).resolve()
    mode = sys.argv[4] if len(sys.argv) > 4 else "independent"
    scene_output = Path(sys.argv[5]).resolve() if len(sys.argv) > 5 else None
    fit_manifest = (json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
                    if len(sys.argv) > 6 and sys.argv[6] != "-" else None)
    post_calibration_fault = (len(sys.argv) > 7 and
                              sys.argv[7] == "post-calibration-fault")
    symmetric = mode in ("symmetric", "symmetric-auto")
    automatic_mirror = mode == "symmetric-auto"
    complex_scene = mode == "complex-skin"
    if not head_source.is_file() or not eyes_source.is_file():
        raise FileNotFoundError("头部或双眼 OBJ 缺失")
    with TemporaryDirectory(prefix="advpy-head-face-") as folder:
        scene = Path(folder) / "head-face-fit.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.loadPlugin("objExport", quiet=True)
        def imported_mesh(source, name):
            nodes = cmds.file(str(source), i=True, type="OBJ",
                              options="mo=1", ignoreVersion=True,
                              returnNewNodes=True)
            shapes = cmds.ls(nodes, long=True, type="mesh",
                             noIntermediate=True) or []
            transforms = {path for shape in shapes for path in
                          (cmds.listRelatives(shape, parent=True,
                                              fullPath=True) or [])}
            if len(transforms) != 1:
                raise RuntimeError("OBJ 必须包含一件网格：" + source.name)
            return (cmds.ls(cmds.rename(next(iter(transforms)), name),
                            long=True, type="transform") or [None])[0]
        head = imported_mesh(head_source, "head")
        eyes = imported_mesh(eyes_source, "eyeOutter")
        split = cmds.polySeparate(eyes, constructionHistory=False)
        eye_meshes = sorted((cmds.ls(item, long=True, type="transform") or [item])[0]
                            for item in split if cmds.objExists(item)
                            and cmds.listRelatives(item, shapes=True,
                                                   type="mesh"))
        if len(eye_meshes) != 2:
            raise RuntimeError("眼球对象必须分成左右两个网格")
        eye_meshes.sort(key=lambda item: cmds.exactWorldBoundingBox(item)[0])
        right_eye, left_eye = eye_meshes
        cmds.select(clear=True)
        head_joint = cmds.joint(name="Head_M", position=(0, 0, 0))
        controller = MayaPanelController()
        fn, _, _ = mesh_topology(head)
        mask_faces = []
        for face in range(fn.numPolygons):
            points = [fn.getPoint(index, om.MSpace.kWorld)
                      for index in fn.getPolygonVertices(face)]
            center_y = sum(point.y for point in points) / len(points)
            center_z = sum(point.z for point in points) / len(points)
            if center_y > -.25 and center_z > 0:
                mask_faces.append(face)
        if len(mask_faces) < 20:
            raise RuntimeError("头部前方 Mask 面不足")
        cmds.select([f"{head}.f[{index}]" for index in mask_faces],
                    replace=True)
        controller.face_pre_record_mask(":")
        cmds.select(head, replace=True)
        controller.face_pre_record_objects(":", "Face", head_joint)
        cmds.select(head, replace=True)
        controller.face_pre_record_objects(":", "AllHead", head_joint)
        rows = []
        for side, eye in ((FaceSide.RIGHT, right_eye),
                          (FaceSide.LEFT, left_eye)):
            if symmetric and side is FaceSide.LEFT:
                continue
            if side is FaceSide.LEFT:
                controller.face_fit_switch_side(":", "Left")
            eye_fit = controller.face_fit_eye_ball(":", eye, head_joint)
            target, rings = (original_eye_rings(
                head, eye, side, fit_manifest)
                if fit_manifest is not None else
                geodesic_eye_rings(head, eye, side))
            for layer, (depth, edges) in zip(("Outer", "Main", "Inner"), rings):
                cmds.select([f"{head}.e[{index}]" for index in edges],
                            replace=True)
                controller.face_fit_eye_lid(":", layer)
                if layer == "Inner":
                    cmds.undo()
                    try:
                        MayaFacePreHost().read_eye_lid_fit(EyeLidLayer.INNER, side)
                    except FitSkeletonValidationError:
                        pass
                    else:
                        raise AssertionError("撤销后 Inner Fit 仍存在")
                    cmds.redo()
                    assert MayaFacePreHost().read_eye_lid_fit(
                        EyeLidLayer.INNER, side)
                assert controller.face_fit_eye_lid_reselect(":", layer) == len(edges)
            host = MayaFacePreHost()
            area, preview = host.read_eye_lid_area()
            rows.append({
                "side": side.value,
                "eye_center_cm": [round(value, 5) for value in target],
                "eye_fit": eye_fit.rsplit("|", 1)[-1],
                "rings": [{"depth": depth, "edge_count": len(edges)}
                          for depth, edges in rings],
                "area_faces": int(cmds.polyEvaluate(area, face=True)),
                "preview_faces": int(cmds.polyEvaluate(preview, face=True)),
            })
        mirror_result = None
        extra_skin = None
        external_driver = None
        external_joint = None
        if complex_scene:
            face_skin = next(item for item in cmds.listHistory(head)
                             if cmds.nodeType(item) == "skinCluster")
            external_joint = cmds.createNode("joint", name="ExternalFaceJoint")
            cmds.skinCluster(face_skin, edit=True,
                             addInfluence=external_joint, weight=0)
            cmds.skinPercent(face_skin, head + ".vtx[0]",
                             transformValue=[(head_joint, .75),
                                             (external_joint, .25)],
                             normalize=True)
            external_driver = cmds.createNode("multiplyDivide",
                                               name="ExternalFaceDriver")
            cmds.setAttr(external_driver + ".input1X", .2)
            cmds.setAttr(external_driver + ".input2X", 2.)
            cmds.connectAttr(external_driver + ".outputX",
                             external_joint + ".translateY")
            accessory = cmds.polyCube(name="UnrelatedAccessory", width=.2,
                                      height=.2, depth=.2,
                                      constructionHistory=False)[0]
            cmds.setAttr(accessory + ".translateX", 30.)
            accessory_joint = cmds.createNode("joint",
                                               name="UnrelatedAccessoryJoint")
            extra_skin = cmds.skinCluster(accessory_joint, accessory,
                                           toSelectedBones=True)[0]
        if symmetric and not automatic_mirror:
            mirror_result = controller.face_fit_mirror_right_to_left(
                ":", left_eye)
            assert mirror_result["mapped_vertices"] >= 20
            assert len(mirror_result["layers"]) == 3
            assert mirror_result["maximum_distance_cm"] \
                <= mirror_result["tolerance_cm"]
            cmds.undo()
            assert not cmds.objExists("FaceFitEyeLidInnerLeft")
            cmds.redo()
            assert MayaFacePreHost().read_eye_lid_fit(
                EyeLidLayer.INNER, FaceSide.LEFT)
        incomplete = controller.face_build_inspect_inputs(":")
        assert not incomplete["ready"] and "FaceFitJaw" in incomplete["missing"]
        assert controller.face_build_set_include(":", FaceInclude.EYES_ONLY.value) \
            == FaceInclude.EYES_ONLY.value
        readiness_after_include = controller.face_build_inspect_inputs(":")
        if automatic_mirror:
            assert not readiness_after_include["ready"]
            assert "LeftEye" in readiness_after_include["missing"]
        else:
            assert readiness_after_include["ready"]
        cmds.undo()
        assert MayaFaceBuildHost().read_include() is FaceInclude.ALL
        cmds.redo()
        assert controller.face_build_inspect_inputs(":")["ready"] \
            is not automatic_mirror
        try:
            MayaFaceEyeLidRigHost().build()
        except FitSkeletonValidationError as error:
            assert "双眼控制" in str(error)
        else:
            raise AssertionError("未建立双眼控制时眼睑构建应被拒绝")
        eye_rig = controller.face_eye_build(":",
            (cmds.ls(head_joint, long=True, type="joint") or [None])[0],
            right_eye, left_eye)
        assert len(eye_rig.skins) == 2
        source_skin = next(item for item in cmds.listHistory(head)
                           if cmds.nodeType(item) == "skinCluster")
        original_weights = MayaDenseSkinHost().capture_dense_skin(source_skin)
        extra_weights = (MayaDenseSkinHost().capture_dense_skin(extra_skin)
                         if complex_scene else None)
        fault_host = MayaFaceEyeLidRigHost()
        original_apply = fault_host.apply_dense_skin
        def injected_failure(data):
            original_apply(data)
            raise RuntimeError("眼睑权重写入故障注入")
        fault_host.apply_dense_skin = injected_failure
        try:
            fault_host.build()
        except RuntimeError as error:
            assert "故障注入" in str(error)
        else:
            raise AssertionError("眼睑构建故障未触发")
        assert not cmds.objExists("FaceMotionSystem")
        if automatic_mirror:
            assert not cmds.objExists("FaceFitEyeLidInnerLeft")
        assert MayaDenseSkinHost().capture_dense_skin(source_skin) == original_weights
        if complex_scene:
            assert MayaDenseSkinHost().capture_dense_skin(extra_skin) == extra_weights
            assert cmds.isConnected(external_driver + ".outputX",
                                    external_joint + ".translateY")
        if post_calibration_fault:
            depth_before = {side: cmds.getAttr(
                "AdvPy_Eye_" + side + ".translateZ")
                for side in ("R", "L")}
            late_fault = MayaFaceEyeLidRigHost()
            original_calibration = late_fault._calibrate_eye_depth
            def injected_late_failure(*args):
                result = original_calibration(*args)
                if result["applied_cm"]:
                    raise RuntimeError("眼球深度校准后故障注入")
                return result
            late_fault._calibrate_eye_depth = injected_late_failure
            try:
                late_fault.build()
            except RuntimeError as error:
                assert "深度校准后故障注入" in str(error)
            else:
                raise AssertionError("眼球深度校准故障未触发")
            assert not cmds.objExists("FaceMotionSystem")
            assert MayaDenseSkinHost().capture_dense_skin(source_skin) \
                == original_weights
            for side, before_depth in depth_before.items():
                assert abs(cmds.getAttr("AdvPy_Eye_" + side
                    + ".translateZ") - before_depth) < 1e-6
        lid_rig = controller.face_build_eye_lids(":")
        if complex_scene:
            assert lid_rig["skin"] == source_skin
            assert MayaDenseSkinHost().capture_dense_skin(extra_skin) == extra_weights
            assert cmds.isConnected(external_driver + ".outputX",
                                    external_joint + ".translateY")
        if automatic_mirror:
            mirror_result = lid_rig["symmetric_mirror"]
            assert mirror_result["mapped_vertices"] == 55
            assert cmds.objExists("FaceFitEyeLidInnerLeft")
        aperture_mode = bool(lid_rig["aperture_sides"])
        expected_control_count = 8
        assert len(lid_rig["controls"]) == expected_control_count
        assert len(lid_rig["eye_controls"]) == 2
        assert len(lid_rig["work_curves"]) == expected_control_count
        assert len(lid_rig["joints"]) >= 16
        eye_depth_after_build = {}
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            alignment = lid_rig["eye_depth_alignment"][side.value]
            assert alignment["applied_cm"] >= 0
            assert alignment["status"] != "not_attempted"
            assert abs(cmds.getAttr("FaceMotionSystem."
                + "advPyEyeDepthCorrection" + suffix[-1])
                - alignment["applied_cm"]) < 1e-6
            if alignment["applied_cm"]:
                assert alignment["status"] == "aligned"
                assert alignment["final_closed_visible"] <= \
                    alignment["initial_closed_visible"]
            if alignment["status"] == "depth_limit_exceeded":
                assert alignment["required_cm"] > alignment["depth_limit_cm"]
            eye_depth_after_build[side.value] = cmds.getAttr(
                "AdvPy_Eye" + suffix + ".translateZ")
            mobile_aperture = (side.value in lid_rig["aperture_sides"]
                and side.value not in lid_rig["stationary_aperture_sides"])
            for outer in ("", "Outer"):
                assert cmds.objExists("ctrlLowerEyeLid" + outer + suffix
                    + "UpwardSum") == mobile_aperture
                assert cmds.objExists("ctrlUpperEyeLid" + outer + suffix
                    + "YawDepthBlink") == mobile_aperture
            for arc in ("Upper", "Lower"):
                assert cmds.objExists("ctrl" + arc + "EyeLidOuter" + suffix
                    + "YawEdgeBlink") == mobile_aperture
            depth = cmds.getAttr("ctrlUpperEyeLid" + suffix
                                 + ".blinkOffsetZ")
            if side.value in lid_rig["stationary_aperture_sides"]:
                assert depth > 0
                roll = sorted((int(node.split("Main", 1)[1].split("_", 1)[0]),
                               cmds.getAttr(node + ".input2X"))
                              for node in cmds.ls(type="multiplyDivide") or []
                              if node.startswith("upperLidMain") and
                              node.endswith(suffix + "BlinkRoll"))
                assert len(roll) >= 3
                assert abs(roll[0][1]) < abs(roll[len(roll)//2][1]) * .1
            else:
                assert abs(depth) < 1e-9
            outer = "ctrlUpperEyeLidOuter" + suffix
            outer_y = cmds.getAttr(outer + ".blinkOffsetY")
            if (side.value in lid_rig["aperture_sides"] and
                    side.value not in lid_rig["stationary_aperture_sides"]):
                assert outer_y < 0
                assert cmds.getAttr("ctrlLowerEyeLidOuter" + suffix
                                    + ".blinkOffsetY") > 0
            else:
                assert abs(outer_y) < 1e-9
        if scene_output is not None:
            scene_output.parent.mkdir(parents=True, exist_ok=True)
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaBinary", force=True)
            copyfile(scene, scene_output)
        skinned = MayaDenseSkinHost().capture_dense_skin(source_skin)
        old_values = memoryview(original_weights.values).cast("d")
        new_values = memoryview(skinned.values).cast("d")
        old_width = len(original_weights.influence_names)
        new_width = len(skinned.influence_names)
        old_indices = [skinned.influence_names.index(name)
                       for name in original_weights.influence_names]
        lid_indices = [skinned.influence_names.index(name) for name in
                       (path.rsplit("|", 1)[-1] for path in
                        lid_rig["joints"].values())]
        changed_vertices = 0
        for vertex in range(original_weights.vertex_count):
            lid_mass = sum(new_values[vertex * new_width + index]
                           for index in lid_indices)
            if lid_mass > 1e-9:
                changed_vertices += 1
            else:
                assert all(abs(new_values[vertex * new_width + target]
                               - old_values[vertex * old_width + source]) < 1e-9
                           for source, target in enumerate(old_indices))
        assert 0 < changed_vertices <= sum(lid_rig["area_vertices"].values())
        aperture_rim = {}
        for side in FaceSide:
            holder = "FaceFitEyeLidInner" + (
                "Left" if side is FaceSide.LEFT else "")
            edge_ids = [int(item.split(".e[")[1][:-1]) for item in
                        (cmds.getAttr(holder + ".selection") or "").split()
                        if ".e[" in item]
            rim_vertices = {vertex for edge in edge_ids
                            for vertex in mesh_topology(head)[0].getEdgeVertices(edge)}
            masses = [sum(new_values[index * new_width + influence]
                          for influence in lid_indices)
                      for index in rim_vertices]
            aperture_rim[side.value] = {
                "vertex_count": len(rim_vertices),
                "weighted_count": sum(value > 1e-6 for value in masses),
                "minimum_weight": round(min(masses), 6),
                "maximum_weight": round(max(masses), 6),
            }
            if side.value in lid_rig["stationary_aperture_sides"]:
                assert aperture_rim[side.value]["weighted_count"] == 0
            elif side.value in lid_rig["aperture_sides"]:
                assert aperture_rim[side.value]["weighted_count"] > 0
        cmds.undo()
        assert not cmds.objExists("FaceMotionSystem")
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            correction = lid_rig["eye_depth_alignment"][side.value][
                "applied_cm"]
            assert abs(cmds.getAttr("AdvPy_Eye" + suffix + ".translateZ")
                       - eye_depth_after_build[side.value] - correction) < 1e-5
        if complex_scene:
            assert MayaDenseSkinHost().capture_dense_skin(extra_skin) == extra_weights
            assert cmds.isConnected(external_driver + ".outputX",
                                    external_joint + ".translateY")
        if automatic_mirror:
            assert not cmds.objExists("FaceFitEyeLidInnerLeft")
        assert len(cmds.skinCluster(lid_rig["skin"], query=True,
                                    influence=True) or []) == old_width
        cmds.redo()
        assert cmds.objExists("FaceMotionSystem")
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            assert abs(cmds.getAttr("AdvPy_Eye" + suffix + ".translateZ")
                       - eye_depth_after_build[side.value]) < 1e-5
            assert abs(cmds.getAttr("FaceMotionSystem."
                + "advPyEyeDepthCorrection" + suffix[-1])
                - lid_rig["eye_depth_alignment"][side.value][
                    "applied_cm"]) < 1e-6
        if complex_scene:
            assert MayaDenseSkinHost().capture_dense_skin(extra_skin) == extra_weights
        if automatic_mirror:
            assert cmds.objExists("FaceFitEyeLidInnerLeft")
        def mesh_points():
            mesh_fn, _, _ = mesh_topology(head)
            return [tuple(point[axis] for axis in range(3))
                    for point in mesh_fn.getPoints(om.MSpace.kWorld)]
        neutral = mesh_points()
        curve_joint_error = max(
            max(abs(cmds.xform(path, query=True, worldSpace=True,
                               translation=True)[axis] - neutral[vertex][axis])
                for axis in range(3))
            for (_side, _layer, _arc, vertex), path in
            lid_rig["joints"].items())
        assert curve_joint_error < 1e-5
        displacement = {}
        for side, layer, arc, amount in (
                (FaceSide.RIGHT, EyeLidLayer.MAIN, "upper", -.05),
                (FaceSide.LEFT, EyeLidLayer.MAIN, "lower", .05),
                (FaceSide.RIGHT, EyeLidLayer.OUTER, "upper", .05)):
            control = lid_rig["controls"][(side, layer, arc)]
            work_curve = lid_rig["work_curves"][(side, layer, arc)]
            middle = len(cmds.ls(work_curve + ".cv[*]", flatten=True)) // 2
            cv = work_curve + ".cv[" + str(middle) + "]"
            neutral_cv = cmds.pointPosition(cv, world=True)
            cmds.setAttr(control + ".translateY", amount)
            moved_cv = cmds.pointPosition(cv, world=True)
            assert abs(moved_cv[1] - neutral_cv[1]) > .005
            moved = mesh_points()
            same_side = [index for index, point in enumerate(neutral)
                         if (point[0] < 0) == (side is FaceSide.RIGHT)]
            opposite = [index for index, point in enumerate(neutral)
                        if (point[0] < 0) != (side is FaceSide.RIGHT)]
            own_delta = max(abs(moved[index][1] - neutral[index][1])
                            for index in same_side)
            other_delta = max(abs(moved[index][1] - neutral[index][1])
                              for index in opposite)
            assert own_delta > .005 and other_delta < 1e-5
            displacement[side.value + layer.value + arc] = round(own_delta, 6)
            cmds.setAttr(control + ".translateY", 0)
            assert abs(cmds.pointPosition(cv, world=True)[1]
                       - neutral_cv[1]) < 1e-5
            reset = mesh_points()
            assert max(abs(reset[index][1]-neutral[index][1])
                       for index in range(len(reset))) < 1e-5
        def middle_gap(side, layer):
            def points(arc):
                curve = lid_rig["work_curves"][(side, layer, arc)]
                return sorted((cmds.pointPosition(cv, world=True)[0],
                               cmds.pointPosition(cv, world=True)[1])
                              for cv in cmds.ls(curve + ".cv[*]", flatten=True))
            upper, lower = points("upper"), points("lower")
            x = (max(upper[0][0], lower[0][0])
                 + min(upper[-1][0], lower[-1][0])) / 2.
            def height(rows):
                for first, second in zip(rows, rows[1:]):
                    if first[0] <= x <= second[0]:
                        t = (x - first[0]) / (second[0] - first[0])
                        return first[1] + t * (second[1] - first[1])
                raise AssertionError("眨眼采样点不在曲线上")
            return height(upper) - height(lower)
        blink_results = {}
        for side in FaceSide:
            eye_control = lid_rig["eye_controls"][side]
            before_gap = middle_gap(side, EyeLidLayer.MAIN)
            before_outer = middle_gap(side, EyeLidLayer.OUTER)
            assert before_gap > .005
            assert before_outer > .005
            cmds.setAttr(eye_control + ".blink", 10)
            after_gap = middle_gap(side, EyeLidLayer.MAIN)
            after_outer = middle_gap(side, EyeLidLayer.OUTER)
            if not aperture_mode:
                assert abs(after_gap) < before_gap * .1
                assert abs(after_outer) < before_outer * .1
            moved = mesh_points()
            own = [index for index, point in enumerate(neutral)
                   if (point[0] < 0) == (side is FaceSide.RIGHT)]
            other = [index for index, point in enumerate(neutral)
                     if (point[0] < 0) != (side is FaceSide.RIGHT)]
            own_delta = max(abs(moved[index][1] - neutral[index][1])
                            for index in own)
            other_delta = max(abs(moved[index][1] - neutral[index][1])
                              for index in other)
            assert own_delta > .005 and other_delta < 1e-5
            blink_results[side.value] = {
                "open_gap_cm": round(before_gap, 6),
                "closed_gap_cm": round(after_gap, 6),
                "outer_open_gap_cm": round(before_outer, 6),
                "outer_closed_gap_cm": round(after_outer, 6),
                "mesh_delta_cm": round(own_delta, 6),
            }
            cmds.setAttr(eye_control + ".blink", 0)
            assert abs(middle_gap(side, EyeLidLayer.MAIN)-before_gap) < 1e-5
        right_curve = lid_rig["work_curves"][(FaceSide.RIGHT,
                                               EyeLidLayer.MAIN, "upper")]
        right_cvs = cmds.ls(right_curve + ".cv[*]", flatten=True)
        follow_cv = right_cvs[len(right_cvs) // 2]
        still_cv = cmds.pointPosition(follow_cv, world=True)
        cmds.setAttr(eye_rig.right_control + ".translateY", .1)
        eye_rotation = cmds.getAttr(eye_rig.right_joint + ".rotateX")
        following_cv = cmds.pointPosition(follow_cv, world=True)
        follow_y = following_cv[1] - still_cv[1]
        assert abs(eye_rotation) > .1 and .001 < abs(follow_y) < .05, (
            eye_rotation, follow_y)
        follow_mesh = mesh_points()
        right_delta = max(abs(follow_mesh[index][1]-neutral[index][1])
                          for index, point in enumerate(neutral) if point[0] < 0)
        left_delta = max(abs(follow_mesh[index][1]-neutral[index][1])
                         for index, point in enumerate(neutral) if point[0] >= 0)
        assert right_delta > .001 and left_delta < 1e-5
        cmds.setAttr(eye_rig.right_control + ".translateY", 0)
        cmds.setAttr(eye_rig.right_control + ".translateX", .1)
        horizontal_rotation = cmds.getAttr(
            eye_rig.right_joint + ".rotateY")
        horizontal_delta = (cmds.pointPosition(follow_cv, world=True)[0]
                            - still_cv[0])
        assert abs(horizontal_rotation) > 1
        eye_bounds = cmds.exactWorldBoundingBox(right_eye)
        assert .001 < abs(horizontal_delta) < eye_bounds[3] - eye_bounds[0]
        cmds.setAttr(eye_rig.right_control + ".translateX", 0)
        upper_control = lid_rig["controls"][(FaceSide.RIGHT,
                                              EyeLidLayer.MAIN, "upper")]
        cmds.setAttr(upper_control + ".fleshy", 0)
        cmds.setAttr(eye_rig.right_control + ".translateY", .1)
        assert abs(cmds.pointPosition(follow_cv, world=True)[1]
                   - still_cv[1]) < 1e-5
        cmds.setAttr(eye_rig.right_control + ".translateY", 0)
        cmds.setAttr(upper_control + ".fleshy", 7)
        cmds.setAttr(lid_rig["eye_controls"][FaceSide.RIGHT] + ".blink", 10)
        closed_still = cmds.pointPosition(follow_cv, world=True)
        cmds.setAttr(eye_rig.right_control + ".translateY", .1)
        closed_following = cmds.pointPosition(follow_cv, world=True)
        assert abs(closed_following[1] - closed_still[1]) < 1e-5
        cmds.setAttr(eye_rig.right_control + ".translateY", 0)
        cmds.setAttr(lid_rig["eye_controls"][FaceSide.RIGHT] + ".blink", 0)
        animated = lid_rig["controls"][(FaceSide.RIGHT,
                                        EyeLidLayer.MAIN, "upper")]
        cmds.setKeyframe(animated, attribute="translateY", time=1, value=0)
        cmds.setKeyframe(animated, attribute="translateY", time=5, value=-.05)
        cmds.setKeyframe(eye_rig.right_control,
                         attribute="translateY", time=1, value=0)
        cmds.setKeyframe(eye_rig.right_control,
                         attribute="translateY", time=5, value=.1)
        eye_animated = lid_rig["eye_controls"][FaceSide.LEFT]
        cmds.setKeyframe(eye_animated, attribute="blink", time=1, value=0)
        cmds.setKeyframe(eye_animated, attribute="blink", time=5, value=10)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        if complex_scene:
            assert MayaDenseSkinHost().capture_dense_skin(extra_skin) == extra_weights
            assert cmds.isConnected(external_driver + ".outputX",
                                    external_joint + ".translateY")
            before_external = mesh_points()[0][1]
            cmds.setAttr(external_driver + ".input1X", .3)
            after_external = mesh_points()[0][1]
            assert abs(after_external - before_external) > .01
            cmds.setAttr(external_driver + ".input1X", .2)
        host = MayaFacePreHost()
        for side in FaceSide:
            for layer in EyeLidLayer:
                assert all(cmds.objExists(path) for path in
                           host.read_eye_lid_fit(layer, side))
            assert all(cmds.objExists(path) for path in
                       host.read_eye_lid_area(side))
        readiness = controller.face_build_inspect_inputs(":")
        assert readiness["ready"] and readiness["required_fit_count"] \
            == (4 if symmetric else 8)
        assert cmds.objExists("FaceMotionSystem")
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            assert abs(cmds.getAttr("AdvPy_Eye" + suffix + ".translateZ")
                       - eye_depth_after_build[side.value]) < 1e-5
        assert len(cmds.skinCluster(lid_rig["skin"], query=True,
                                    influence=True) or []) == old_width + len(lid_rig["joints"])
        cmds.currentTime(1, edit=True)
        frame1 = mesh_points()
        cmds.currentTime(5, edit=True)
        frame5 = mesh_points()
        key_delta = max(abs(frame1[index][1] - frame5[index][1])
                        for index in range(len(frame1))
                        if frame1[index][0] < 0)
        assert key_delta > .005
        assert abs(cmds.getAttr(eye_rig.right_control + ".translateY")-.1) < 1e-6
        assert abs(cmds.getAttr("ctrlEye_L.blink")-10) < 1e-6
        result = {"head_vertex_count": int(cmds.polyEvaluate(head, vertex=True)),
                  "head_face_count": int(cmds.polyEvaluate(head, face=True)),
                  "mask_face_count": len(mask_faces), "sides": rows,
                  "symmetric_mirror": mirror_result,
                  "face_build_readiness": readiness,
                  "eyelid_deformation_cm": displacement,
                  "blink": blink_results,
                  "eye_follow": {"eye_rotate_x_deg": round(eye_rotation, 6),
                                 "curve_delta_y_cm": round(follow_y, 6),
                                 "eye_rotate_y_deg": round(horizontal_rotation, 6),
                                 "curve_delta_x_cm": round(horizontal_delta, 6),
                                 "mesh_delta_y_cm": round(right_delta, 6)},
                  "curve_joint_max_error_cm": round(curve_joint_error, 8),
                  "eyelid_joint_count": len(lid_rig["joints"]),
                  "weighted_vertices": changed_vertices,
                  "stationary_aperture_sides": lid_rig[
                      "stationary_aperture_sides"],
                  "eye_depth_alignment": lid_rig["eye_depth_alignment"],
                  "aperture_rim": aperture_rim,
                  "reopened_animation_delta_cm": round(key_delta, 6),
                  "complex_skin": (complex_scene and {
                      "extra_skin_preserved": True,
                      "external_driver_preserved": True,
                      "external_vertex_delta_cm": round(
                          after_external - before_external, 6)}),
                  "passed": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        print("Imported full-head bilateral Face Fit Maya smoke: OK", flush=True)


if __name__ == "__main__":
    main()
