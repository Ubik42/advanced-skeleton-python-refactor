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
        result = {"head_vertex_count": int(cmds.polyEvaluate(head, vertex=True)),
                  "head_face_count": int(cmds.polyEvaluate(head, face=True)),
                  "mask_face_count": len(mask_faces), "sides": rows,
                  "face_build_readiness": readiness,
                  "passed": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        print("Imported full-head bilateral Face Fit Maya smoke: OK", flush=True)


if __name__ == "__main__":
    main()
