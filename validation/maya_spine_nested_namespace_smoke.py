"""Replace generated spine characters inside sibling nested namespaces."""
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(folder, mode):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        animated = mode == 'extension'
        original = folder / ('spine-animated-extension-before.ma' if animated
                             else 'spine-4-to-8-before.ma')
        input_digest = sha256(original.read_bytes()).hexdigest()
        cmds.file(str(original), open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.namespace(addNamespace='cast')
        for role in ('source', 'target'):
            cmds.namespace(addNamespace='cast:' + role)
            cmds.namespace(moveNamespace=[':' + role, ':cast:' + role])
            cmds.namespace(removeNamespace=':' + role)
        source_ns, target_ns = 'cast:source', 'cast:target'
        source_reg = MayaBodyBuildHost(namespace=source_ns).read_character_registration()
        target_reg = MayaBodyBuildHost(namespace=target_ns).read_character_registration()
        accessory = (cmds.ls('cast:source:Accessory', long=True) or [None])[0]
        uuid = cmds.ls(accessory, uuid=True)[0] if animated else None
        frames = tuple(1 + index * .125 for index in range(73))

        def trajectory():
            path = (cmds.ls(uuid, long=True) or [None])[0]
            current = cmds.currentTime(query=True)
            undo_state = cmds.undoInfo(query=True, state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                values = []
                for frame in frames:
                    cmds.currentTime(frame, edit=True)
                    values.append(tuple(cmds.xform(path, query=True,
                        worldSpace=True, matrix=True)))
                return tuple(values)
            finally:
                cmds.currentTime(current, edit=True)
                cmds.undoInfo(stateWithoutFlush=undo_state)

        wanted = trajectory() if animated else ()

        def trajectory_error():
            return max(abs(a-b) for before, after in zip(wanted, trajectory())
                       for a,b in zip(before, after))

        skins = (('cast:source:SourceSkin', '|cast:source:SourceMesh'),)
        if animated:
            skins += (('cast:source:SecondSkin', '|cast:source:SecondMesh'),)
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace=target_ns)).apply_many(
                source_ns, target_ns, skins, start_frame=1, end_frame=10,
                fk_substeps=4, max_mesh_error=.1, max_body_error=.1,
                extensions=(accessory,) if animated else ())
        moved = (cmds.ls(uuid, long=True) or [None])[0] if animated else None
        curves = (cmds.listConnections(moved.rsplit('|',1)[0], source=True,
            destination=False, type='animCurve') or []) if animated else []
        motion_error = trajectory_error() if animated else 0.
        promoted = (not cmds.namespace(exists=target_ns)
            and len(MayaBodyBuildHost(namespace=source_ns)
                .read_character_registration().spine.body_joints)
                == len(target_reg.spine.body_joints)
            and (not animated or moved is not None
                 and any(curve.startswith('cast:source:AdvPy_Extension_')
                         for curve in curves)))
        cmds.undo()
        undone = (cmds.namespace(exists=target_ns)
            and len(MayaBodyBuildHost(namespace=source_ns)
                .read_character_registration().spine.body_joints)
                == len(source_reg.spine.body_joints))
        cmds.redo()
        redo_error = trajectory_error() if animated else 0.
        redone = (not cmds.namespace(exists=target_ns)
            and len(MayaBodyBuildHost(namespace=source_ns)
                .read_character_registration().spine.body_joints)
                == len(target_reg.spine.body_joints))
        output = folder / f'spine-nested-{mode}.ma'
        cmds.file(rename=str(output))
        cmds.file(save=True, type='mayaAscii', force=True)
        cmds.file(str(output), open=True, force=True)
        reopen_error = trajectory_error() if animated else 0.
        reopened = (not cmds.namespace(exists=target_ns)
            and cmds.namespace(exists='cast')
            and len(MayaBodyBuildHost(namespace=source_ns)
                .read_character_registration().spine.body_joints)
                == len(target_reg.spine.body_joints)
            and (not animated or bool(cmds.ls(uuid, long=True))))
        checks = dict(frames=result.frames == 37, skins=result.skin_count == len(skins),
                      promoted=promoted, undo=undone, redo=redone,
                      reopened=reopened,
                      attachment_motion=not animated or
                          max(motion_error, redo_error, reopen_error) < 1e-4,
                      input_unchanged=sha256(original.read_bytes()).hexdigest()
                          == input_digest)
        report = dict(mode=mode, attachment_max_matrix_error=max(
            motion_error, redo_error, reopen_error), checks=checks)
        (folder / f'spine-nested-{mode}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve(), sys.argv[2]))
