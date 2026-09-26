"""Read-only inventory of an externally supplied AdvancedSkeleton Maya scene."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(scene: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        if not scene.is_file() or scene.suffix.lower() not in (".ma", ".mb"):
            raise ValueError("输入必须是已有的 Maya 场景文件")
        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        joints = tuple(cmds.ls(type="joint", long=True) or ())
        curves = tuple(cmds.ls(type="nurbsCurve", long=True) or ())
        meshes = tuple(cmds.ls(type="mesh", long=True,
                               noIntermediate=True) or ())
        control_transforms = tuple(dict.fromkeys(
            (cmds.listRelatives(shape, parent=True, fullPath=True) or [""])[0]
            for shape in curves))
        top_level = tuple(cmds.ls(assemblies=True, long=True) or ())
        fit_roots = tuple(child for path in top_level
                          for child in (cmds.listRelatives(
                              path, children=True, fullPath=True) or ())
                          if child.rsplit("|", 1)[-1] == "FitSkeleton")
        fit_joints = tuple(path for path in joints if any(
            path.startswith(root + "|") for root in fit_roots))
        namespaces = tuple(cmds.namespaceInfo(
            listOnlyNamespaces=True, recurse=True) or ())
        script_nodes = tuple(cmds.ls(type="script", long=True) or ())
        payload = {
            "source": scene.name,
            "maya_version": cmds.about(version=True),
            "joint_count": len(joints),
            "mesh_count": len(meshes),
            "control_curve_count": len(curves),
            "control_transform_count": len(control_transforms),
            "top_level_nodes": top_level,
            "top_level_children": {
                path: tuple(cmds.listRelatives(
                    path, children=True, fullPath=True) or ())
                for path in top_level},
            "up_axis": cmds.upAxis(query=True, axis=True),
            "linear_unit": cmds.currentUnit(query=True, linear=True),
            "namespaces": namespaces,
            "script_nodes": script_nodes,
            "joint_leaf_names": tuple(path.rsplit("|", 1)[-1]
                                      for path in joints),
            "control_leaf_names": tuple(path.rsplit("|", 1)[-1]
                                        for path in control_transforms),
            "mesh_paths": meshes,
            "fit_joint_count": len(fit_joints),
            "fit_joints": tuple({
                "path": path,
                "parent": (cmds.listRelatives(
                    path, parent=True, fullPath=True) or [""])[0],
                "world_position": tuple(float(value) for value in
                                        cmds.xform(path, query=True,
                                                   worldSpace=True,
                                                   translation=True)),
            } for path in fit_joints),
        }
        report.write_text(json.dumps(
            payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
