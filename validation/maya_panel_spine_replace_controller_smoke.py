"""Exercise the Maya panel's cross-spine action on a generated character."""
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
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.product.maya_panel_controller import MayaPanelController

        source = folder / 'spine-4-to-8-before.ma'
        source_digest = sha256(source.read_bytes()).hexdigest()
        cmds.file(str(source), open=True, force=True)
        cmds.undoInfo(state=True)
        action = MayaPanelController()
        skins = (('source:SourceSkin', '|source:SourceMesh'),)
        try:
            action.spine_replace(':', 'target', skins, start=1, end=10)
        except ValueError as error:
            root_rejected = '独立命名空间' in str(error)
        else:
            root_rejected = False
        stages = []
        result = action.spine_replace('source', 'target', skins,
            start=1, end=10, mode='fk', fk_substeps=4,
            max_mesh_error=.1, max_body_error=.007,
            progress=stages.append)
        promoted = (not cmds.namespace(exists='target') and
            len(MayaBodyBuildHost(namespace='source')
                .read_character_registration().spine.body_joints) == 9)
        cmds.undo()
        undone = (cmds.namespace(exists='target') and
            len(MayaBodyBuildHost(namespace='source')
                .read_character_registration().spine.body_joints) == 5)
        cmds.redo()
        redone = (not cmds.namespace(exists='target') and
            len(MayaBodyBuildHost(namespace='source')
                .read_character_registration().spine.body_joints) == 9)
        output = folder / 'spine-4-to-8-panel-replaced.ma'
        cmds.file(rename=str(output))
        cmds.file(save=True, type='mayaAscii', force=True)
        cmds.file(str(output), open=True, force=True)
        reopened = (len(MayaBodyBuildHost(namespace='source')
            .read_character_registration().spine.body_joints) == 9
            and cmds.objExists('source:SourceSkin'))
        checks = dict(root_rejected=root_rejected,
                      frames=result.frames == 37,
                      groups=result.fk_groups == 7,
                      skin=result.skin_count == 1,
                      progress=len(stages) == 2,
                      promoted=promoted, undo=undone, redo=redone,
                      reopened=reopened,
                      input_unchanged=sha256(source.read_bytes()).hexdigest()
                          == source_digest)
        report = dict(checks=checks)
        (folder / 'spine-4-to-8-panel-controller.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
