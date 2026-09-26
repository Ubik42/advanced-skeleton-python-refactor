"""Preflight an original Fit scene; optional build edits only unsaved memory."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(scene: Path, report: Path, isolated_build: bool = False) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.body_skeleton import BuildBodySkeleton
        from adv_py.application.oriented_body_skeleton import BuildOrientedBodySkeleton
        from adv_py.application.body_character_rig import BuildBodyCharacterRig
        from adv_py.core.joint_labels import JointLabel
        from adv_py.application.fit_symmetry import PlanFitSymmetry

        if not scene.is_file() or scene.suffix.lower() not in (".ma", ".mb"):
            raise ValueError("输入必须是已有的 Maya 场景文件")
        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fit = cmds.ls("FitSkeleton", type="transform", long=True) or []
        result = {"source": scene.name, "fit_containers": fit,
                  "fit_joint_count": 0, "metadata": {}, "plan": {}}
        if len(fit) == 1:
            host = MayaBodyBuildHost()
            hierarchy = host.capture_fit_hierarchy(fit[0])
            result["fit_joint_count"] = len(hierarchy.joints)
            for node in hierarchy.joints:
                try:
                    meta = host.read_fit_joint_metadata(node.path)
                    result["metadata"][node.short_name] = {
                        "no_mirror": meta.no_mirror,
                        "no_mirror_left": meta.no_mirror_left,
                        "label": getattr(host.read_joint_label(node.path),
                                         "text", None),
                    }
                except Exception as exc:
                    result["metadata"][node.short_name] = {
                        "error": f"{type(exc).__name__}: {exc}"}
            try:
                plan = PlanFitSymmetry(host).execute(fit[0])
                result["plan"] = {"status": "ready",
                                  "instance_count": len(plan.instances),
                                  "output_names": [item.output_name
                                                   for item in plan.instances]}
            except Exception as exc:
                result["plan"] = {"status": "failed",
                                  "error": f"{type(exc).__name__}: {exc}"}
            try:
                build = BuildBodySkeleton(host).plan(fit[0])
                result["body_build"] = {
                    "ready": build.ready,
                    "missing_labels": [path.rsplit("|", 1)[-1]
                                       for path in build.missing_labels],
                    "name_collisions": list(build.name_collisions),
                    "spec_count": len(build.specs),
                }
            except Exception as exc:
                result["body_build"] = {
                    "error": f"{type(exc).__name__}: {exc}"}
            if isolated_build:
                # The source file stays untouched. Only this unsaved in-memory
                # scene loses the existing rig so names can be built afresh.
                group = (cmds.listRelatives(fit[0], parent=True,
                                            fullPath=True) or [""])[0]
                scene_siblings = (cmds.listRelatives(
                    group, children=True, fullPath=True) or ()) if group else (
                        cmds.ls(assemblies=True, long=True) or ())
                siblings = [path for path in scene_siblings
                            if path != fit[0]]
                cmds.delete(siblings)
                fit_before = {node.short_name: node.world_position
                              for node in hierarchy.joints}
                try:
                    with host.transaction("标注原版 Fit 副本"):
                        for node in hierarchy.joints:
                            if host.read_joint_label(node.path) is None:
                                host.set_joint_label(
                                    node.path, JointLabel.parse(node.short_name))
                    built = BuildOrientedBodySkeleton(host).apply(fit[0])
                    current_fit = host.capture_fit_hierarchy(fit[0])
                    result["isolated_build"] = {
                        "status": "passed",
                        "body_count": len(built.snapshot.joints),
                        "fit_unchanged": fit_before == {
                            node.short_name: node.world_position
                            for node in current_fit.joints},
                    }
                    try:
                        character = BuildBodyCharacterRig(host).plan(
                            fit[0], include_torso=True)
                        result["isolated_build"]["character_plan"] = {
                            "ready": character.ready,
                            "blockers": list(character.blockers),
                        }
                        if character.ready:
                            rig = BuildBodyCharacterRig(host).apply(
                                fit[0], include_torso=True)
                            result["isolated_build"]["character_rig"] = {
                                "status": "passed",
                                "body_count": len(rig.body.joints),
                                "hand_controls": rig.hand is not None,
                                "fit_unchanged": fit_before == {
                                    node.short_name: node.world_position
                                    for node in host.capture_fit_hierarchy(
                                        fit[0]).joints},
                            }
                    except Exception as exc:
                        result["isolated_build"]["character_rig"] = {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}"}
                except Exception as exc:
                    result["isolated_build"] = {
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}"}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          "--isolated-build" in sys.argv[3:]))
