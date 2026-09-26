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
        from adv_py.adapters.maya_axial_part import MayaAxialPartHost
        from adv_py.adapters.maya_external_mesh import MayaExternalMeshHost
        from adv_py.application.external_mesh_io import (
            ExportExternalMesh, ImportExternalMesh)
        from adv_py.application.external_fit_export import ExportExternalFitSkeleton
        from adv_py.application.fit_skeleton_io import CreateAndImportFitSkeleton
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.character_registry import ResolveBodyCharacter
        from adv_py.application.axial_part_deform import BuildAxialPartDeform

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        shapes = cmds.ls(type="mesh", long=True, noIntermediate=True) or []
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(shapes) != 1 or len(fits) != 1:
            raise ValueError("源场景需要唯一网格和 FitSkeleton")
        source_points = _points(shapes[0])
        part_names = tuple(f"{stem}Part{index}_M" for stem in
                           ("Root", "Spine1", "Neck") for index in (1, 2))
        source_parts = {name: tuple(cmds.xform(name, query=True,
            worldSpace=True, translation=True)) for name in part_names}
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
            parts = BuildAxialPartDeform(MayaAxialPartHost()).apply()
            part_error = max(max(abs(a - b) for a, b in zip(
                source_parts[spec.name], cmds.xform(spec.path, query=True,
                    worldSpace=True, translation=True))) for spec in parts)
            target_points = _points(imported.mesh)
            maximum_error = max(max(abs(a - b) for a, b in zip(source, target))
                                for source, target in zip(source_points,
                                                          target_points))
            data = {"source": scene.name,
                    "export_vertex_count": mesh_result.vertex_count,
                    "import_vertex_count": imported.vertex_count,
                    "body_count": len(built.registration.body),
                    "axial_part_count": len(parts),
                    "axial_part_position_error": part_error,
                    "maximum_world_point_error": maximum_error}
            cmds.undo()
            data["undo_removed_parts"] = all(not cmds.objExists(
                spec.path) for spec in parts)
            data["mesh_survives_undo"] = cmds.objExists(imported.mesh)
            cmds.redo()
            data["redo_restored_parts"] = all(cmds.objExists(
                spec.path) for spec in parts)
            neck_part = next(spec.path for spec in parts
                             if spec.name == "NeckPart1_M")
            before_bend = tuple(cmds.xform(neck_part, query=True,
                                           worldSpace=True, translation=True))
            neck_control = "AdvPy_TorsoNeck_MFK"
            cmds.setAttr(neck_control + ".rotateY", 20.0)
            after_bend = tuple(cmds.xform(neck_part, query=True,
                                          worldSpace=True, translation=True))
            data["neck_part_follows_control"] = max(abs(a - b)
                for a, b in zip(before_bend, after_bend)) > 1e-4
            cmds.setAttr(neck_control + ".rotateY", 0.0)
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
            try:
                resolver = ResolveBodyCharacter(MayaBodyBuildHost())
                names = resolver.discover()
                data["registration_valid"] = (len(names) == 1 and
                    len(resolver.execute(names[0]).body) == 74)
            except Exception as error:
                data["registration_valid"] = False
                data["registration_error"] = str(error)
            data["reopen_part_count"] = sum(bool(cmds.ls(name,
                type="joint")) for name in part_names)
            dummy = cmds.createNode("joint", name="UnmarkedProbeJoint",
                                    parent="Root_M")
            try:
                resolver.execute(names[0])
            except ValueError:
                data["unmarked_joint_rejected"] = True
            else:
                data["unmarked_joint_rejected"] = False
            cmds.delete(dummy)
            cmds.file(new=True, force=True)
        data["status"] = "passed" if (
            data["export_vertex_count"] == 18151
            and data["import_vertex_count"] == 18151
            and data["body_count"] == 74
            and data["axial_part_count"] == 6
            and data["axial_part_position_error"] < 1e-5
            and data["maximum_world_point_error"] < 1e-5
            and data["undo_removed_parts"]
            and data["mesh_survives_undo"]
            and data["redo_restored_parts"]
            and data["neck_part_follows_control"]
            and data["independent_import"]
            and data["reopen_mesh_count"] == 18151
            and data["reopen_body_count"] == 74
            and data["registration_valid"]
            and data["unmarked_joint_rejected"]
            and data["reopen_part_count"] == 6) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0 if data["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
