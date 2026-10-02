"""Full One Joint Prop source graph, deformation, persistence and rebuild."""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/one-joint-prop-source'


def main(*, case_name=None, position=(0,5,-2), dimensions=(4,6,2),
         extra_mesh=False, initialize=True):
    import maya.standalone
    if initialize:
        maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_one_joint_prop import MayaOneJointPropHost
    from adv_py.application.one_joint_prop import BuildOneJointProp
    from adv_py.core.body_build_options import BodyBuildOptions
    from adv_py.application.character_rebuild import RebuildBodyCharacter
    output=OUT/case_name if case_name else OUT
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': []}

    def points(mesh):
        return tuple(cmds.xform(mesh + '.vtx[*]', query=True, worldSpace=True, translation=True))

    def snapshot(controls):
        return {'matrix': cmds.xform('Root_M', query=True, worldSpace=True, matrix=True),
                'points': points('PropMesh'),
                'additional_points': points('AccessoryMesh') if extra_mesh else (),
                'curves': {role: tuple(cmds.xform(node + '.cv[*]', query=True,
                                                worldSpace=True, translation=True))
                           if cmds.listRelatives(node, shapes=True, type='nurbsCurve') else ()
                           for role, node in controls.items()}}

    poses = (
        ('bind', ()),
        ('main_translate', (('Main', 'translate', (2., -1., 3.)),)),
        ('main_rotate', (('Main', 'rotate', (17., -23., 31.)),)),
        ('main_uniform_scale', (('Main', 'scale', (1.7, 1.7, 1.7)),)),
        ('main_nonuniform_scale', (('Main', 'scale', (1.3, .8, 1.6)),)),
        ('root_translate', (('RootX', 'translate', (1.2, -2., .7)),)),
        ('root_rotate', (('RootX', 'rotate', (20., -15., 33.)),)),
        ('root_extra', (('RootExtra', 'rotate', (-11., 17., 27.)),)),
        ('combined', (('Main', 'scale', (1.3, .8, 1.6)),
                      ('RootX', 'rotate', (20., -15., 33.)),
                      ('RootExtra', 'translate', (.5, .7, -1.2)))),
    )

    def sample(controls):
        values = {(node, attr): cmds.getAttr(node + '.' + attr)[0]
                  for node in controls.values() for attr in ('translate', 'rotate', 'scale')}
        samples = {}
        for name, edits in poses:
            for (node, attr), value in values.items():
                if cmds.getAttr(node + '.' + attr, settable=True):
                    cmds.setAttr(node + '.' + attr, *value, type='double3')
            for role, attr, value in edits:
                cmds.setAttr(controls[role] + '.' + attr, *value, type='double3')
            samples[name] = snapshot(controls)
        for (node, attr), value in values.items():
            if cmds.getAttr(node + '.' + attr, settable=True):
                cmds.setAttr(node + '.' + attr, *value, type='double3')
        return samples

    def maximum(a, b):
        assert len(a) == len(b), (len(a), len(b))
        return max((abs(x-y) for x, y in zip(a, b)), default=0.)

    try:
        reference_folder=ROOT/'validation/results/original-one-joint-prop'
        if case_name: reference_folder=reference_folder/case_name
        cmds.file(str(reference_folder/'reference.mb'),
                  open=True, force=True, executeScriptNodes=False)
        native = sample({'Main': 'Main', 'RootX': 'RootX_M', 'RootExtra': 'RootExtraX_M'})
        native_fit = tuple(cmds.xform('FitSkeleton.cv[*]', query=True,
                                     objectSpace=True, translation=True))
        native_settings = {attr: cmds.getAttr('skinCluster1.' + attr)
                           for attr in ('maxInfluences', 'maintainMaxInfluences',
                                        'normalizeWeights', 'skinningMethod')}
        native_build_options = BodyBuildOptions(**{field: bool(cmds.getAttr('FitSkeleton.' + attr))
            for field, attr in (('game_engine', 'gameEngine'),
                                ('use_offset_parent_matrix', 'useOffsetParentMatrix'),
                                ('sub_controllers', 'subControllers'),
                                ('extra_controllers', 'extraControllers'))})
        cmds.file(new=True, force=True)
        mesh = cmds.polyCube(name='PropMesh', width=dimensions[0],
                             height=dimensions[1], depth=dimensions[2])[0]
        cmds.xform(mesh, worldSpace=True, translation=position)
        additional=()
        if extra_mesh:
            accessory=cmds.polySphere(name='AccessoryMesh',radius=.4)[0]
            cmds.xform(accessory,worldSpace=True,translation=(2,5,1))
            additional=(cmds.ls(accessory,long=True)[0],)
        mesh = cmds.ls(mesh, long=True)[0]
        before = points(mesh)
        host = MayaOneJointPropHost()
        result = BuildOneJointProp(host).apply((mesh,), additional, build_options=native_build_options)
        report['build_options']=dict(vars(native_build_options)) if hasattr(native_build_options,'__dict__') else {
            field:getattr(native_build_options,field) for field in ('game_engine',
                'use_offset_parent_matrix','sub_controllers','extra_controllers')}
        root = host._one_joint_prop_body.rig.plan.root
        controls = {'Main': result.control, 'RootX': root.root_x.control_path,
                    'RootExtra': root.root_x.extra_path}
        python = sample(controls)
        errors = {}
        for pose, reference in native.items():
            actual = python[pose]
            row = {'matrix': maximum(reference['matrix'], actual['matrix']),
                   'points': maximum(reference['points'], actual['points']),
                   'additional_points': maximum(reference['additional_points'], actual['additional_points']),
                   'curves': max(maximum(reference['curves'][role], actual['curves'][role])
                                 for role in controls)}
            errors[pose] = row
        report['source_errors'] = errors
        report['fit_curve_error'] = maximum(native_fit, cmds.xform('FitSkeleton.cv[*]',
            query=True, objectSpace=True, translation=True))
        report['skin_settings'] = {attr: cmds.getAttr(result.skins[0] + '.' + attr)
                                  for attr in native_settings}
        report['control_set'] = cmds.sets('ControlSet', query=True)
        report['registered_body_joints'] = len(host._one_joint_prop_body.registration.body)
        report['geometry_parent'] = cmds.listRelatives('PropMesh', parent=True, fullPath=True)
        assert report['skin_settings'] == native_settings
        assert report['geometry_parent'] == ['|Group|Geometry']
        assert report['registered_body_joints'] == 1
        assert len(result.meshes) == len(result.skins) == (2 if extra_mesh else 1)
        report['bound_mesh_count'] = len(result.meshes)
        cmds.file(rename=str(output / 'built.mb'))
        cmds.file(save=True, type='mayaBinary', force=True)
        cmds.file(str(output / 'built.mb'), open=True, force=True, executeScriptNodes=False)
        assert maximum(points('PropMesh'), before) < 1e-5
        report['save_reopen'] = True
        skin_uuids = tuple(cmds.ls(node, uuid=True)[0] for node in result.skins)
        cmds.setKeyframe(result.control.rsplit('|', 1)[-1] + '.rotateY', time=1, value=0)
        cmds.setKeyframe(result.control.rsplit('|', 1)[-1] + '.rotateY', time=3, value=25)
        anim_ids = set(cmds.ls(type='animCurve', uuid=True))
        expected = {}
        for frame in (1, 2, 3):
            cmds.currentTime(frame)
            expected[frame] = (points('PropMesh'), points('AccessoryMesh') if extra_mesh else ())
        cmds.currentTime(1)
        RebuildBodyCharacter(MayaOneJointPropHost(namespace='')).apply('PropRebuild')
        assert all(cmds.ls(uid) for uid in skin_uuids), 'Skin UUID replaced during rebuild'
        assert anim_ids.issubset(set(cmds.ls(type='animCurve', uuid=True)))
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            for frame, reference in expected.items():
                cmds.currentTime(frame)
                assert maximum(reference[0], points('PropMesh')) < 1e-5
                assert maximum(reference[1], points('AccessoryMesh') if extra_mesh else ()) < 1e-5
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        report['rebuild_skin_animation'] = True
        cmds.undo()
        assert all(cmds.ls(uid) for uid in skin_uuids)
        cmds.redo()
        assert all(cmds.ls(uid) for uid in skin_uuids)
        report['rebuild_undo_redo'] = True
        assert max(value for row in errors.values() for value in row.values()) < 1e-4, errors
        assert report['fit_curve_error'] < 1e-5
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['traceback'] = traceback.format_exc()
    finally:
        (output / 'parity.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('One Joint Prop source parity:', report['status'])
        if initialize:
            maya.standalone.uninitialize()


def batch():
    import maya.standalone
    maya.standalone.initialize(name='python')
    try:
        for name,position,dimensions,extra in (
            ('opm',(0,5,-2),(4,6,2),False),
            ('opm_extra',(0,5,-2),(4,6,2),False),
            ('origin',(0,0,0),(2,2,2),True),
            ('below_ground',(0,-.5,0),(2,2,2),False),
        ):
            main(case_name=name,position=position,dimensions=dimensions,
                 extra_mesh=extra,initialize=False)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    batch() if '--batch' in sys.argv else main()
