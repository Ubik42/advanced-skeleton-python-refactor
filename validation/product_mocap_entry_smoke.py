"""Independent-process FBX import and full FK control retargeting."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples"),
                str(ROOT / "validation")]

from adv_py.application import (load_character_animation,
    save_mocap_mapping_preset)
from adv_py.core import MocapJointMapping, MocapMappingPreset
from product_entry_smoke import _run


def _fixture(scene: Path, source: Path, mapping: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds, mel
        from maya_complete_character import build_character
        from adv_py.application import (EnableBodyCharacterLimbAnimation,
            RegisterBodyCharacter)
        from adv_py.adapters import MayaMocapControlHost

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.loadPlugin("fbxmaya", quiet=True)
        built = build_character(with_hand=False)
        registration = RegisterBodyCharacter(built.host).apply(built.rig)
        EnableBodyCharacterLimbAnimation(MayaMocapControlHost()).apply()
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.namespace(add="TakeA")
        root = cmds.createNode("joint", name="TakeA:Hips", skipSelect=True)
        spine = cmds.createNode("joint", name="TakeA:Spine", parent=root,
                                skipSelect=True)
        chest = cmds.createNode("joint", name="TakeA:Chest", parent=spine,
                                skipSelect=True)
        cmds.setAttr(spine + ".translateY", 5.)
        cmds.setAttr(chest + ".translateY", 5.)
        nodes = {"Hips": root, "Spine": spine, "Chest": chest}
        neck = cmds.createNode("joint", name="TakeA:Neck", parent=chest,
                               skipSelect=True)
        head = cmds.createNode("joint", name="TakeA:Head", parent=neck,
                               skipSelect=True)
        nodes.update(Neck=neck, Head=head)
        for side in ("R", "L"):
            scapula = cmds.createNode("joint", name="TakeA:Scapula_" + side,
                                      parent=chest, skipSelect=True)
            nodes["Scapula_" + side] = scapula
            for limb, parts, parent in (("arm", ("Shoulder", "Elbow", "Wrist"), scapula),
                                         ("leg", ("Hip", "Knee", "Ankle"), root)):
                for part in parts:
                    parent = cmds.createNode("joint", name="TakeA:" + part + "_" + side,
                                             parent=parent, skipSelect=True)
                    cmds.setAttr(parent + ".translateX", 3.)
                    nodes[part + "_" + side] = parent
                if limb == "leg":
                    toe = cmds.createNode("joint", name="TakeA:Toes_" + side,
                                          parent=parent, skipSelect=True)
                    cmds.setAttr(toe + ".translateX", 1.)
                    nodes["Toes_" + side] = toe
        for frame, travel, amount in ((1, 0., 0.), (5, 4., 1.), (10, 9., 2.)):
            cmds.setKeyframe(root, attribute="translateX", time=frame, value=travel)
            cmds.setKeyframe(spine, attribute="rotateZ", time=frame, value=amount * 8.)
            cmds.setKeyframe(chest, attribute="rotateX", time=frame, value=amount * 5.)
            for name in ("Neck", "Head", "Scapula_R", "Scapula_L",
                         "Shoulder_R", "Elbow_R", "Wrist_R",
                         "Hip_L", "Knee_L", "Ankle_L", "Toes_L"):
                cmds.setKeyframe(nodes[name], attribute="rotateZ", time=frame,
                                 value=amount * 6.)
        mappings = [MocapJointMapping("Hips", "Root_M", True, True)]
        mappings.extend(MocapJointMapping(name, target)
            for name, target in (("Spine", "Spine1_M"), ("Chest", "Chest_M"),
                ("Neck", "Neck_M"), ("Head", "Head_M")))
        mappings.extend(MocapJointMapping("Scapula_" + side, "Scapula_" + side)
                        for side in ("R", "L"))
        mappings.extend(MocapJointMapping(part + "_" + side, part + "_" + side)
            for part in ("Shoulder", "Elbow", "Wrist", "Hip", "Knee", "Ankle", "Toes")
            for side in ("R", "L"))
        save_mocap_mapping_preset(MocapMappingPreset("Product full FK",
            tuple(mappings), len(registration.body)), mapping)
        cmds.select(root, replace=True)
        mel.eval("FBXResetExport;")
        mel.eval("FBXExportBakeComplexAnimation -v false;")
        mel.eval("FBXExportInputConnections -v false;")
        mel.eval("FBXExportConstraints -v false;")
        cmds.file(str(source), force=True, options="v=0;", type="FBX export",
                  exportSelected=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-mocap-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        scene, source, mapping = (folder / "character.ma",
                                  folder / "take.fbx", folder / "mapping.json")
        setup = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
                                str(scene), str(source), str(mapping)], cwd=ROOT,
                               capture_output=True, text=True, timeout=180)
        if setup.returncode:
            raise RuntimeError("fixture failed: " + setup.stderr[-1500:])
        hashes = (sha256(scene.read_bytes()).hexdigest(),
                  sha256(source.read_bytes()).hexdigest())
        output = folder / "retargeted.ma"
        applied = _run(mayapy, "mocap-retarget", str(scene), "--namespace", ":",
                       "--source", str(source), "--mapping", str(mapping),
                       "--source-namespace", "ExternalTake", "--start", "1",
                       "--end", "10", "--mode", "fk", "--output", str(output))
        limb_output = folder / "limb-ik.ma"
        limb_ik = _run(mayapy, "mocap-retarget", str(scene), "--namespace", ":",
                       "--source", str(source), "--mapping", str(mapping),
                       "--source-namespace", "LimbTake", "--start", "1",
                       "--end", "10", "--mode", "limb-ik",
                       "--output", str(limb_output))
        full_output = folder / "full-ik.ma"
        full_ik = _run(mayapy, "mocap-retarget", str(scene), "--namespace", ":",
                       "--source", str(source), "--mapping", str(mapping),
                       "--source-namespace", "FullTake", "--start", "1",
                       "--end", "10", "--mode", "full-ik",
                       "--output", str(full_output))
        clip_path = folder / "captured.json"
        captured = (_run(mayapy, "animation-capture", str(output),
                         "--namespace", ":", "--start", "1", "--end", "10",
                         "--step", "3", "--output", str(clip_path))
                    if output.exists() else (1, None, "output missing"))
        limb_clip = folder / "limb-ik.json"
        limb_captured = (_run(mayapy, "animation-capture", str(limb_output),
            "--namespace", ":", "--start", "1", "--end", "10", "--step", "3",
            "--output", str(limb_clip)) if limb_output.exists()
            else (1, None, "limb IK output missing"))
        full_clip = folder / "full-ik.json"
        full_captured = (_run(mayapy, "animation-capture", str(full_output),
            "--namespace", ":", "--start", "1", "--end", "10", "--step", "3",
            "--output", str(full_clip)) if full_output.exists()
            else (1, None, "full IK output missing"))
        characters = (_run(mayapy, "characters", str(output)) if output.exists()
                      else (1, None, "output missing"))
        animation = (load_character_animation(clip_path) if clip_path.exists() else None)
        values = ([dict(pose.channels) for _, pose in animation.samples]
                  if animation else [])
        varying = (sum(any(abs(row[key] - values[0][key]) > 1e-5
                           for row in values[1:]) for key in values[0]) if values else 0)
        ik_clips = [load_character_animation(path) for path in (limb_clip, full_clip)
                    if path.exists()]
        collision_output = folder / "collision.ma"
        collision = _run(mayapy, "mocap-retarget", str(scene), "--namespace", ":",
                         "--source", str(source), "--mapping", str(mapping),
                         "--source-namespace", "UI", "--start", "1", "--end", "10",
                         "--output", str(collision_output))
        checks = {
            "external_fbx_retargeted": applied[0] == 0 and applied[1] is not None
                and applied[1]["source_joints"] == 21 and applied[1]["frames"] == 10,
            "limb_ik_retargeted": limb_ik[0] == 0 and limb_captured[0] == 0
                and limb_output.exists(),
            "full_ik_retargeted": full_ik[0] == 0 and full_captured[0] == 0
                and full_output.exists() and len(ik_clips) == 2,
            "reopened_character_has_animated_controls": captured[0] == 0
                and animation is not None and varying >= 3,
            "source_namespace_saved_with_character": characters[0] == 0
                and characters[1] is not None
                and any(row.get("writable") for row in characters[1]["characters"]),
            "occupied_namespace_rejected": collision[0] == 2
                and not collision_output.exists(),
            "sources_unchanged": hashes == (sha256(scene.read_bytes()).hexdigest(),
                sha256(source.read_bytes()).hexdigest()),
        }
        payload = {**checks, "varying_channels": varying,
            "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"applied": applied[2][-1200:],
                "limb_ik": limb_ik[2][-1200:], "full_ik": full_ik[2][-1200:],
                "limb_captured": limb_captured[2][-700:],
                "full_captured": full_captured[2][-700:],
                "captured": captured[2][-700:], "collision": collision[2][-500:]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
