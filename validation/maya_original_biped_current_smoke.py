"""Run the current public build on the untouched original biped Fit asset."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(source, output, *, rebuild=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController

    output.mkdir(parents=True, exist_ok=True)
    cmds.file(str(source.resolve()), open=True, force=True,
              executeScriptNodes=False)
    cmds.undoInfo(state=True)
    # This proxy checks binding/deformation plumbing, not model appearance.
    mesh = cmds.polyCube(name='BipedBindProxy', width=30, height=100,
                         depth=20, subdivisionsY=10)[0]
    cmds.setAttr(mesh + '.translateY', 100)
    controller = MayaPanelController()
    result = controller.body_build(':', meshes=(mesh,), segment_influences=True)
    host = MayaBodyBuildHost()
    registration = host.read_character_registration()
    assert result.joint_count == len(registration.body)
    assert result.segment_joint_count > 0
    skins = cmds.ls(type='skinCluster') or []
    assert len(skins) == 1, skins
    cmds.setKeyframe('AdvPy_Global', attribute='translateX', time=1, value=0)
    cmds.setKeyframe('AdvPy_Global', attribute='translateX', time=5, value=10)
    cmds.currentTime(1)
    start = tuple(cmds.pointPosition(mesh + '.vtx[0]', world=True))
    cmds.currentTime(5)
    end = tuple(cmds.pointPosition(mesh + '.vtx[0]', world=True))
    assert abs((end[0] - start[0]) - 10) < 1e-4, (start, end)
    cmds.currentTime(1)
    scene = output / 'original-biped-current.mb'
    cmds.file(rename=str(scene.resolve()))
    cmds.file(save=True, type='mayaBinary', force=True)
    cmds.file(str(scene.resolve()), open=True, force=True, executeScriptNodes=False)
    reopened = MayaBodyBuildHost().read_character_registration()
    assert reopened == registration
    published = controller.publish_fbx(':', output / 'original-biped-current.fbx',
                                       start=1, end=5, include_skins=True)
    assert published.bytes_written > 0
    report = dict(source=str(source.resolve()), body_joints=result.joint_count,
                  part_joints=result.segment_joint_count,
                  channels=result.channel_count, skins=skins,
                  native_global_deformation=True, registry_reopened=True,
                  fbx_bytes=published.bytes_written, scene=str(scene.resolve()))
    (output / 'original-biped-current.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS original biped current build', report)
    if rebuild:
        rebuilt=controller.body_rebuild(':','BipedRebuild')
        assert rebuilt.joint_count == result.joint_count
        retained=MayaBodyBuildHost(namespace='').read_character_registration()
        assert len(retained.body) == len(registration.body)
        assert not cmds.namespace(exists='BipedRebuild')
        assert len(cmds.ls(type='skinCluster') or []) == 1
        for frame,expected in ((1,start),(5,end)):
            cmds.currentTime(frame)
            actual=tuple(cmds.pointPosition(mesh+'.vtx[0]',world=True))
            assert max(abs(a-b) for a,b in zip(expected,actual)) < 1e-4
        report['native_rebuild_retained_skin_animation']=True
        (output / 'original-biped-current.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS original biped rebuild with Skin and native animation')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]),rebuild='--rebuild' in sys.argv[3:])
