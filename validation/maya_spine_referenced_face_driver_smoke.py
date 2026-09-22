"""Referenced DG driver takeover; requires the generated Face topology fixture."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, inspect_scene: str | None = None) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        external = "external:SharedFaceScale"
        def check():
            reg = MayaBodyBuildHost(namespace="source").read_character_registration()
            source = cmds.connectionInfo("source:FaceGain.input2X",
                                         sourceFromDestination=True)
            return dict(spine_joints=len(reg.spine.body_joints),
                        target_removed=not cmds.namespace(exists="target"),
                        external_referenced=cmds.objExists(external) and
                            cmds.referenceQuery(external, isNodeReferenced=True),
                        external_connection=source == external + ".outputX",
                        external_value=abs(cmds.getAttr(external + ".outputX") - .75) < 1e-6,
                        unrelated_unloaded=cmds.objExists("unrelatedRN") and
                            not cmds.referenceQuery("unrelatedRN", isLoaded=True),
                        follower_value=abs(cmds.getAttr(
                            "source:FaceFollower.translateX", time=5) - .75) < 1e-6,
                        skins_preserved=cmds.objExists("source:SourceSkin") and
                            cmds.objExists("source:FaceSkin"))

        if inspect_scene is not None:
            cmds.file(str(folder / inspect_scene), open=True, force=True)
            state = check()
            good = (state["spine_joints"] == 7 and
                    all(value for key, value in state.items() if key != "spine_joints"))
            print(json.dumps({"valid": good, **state}), flush=True)
            return 0 if good else 1

        asset = folder / "shared-face-scale.ma"
        cmds.file(new=True, force=True)
        node = cmds.createNode("multiplyDivide", name="SharedFaceScale")
        cmds.setAttr(node + ".input1X", .75)
        cmds.setAttr(node + ".input2X", 1.)
        cmds.file(rename=str(asset))
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.file(str(folder / "face-topology-before.ma"), open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.lockNode(external, lock=False)
        cmds.delete(external)
        cmds.namespace(removeNamespace=":external")
        cmds.file(str(asset), reference=True, namespace="external")
        cmds.connectAttr(external + ".outputX", "source:FaceGain.input2X", force=True)
        cmds.file(str(asset), reference=True, namespace="unrelated")
        unrelated_reference = cmds.referenceQuery(
            "unrelated:SharedFaceScale", referenceNode=True)
        cmds.file(unloadReference=unrelated_reference)
        original_uuid = (cmds.ls(external, uuid=True) or [None])[0]
        before = check()
        scene = folder / "face-topology-referenced-before.ma"
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)

        data = json.loads((folder / "face-topology-input.json").read_text(encoding="utf8"))
        args = ("source", "target", (("source:SourceSkin", "|source:SourceMesh"),
                                     ("source:FaceSkin", "|source:FaceNeutral")))
        kwargs = dict(start_frame=1, end_frame=10, max_mesh_error=.2,
            extensions=(data["control"], data["prop"], data["spine_prop"]),
            retained_assets=tuple(data["targets"]),
            retained_graph_roots=(data["driver"],))
        reference_node = cmds.referenceQuery(external, referenceNode=True)
        cmds.file(unloadReference=reference_node)
        unloaded = folder / "face-topology-reference-unloaded-before.ma"
        cmds.file(rename=str(unloaded))
        cmds.file(save=True, type="mayaAscii", force=True)
        try:
            unloaded_replacement = ReplaceRegisteredSpineCharacter(
                MayaOriginalSkinSpineMigrationHost(namespace="target"))
            unloaded_replacement.apply_many(*args, **kwargs)
        except ValueError as error:
            unloaded_rejected = ("角色替换前须加载相关场景引用" in str(error)
                and not cmds.referenceQuery(reference_node, isLoaded=True)
                and len(MayaBodyBuildHost(namespace="source")
                    .read_character_registration().spine.body_joints) == 5)
        else:
            unloaded_rejected = False
        cmds.file(loadReference=reference_node)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        reload_restored = check() == before

        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_promotion(self, plan):
                super().apply_original_spine_promotion(plan)
                raise RuntimeError("Injected failure after referenced driver promotion")

        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()

        try:
            failed_replacement = ReplaceRegisteredSpineCharacter(
                FailedHost(namespace="target"))
            failed_replacement.apply_many(*args, **kwargs)
        except RuntimeError as error:
            rollback = ("Injected failure after referenced driver promotion" in str(error)
                and check() == before and
                (cmds.ls(external, uuid=True) or [None])[0] == original_uuid)
        else:
            rollback = False

        replacement = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace="target"))
        replacement.apply_many(*args, **kwargs)
        passed = check()
        same_uuid = (cmds.ls(external, uuid=True) or [None])[0] == original_uuid
        cmds.undo()
        undo = check() == before
        cmds.redo()
        redo = check() == passed
        output = folder / "face-topology-referenced-replaced.ma"
        cmds.file(rename=str(output))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(output), open=True, force=True)
        reopened = check() == passed and cmds.referenceQuery(
            external, isNodeReferenced=True)
        report = dict(before=before, passed=passed,
                      unloaded_rejected=unloaded_rejected,
                      reload_restored=reload_restored, rollback=rollback,
                      same_external_uuid=same_uuid, undo=undo, redo=redo,
                      reopened=reopened)
        (folder / "face-topology-referenced-result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if (unloaded_rejected and reload_restored and rollback and
            same_uuid and undo and redo and reopened and
            passed["spine_joints"] == 7 and
            all(value for key, value in passed.items() if key != "spine_joints")) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(),
                          sys.argv[2] if len(sys.argv) > 2 else None))
