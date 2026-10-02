"""Capture the actual layer weights/matrices on both complete Mixed graphs."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-mixed-graph'


def snapshot():
    from maya import cmds as c
    from maya.api import OpenMaya as om, OpenMayaAnim as oma
    result = {'skins': {}, 'transforms': {}, 'blendshapes': {}}
    for node in c.ls(type='skinCluster'):
        selection = om.MSelectionList(); selection.add(node)
        fn = oma.MFnSkinCluster(selection.getDependNode(0))
        for obj in fn.getOutputGeometry():
            path = om.MDagPath.getAPathTo(obj)
            if not obj.hasFn(om.MFn.kMesh):
                continue
            mesh = om.MFnMesh(path)
            component = om.MFnSingleIndexedComponent()
            comp = component.create(om.MFn.kMeshVertComponent)
            component.addElements(range(mesh.numVertices))
            weights, count = fn.getWeights(path, comp)
            influences = fn.influenceObjects()
            result['skins'][node] = {'geometry': path.fullPathName(),
                'influences': [p.partialPathName() for p in influences], 'weights': list(weights),
                'bind_pre': {p.partialPathName(): c.getAttr(node + '.bindPreMatrix[%d]' % fn.indexForInfluenceObject(p)) for p in influences},
                'world_points': c.xform(path.fullPathName() + '.vtx[*]', query=True, worldSpace=True, translation=True)}
    for node in c.ls(type='transform'):
        if node.startswith(('SDK', 'Face', 'OnFace', 'SideReverse', 'upper', 'middle', 'lower', 'Lip', 'Jaw', 'Eye', 'HeadMatrix', 'SmilePull')):
            result['transforms'][node] = {'matrix': c.xform(node, query=True, worldSpace=True, matrix=True),
                'parent': c.listRelatives(node, parent=True, fullPath=True) or [],
                'incoming': c.listConnections(node, source=True, destination=False, plugs=True, connections=True) or []}
    for node in c.ls('asFaceBS*', type='blendShape'):
        result['blendshapes'][node] = {'aliases': c.aliasAttr(node, query=True), 'weights': c.getAttr(node + '.weight[*]'),
            'envelope': c.getAttr(node + '.envelope'), 'history': c.listHistory(node)}
    return result


def main():
    from maya import cmds as c, mel
    from maya_face_conversion_parity import fixture, OUTPUT as CONVERSION_OUTPUT
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_conversion import ConvertOriginalFaceToBlendShapes
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running'}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 0)); mel.eval('AdvancedSkeleton;')
        fixture(True, False)
        checkpoint = OUTPUT / 'input.mb'
        c.file(rename=str(checkpoint)); c.file(save=True, type='mayaBinary', force=True)
        mel.eval('asBSConvertDStoBS;')
        (OUTPUT / 'native.json').write_text(json.dumps(snapshot()), encoding='utf8')
        c.file(rename=str(OUTPUT / 'native.mb')); c.file(save=True, type='mayaBinary', force=True)
        c.file(str(checkpoint), open=True, force=True, executeScriptNodes=False)
        ConvertOriginalFaceToBlendShapes(MayaOriginalFaceBuildHost()).apply(keep_joints=True, keep_targets=False)
        (OUTPUT / 'python.json').write_text(json.dumps(snapshot()), encoding='utf8')
        c.file(rename=str(OUTPUT / 'python.mb')); c.file(save=True, type='mayaBinary', force=True)
        report['status'] = 'captured'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        from maya import utils
        utils.executeDeferred(c.quit, force=True)
