"""Run the current public build on the untouched original biped Fit asset."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(source, output, *, rebuild=False, restricted_skin=False, opm=False,
         bendy=False, export=True):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController

    output.mkdir(parents=True, exist_ok=True)
    cmds.file(str(source.resolve()), open=True, force=True,
              executeScriptNodes=False)
    cmds.undoInfo(state=True)
    if opm:
        if not cmds.objExists('FitSkeleton.useOffsetParentMatrix'):
            cmds.addAttr('FitSkeleton', ln='useOffsetParentMatrix', at='bool')
        cmds.setAttr('FitSkeleton.useOffsetParentMatrix', True)
    if bendy:
        for joint in ('Shoulder', 'Elbow'):
            if not cmds.objExists(joint + '.bendyCtrls'):
                cmds.addAttr(joint, ln='bendyCtrls', at='long', min=0)
            cmds.setAttr(joint + '.bendyCtrls', 3)
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
    skins = cmds.ls(cmds.listHistory(mesh) or [], type='skinCluster') or []
    assert len(skins) == 1, skins
    mesh=cmds.ls(mesh,long=True)[0]
    if restricted_skin:
        with host.transaction('Restrict biped proxy Skin membership'):
            host.apply_skin_vertex_membership(skins[0],mesh,
                tuple(range(0,int(cmds.polyEvaluate(mesh,vertex=True)),2)))
    skin_uuid=cmds.ls(skins[0],uuid=True)[0]
    cmds.setKeyframe('AdvPy_Global', attribute='translateX', time=1, value=0)
    cmds.setKeyframe('AdvPy_Global', attribute='translateX', time=5, value=10)
    cmds.currentTime(1)
    from adv_py.application.character_pose import save_character_pose,load_character_pose
    from adv_py.core.character_pose import validate_character_pose
    pose=host.capture_character_pose(registration)
    pose_file=output/'original-biped-pose.json'
    save_character_pose(pose,pose_file)
    assert load_character_pose(pose_file)==pose
    validate_character_pose(pose,registration)
    from adv_py.core.character_animation import (CharacterAnimation,
        encode_character_animation,decode_character_animation,validate_character_animation)
    animation=CharacterAnimation(host.character_time_unit(),host.sample_character_animation(
        registration,(1.,3.,5.)))
    assert decode_character_animation(encode_character_animation(animation))==animation
    validate_character_animation(animation,registration)
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    curve_uuids={curve.uuid for curve in CaptureBodyCharacterPreservation(host).execute().curves}
    sets=host.capture_body_rebuild_selection_members()
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
    published = (controller.publish_fbx(':', output / 'original-biped-current.fbx',
                                       start=1, end=5, include_skins=True)
                 if export else None)
    if export:
        assert published.bytes_written > 0
    report = dict(source=str(source.resolve()), body_joints=result.joint_count,
                  opm=opm, bendy=bendy,
                  part_joints=result.segment_joint_count,
                  channels=result.channel_count, skins=skins,
                  restricted_skin=restricted_skin,portable_pose_roundtrip=True,
                  portable_animation_roundtrip=True,
                  native_global_deformation=True, registry_reopened=True,
                  fbx_bytes=published.bytes_written if published else None, export_tested=export, scene=str(scene.resolve()))
    (output / 'original-biped-current.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS original biped current build', report)
    if rebuild:
        rebuilt=controller.body_rebuild(':','BipedRebuild')
        assert rebuilt.joint_count == result.joint_count
        assert rebuilt.segment_joint_count == result.segment_joint_count
        retained=MayaBodyBuildHost(namespace='').read_character_registration()
        assert len(retained.body) == len(registration.body)
        assert not cmds.namespace(exists='BipedRebuild')
        assert len(cmds.ls(cmds.listHistory(mesh) or [], type='skinCluster') or []) == 1
        assert cmds.ls(skins[0],uuid=True)==[skin_uuid]
        actual_curves={curve.uuid for curve in CaptureBodyCharacterPreservation(
            MayaBodyBuildHost(namespace='')).execute().curves}
        assert actual_curves==curve_uuids,(curve_uuids,actual_curves)
        assert MayaBodyBuildHost(namespace='').capture_body_rebuild_selection_members()==sets
        cmds.undo()
        assert MayaBodyBuildHost(namespace='').read_character_registration()==registration
        assert cmds.ls(skins[0],uuid=True)==[skin_uuid]
        cmds.redo()
        assert MayaBodyBuildHost(namespace='').read_character_registration()==retained
        for frame,expected in ((1,start),(5,end)):
            cmds.currentTime(frame)
            actual=tuple(cmds.pointPosition(mesh+'.vtx[0]',world=True))
            assert max(abs(a-b) for a,b in zip(expected,actual)) < 1e-4
        rebuilt_scene=output/'original-biped-rebuilt.mb'
        cmds.file(rename=str(rebuilt_scene.resolve()))
        cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(rebuilt_scene.resolve()),open=True,force=True,executeScriptNodes=False)
        assert MayaBodyBuildHost(namespace='').read_character_registration()==retained
        report['rebuilt_scene']=str(rebuilt_scene.resolve())
        report['rebuilt_scene_reopened']=True
        report['native_skin_curve_identity_preserved']=True
        report['single_undo_redo_preserved']=True
        report['native_rebuild_retained_skin_animation']=True
        (output / 'original-biped-current.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS original biped rebuild with Skin and native animation')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]),rebuild='--rebuild' in sys.argv[3:],
         restricted_skin='--restricted-skin' in sys.argv[3:],
         opm='--opm' in sys.argv[3:], bendy='--bendy' in sys.argv[3:],
         export='--no-export' not in sys.argv[3:])
