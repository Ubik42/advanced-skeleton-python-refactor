"""Capture the untouched original One Joint Prop graph for the faithful port."""
from pathlib import Path
import json
import traceback

ROOT = Path(__file__).resolve().parents[1]


def main():
    from maya import cmds, mel
    output = ROOT / 'validation/results/original-one-joint-prop'
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
        mesh = cmds.polyCube(name='PropMesh', width=4, height=6, depth=2)[0]
        cmds.xform(mesh, worldSpace=True, translation=(0, 5, -2))
        cmds.textField('asBodySkinTextField', edit=True, text=mesh)
        cmds.textField('asBodyAllTextField', edit=True, text='')
        mel.eval('asOneJointProp;')
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
        cmds.quit(force=True)
