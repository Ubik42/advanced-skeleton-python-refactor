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
        skin_clusters = tuple(cmds.ls(type="skinCluster") or ())
        skin_details = []
        if skin_clusters:
            from maya.api import OpenMaya as om
            from maya.api import OpenMayaAnim as oma
        for skin in skin_clusters:
            geometry = tuple(cmds.skinCluster(
                skin, query=True, geometry=True) or ())
            detail = {
                "name": skin,
                "influences": tuple(cmds.skinCluster(
                    skin, query=True, influence=True) or ()),
                "geometry": geometry,
            }
            if len(geometry) == 1:
                shape = (cmds.ls(geometry[0], long=True) or [""])[0]
                vertex_count = int(cmds.polyEvaluate(shape, vertex=True))
                skin_selection = om.MSelectionList()
                skin_selection.add(skin)
                mesh_selection = om.MSelectionList()
                mesh_selection.add(shape)
                skin_fn = oma.MFnSkinCluster(
                    skin_selection.getDependNode(0))
                component_fn = om.MFnSingleIndexedComponent()
                component = component_fn.create(om.MFn.kMeshVertComponent)
                component_fn.setCompleteData(vertex_count)
                values, count = skin_fn.getWeights(
                    mesh_selection.getDagPath(0), component)
                influences = skin_fn.influenceObjects()
                detail["vertex_count"] = vertex_count
                detail["weight_mass"] = {
                    influence.fullPathName().rsplit("|", 1)[-1]:
                    sum(values[index] for index in range(
                        offset, len(values), count))
                    for offset, influence in enumerate(influences)
                }
                detail["weight_mass_total"] = sum(
                    detail["weight_mass"].values())
                detail["normalization_error"] = max(
                    abs(sum(values[index:index + count]) - 1.0)
                    for index in range(0, len(values), count))
            skin_details.append(detail)
        skin_fit_coverage = None
        if len(fit_roots) == 1 and len(skin_details) == 1:
            try:
                from adv_py.adapters.maya_body import MayaBodyBuildHost
                from adv_py.application.fit_symmetry import PlanFitSymmetry

                planned = PlanFitSymmetry(MayaBodyBuildHost()).execute(
                    fit_roots[0])
                names = {item.output_name for item in planned.instances}
                masses = skin_details[0].get("weight_mass", {})
                unmatched = {name: mass for name, mass in masses.items()
                             if name not in names}
                total = float(sum(masses.values()))
                skin_fit_coverage = {
                    "planned_body_count": len(planned.instances),
                    "exact_influence_count": len(masses) - len(unmatched),
                    "unmatched_influence_count": len(unmatched),
                    "unmatched_weight_mass": sum(unmatched.values()),
                    "unmatched_weight_fraction": (
                        sum(unmatched.values()) / total if total else 0.0),
                    "largest_unmatched": tuple(sorted(
                        unmatched.items(), key=lambda item: -item[1])[:20]),
                }
            except Exception as exc:
                skin_fit_coverage = {
                    "error": f"{type(exc).__name__}: {exc}"}
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
            "skin_clusters": tuple(skin_details),
            "skin_fit_coverage": skin_fit_coverage,
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
