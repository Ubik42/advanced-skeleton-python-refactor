"""Independent Maya processes for the product animation editing chain."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]

from adv_py.application import load_character_animation
from adv_py.core.body_control_spaces import control_space_pose_error
from product_entry_smoke import _hash, _run


def main(mayapy: Path, source: Path, report: Path) -> int:
    source = source.resolve(strict=True)
    original_hash = _hash(source)
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-animation-edit-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        scene = source
        events = []

        def edit(command: str, *options: str):
            nonlocal scene
            output = folder / f"{len(events):02d}-{command}.ma"
            result = _run(mayapy, command, str(scene), "--namespace", ":",
                          *options, "--output", str(output))
            events.append((command, result[0], result[1], result[2][-500:]))
            if result[0] == 0 and output.exists():
                scene = output
            return result

        limb = edit("animation-enable", "--kind", "limb")
        stretch = edit("animation-enable", "--kind", "stretch")
        spaces = edit("animation-enable", "--kind", "spaces")
        key1 = edit("animation-key", "--frame", "1")
        key3 = edit("animation-key", "--frame", "3")
        before_path = folder / "before.json"
        before = _run(mayapy, "animation-capture", str(scene),
            "--namespace", ":", "--start", "1", "--end", "3",
            "--output", str(before_path))
        baked_limb = edit("animation-bake-limb", "--start", "1", "--end", "3",
            "--limb", "arm", "--side", "R", "--mode", "ik")
        baked_spine = edit("animation-bake-spine", "--start", "1", "--end", "3",
            "--mode", "ik")
        switched = edit("animation-switch-space", "--key", "hand_R",
            "--mode", "body", "--frame", "2")
        after_path = folder / "after.json"
        after = _run(mayapy, "animation-capture", str(scene),
            "--namespace", ":", "--start", "1", "--end", "3",
            "--output", str(after_path))
        repeated = _run(mayapy, "animation-switch-space", str(scene),
            "--namespace", ":", "--key", "head", "--mode", "body",
            "--frame", "2", "--output", str(scene))
        error = None
        if before_path.exists() and after_path.exists():
            original = load_character_animation(before_path)
            edited = load_character_animation(after_path)
            if len(original.samples) == len(edited.samples):
                error = max(control_space_pose_error(left.body_frames,
                    right.body_frames) for (_, left), (_, right) in zip(
                        original.samples, edited.samples))
        checks = {
            "independent_edit_chain": all(event[1] == 0 for event in events)
                and all(event[2] is not None for event in events),
            "full_key_channels": key1[1] is not None
                and key1[1].get("channels", 0) >= 300
                and key3[1] is not None
                and key3[1].get("channels") == key1[1]["channels"],
            "range_modes": baked_limb[1] is not None
                and baked_limb[1].get("frames") == 3
                and baked_spine[1] is not None
                and baked_spine[1].get("frames") == 3,
            "space_event": switched[1] is not None
                and switched[1].get("mode") == "body",
            "reopened_body_pose_preserved": before[0] == 0 and after[0] == 0
                and error is not None and error < 1e-4,
            "refuses_existing_output": repeated[0] == 2,
            "input_scene_unchanged": _hash(source) == original_hash,
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed",
                   "max_body_matrix_error": error}
        if not all(checks.values()):
            payload["diagnostics"] = {"events": events,
                "before": before[2][-500:], "after": after[2][-500:],
                "repeated": repeated[2][-500:]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
