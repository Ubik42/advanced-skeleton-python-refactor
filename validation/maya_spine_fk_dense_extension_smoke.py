"""Keep an animated attachment through dense cross-spine FK keys."""
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        original = folder / 'spine-animated-extension-before.ma'
        digest = sha256(original.read_bytes()).hexdigest()
        cmds.file(str(original), open=True, force=True)
        cmds.undoInfo(state=True)
        accessory = (cmds.ls('source:Accessory', long=True) or [None])[0]
        if accessory is None:
            raise RuntimeError('缺少自生成附件场景')
        uuid = cmds.ls(accessory, uuid=True)[0]
        frames = tuple(1 + index * .125 for index in range(73))

        def world():
            path = (cmds.ls(uuid, long=True) or [None])[0]
            if path is None:
                raise RuntimeError('附件 UUID 丢失')
            current = cmds.currentTime(query=True)
            undo_state = cmds.undoInfo(query=True, state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                samples = []
                for frame in frames:
                    cmds.currentTime(frame, edit=True)
                    samples.append((frame, tuple(cmds.xform(path, query=True,
                        worldSpace=True, matrix=True))))
                return tuple(samples)
            finally:
                cmds.currentTime(current, edit=True)
                cmds.undoInfo(stateWithoutFlush=undo_state)

        wanted = world()
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target')).apply_many(
                'source', 'target',
                (('source:SourceSkin', '|source:SourceMesh'),
                 ('source:SecondSkin', '|source:SecondMesh')),
                start_frame=1, end_frame=10, fk_substeps=4,
                extensions=(accessory,), max_mesh_error=1, max_body_error=1)

        def error():
            return max(abs(a-b) for (_, before), (_, after) in zip(wanted,world())
                       for a,b in zip(before,after))

        moved = (cmds.ls(uuid, long=True) or [None])[0]
        measured = error()
        cmds.undo()
        undone = ((cmds.ls(uuid, long=True) or [None])[0] == accessory
                  and cmds.namespace(exists='target'))
        cmds.redo()
        redo_error = error()
        output = folder / 'spine-animated-extension-fk-dense.ma'
        cmds.file(rename=str(output))
        cmds.file(save=True, type='mayaAscii', force=True)
        cmds.file(str(output), open=True, force=True)
        MayaBodyBuildHost(namespace='source').read_character_registration()
        reopen_error = error()
        checks = dict(frames=result.frames == 37, skins=result.skin_count == 2,
                      moved=moved is not None and moved != accessory,
                      trajectory=measured < 1e-4,
                      undo=undone, redo=abs(redo_error-measured) < 1e-6,
                      reopened=abs(reopen_error-measured) < 1e-6,
                      input_unchanged=sha256(original.read_bytes()).hexdigest()
                          == digest)
        report = dict(attachment_max_matrix_error=measured, checks=checks)
        (folder / 'spine-animated-extension-fk-dense.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
