"""Exercise bilateral eyelid fitting on an imported triangulated head mesh.

Pass a local head OBJ and a two-shell eye OBJ. Neither asset is modified or
copied into this repository.
"""
from __future__ import annotations

import json
from pathlib import Path
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
            candidates.append((depth, border))
    if len(candidates) < 3:
        raise RuntimeError("头部眼区找不到三圈可拆分的闭合边环")
    chosen = (candidates[-1], candidates[len(candidates)//2], candidates[0])
    return target, chosen


def main() -> None:
    head_source = Path(sys.argv[1]).resolve()
    eyes_source = Path(sys.argv[2]).resolve()
    output = Path(sys.argv[3]).resolve()
    if not head_source.is_file() or not eyes_source.is_file():
        raise FileNotFoundError("头部或双眼 OBJ 缺失")
    with TemporaryDirectory(prefix="advpy-head-face-") as folder:
        scene = Path(folder) / "head-face-fit.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.loadPlugin("objExport", quiet=True)
        cmds.file(str(head_source), i=True, type="OBJ", options="mo=1",
                  ignoreVersion=True)
        cmds.file(str(eyes_source), i=True, type="OBJ", options="mo=1",
                  ignoreVersion=True)
        head = (cmds.ls("head", long=True, type="transform") or [None])[0]
        eyes = (cmds.ls("eyeOutter", long=True, type="transform") or [None])[0]
        if not head or not eyes:
            raise RuntimeError("导入文件缺少 head 或 eyeOutter 网格")
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
            if side is FaceSide.LEFT:
                controller.face_fit_switch_side(":", "Left")
            eye_fit = controller.face_fit_eye_ball(":", eye, head_joint)
            target, rings = geodesic_eye_rings(head, eye, side)
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
        incomplete = controller.face_build_inspect_inputs(":")
        assert not incomplete["ready"] and "FaceFitJaw" in incomplete["missing"]
        assert controller.face_build_set_include(":", FaceInclude.EYES_ONLY.value) \
            == FaceInclude.EYES_ONLY.value
        assert controller.face_build_inspect_inputs(":")["ready"]
        cmds.undo()
        assert MayaFaceBuildHost().read_include() is FaceInclude.ALL
        cmds.redo()
        assert controller.face_build_inspect_inputs(":")["ready"]
        source_skin = (cmds.ls(type="skinCluster") or [None])[0]
        original_weights = MayaDenseSkinHost().capture_dense_skin(source_skin)
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
        assert MayaDenseSkinHost().capture_dense_skin(source_skin) == original_weights
        lid_rig = controller.face_build_eye_lids(":")
        assert len(lid_rig["controls"]) == 8
        assert len(lid_rig["joints"]) >= 16
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
        cmds.undo()
        assert not cmds.objExists("FaceMotionSystem")
        assert len(cmds.skinCluster(lid_rig["skin"], query=True,
                                    influence=True) or []) == 1
        cmds.redo()
        assert cmds.objExists("FaceMotionSystem")
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
            cmds.setAttr(control + ".translateY", amount)
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
            reset = mesh_points()
            assert max(abs(reset[index][1]-neutral[index][1])
                       for index in range(len(reset))) < 1e-5
        animated = lid_rig["controls"][(FaceSide.RIGHT,
                                        EyeLidLayer.MAIN, "upper")]
        cmds.setKeyframe(animated, attribute="translateY", time=1, value=0)
        cmds.setKeyframe(animated, attribute="translateY", time=5, value=-.05)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        host = MayaFacePreHost()
        for side in FaceSide:
            for layer in EyeLidLayer:
                assert all(cmds.objExists(path) for path in
                           host.read_eye_lid_fit(layer, side))
            assert all(cmds.objExists(path) for path in
                       host.read_eye_lid_area(side))
        readiness = controller.face_build_inspect_inputs(":")
        assert readiness["ready"] and readiness["required_fit_count"] == 8
        assert cmds.objExists("FaceMotionSystem")
        assert len(cmds.skinCluster(lid_rig["skin"], query=True,
                                    influence=True) or []) == 1 + len(lid_rig["joints"])
        cmds.currentTime(1, edit=True)
        frame1 = mesh_points()
        cmds.currentTime(5, edit=True)
        frame5 = mesh_points()
        key_delta = max(abs(frame1[index][1] - frame5[index][1])
                        for index in range(len(frame1))
                        if frame1[index][0] < 0)
        assert key_delta > .005
        result = {"head_vertex_count": int(cmds.polyEvaluate(head, vertex=True)),
                  "head_face_count": int(cmds.polyEvaluate(head, face=True)),
                  "mask_face_count": len(mask_faces), "sides": rows,
                  "face_build_readiness": readiness,
                  "eyelid_deformation_cm": displacement,
                  "curve_joint_max_error_cm": round(curve_joint_error, 8),
                  "eyelid_joint_count": len(lid_rig["joints"]),
                  "weighted_vertices": changed_vertices,
                  "reopened_animation_delta_cm": round(key_delta, 6),
                  "passed": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        print("Imported full-head bilateral Face Fit Maya smoke: OK", flush=True)


if __name__ == "__main__":
    main()
