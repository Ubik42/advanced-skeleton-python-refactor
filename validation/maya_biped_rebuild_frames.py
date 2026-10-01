"""Record native frames before the strict rebuild binding gate, without bypassing it."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(scene, output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController

    cmds.file(str(scene.resolve()), open=True, force=True, executeScriptNodes=False)
    cmds.undoInfo(state=True)
    preserve = MayaBodyBuildHost.preserve_character_rebuild_binding

    def frames(namespace):
        result = {}
        for path in cmds.ls(namespace + '*', long=True) or []:
            if cmds.nodeType(path) not in ('joint', 'transform'):
                continue
            leaf = path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            if not any(token in leaf for token in (
                    'Toes', 'Ankle', 'RingFinger', 'PinkyFinger', 'Cup', 'Wrist')):
                continue
            attributes = {}
            for attr in ('translate', 'rotate', 'scale', 'jointOrient', 'rotateAxis',
                         'rotateOrder', 'segmentScaleCompensate', 'inheritsTransform'):
                if cmds.objExists(path + '.' + attr):
                    attributes[attr] = cmds.getAttr(path + '.' + attr)
            result[path.replace(namespace, '')] = dict(
                attributes=attributes,
                world=cmds.xform(path, query=True, worldSpace=True, matrix=True),
                local=cmds.xform(path, query=True, objectSpace=True, matrix=True))
        return result

    def record(host, stage, original, replacement):
        old = frames('')
        new = frames('BipedRebuild:')
        old = {path: row for path, row in old.items() if 'BipedRebuild:' not in path}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(
            original=old, replacement=new,
            policy=repr(host.capture_body_generic_fk_feature_policy(original)),
            bind_differences=[dict(path=a.path, before=a.matrix, after=b.matrix)
                for a, b in zip(original.body, replacement.body)
                if max(abs(x-y) for x, y in zip(a.matrix, b.matrix)) > 1e-6]),
            indent=2), encoding='utf-8')
        return preserve(host, stage, original, replacement)

    MayaBodyBuildHost.preserve_character_rebuild_binding = record
    print(MayaPanelController().body_rebuild(':', 'BipedRebuild'))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
