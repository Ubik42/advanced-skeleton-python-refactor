"""Portable sculpt asset export/import/build across Maya processes."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]

from adv_py.core.character_registry import digest
from adv_py.core import merge_face_target_assets
from adv_py.application import load_face_target_asset, save_face_target_asset
from product_entry_smoke import _hash, _run


def _inspect(mayapy: Path, scene: Path, built: bool,
             merged_asset: Path | None = None):
    process = subprocess.run([str(mayapy), str(ROOT / "validation" /
        "maya_face_asset_inspect.py"), str(scene),
        "merged" if merged_asset else "built" if built else "imported",
        *([str(merged_asset)] if merged_asset else [])], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120)
    rows = []
    for line in process.stdout.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get("status") == "ok":
                rows.append(value)
        except ValueError:
            pass
    return process.returncode, rows[-1] if rows else None, process.stderr


def main(mayapy: Path, source: Path, report: Path) -> int:
    source = source.resolve(strict=True)
    source_hash = _hash(source)
    with tempfile.TemporaryDirectory(prefix="adv-py-face-asset-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        asset_path = folder / "smile.asset.json"
        imported_scene = folder / "imported.ma"
        built_scene = folder / "built.ma"
        refused_scene = folder / "refused.ma"
        exported = _run(mayapy, "face-asset-export", str(source),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--name", "smile_R", "--kind", "expression",
            "--target", "|SmileTarget", "--frame", "1",
            "--output", str(asset_path))
        library = folder / "library"
        registered = _run(Path(sys.executable), "face-library-add",
            "--library", str(library), "--asset", str(asset_path),
            "--release", "1.0.0")
        listed = _run(Path(sys.executable), "face-library-list",
            "--library", str(library))
        resolved_path = folder / "resolved.asset.json"
        resolved = _run(Path(sys.executable), "face-library-export",
            "--library", str(library), "--name", "smile_R",
            "--release", "1.0.0", "--output", str(resolved_path))
        changed_path = folder / "changed.asset.json"
        other_path = folder / "other.asset.json"
        if asset_path.exists():
            original = load_face_target_asset(asset_path)
            first = original.deltas[0]
            changed = replace(original, deltas=((first[0], first[1] + .1,
                first[2], first[3]),) + original.deltas[1:])
            save_face_target_asset(changed, changed_path)
            second = original.deltas[1]
            other = replace(original, deltas=(original.deltas[0],
                (second[0], second[1], second[2] + .1, second[3]))
                + original.deltas[2:])
            save_face_target_asset(other, other_path)
        conflict = _run(Path(sys.executable), "face-library-add",
            "--library", str(library), "--asset", str(changed_path),
            "--release", "1.0.0")
        left_added = _run(Path(sys.executable), "face-library-add",
            "--library", str(library), "--asset", str(changed_path),
            "--release", "1.1.0")
        right_added = _run(Path(sys.executable), "face-library-add",
            "--library", str(library), "--asset", str(other_path),
            "--release", "1.2.0")
        merged = _run(Path(sys.executable), "face-library-merge",
            "--library", str(library), "--name", "smile_R",
            "--base", "1.0.0", "--left", "1.1.0", "--right", "1.2.0",
            "--release", "2.0.0")
        merged_path = folder / "merged.asset.json"
        merged_export = _run(Path(sys.executable), "face-library-export",
            "--library", str(library), "--name", "smile_R",
            "--release", "2.0.0", "--output", str(merged_path))
        merged_scene = folder / "merged.ma"
        merged_import = _run(mayapy, "face-asset-import", str(source),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--asset", str(merged_path), "--target", "|MergedSmile",
            "--output", str(merged_scene))
        merged_inspect = (_inspect(mayapy, merged_scene, False, merged_path)
            if merged_scene.exists() else (1, None, "missing merged scene"))
        invalid_path = folder / "wrong-neutral.asset.json"
        if resolved_path.exists():
            invalid = json.loads(resolved_path.read_text(encoding="utf-8"))
            invalid["payload"]["neutral_position_digest"] = "0" * 64
            invalid["digest"] = digest(invalid["payload"])
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
        refused = _run(mayapy, "face-asset-import", str(source),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--asset", str(invalid_path), "--target", "|ImportedSmile",
            "--output", str(refused_scene))
        imported = _run(mayapy, "face-asset-import", str(source),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--asset", str(resolved_path), "--target", "|ImportedSmile",
            "--output", str(imported_scene))
        inspected_import = (_inspect(mayapy, imported_scene, False)
                            if imported_scene.exists() else (1, None, "missing import"))
        specification = folder / "face-build.json"
        specification.write_text(json.dumps({"neutral": "|FaceNeutral",
            "targets": [
                {"name": "smile_R", "kind": "expression",
                 "mesh": "|ImportedSmile"},
                {"name": "viseme_A", "kind": "viseme",
                 "mesh": "|VisemeATarget"}]}), encoding="utf-8")
        built = _run(mayapy, "face-build", str(imported_scene),
            "--namespace", "hero", "--spec", str(specification),
            "--output", str(built_scene))
        inspected_build = (_inspect(mayapy, built_scene, True)
                           if built_scene.exists() else (1, None, "missing build"))
        checks = {
            "exported_sparse_asset_without_mutating_scene": (
                exported[0] == 0 and exported[1] is not None
                and exported[1]["changed_vertices"] == 4
                and asset_path.is_file() and _hash(source) == source_hash),
            "library_resolves_immutable_version": (
                registered[0] == 0 and listed[0] == 0
                and listed[1] is not None and len(listed[1]["assets"]) == 1
                and listed[1]["assets"][0]["valid"]
                and resolved[0] == 0 and resolved_path.is_file()
                and load_face_target_asset(resolved_path)
                    == load_face_target_asset(asset_path)),
            "library_rejects_conflicting_same_version": (
                conflict[0] == 2
                and load_face_target_asset(resolved_path)
                    == load_face_target_asset(asset_path)),
            "library_merges_independent_sculpt_edits": (
                left_added[0] == 0 and right_added[0] == 0
                and merged[0] == 0 and merged_export[0] == 0
                and len(merged[1]["asset"]["parents"]) == 3
                and load_face_target_asset(merged_path) ==
                    merge_face_target_assets(original, changed, other)),
            "merged_asset_imports_matching_geometry": (
                merged_import[0] == 0 and merged_inspect[0] == 0
                and merged_inspect[1] is not None
                and merged_inspect[1]["max_target_error"] < 1e-6
                and merged_inspect[1]["source"] == "portable_asset"),
            "wrong_neutral_rejected_without_output": (
                refused[0] == 2 and not refused_scene.exists()),
            "imported_geometry_matches_original_after_reopen": (
                imported[0] == 0 and inspected_import[0] == 0
                and inspected_import[1] is not None
                and inspected_import[1]["max_target_error"] < 1e-6
                and inspected_import[1]["source"] == "portable_asset"
                and inspected_import[1]["channel"] == "smile_R"),
            "imported_asset_drives_blendshape_after_reopen": (
                built[0] == 0 and inspected_build[0] == 0
                and inspected_build[1] is not None
                and inspected_build[1]["joint_count"] == 72
                and inspected_build[1]["face_channels"] == 2
                and inspected_build[1]["max_target_error"] < 1e-6
                and inspected_build[1]["max_deformation"] > .1),
            "input_scene_unchanged": _hash(source) == source_hash,
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"export": exported[2][-500:],
                "register": registered[2][-500:], "list": listed[2][-500:],
                "resolve": resolved[2][-500:], "conflict": conflict[2][-500:],
                "merged": merged[2][-500:],
                "merged_import": merged_import[2][-500:],
                "merged_inspect": merged_inspect[2][-500:],
                "refuse": refused[2][-500:], "import": imported[2][-500:],
                "inspect_import": inspected_import[2][-500:],
                "build": built[2][-500:],
                "inspect_build": inspected_build[2][-500:]}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
