"""Bound non-spine Body motion during original-Skin FK topology takeover."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, source_count: int, target_count: int) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import (MayaBodyBuildHost,
                                     MayaOriginalSkinSpineMigrationHost)
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        stem = f"spine-{source_count}-to-{target_count}"
        input_scene = folder / f"{stem}-before.ma"
        input_digest = sha256(input_scene.read_bytes()).hexdigest()
        cmds.file(str(input_scene), open=True, force=True)
        cmds.undoInfo(state=True)
        host = MayaOriginalSkinSpineMigrationHost(namespace="target")
        source = host.read_source_character_registration("source")
        target = host.read_character_registration()
        short = lambda path: path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        internal = {short(path) for path in source.spine.body_joints[1:-1]}
        names = tuple(sorted(short(row.path) for row in source.body
                             if short(row.path) not in internal))
        frames = tuple(1 + index * .25 for index in range(37))
        wanted = host.capture_source_registered_spine_body_take(
            "source", source, names, frames)
        skin = "source:SourceSkin"
        mesh = "|source:SourceMesh"
        skin_host = MayaOriginalSpinePromotionHost()
        original_skin = skin_host.capture_all_skin_weights(skin, mesh)
        service = ReplaceRegisteredSpineCharacter(host)
        args = ("source", "target", skin, mesh)
        try:
            service.apply(*args, start_frame=1, end_frame=10,
                          max_mesh_error=.08, max_body_error=.08)
        except ValueError as error:
            rejected = "FK 迁移身体空间误差超限" in str(error)
        else:
            rejected = False
        rollback = (rejected and cmds.namespace(exists="target") and
            len(MayaBodyBuildHost(namespace="source")
                .read_character_registration().spine.body_joints)
                == source_count + 1 and
            skin_host.capture_all_skin_weights(skin, mesh) == original_skin)
        if not rollback:
            raise RuntimeError("FK 身体误差拒绝未恢复原场景")

        result = service.apply(*args, start_frame=1, end_frame=10,
                               max_mesh_error=.08, max_body_error=.082)

        def body_state():
            promoted = MayaOriginalSkinSpineMigrationHost(namespace="source")
            return promoted.capture_registered_spine_body_take(
                target, names, frames)

        def error(actual):
            return max(abs(a-b) for expected_frame,actual_frame in zip(wanted,actual)
                for (name,left),(actual_name,right) in zip(expected_frame,actual_frame)
                for old_point,new_point in zip(left,right)
                for a,b in zip(old_point,new_point))

        after = body_state()
        maximum = error(after)
        promoted = (not cmds.namespace(exists="target") and
            len(MayaBodyBuildHost(namespace="source")
                .read_character_registration().spine.body_joints)
                == target_count + 1 and maximum <= .082)
        cmds.undo()
        undone = (cmds.namespace(exists="target") and
            skin_host.capture_all_skin_weights(skin, mesh) == original_skin and
            len(MayaBodyBuildHost(namespace="source")
                .read_character_registration().spine.body_joints)
                == source_count + 1)
        cmds.redo()
        redo_error = error(body_state())
        redone = (not cmds.namespace(exists="target") and
                  abs(redo_error - maximum) < 1e-6)
        output = folder / f"{stem}-fk-body-gate.ma"
        cmds.file(rename=str(output))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(output), open=True, force=True)
        reopen_error = error(body_state())
        reopened = (not cmds.namespace(exists="target") and
                    abs(reopen_error - maximum) < 1e-6)
        checks = dict(rejected=rejected, rollback=rollback, promoted=promoted,
                      undo=undone, redo=redone, reopened=reopened,
                      input_unchanged=sha256(input_scene.read_bytes()).hexdigest()
                          == input_digest,
                      frames=result.frames == 10, vertices=result.vertices == 4)
        report = dict(source=source_count, target=target_count,
                      body_max_error_cm=maximum,
                      redo_error_cm=redo_error,
                      reopen_error_cm=reopen_error, checks=checks)
        (folder / f"{stem}-fk-body-gate.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) and .08 < maximum <= .082 else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3])))
