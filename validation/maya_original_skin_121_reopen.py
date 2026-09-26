"""Verify the migrated public Skin in a fresh Maya process."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, source_report: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.character_registry import ResolveBodyCharacter

        expected = json.loads(source_report.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        captured = MayaDenseSkinHost().capture_dense_skin("AdvPy_SamSkin")
        shape = (cmds.skinCluster("AdvPy_SamSkin", query=True,
                                  geometry=True) or [])[0]
        shape = (cmds.ls(shape, long=True, type="mesh") or [])[0]
        mesh = (cmds.listRelatives(shape, parent=True, fullPath=True) or [])[0]
        uv_sets = tuple(cmds.polyUVSet(mesh, query=True,
                                       allUVSets=True) or [])
        shaders = tuple(sorted(set(cmds.listConnections(
            shape, type="shadingEngine") or [])))
        data = {
            "scene": scene.name,
            "vertex_count": captured.vertex_count,
            "influence_count": len(captured.influence_names),
            "weight_sha256": sha256(captured.values).hexdigest(),
            "uv_sets": uv_sets,
            "shading_engines": shaders,
            "registered_body_count": len(
                ResolveBodyCharacter(MayaBodyBuildHost()).execute().body),
            "unknown_plugins": cmds.unknownPlugin(query=True,
                                                    list=True) or [],
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if (data["vertex_count"] != expected["vertex_count"]
                or data["influence_count"] != 121
                or data["weight_sha256"] != expected["target_weight_sha256"]
                or tuple(data["uv_sets"]) != tuple(expected["source_uv_sets"])
                or tuple(data["shading_engines"]) != tuple(
                    expected["source_shading_engines"])
                or data["registered_body_count"] != 74
                or "skin_bulk" in data["unknown_plugins"]):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3])))
