"""Read-only source-rig evidence for weighted joints outside the new Body plan."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(scene: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.fit_symmetry import PlanFitSymmetry

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        skins = cmds.ls(type="skinCluster") or []
        if len(fits) != 1 or len(skins) != 1:
            raise ValueError("源场景需要唯一 FitSkeleton 和 skinCluster")
        planned = PlanFitSymmetry(MayaBodyBuildHost()).execute(fits[0])
        body_names = {item.output_name for item in planned.instances}
        influences = [cmds.ls(path, type="joint", long=True)[0]
                      for path in cmds.skinCluster(skins[0], query=True,
                                                   influence=True) or []]
        auxiliary = [path for path in influences
                     if path.rsplit("|", 1)[-1] not in body_names]
        rows = []
        for path in auxiliary:
            parent = (cmds.listRelatives(path, parent=True,
                                         fullPath=True) or [None])[0]
            inputs = {}
            for attribute in ("translate", "rotate", "scale", "jointOrient",
                              "offsetParentMatrix"):
                plug = path + "." + attribute
                sources = cmds.listConnections(plug, source=True,
                    destination=False, plugs=True, skipConversionNodes=False) or []
                children = cmds.attributeQuery(attribute, node=path,
                                                listChildren=True) or []
                for child in children:
                    sources.extend(cmds.listConnections(path + "." + child,
                        source=True, destination=False, plugs=True,
                        skipConversionNodes=False) or [])
                if sources:
                    inputs[attribute] = sorted(set(sources))
            constraints = []
            for node in sorted({plug.split(".", 1)[0]
                                for sources in inputs.values()
                                for plug in sources}):
                kind = cmds.nodeType(node)
                query = {"pointConstraint": cmds.pointConstraint,
                         "orientConstraint": cmds.orientConstraint,
                         "parentConstraint": cmds.parentConstraint}.get(kind)
                if query is not None:
                    targets = query(node, query=True, targetList=True) or []
                    aliases = query(node, query=True, weightAliasList=True) or []
                    constraints.append({"node": node, "type": kind,
                        "targets": targets,
                        "weights": [cmds.getAttr(node + "." + alias)
                                    for alias in aliases]})
            rows.append({
                "name": path.rsplit("|", 1)[-1],
                "parent": parent.rsplit("|", 1)[-1] if parent else None,
                "parent_is_body": bool(parent and parent.rsplit("|", 1)[-1]
                                       in body_names),
                "inputs": inputs,
                "constraints": constraints,
                "world_position": cmds.xform(path, query=True,
                                              worldSpace=True, translation=True),
            })
        payload = {
            "source": scene.name,
            "skin": skins[0],
            "planned_body_count": len(body_names),
            "influence_count": len(influences),
            "auxiliary_count": len(rows),
            "direct_body_children": sum(row["parent_is_body"] for row in rows),
            "connected_auxiliary_count": sum(bool(row["inputs"]) for row in rows),
            "auxiliary": rows,
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
