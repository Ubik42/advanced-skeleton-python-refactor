"""Build and reopen a complete registered body from a generated Fit scene."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]
from product_entry_smoke import _run


def _fixture(scene: Path, segments: int = 2) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (CreateFitSkeleton,
            BuildSyntheticBodySourceFit, BuildVariableBodySourceFit)

        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        if segments == 0:
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            return
        if segments != 2:
            cmds.namespace(addNamespace="hero")
        host = MayaBodyBuildHost(namespace="hero" if segments != 2 else None)
        container = CreateFitSkeleton(host).apply().state.path
        if segments == 2:
            BuildSyntheticBodySourceFit(host).apply(container)
        else:
            BuildVariableBodySourceFit(host).apply(container,
                spine_segments=segments, with_hand=True)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def _inspect(scene: Path, namespace: str = ":") -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import ResolveBodyCharacter, CaptureBodyCharacterPose

        cmds.file(str(scene), open=True, force=True)
        host = MayaBodyBuildHost(namespace=None if namespace == ":" else namespace)
        registration = ResolveBodyCharacter(host).execute()
        pose = CaptureBodyCharacterPose(host).execute()
        print(json.dumps({"status": "ok", "joints": len(registration.body),
            "channels": len(registration.channels),
            "pose_channels": len(pose.channels),
            "digest": registration.compatibility_digest,
            "body_matrices": [list(joint.matrix) for joint in registration.body],
            "body_names": [joint.path.rsplit("|", 1)[-1]
                           for joint in registration.body],
            "channel_keys": [channel.key for channel in registration.channels],
            "spine_lengths": list(registration.spine.lengths)}), flush=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-body-build-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        source = folder / "fit-only.ma"
        built = folder / "registered-body.ma"
        fixture = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
            str(source)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if fixture.returncode:
            raise RuntimeError("fixture failed: " + fixture.stderr[-1200:])
        original_hash = sha256(source.read_bytes()).hexdigest()
        build = _run(mayapy, "body-build", str(source), "--namespace", ":",
            "--output", str(built))
        inspect = (subprocess.run([str(mayapy), str(Path(__file__)), "--inspect",
            str(built)], cwd=ROOT, capture_output=True, text=True, timeout=120)
            if built.exists() else None)
        details = None
        if inspect:
            for line in reversed(inspect.stdout.splitlines()):
                try:
                    row = json.loads(line)
                    if row.get("status") == "ok":
                        details = row
                        break
                except (ValueError, AttributeError):
                    pass
        checks = {
            "built_from_fit_and_registered": build[0] == 0 and build[1] is not None
                and built.exists() and build[1]["joints"] == 30,
            "reopened_pose_and_registration": inspect is not None
                and inspect.returncode == 0 and details is not None
                and details["joints"] == 30
                and details["channels"] == details["pose_channels"]
                and details["digest"] == build[1]["compatibility_digest"],
            "source_unchanged": original_hash == sha256(source.read_bytes()).hexdigest(),
        }
        variable_source = folder / "variable-fit.ma"
        variable_built = folder / "variable-registered.ma"
        variable_fixture = subprocess.run([str(mayapy), str(Path(__file__)),
            "--fixture", str(variable_source), "4"], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
        if variable_fixture.returncode:
            raise RuntimeError("variable fixture failed: "
                               + variable_fixture.stderr[-1200:])
        variable_hash = sha256(variable_source.read_bytes()).hexdigest()
        variable_build = _run(mayapy, "body-build", str(variable_source),
            "--namespace", "hero", "--spine-segments", "4",
            "--head-aim", "--output", str(variable_built))
        variable_inspect = (subprocess.run([str(mayapy), str(Path(__file__)),
            "--inspect", str(variable_built), "hero"], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
            if variable_built.exists() else None)
        variable_details = None
        if variable_inspect:
            for line in reversed(variable_inspect.stdout.splitlines()):
                try:
                    row = json.loads(line)
                    if row.get("status") == "ok":
                        variable_details = row
                        break
                except (ValueError, AttributeError):
                    pass
        checks["variable_named_character_reopened"] = (
            variable_build[0] == 0 and variable_build[1] is not None
            and variable_inspect is not None and variable_inspect.returncode == 0
            and variable_details is not None and variable_details["joints"] > 70
            and variable_details["channels"] == variable_details["pose_channels"]
            and variable_details["digest"] == variable_build[1]["compatibility_digest"]
            and variable_hash == sha256(variable_source.read_bytes()).hexdigest())
        rejected_output = folder / "rejected.ma"
        rejected = _run(mayapy, "body-build", str(source), "--namespace", ":",
            "--fit", "MissingFit", "--output", str(rejected_output))
        checks["bad_fit_rejected_without_scene"] = (
            rejected[0] == 2 and not rejected_output.exists()
            and original_hash == sha256(source.read_bytes()).hexdigest())
        document = folder / "portable.fit.json"
        exported_fit = _run(mayapy, "fit-export", str(source),
            "--namespace", ":", "--output", str(document))
        empty_source = folder / "empty.ma"
        empty_fixture = subprocess.run([str(mayapy), str(Path(__file__)),
            "--fixture", str(empty_source), "0"], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
        if empty_fixture.returncode:
            raise RuntimeError("empty fixture failed: "
                               + empty_fixture.stderr[-1200:])
        empty_hash = sha256(empty_source.read_bytes()).hexdigest()
        imported_fit_scene = folder / "imported-fit.ma"
        imported_fit = (_run(mayapy, "fit-import", str(empty_source),
            "--namespace", ":", "--document", str(document),
            "--output", str(imported_fit_scene)) if document.exists()
            else (1, None, "fit document missing"))
        rebuilt_scene = folder / "from-imported-fit.ma"
        built_imported = (_run(mayapy, "body-build", str(imported_fit_scene),
            "--namespace", ":", "--output", str(rebuilt_scene))
            if imported_fit_scene.exists() else (1, None, "imported scene missing"))
        rebuilt_inspect = (subprocess.run([str(mayapy), str(Path(__file__)),
            "--inspect", str(rebuilt_scene)], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
            if rebuilt_scene.exists() else None)
        rebuilt_details = None
        if rebuilt_inspect:
            for line in reversed(rebuilt_inspect.stdout.splitlines()):
                try:
                    row = json.loads(line)
                    if row.get("status") == "ok":
                        rebuilt_details = row
                        break
                except (ValueError, AttributeError):
                    pass
        matrix_error = (max(abs(a - b) for left, right in zip(
            details["body_matrices"], rebuilt_details["body_matrices"])
            for a, b in zip(left, right))
            if details and rebuilt_details
            and len(details["body_matrices"]) == len(rebuilt_details["body_matrices"])
            else None)
        spine_error = (max(abs(a - b) for a, b in zip(
            details["spine_lengths"], rebuilt_details["spine_lengths"]))
            if details and rebuilt_details
            and len(details["spine_lengths"]) == len(rebuilt_details["spine_lengths"])
            else None)
        checks["fit_document_to_registered_character"] = (
            exported_fit[0] == 0 and exported_fit[1] is not None
            and imported_fit[0] == 0 and imported_fit[1] is not None
            and built_imported[0] == 0 and built_imported[1] is not None
            and rebuilt_inspect is not None and rebuilt_inspect.returncode == 0
            and details is not None and rebuilt_details is not None
            and rebuilt_details["joints"] == 30
            and rebuilt_details["body_names"] == details["body_names"]
            and rebuilt_details["channel_keys"] == details["channel_keys"]
            and matrix_error is not None and matrix_error < 1e-5
            and spine_error is not None and spine_error < 1e-5
            and empty_hash == sha256(empty_source.read_bytes()).hexdigest())
        portable_pose = folder / "source.pose.json"
        pose_capture = _run(mayapy, "pose-capture", str(built),
            "--namespace", ":", "--output", str(portable_pose))
        posed_scene = folder / "posed-imported.ma"
        pose_apply = (_run(mayapy, "pose-apply", str(rebuilt_scene),
            "--namespace", ":", "--pose", str(portable_pose),
            "--output", str(posed_scene)) if portable_pose.exists()
            and rebuilt_scene.exists() else (1, None, "pose or scene missing"))
        checks["pose_portable_across_fit_roundtrip"] = (
            pose_capture[0] == 0 and pose_apply[0] == 0
            and posed_scene.exists() and details is not None
            and rebuilt_details is not None
            and details["digest"] == rebuilt_details["digest"])
        portable_animation = folder / "source.animation.json"
        animation_capture = _run(mayapy, "animation-capture", str(built),
            "--namespace", ":", "--start", "1", "--end", "2",
            "--output", str(portable_animation))
        animated_scene = folder / "animated-imported.ma"
        animation_apply = (_run(mayapy, "animation-apply", str(rebuilt_scene),
            "--namespace", ":", "--clip", str(portable_animation),
            "--output", str(animated_scene)) if portable_animation.exists()
            and rebuilt_scene.exists() else (1, None, "animation or scene missing"))
        checks["animation_portable_across_fit_roundtrip"] = (
            animation_capture[0] == 0 and animation_apply[0] == 0
            and animated_scene.exists())
        def compact(row):
            return ({key: value for key, value in row.items()
                     if key not in ("body_matrices", "body_names", "channel_keys",
                                    "spine_lengths")} if row else None)
        payload = {**checks, "details": compact(details),
            "variable_details": compact(variable_details),
            "imported_details": compact(rebuilt_details),
            "fit_roundtrip_matrix_error": matrix_error,
            "fit_roundtrip_spine_length_error": spine_error,
            "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"build": build[2][-1200:],
                "inspect": inspect.stderr[-1200:] if inspect else "missing",
                "variable_build": variable_build[2][-1200:],
                "variable_inspect": variable_inspect.stderr[-1200:]
                    if variable_inspect else "missing",
                "rejected": rejected[2][-1200:],
                "fit_export": exported_fit[2][-1200:],
                "fit_import": imported_fit[2][-1200:],
                "imported_build": built_imported[2][-1200:],
                "imported_inspect": rebuilt_inspect.stderr[-1200:]
                    if rebuilt_inspect else "missing",
                "pose_capture": pose_capture[2][-1200:],
                "pose_apply": pose_apply[2][-1200:],
                "animation_capture": animation_capture[2][-1200:],
                "animation_apply": animation_apply[2][-1200:]}
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 2)
    elif sys.argv[1] == "--inspect":
        _inspect(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else ":")
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
