"""Public Partial Joints lifecycle on the current original biped Body build.

Run once per actual Body matrix mode. No Fit mode toggle on an existing rig.
"""
from pathlib import Path
import json, sys, traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(source, output, opm=False, no_parts=False):
    source, output = source.resolve(), output.resolve()
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_partial_joints import MayaPartialJointsHost
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'opm': opm, 'no_parts': no_parts,
              'stages': [], 'samples': []}
    try:
        cmds.file(str(source), open=True, force=True, executeScriptNodes=False)
        cmds.undoInfo(state=True)
        controller = MayaPanelController()
        if not cmds.objExists('AdvPy_Global'):
            if not cmds.objExists('FitSkeleton.useOffsetParentMatrix'):
                cmds.addAttr('FitSkeleton', ln='useOffsetParentMatrix', at='bool')
            cmds.setAttr('FitSkeleton.useOffsetParentMatrix', opm)
            if no_parts:
                for joint in cmds.listRelatives('FitSkeleton', ad=True, type='joint', fullPath=True) or []:
                    for attribute in ('numJoints', 'inbetweenJoints'):
                        if cmds.objExists(joint + '.' + attribute):
                            cmds.setAttr(joint + '.' + attribute, 0)
            mesh = cmds.polyCube(name='BipedBindProxy', width=30, height=100,
                                 depth=20, subdivisionsY=10)[0]
            cmds.setAttr(mesh + '.ty', 100)
            controller.body_build(':', meshes=(mesh,), segment_influences=True)
        else:
            for curve in cmds.listConnections('AdvPy_Global.tx', s=True, d=False,
                                               type='animCurve') or []:
                cmds.delete(curve)
            cmds.setAttr('AdvPy_Global.tx', 0)
        neutral = MayaCorrectiveShapesHost()
        with neutral.transaction('Prepare original partial build pose'):
            neutral.go_to_original_corrective_build_pose()
            neutral.set_original_corrective_all_fk()
        host = MayaPartialJointsHost()
        assert host.partial_uses_opm() is opm
        cmds.file(rename=str(output / 'neutral-body.mb'))
        cmds.file(save=True, type='mayaBinary', force=True)
        baseline = set(cmds.ls(type='joint'))
        cmds.select('AdvPy_Elbow_RFK', r=True)
        specs = controller.partial_joints_create(':', include_controller=True)
        assert len(specs) == 1 and specs[0].stem == 'Elbow', specs
        assert len(set(cmds.ls(type='joint')) - baseline) == 1
        assert host._height() == cmds.getAttr('AdvPy_Global.height')
        for attribute in ('sx', 'sy', 'sz', 'v'):
            assert cmds.getAttr('FKExtraElbowPartial_R.' + attribute, lock=True)
        cmds.undo(); assert not cmds.objExists('ElbowPartial_R')
        cmds.redo(); assert cmds.objExists('ElbowPartial_R')
        report['stages'].append('internal_fk_selection_single_control_undo_redo')
        for rotation in (0., 45., -30.):
            cmds.setAttr('AdvPy_Elbow_RFK.rz', rotation)
            for follow in (0., 5., 10.):
                cmds.setAttr('FKElbowPartial_R.follow', follow)
                matrix = cmds.xform('ElbowPartial_R', q=True, ws=True, matrix=True)
                assert all(abs(value) < 1e9 for value in matrix)
                report['samples'].append({'rotation': rotation, 'follow': follow,
                                           'matrix': matrix})
        assert report['samples'][3]['matrix'] != report['samples'][5]['matrix']
        cmds.setAttr('FKElbowPartial_R.tx', .5)
        driven = cmds.xform('ElbowPartial_R', q=True, ws=True, matrix=True)
        cmds.setAttr('FKElbowPartial_R.tx', 0)
        assert driven != cmds.xform('ElbowPartial_R', q=True, ws=True, matrix=True)
        cmds.setAttr('AdvPy_Elbow_RFK.rz', 0)
        cmds.setAttr('FKElbowPartial_R.follow', 5)
        report['stages'].append('driver_follow_and_partial_control_deformation')
        cmds.setAttr('FKElbowPartial_R.tx', .5)
        cmds.setAttr('FKElbowPartial_R.follow', 9)
        with neutral.transaction('Restore original Partial build pose'):
            neutral.go_to_original_corrective_build_pose()
        assert abs(cmds.getAttr('FKElbowPartial_R.tx')) < 1e-8
        assert cmds.getAttr('FKElbowPartial_R.follow') == 5
        report['stages'].append('partial_control_build_pose_restore')
        cmds.select('AdvPy_Elbow_LFK', r=True)
        specs = controller.partial_joints_create(':')
        assert len(specs) == 1 and specs[0].side == 'L'
        report['stages'].append('opposite_side_single_without_control')
        cmds.select('AdvPy_Elbow_RFK', r=True)
        controller.partial_joints_delete(':')
        assert not cmds.objExists('FKElbowPartial_R')
        assert not cmds.objExists('ElbowPartial_R_parentConstraint1')
        assert not cmds.getAttr('buildPose.udExtraAttr')
        cmds.select('AdvPy_Elbow_RFK', r=True)
        specs = controller.partial_joints_create(':', count=6, auto_bind=True)
        assert len(specs) == 1 and not specs[0].use_opm
        skin = cmds.ls(type='skinCluster')[0]
        joints = tuple('ElbowPartial%d_R' % index for index in range(1, 7))
        assert set(joints) <= set(cmds.skinCluster(skin, q=True, influence=True))
        cmds.undo(); assert not cmds.objExists(joints[0])
        cmds.redo(); assert cmds.objExists(joints[0])
        samples = []
        for scale in (1., 1.5):
            cmds.setAttr('AdvPy_Global.globalScale', scale)
            for rotation in (0., 60.):
                cmds.setAttr('AdvPy_Elbow_RFK.rz', rotation)
                host._verify_multi_chain(specs[0])
                samples.append([cmds.xform(joint, q=True, ws=True, t=True) for joint in joints])
        assert samples[0] != samples[1] and samples[0] != samples[2]
        cmds.setAttr('AdvPy_Global.globalScale', 1)
        cmds.setAttr('AdvPy_Elbow_RFK.rz', 0)
        report['stages'].append('six_joint_skin_spline_follow_global_scale_undo_redo')
        scene = output / 'partial-joints.mb'
        cmds.file(rename=str(scene)); cmds.file(save=True, type='mayaBinary', force=True)
        cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
        MayaPartialJointsHost()._verify_multi_chain(specs[0])
        assert cmds.objExists('ElbowPartial_L')
        report['stages'].append('native_save_reopen_graph')
        cmds.select('AdvPy_Elbow_RFK', r=True)
        removed = controller.partial_joints_delete(':')
        assert len(removed) == 1 and not removed[0].single and removed[0].multi
        assert not cmds.objExists('ElbowPartial_R') and not cmds.objExists(joints[0])
        assert cmds.objExists('ElbowPartial_L')
        cmds.undo(); assert cmds.objExists(joints[0])
        cmds.redo(); assert not cmds.objExists('ElbowPartial_R')
        cmds.select(clear=True); controller.partial_joints_delete(':')
        assert not cmds.objExists('PartialJointsSystem')
        assert not cmds.ls('*PartialMM*', '*PartialBM*', '*Partial*FollowMDL*')
        report['stages'].append('selected_multi_delete_undo_redo_and_all_cleanup')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
        raise
    finally:
        (output / 'partial-joints.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), '--opm' in sys.argv[3:],
         '--no-parts' in sys.argv[3:])
