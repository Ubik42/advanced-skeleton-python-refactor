"""Compare weights and animated meshes after a skinned FBX round trip."""
from __future__ import annotations

from array import array
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _samples(cmds, mesh: str, count: int):
    indices = (0, count // 2, count - 1,
               *((12743,) if count > 12743 else ()))
    return tuple(tuple(cmds.pointPosition(
        f"{mesh}.vtx[{index}]", world=True)) for index in indices)


def _mesh(cmds, skin: str) -> str:
    shape = (cmds.skinCluster(skin, query=True, geometry=True) or [])[0]
    return (cmds.listRelatives(shape, parent=True,
                               fullPath=True) or [])[0]


def _weight_error(source, target):
    assert source.vertex_count == target.vertex_count
    source_index = {name.rsplit(":", 1)[-1]: index for index, name
                    in enumerate(source.influence_names)}
    target_index = {name.rsplit(":", 1)[-1]: index for index, name
                    in enumerate(target.influence_names)}
    assert source_index.keys() == target_index.keys()
    left = array("d")
    left.frombytes(source.values)
    right = array("d")
    right.frombytes(target.values)
    width = len(source_index)
    return max((abs(left[vertex * width + source_index[name]]
                    - right[vertex * width + target_index[name]]),
                vertex, name,
                left[vertex * width + source_index[name]],
                right[vertex * width + target_index[name]])
        for vertex in range(source.vertex_count)
        for name in source_index)


def _vertex_weights(data, vertex):
    values = array("d")
    values.frombytes(data.values)
    width = len(data.influence_names)
    return {name.rsplit(":", 1)[-1]: value
            for index, name in enumerate(data.influence_names)
            if abs(value := values[vertex * width + index]) > 1e-7}


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.application.body_fbx_export import ExportBodyFbx
        from adv_py.application.body_export_skeleton import (
            BakeBodyExportSkeleton, BuildBodyExportSkeleton)
        from adv_py.application.body_root_motion import BuildBodyRootMotion

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        cmds.currentTime(5)
        cmds.setKeyframe("AdvPy_KneeFK_L", attribute="rotateX",
                         time=5, value=20.0)
        cmds.currentTime(1)
        cmds.delete("|AdvPy_GameRootMotion")
        build_host = MayaBodyBuildHost()
        BuildBodyRootMotion(build_host).apply()
        BuildBodyExportSkeleton(build_host).apply()
        BakeBodyExportSkeleton(build_host).apply(
            start_frame=1, end_frame=5)
        skins = sorted(cmds.ls(type="skinCluster") or [])
        assert len(skins) == 2
        host = MayaDenseSkinHost()
        source = tuple(host.capture_dense_skin(skin) for skin in skins)
        meshes = tuple(_mesh(cmds, skin) for skin in skins)
        before = {}
        for frame in (1, 5):
            cmds.currentTime(frame)
            before[frame] = tuple(_samples(cmds, mesh, data.vertex_count)
                                  for mesh, data in zip(meshes, source))
        source_knee_motion = abs(before[5][0][-1][2]
                                 - before[1][0][-1][2])
        original_scene = cmds.file(query=True, sceneName=True)
        original_skins = tuple(cmds.ls(type="skinCluster") or [])
        original_meshes = tuple(cmds.ls(type="mesh", long=True) or [])

        with tempfile.TemporaryDirectory(prefix="advpy-skinned-fbx-") as temp:
            destination = Path(temp) / "character.fbx"
            result = ExportBodyFbx(MayaBodyBuildHost()).apply(destination,
                start_frame=1, end_frame=5, include_skins=True)
            source_intact = (cmds.file(query=True, sceneName=True)
                == original_scene and tuple(cmds.ls(type="skinCluster") or [])
                == original_skins and tuple(cmds.ls(type="mesh", long=True)
                    or []) == original_meshes
                and all(host.capture_dense_skin(skin)
                    == data for skin, data in zip(skins, source)))
            cmds.file(new=True, force=True)
            cmds.file(str(destination), i=True, type="FBX",
                      ignoreVersion=True, executeScriptNodes=False)
            imported_skins = sorted(cmds.ls(type="skinCluster") or [],
                key=lambda skin: cmds.polyEvaluate(_mesh(cmds, skin),
                                                    vertex=True), reverse=True)
            imported = tuple(host.capture_dense_skin(skin)
                             for skin in imported_skins)
            imported_meshes = tuple(_mesh(cmds, skin)
                                    for skin in imported_skins)
            per_skin = tuple(_weight_error(a, b)
                             for a, b in zip(source, imported))
            affected = max(range(len(per_skin)),
                           key=lambda index: per_skin[index][0])
            weight_detail = per_skin[affected]
            weight_error = weight_detail[0]
            point_error = 0.0
            for frame in (1, 5):
                cmds.currentTime(frame)
                actual = tuple(_samples(cmds, mesh, data.vertex_count)
                    for mesh, data in zip(imported_meshes, imported))
                point_error = max(point_error, *(abs(a - b)
                    for expected_mesh, actual_mesh in zip(before[frame], actual)
                    for expected, observed in zip(expected_mesh, actual_mesh)
                    for a, b in zip(expected, observed)))
            cmds.currentTime(1)
            knee = (cmds.ls("Knee_L", type="joint", long=True) or [])[0]
            driven_vertex = weight_detail[1]
            driven_mesh = imported_meshes[affected]
            before_knee = tuple(cmds.pointPosition(
                f"{driven_mesh}.vtx[{driven_vertex}]", world=True))
            original_position = cmds.getAttr(knee + ".translateX")
            cmds.setKeyframe(knee, attribute="translateX", time=1,
                             value=original_position + 1.0)
            cmds.currentTime(2)
            cmds.currentTime(1)
            after_knee = tuple(cmds.pointPosition(
                f"{driven_mesh}.vtx[{driven_vertex}]", world=True))
            knee_deformation = max(abs(a - b) for a, b
                                   in zip(before_knee, after_knee))
            data = {"source": scene.name,
                    "fbx_bytes": result.artifact.byte_count,
                    "source_intact": source_intact,
                    "imported_joints": len(cmds.ls(type="joint") or []),
                    "imported_skins": len(imported),
                    "vertex_counts": [item.vertex_count
                                      for item in imported],
                    "imported_mesh_names": [mesh.rsplit("|", 1)[-1]
                                            for mesh in imported_meshes],
                    "max_weight_error": weight_error,
                    "max_weight_detail": weight_detail,
                    "source_vertex_weights": _vertex_weights(
                        source[affected], weight_detail[1]),
                    "imported_vertex_weights": _vertex_weights(
                        imported[affected], weight_detail[1]),
                    "max_sampled_world_point_error": point_error,
                    "source_knee_motion_z_cm": source_knee_motion,
                    "knee_deformation_cm": knee_deformation}
            report.write_text(json.dumps(data, indent=2) + "\n",
                              encoding="utf-8")
            if not (source_intact and data["imported_joints"] == 75
                    and len(imported) == 2
                    and data["vertex_counts"] == [18151, 8]
                    and data["imported_mesh_names"] == [
                        "BodyMesh", "GarmentMesh"]
                    and weight_error < 0.002
                    and point_error < 1e-4
                    and source_knee_motion > 0.01
                    and knee_deformation > 0.01):
                raise AssertionError(data)
            return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
