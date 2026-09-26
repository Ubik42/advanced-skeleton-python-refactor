"""Move the public source mesh into a newly built character scene."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


def _points(mesh: str):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    dag = selection.getDagPath(0)
    if dag.apiType() == om.MFn.kTransform:
        dag.extendToShape()
    return tuple(tuple(float(axis) for axis in point) for point in
                 om.MFnMesh(dag).getPoints(om.MSpace.kWorld))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_external_mesh import MayaExternalMeshHost
        from adv_py.application.external_mesh_io import (
            ExportExternalMesh, ImportExternalMesh)
        from adv_py.application.external_fit_export import ExportExternalFitSkeleton
        from adv_py.application.fit_skeleton_io import CreateAndImportFitSkeleton
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        shapes = cmds.ls(type="mesh", long=True, noIntermediate=True) or []
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(shapes) != 1 or len(fits) != 1:
            raise ValueError("源场景需要唯一网格和 FitSkeleton")
        source_points = _points(shapes[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh_file = root / "body.ma"
            fit_file = root / "sam.fit.json"
            mesh_result = ExportExternalMesh(MayaExternalMeshHost()).apply(
                shapes[0], mesh_file)
            fit = ExportExternalFitSkeleton(MayaBodyBuildHost()).apply(
                fit_file, fits[0])
            cmds.file(new=True, force=True)
            cmds.upAxis(axis=fit.document.up_axis.value, rotateView=False)
            imported_fit = CreateAndImportFitSkeleton(
                MayaBodyBuildHost()).apply(fit_file)
            built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
                imported_fit.verified.container.path)
            imported = ImportExternalMesh(MayaExternalMeshHost()).apply(mesh_file)
            target_points = _points(imported.mesh)
            maximum_error = max(max(abs(a - b) for a, b in zip(source, target))
                                for source, target in zip(source_points,
                                                          target_points))
            data = {"source": scene.name,
                    "export_vertex_count": mesh_result.vertex_count,
                    "import_vertex_count": imported.vertex_count,
                    "body_count": len(built.registration.body),
                    "maximum_world_point_error": maximum_error}
            data["independent_import"] = not (cmds.file(query=True,
                reference=True) or [])
            output = root / "character-with-mesh.mb"
            cmds.file(rename=str(output))
            cmds.file(save=True, type="mayaBinary")
            cmds.file(str(output), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_mesh_count"] = MayaExternalMeshHost().capture_mesh_vertex_count(
                "advMesh:AdvPy_SourceMesh")
            data["reopen_body_count"] = len(MayaBodyBuildHost().capture_body_skeleton(
                "Root_M").joints)
            cmds.file(new=True, force=True)
        data["status"] = "passed" if (
            data["export_vertex_count"] == 18151
            and data["import_vertex_count"] == 18151
            and data["body_count"] == 74
            and data["maximum_world_point_error"] < 1e-5
            and data["independent_import"]
            and data["reopen_mesh_count"] == 18151
            and data["reopen_body_count"] == 74) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0 if data["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
