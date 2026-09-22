"""Validate skin weight product commands across independent Maya processes."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]

from adv_py.core import skin_weight_document_from_json
from product_entry_smoke import _run


def _fixture(original: Path, altered: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        cmds.file(new=True, force=True)
        first = cmds.joint(name="SkinRoot", position=(0, 0, 0))
        second = cmds.joint(name="SkinTip", position=(0, 2, 0))
        cmds.select(clear=True)
        mesh = cmds.polyCylinder(name="SkinMesh", subdivisionsX=8,
                                 subdivisionsY=2, constructionHistory=False)[0]
        skin = cmds.skinCluster(first, second, mesh, name="SkinCluster",
                                maximumInfluences=2, toSelectedBones=True)[0]
        cmds.skinPercent(skin, mesh + ".vtx[0]",
                         transformValue=[(first, .8), (second, .2)])
        cmds.file(rename=str(original))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.skinPercent(skin, mesh + ".vtx[0]",
                         transformValue=[(first, .2), (second, .8)])
        cmds.file(rename=str(altered))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-skin-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        original, altered = folder / "original.ma", folder / "altered.ma"
        setup = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
                                str(original), str(altered)], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
        if setup.returncode:
            raise RuntimeError("fixture failed: " + setup.stderr[-1000:])
        source_hashes = (sha256(original.read_bytes()).hexdigest(),
                         sha256(altered.read_bytes()).hexdigest())
        baseline, changed = folder / "baseline.json", folder / "changed.json"
        restored, reread = folder / "restored.ma", folder / "reread.json"
        export = _run(mayapy, "skin-export", str(original), "--namespace", ":",
                      "--skin", "SkinCluster", "--mesh", "|SkinMesh",
                      "--output", str(baseline))
        collision = _run(mayapy, "skin-export", str(original), "--namespace", ":",
                         "--skin", "SkinCluster", "--mesh", "|SkinMesh",
                         "--output", str(baseline))
        changed_export = _run(mayapy, "skin-export", str(altered),
                              "--namespace", ":", "--skin", "SkinCluster",
                              "--mesh", "|SkinMesh", "--output", str(changed))
        applied = _run(mayapy, "skin-import", str(altered), "--namespace", ":",
                       "--weights", str(baseline), "--output", str(restored))
        reopened = (_run(mayapy, "skin-export", str(restored), "--namespace", ":",
                         "--skin", "SkinCluster", "--mesh", "|SkinMesh",
                         "--output", str(reread)) if restored.exists()
                    else (1, None, "restored scene missing"))
        invalid = folder / "invalid.json"
        invalid.write_text(baseline.read_text(encoding="utf-8").replace(
            '"content_sha256":', '"content_sha256": "bad", "old_digest":'),
            encoding="utf-8")
        refused_scene = folder / "refused.ma"
        refused = _run(mayapy, "skin-import", str(altered), "--namespace", ":",
                       "--weights", str(invalid), "--output", str(refused_scene))
        documents = [skin_weight_document_from_json(path.read_text(encoding="utf-8"))
                     for path in (baseline, changed, reread)] if reread.exists() else []
        checks = {
            "exported_complete_weight_document": export[0] == 0 and bool(documents)
                and len(documents[0].vertices) == documents[0].vertex_count,
            "changed_scene_differs": changed_export[0] == 0 and bool(documents)
                and documents[0] != documents[1],
            "import_restores_weight_values_after_reopen": applied[0] == 0
                and reopened[0] == 0 and bool(documents)
                and documents[0] == documents[2]
                and applied[1] is not None and applied[1]["changed_vertices"] >= 1,
            "existing_export_is_not_overwritten": collision[0] == 2,
            "invalid_document_is_rejected_without_scene": refused[0] == 2
                and not refused_scene.exists(),
            "source_scenes_unchanged": source_hashes == (
                sha256(original.read_bytes()).hexdigest(),
                sha256(altered.read_bytes()).hexdigest()),
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {name: result[2][-700:] for name, result in
                (("export", export), ("changed_export", changed_export),
                 ("applied", applied), ("reopened", reopened),
                 ("refused", refused))}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
