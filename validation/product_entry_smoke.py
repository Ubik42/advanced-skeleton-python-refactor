"""Independent mayapy process validation of the headless user entry."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adv_py.core import (FacePerformance, FaceShapeKind,
                         face_performance_to_json)


def _run(mayapy: Path, *arguments: str):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    process = subprocess.run([str(mayapy), "-m", "adv_py.product", *arguments],
        cwd=ROOT, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120)
    documents = []
    for line in process.stdout.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and "status" in value:
                documents.append(value)
        except ValueError:
            pass
    return process.returncode, documents[-1] if documents else None, process.stderr


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _inspect(mayapy: Path, scene: Path, control: str):
    process = subprocess.run([str(mayapy), str(ROOT / "validation" /
        "maya_product_scene_inspect.py"), str(scene), control],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
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
    unbuilt = source.with_name(source.stem + "-unbuilt.ma")
    unbuilt = unbuilt.resolve(strict=True)
    input_hash = _hash(unbuilt)
    with tempfile.TemporaryDirectory(prefix="adv-py-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        labels = folder / "landmarks.json"
        labels.write_text(json.dumps({"landmarks": [
            {"vertex": 3, "displacement": [0., .2, .1], "radius": 1.}]}),
            encoding="utf-8")
        target_scene = folder / "target.ma"
        built_scene = folder / "built.ma"
        clip_scene = folder / "animated.ma"
        refused_scene = folder / "refused.ma"
        specification = folder / "face-build.json"
        specification.write_text(json.dumps({"neutral": "|FaceNeutral",
            "targets": [
                {"name": "smile_R", "kind": "expression", "mesh": "|SmileTarget"},
                {"name": "viseme_A", "kind": "viseme", "mesh": "|VisemeATarget"},
                {"name": "blink_L", "kind": "expression", "mesh": "|BlinkTarget"},
            ]}), encoding="utf-8")
        discovered = _run(mayapy, "characters", str(unbuilt))
        generated = _run(mayapy, "face-target", str(unbuilt),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--name", "blink_L", "--kind", "expression",
            "--target", "|BlinkTarget", "--landmarks", str(labels),
            "--output", str(target_scene))
        control = (discovered[1]["characters"][0]["face_control"]
                   if discovered[1] and discovered[1].get("characters") else "|MissingControl")
        target_hash = _hash(target_scene) if target_scene.exists() else None
        collision = _run(mayapy, "face-target", str(unbuilt),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--name", "blink_L", "--kind", "expression",
            "--target", "|BlinkTarget", "--landmarks", str(labels),
            "--output", str(target_scene))
        built = _run(mayapy, "face-build", str(target_scene),
            "--namespace", "hero", "--spec", str(specification),
            "--output", str(built_scene))
        built_hash = _hash(built_scene) if built_scene.exists() else None
        wrong = FacePerformance((("viseme_A", FaceShapeKind.VISEME),),
            "ntsc", ((40, (0.,)), (44, (1.,))))
        invalid_clip = folder / "invalid.json"
        invalid_clip.write_text(face_performance_to_json(wrong), encoding="utf-8")
        rejected = _run(mayapy, "face-animation", str(built_scene),
            "--namespace", "hero", "--control", control,
            "--clip", str(invalid_clip), "--output", str(refused_scene))
        valid = FacePerformance((("viseme_A", FaceShapeKind.VISEME),),
            "film", ((40, (0.,)), (44, (1.,))))
        valid_clip = folder / "valid.json"
        valid_clip.write_text(face_performance_to_json(valid), encoding="utf-8")
        applied = _run(mayapy, "face-animation", str(built_scene),
            "--namespace", "hero", "--control", control,
            "--clip", str(valid_clip), "--output", str(clip_scene))
        inspected = (_inspect(mayapy, clip_scene, control)
                     if clip_scene.exists() else (1, None, "output missing"))
        checks = {
            "discovers_only_valid_namespaced_character": (
                discovered[0] == 0 and discovered[1] is not None
                and len(discovered[1]["characters"]) == 1
                and discovered[1]["characters"][0]["namespace"] == "hero"
                and discovered[1]["characters"][0]["writable"]),
            "builds_face_controls_from_target_manifest": (
                built[0] == 0 and built[1] is not None
                and built[1]["channels"] == 3
                and built[1]["max_geometry_delta"] > .1
                and built_scene.is_file() and _hash(target_scene) == target_hash),
            "generates_new_scene_without_overwriting_input": (
                generated[0] == 0 and generated[1] is not None
                and target_scene.is_file()
                and _hash(unbuilt) == input_hash),
            "rejects_existing_output_before_mutation": (
                collision[0] == 2 and target_scene.is_file()
                and target_hash == _hash(target_scene)),
            "rejects_wrong_time_unit_without_output": (
                rejected[0] == 2 and not refused_scene.exists()
                and built_scene.is_file() and built_hash == _hash(built_scene)),
            "applies_clip_to_new_scene": (
                applied[0] == 0 and applied[1] is not None
                and clip_scene.is_file() and built_scene.is_file()
                and built_hash == _hash(built_scene)),
            "fresh_process_reads_target_and_animation": (
                inspected[0] == 0 and inspected[1] is not None
                and inspected[1]["joint_count"] == 72
                and inspected[1]["target_vertices"] == 4
                and inspected[1]["provenance_channel"] == "blink_L"
                and inspected[1]["face_channels"] == 3
                and inspected[1]["mesh_delta"] > .1
                and abs(inspected[1]["viseme_at_44"] - 1.) < 1e-8),
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"discover": discovered[2][-500:],
                "build": built[2][-500:], "generate": generated[2][-500:],
                "collision": collision[2][-500:],
                "reject": rejected[2][-500:],
                "apply": applied[2][-500:], "inspect": inspected[2][-500:]}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
