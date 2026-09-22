"""Independent-process product flow for body pose, animation and presets."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]

from adv_py.application import (load_character_animation, load_character_pose,
                                save_character_pose)
from adv_py.core.character_pose import character_pose_error
from product_entry_smoke import _hash, _run


def main(mayapy: Path, pose_scene: Path, target_pose: Path,
         animation_scene: Path, report: Path) -> int:
    pose_scene = pose_scene.resolve(strict=True)
    target_pose = target_pose.resolve(strict=True)
    animation_scene = animation_scene.resolve(strict=True)
    hashes = (_hash(pose_scene), _hash(animation_scene))
    with tempfile.TemporaryDirectory(prefix="adv-py-body-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        preset_dir = folder / "presets"
        preset_dir.mkdir()
        shutil.copy2(target_pose, preset_dir / "target.pose.json")
        shutil.copy2(animation_scene.parent / "animation.json",
                     preset_dir / "walk.animation.json")
        (preset_dir / "unrelated.json").write_text('{"format":"other"}',
                                                      encoding="utf-8")
        inspected = _run(mayapy, "presets", str(pose_scene),
                         "--namespace", ":", "--directory", str(preset_dir))
        captured_pose_path = folder / "current.pose.json"
        captured_pose = _run(mayapy, "pose-capture", str(pose_scene),
            "--namespace", ":", "--frame", "1", "--output",
            str(captured_pose_path))
        pose_output = folder / "posed.ma"
        applied_pose = _run(mayapy, "pose-apply", str(pose_scene),
            "--namespace", ":", "--pose", str(target_pose),
            "--output", str(pose_output))
        reopened_pose_path = folder / "reopened.pose.json"
        reopened_pose = (_run(mayapy, "pose-capture", str(pose_output),
            "--namespace", ":", "--output", str(reopened_pose_path))
            if pose_output.exists() else (1, None, "pose output missing"))
        bad_pose = replace(load_character_pose(target_pose), compatibility="0" * 64)
        bad_path = folder / "invalid.pose.json"
        save_character_pose(bad_pose, bad_path)
        refused_path = folder / "refused.ma"
        refused = _run(mayapy, "pose-apply", str(pose_scene),
            "--namespace", ":", "--pose", str(bad_path),
            "--output", str(refused_path))
        clip_path = folder / "captured.animation.json"
        captured_animation = _run(mayapy, "animation-capture",
            str(animation_scene), "--namespace", ":", "--start", "1",
            "--end", "21", "--step", "5", "--output", str(clip_path))
        animated_output = folder / "animated.ma"
        applied_animation = (_run(mayapy, "animation-apply",
            str(animation_scene), "--namespace", ":", "--clip",
            str(clip_path), "--output", str(animated_output))
            if clip_path.exists() else (1, None, "clip missing"))
        reopened_clip_path = folder / "reopened.animation.json"
        reopened_animation = (_run(mayapy, "animation-capture",
            str(animated_output), "--namespace", ":", "--start", "1",
            "--end", "21", "--step", "5", "--output", str(reopened_clip_path))
            if animated_output.exists() else (1, None, "animation output missing"))
        rebuilt_output = folder / "rebuilt.ma"
        rebuilt = _run(mayapy, "rebuild", str(animation_scene),
            "--namespace", ":", "--replacement", "ProductRebuildStage",
            "--output", str(rebuilt_output))
        rebuilt_clip_path = folder / "rebuilt.animation.json"
        rebuilt_animation = (_run(mayapy, "animation-capture",
            str(rebuilt_output), "--namespace", ":", "--start", "1",
            "--end", "21", "--step", "5", "--output", str(rebuilt_clip_path))
            if rebuilt_output.exists() else (1, None, "rebuild output missing"))
        presets = inspected[1]["presets"] if inspected[1] else []
        rows = {row["filename"]: row for row in presets}
        pose_error = (character_pose_error(load_character_pose(target_pose),
            load_character_pose(reopened_pose_path))
            if reopened_pose_path.exists() else None)
        prior_error = (max(abs(a - b) for (_, a), (_, b) in zip(
            load_character_pose(target_pose).channels,
            load_character_pose(captured_pose_path).channels))
            if captured_pose_path.exists() else None)
        animation_errors = None
        if clip_path.exists() and reopened_clip_path.exists():
            before = load_character_animation(clip_path)
            after = load_character_animation(reopened_clip_path)
            animation_errors = [character_pose_error(a, b) for (_, a), (_, b)
                                in zip(before.samples, after.samples)]
        rebuild_errors = None
        if clip_path.exists() and rebuilt_clip_path.exists():
            before = load_character_animation(clip_path)
            after = load_character_animation(rebuilt_clip_path)
            rebuild_errors = [character_pose_error(a, b) for (_, a), (_, b)
                              in zip(before.samples, after.samples)]
        checks = {
            "preset_directory_reports_compatible_pose": (
                inspected[0] == 0 and rows.get("target.pose.json", {}).get("applicable")
                and rows.get("unrelated.json", {}).get("kind") == "unknown"),
            "captures_actual_perturbed_pose": (
                captured_pose[0] == 0 and prior_error is not None
                and prior_error > .1),
            "applies_pose_and_reopens_matching_body": (
                applied_pose[0] == 0 and reopened_pose[0] == 0
                and pose_error is not None and pose_error < 1e-4),
            "rejects_incompatible_pose_without_output": (
                refused[0] == 2 and not refused_path.exists()),
            "captures_and_applies_full_body_animation": (
                captured_animation[0] == 0 and applied_animation[0] == 0
                and reopened_animation[0] == 0
                and animation_errors is not None and len(animation_errors) == 5
                and max(animation_errors) < 1e-4),
            "rebuild_preserves_full_body_animation": (
                rebuilt[0] == 0 and rebuilt[1] is not None
                and rebuilt[1]["joints"] == 30
                and rebuilt_animation[0] == 0 and rebuild_errors is not None
                and len(rebuild_errors) == 5 and max(rebuild_errors) < 1e-4),
            "source_scenes_unchanged": hashes == (_hash(pose_scene),
                                                   _hash(animation_scene)),
        }
        payload = {**checks, "pose_error": pose_error,
            "max_animation_error": max(animation_errors) if animation_errors else None,
            "max_rebuild_animation_error": max(rebuild_errors) if rebuild_errors else None,
            "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"presets": inspected[2][-500:],
                "pose_capture": captured_pose[2][-500:],
                "pose_apply": applied_pose[2][-500:],
                "pose_reopen": reopened_pose[2][-500:],
                "animation_capture": captured_animation[2][-500:],
                "animation_apply": applied_animation[2][-500:],
                "animation_reopen": reopened_animation[2][-500:],
                "rebuild": rebuilt[2][-500:],
                "rebuild_reopen": rebuilt_animation[2][-500:]}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                          Path(sys.argv[4]), Path(sys.argv[5])))
