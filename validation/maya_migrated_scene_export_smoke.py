"""Export referenced-source migrations as independent Maya character scenes."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _points(mesh: str):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    path = selection.getDagPath(0)
    if path.apiType() == om.MFn.kTransform:
        path.extendToShape()
    return tuple((p.x, p.y, p.z) for p in
                 om.MFnMesh(path).getPoints(om.MSpace.kWorld))


def _check(source: Path, output: Path, *, skin_count: int) -> dict:
    from maya import cmds
    from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
    from adv_py.application.character_registry import ResolveBodyCharacter
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController

    cmds.file(str(source.resolve()), open=True, force=True,
              executeScriptNodes=False)
    namespace = "Sam_AdvPy"
    skins = sorted(cmds.ls(namespace + ":*", type="skinCluster") or [])
    assert len(skins) == skin_count
    host = MayaDenseSkinHost()
    before = {skin: host.capture_dense_skin(skin) for skin in skins}
    meshes = ("Sam_AdvPy:AdvPy_MigratedMesh",) + tuple(
        "Sam_AdvPy:AdvPy_MigratedMesh_" + str(index)
        for index in range(2, skin_count + 1))
    cmds.currentTime(5)
    posed = {mesh: _points(mesh) for mesh in meshes}
    cmds.currentTime(1)
    refs = tuple(cmds.file(query=True, reference=True) or [])
    cmds.select("Sam_AdvPy:Root_M", replace=True)
    original_scene = cmds.file(query=True, sceneName=True)
    size = MayaPanelController().publish_migrated_maya_scene(
        namespace, output)
    try:
        MayaPanelController().publish_migrated_maya_scene(namespace, output)
    except ValueError:
        existing_output_rejected = True
    else:
        existing_output_rejected = False
    selection_restored = cmds.ls(selection=True) == ["Sam_AdvPy:Root_M"]
    source_unchanged = (cmds.file(query=True, sceneName=True)
                        == original_scene and tuple(cmds.file(
                        query=True, reference=True) or []) == refs
                        and all(host.capture_dense_skin(skin) == data
                                for skin, data in before.items()))
    cmds.file(str(output), open=True, force=True,
              executeScriptNodes=False)
    exported_refs = tuple(cmds.file(query=True, reference=True) or [])
    after = {skin: host.capture_dense_skin(skin) for skin in skins}
    key_times = tuple(cmds.keyframe(
        "Sam_AdvPy:AdvPy_TorsoRoot_MFK.rotateY", query=True,
        timeChange=True) or [])
    cmds.currentTime(5)
    pose_error = max(abs(a - b) for mesh in meshes
                     for expected, actual in zip(posed[mesh], _points(mesh))
                     for a, b in zip(expected, actual))
    registered = len(ResolveBodyCharacter(MayaBodyBuildHost(
        namespace=namespace)).execute().body)
    result = {"source": source.name, "exported_bytes": size,
              "skins": len(after), "references": len(exported_refs),
              "selection_restored": selection_restored,
              "source_unchanged": source_unchanged,
              "existing_output_rejected": existing_output_rejected,
              "weights_equal": before == after,
              "pose_error": pose_error, "registered_body": registered,
              "root_key_times": key_times}
    if not (size > 100000 and not exported_refs and selection_restored
            and source_unchanged and existing_output_rejected
            and before == after and pose_error < 1e-5
            and registered == 74):
        raise AssertionError(result)
    return result


def main(single: Path, related: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="advpy-scene-export-") as temp:
            results = (_check(single, Path(temp) / "single.mb", skin_count=1),
                _check(related, Path(temp) / "related.mb", skin_count=2))
        report.write_text(json.dumps(results, indent=2) + "\n",
                          encoding="utf-8")
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3])))
