"""Capture the untouched original One Joint Prop graph for the faithful port."""
from pathlib import Path
import json
import traceback

ROOT = Path(__file__).resolve().parents[1]


def main(*, case_name=None, options=None, position=(0, 5, -2), dimensions=(4, 6, 2),
         extra_mesh=False, quit_on_finish=True):
    from maya import cmds, mel
    output = ROOT / 'validation/results/original-one-joint-prop'
    if case_name:
        output = output / case_name
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'source': 'ADV 6.925 asOneJointProp',
              'source_bind_flags': {'maximumInfluences': 3, 'dropoffRate': 4,
                                    'removeUnusedInfluence': False}}
    try:
        cmds.file(new=True, force=True)
        cmds.optionVar(intValue=('asHaveRanThisVersion', 1))
        cmds.optionVar(intValue=('asDock', 0))
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        mel.eval('AdvancedSkeleton;')
        mesh = cmds.polyCube(name='PropMesh', width=dimensions[0],
                             height=dimensions[1], depth=dimensions[2])[0]
        cmds.xform(mesh, worldSpace=True, translation=position)
        all_text=''
        if extra_mesh:
            accessory=cmds.polySphere(name='AccessoryMesh',radius=.4)[0]
            cmds.xform(accessory,worldSpace=True,translation=(2,5,1))
            all_text=accessory
        for key, value in (options or {}).items():
            cmds.checkBox('asBody' + key + 'CheckBox', edit=True, value=value)
        cmds.textField('asBodySkinTextField', edit=True, text=mesh)
        cmds.textField('asBodyAllTextField', edit=True, text=all_text)
        mel.eval('asOneJointProp;')
        if options:
            # The native fresh-Fit UI callback can reset Preparation boxes.
            # Capture requested matrix/extra variants via the untouched native
            # rebuild entry, with both its Fit values and UI input explicit.
            attributes={'OffsetParentMatrix':'useOffsetParentMatrix',
                        'ExtraControllers':'extraControllers',
                        'SubControllers':'subControllers','GameEngine':'gameEngine'}
            for key,value in options.items():
                cmds.setAttr('FitSkeleton.'+attributes[key],value)
                cmds.checkBox('asBody'+key+'CheckBox',edit=True,value=value)
            mel.eval('asReBuildAdvancedSkeleton;')
            report['requested_options_rebuilt']=options
        report['nodes'] = {node: {'type': cmds.nodeType(node),
            'parent': cmds.listRelatives(node, parent=True, fullPath=True) or []}
            for node in cmds.ls(long=True) if not node.startswith(':')}
        report['root'] = {attr: cmds.getAttr('Root.' + attr)
            for attr in ('fat', 'jointOrient', 'translate')}
        report['skin_clusters'] = cmds.ls(type='skinCluster') or []
        report['skin_settings'] = {skin: {attr: cmds.getAttr(skin + '.' + attr)
            for attr in ('maxInfluences', 'maintainMaxInfluences', 'normalizeWeights')}
            for skin in report['skin_clusters']}
        for skin, settings in report['skin_settings'].items():
            settings['influences'] = cmds.skinCluster(skin, query=True, influence=True)
            # Maya may return None after a one-influence bind; retain that
            # unavailable query separately from the explicit source flags.
            settings['dropoff_query'] = cmds.skinCluster(skin, query=True, dropoffRate=True)
        report['geometry_parent'] = cmds.listRelatives(mesh, parent=True, fullPath=True) or []
        report['mesh_points'] = cmds.xform(mesh + '.vtx[*]', query=True,
                                           worldSpace=True, translation=True)
        report['control_set'] = cmds.sets('ControlSet', query=True) or []
        report['deform_set'] = cmds.sets('DeformSet', query=True) or []
        report['main_height'] = cmds.getAttr('Main.height')
        report['curves'] = {shape: {
            'form': cmds.getAttr(shape + '.form'),
            'degree': cmds.getAttr(shape + '.degree'),
            'spans': cmds.getAttr(shape + '.spans'),
            'points': cmds.xform(shape + '.cv[*]', query=True, objectSpace=True, translation=True)}
            for shape in cmds.ls(type='nurbsCurve', long=True)}
        report['transforms'] = {node: {
            'matrix': cmds.xform(node, query=True, worldSpace=True, matrix=True),
            'inputs': cmds.listConnections(node, source=True, destination=False,
                                          connections=True, plugs=True) or []}
            for node in cmds.ls(type='transform', long=True)}
        report['root_matrix'] = cmds.xform('Root_M', query=True, worldSpace=True, matrix=True)
        cmds.file(rename=str(output / 'reference.mb'))
        cmds.file(save=True, type='mayaBinary', force=True)
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['traceback'] = traceback.format_exc()
    finally:
        (output / 'reference.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if quit_on_finish:
            cmds.quit(force=True)


def batch():
    from maya import cmds
    try:
        for name, options, position, dimensions, extra in (
            ('opm', {'OffsetParentMatrix': True}, (0,5,-2), (4,6,2), False),
            ('opm_extra', {'OffsetParentMatrix': True, 'ExtraControllers': True,
                           'SubControllers': True}, (0,5,-2), (4,6,2), False),
            ('origin', {'OffsetParentMatrix': False, 'ExtraControllers': False,
                        'SubControllers': False}, (0,0,0), (2,2,2), True),
            ('below_ground', {'OffsetParentMatrix': False}, (0,-.5,0), (2,2,2), False),
        ):
            main(case_name=name, options=options, position=position,
                 dimensions=dimensions, extra_mesh=extra, quit_on_finish=False)
    finally:
        cmds.quit(force=True)
