"""Generate a moved reference and inspect the product's relocated takeover."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, mode: str, output: str | None = None) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost

        manifest_path = folder / "face-reference-relocation-manifest.json"
        if mode == "inspect":
            manifest = json.loads(manifest_path.read_text(encoding="utf8"))
            cmds.file(str(Path(output).resolve()), open=True, force=True)
            reference_node = manifest["node"]
            current = cmds.referenceQuery(reference_node, filename=True,
                                          withoutCopyNumber=True)
            registration = MayaBodyBuildHost(namespace="source").read_character_registration()
            checks = dict(spine_joints=len(registration.spine.body_joints) == 7,
                source_identity=not cmds.namespace(exists="target"),
                reference_loaded=cmds.referenceQuery(reference_node, isLoaded=True),
                replacement_path=Path(current).resolve() == Path(manifest["replacement"]),
                external_connection=cmds.connectionInfo("source:FaceGain.input2X",
                    sourceFromDestination=True) == "external:SharedFaceScale.outputX",
                follower_value=abs(cmds.getAttr(
                    "source:FaceFollower.translateX", time=5) - .75) < 1e-6,
                input_unchanged=sha256(Path(manifest["scene"]).read_bytes()).hexdigest()
                    == manifest["scene_sha256"],
                old_file_missing=not Path(manifest["expected"]).exists())
            print(json.dumps(checks), flush=True)
            return 0 if all(checks.values()) else 1

        if mode != "prepare":
            raise ValueError("mode must be prepare or inspect")
        token = uuid4().hex[:12]
        expected = (folder / f"face-scale-original-{token}.ma").resolve()
        replacement = (folder / f"face-scale-moved-{token}.ma").resolve()
        scene = (folder / f"face-relocation-before-{token}.ma").resolve()
        mapping = (folder / f"face-relocation-map-{token}.json").resolve()
        cmds.file(new=True, force=True)
        driver = cmds.createNode("multiplyDivide", name="SharedFaceScale")
        cmds.setAttr(driver + ".input1X", .75)
        cmds.setAttr(driver + ".input2X", 1.)
        cmds.file(rename=str(expected))
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.file(str(folder / "face-topology-before.ma"), open=True, force=True)
        cmds.lockNode("external:SharedFaceScale", lock=False)
        cmds.delete("external:SharedFaceScale")
        cmds.namespace(removeNamespace=":external")
        cmds.file(str(expected), reference=True, namespace="external")
        cmds.connectAttr("external:SharedFaceScale.outputX",
                         "source:FaceGain.input2X", force=True)
        reference_node = cmds.referenceQuery("external:SharedFaceScale",
                                             referenceNode=True)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        scene_digest = sha256(scene.read_bytes()).hexdigest()
        cmds.file(new=True, force=True)
        expected.rename(replacement)
        digest = sha256(replacement.read_bytes()).hexdigest()
        mapping.write_text(json.dumps({
            "format": "adv_py_reference_relocation", "version": 1,
            "references": [{"node": reference_node,
                            "expected_path": str(expected),
                            "replacement_path": str(replacement),
                            "sha256": digest}]}, ensure_ascii=False, indent=2),
            encoding="utf8")
        bad_digest = folder / f"face-relocation-bad-digest-{token}.json"
        bad_path = folder / f"face-relocation-bad-path-{token}.json"
        document = json.loads(mapping.read_text(encoding="utf8"))
        document["references"][0]["sha256"] = "0" * 64
        bad_digest.write_text(json.dumps(document, ensure_ascii=False, indent=2),
                              encoding="utf8")
        document["references"][0]["sha256"] = digest
        document["references"][0]["expected_path"] = str(replacement)
        bad_path.write_text(json.dumps(document, ensure_ascii=False, indent=2),
                            encoding="utf8")
        manifest = dict(scene=str(scene), expected=str(expected),
            replacement=str(replacement), mapping=str(mapping),
            bad_digest_map=str(bad_digest), bad_path_map=str(bad_path),
            node=reference_node, scene_sha256=scene_digest)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                 encoding="utf8")
        cmds.file(str(scene), open=True, force=True)
        checks = dict(reference_unloaded=not cmds.referenceQuery(
            reference_node, isLoaded=True),
            old_file_missing=not expected.exists(), new_file_exists=replacement.is_file())
        print(json.dumps({"manifest": manifest, "checks": checks},
                         ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), sys.argv[2],
                          sys.argv[3] if len(sys.argv) > 3 else None))
