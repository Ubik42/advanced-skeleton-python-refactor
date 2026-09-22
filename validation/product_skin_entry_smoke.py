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
from adv_py.core.skin_weight_io import (SkinWeightPathMapping,
    SkinWeightInfluenceMapping, remap_skin_weight_document)
from product_entry_smoke import _run


def _fixture(original: Path, altered: Path, target: Path) -> None:
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
        cmds.file(new=True, force=True)
        cmds.joint(name="TargetRoot", position=(0, 0, 0))
        cmds.joint(name="TargetTip", position=(0, 2, 0))
        cmds.select(clear=True)
        cmds.polyCylinder(name="TargetMesh", subdivisionsX=8,
                          subdivisionsY=2, constructionHistory=False)
        cmds.file(rename=str(target))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-skin-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        original, altered, target = (folder / name for name in
            ("original.ma", "altered.ma", "target.ma"))
        setup = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
                                str(original), str(altered), str(target)], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
        if setup.returncode:
            raise RuntimeError("fixture failed: " + setup.stderr[-1000:])
        source_hashes = (sha256(original.read_bytes()).hexdigest(),
                         sha256(altered.read_bytes()).hexdigest(),
                         sha256(target.read_bytes()).hexdigest())
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
        mapping_spec = {"target_skin": "TargetSkin", "target_mesh": "|TargetMesh",
            "influences": [{"source": "|SkinRoot", "target": "|TargetRoot"},
                           {"source": "|SkinRoot|SkinTip",
                            "target": "|TargetRoot|TargetTip"}]}
        mapping_path = folder / "target.mapping.json"
        mapping_path.write_text(json.dumps(mapping_spec), encoding="utf-8")
        bound_scene = folder / "target-bound.ma"
        bound = _run(mayapy, "skin-bind", str(target), "--namespace", ":",
            "--mesh", "|TargetMesh", "--influence", "|TargetRoot",
            "--influence", "|TargetRoot|TargetTip", "--skin", "TargetSkin",
            "--max-influences", "2",
            *(["--no-maintain-max-influences"] if documents
              and not documents[0].maintain_maximum_influences else []),
            "--output", str(bound_scene))
        mapped_scene = folder / "target-restored.ma"
        mapped = (_run(mayapy, "skin-import", str(bound_scene),
            "--namespace", ":", "--weights", str(baseline),
            "--mapping", str(mapping_path), "--output", str(mapped_scene))
            if bound_scene.exists() else (1, None, "bound scene missing"))
        mapped_document_path = folder / "target-reread.json"
        mapped_export = (_run(mayapy, "skin-export", str(mapped_scene),
            "--namespace", ":", "--skin", "TargetSkin",
            "--mesh", "|TargetMesh", "--output", str(mapped_document_path))
            if mapped_scene.exists() else (1, None, "mapped scene missing"))
        mapped_document = (skin_weight_document_from_json(
            mapped_document_path.read_text(encoding="utf-8"))
            if mapped_document_path.exists() else None)
        expected_mapping = SkinWeightPathMapping("TargetSkin", "|TargetMesh",
            (SkinWeightInfluenceMapping("|SkinRoot", "|TargetRoot"),
             SkinWeightInfluenceMapping("|SkinRoot|SkinTip",
                                         "|TargetRoot|TargetTip")))
        missing_spec = {**mapping_spec,
            "influences": mapping_spec["influences"][:1]}
        missing_path = folder / "missing.mapping.json"
        missing_path.write_text(json.dumps(missing_spec), encoding="utf-8")
        missing_output = folder / "missing-refused.ma"
        missing = (_run(mayapy, "skin-import", str(bound_scene),
            "--namespace", ":", "--weights", str(baseline),
            "--mapping", str(missing_path), "--allow-unweighted-missing",
            "--output", str(missing_output)) if bound_scene.exists()
            else (1, None, "bound scene missing"))
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
            "cross_character_bind_and_weight_restore": bound[0] == 0
                and mapped[0] == 0 and mapped_export[0] == 0
                and mapped_document is not None and bool(documents)
                and mapped_document == remap_skin_weight_document(
                    documents[0], expected_mapping),
            "weighted_missing_influence_rejected": missing[0] == 2
                and not missing_output.exists(),
            "source_scenes_unchanged": source_hashes == (
                sha256(original.read_bytes()).hexdigest(),
                sha256(altered.read_bytes()).hexdigest(),
                sha256(target.read_bytes()).hexdigest()),
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {name: result[2][-700:] for name, result in
                (("export", export), ("changed_export", changed_export),
                 ("applied", applied), ("reopened", reopened),
                 ("refused", refused), ("bound", bound), ("mapped", mapped),
                 ("mapped_export", mapped_export), ("missing", missing))}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
