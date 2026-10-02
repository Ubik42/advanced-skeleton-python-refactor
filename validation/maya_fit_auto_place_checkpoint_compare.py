"""Compare matching geometry before original error / Python cleanup checkpoints."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]


def main():
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from maya.api import OpenMaya as om
    from maya.api import OpenMayaAnim as oma
    snapshots=[]
    stage = '--shoulder' in sys.argv
    paths=(ROOT/'validation/results/fit-auto-place-native-trace/shoulder-checkpoint.mb',
           ROOT/'validation/results/fit-auto-place-diagnostic-v3/shoulder-checkpoint.mb') if stage else (
           ROOT/'validation/results/fit-auto-place-sam-source/native-checkpoint.mb',
           ROOT/'validation/results/fit-auto-place-diagnostic-v2/before-cleanup.mb')
    for path in paths:
        c.file(str(path),open=True,force=True,executeScriptNodes=False)
        rows={}
        for name in ('CombinedSkin','CombinedSkinUpper_M','CombinedSkinLower_M','CombinedSkinUpper_R'):
            selection=om.MSelectionList();selection.add(name)
            dag=selection.getDagPath(0);dag.extendToShape()
            fn=om.MFnMesh(dag)
            rows[name]={'points':[tuple(p)[:3] for p in fn.getPoints(om.MSpace.kWorld)],
                        'faces':fn.numPolygons,'vertices':fn.numVertices}
        rows['guides']={name:c.xform(name,query=True,worldSpace=True,matrix=True)
            for name in c.ls('asFitPivot*',type='transform') or []
            if len(c.ls(name))==1 and not 'Finger' in name}
        rows['straighten']={name:c.xform(name,query=True,worldSpace=True,matrix=True)
            for name in ('asFitShoulderStraight','asFitElbowStraight') if c.objExists(name)}
        selection=om.MSelectionList();selection.add('CombinedSkinUpperSC_M')
        fn=oma.MFnSkinCluster(selection.getDependNode(0))
        selection=om.MSelectionList();selection.add('CombinedSkinUpper_M')
        dag=selection.getDagPath(0);dag.extendToShape()
        component=om.MFnSingleIndexedComponent();obj=component.create(om.MFn.kMeshVertComponent)
        component.addElements(range(om.MFnMesh(dag).numVertices))
        weights,count=fn.getWeights(dag,obj)
        rows['weights']={'weights':list(weights),'influences':[p.partialPathName() for p in fn.influenceObjects()],
                         'nonzero':sum(value>1e-8 for value in weights),
                         'normalize':c.getAttr('CombinedSkinUpperSC_M.normalizeWeights')}
        c.setAttr('asFitDeltaMush.envelope',0.)
        rows['upper_without_delta']={'points':[tuple(p)[:3] for p in om.MFnMesh(dag).getPoints(om.MSpace.kWorld)],
                                   'vertices':om.MFnMesh(dag).numVertices,'faces':om.MFnMesh(dag).numPolygons}
        snapshots.append(rows)
    native,python=snapshots;report={}
    for name,row in native.items():
        if name=='weights':
            report[name]={'native_influences':row['influences'],'python_influences':python[name]['influences'],
                          'native_nonzero':row['nonzero'],'python_nonzero':python[name]['nonzero'],
                          'native_normalize':row['normalize'],'python_normalize':python[name]['normalize']}
            report[name]['native_counts']=[sum(value>.99 for value in row['weights'][i::len(row['influences'])]) for i in range(len(row['influences']))]
            report[name]['python_counts']=[sum(value>.99 for value in python[name]['weights'][i::len(python[name]['influences'])]) for i in range(len(python[name]['influences']))]
            if len(row['weights'])==len(python[name]['weights']):
                report[name]['maximum_error']=max(abs(a-b) for a,b in zip(row['weights'],python[name]['weights']))
        elif name in ('guides','straighten'):
            report[name]={node:max(abs(a-b) for a,b in zip(values,python[name][node]))
                          for node,values in row.items() if node in python[name]}
        else:
            report[name]={'native_count':row['vertices'],'python_count':python[name]['vertices'],
                          'native_faces':row['faces'],'python_faces':python[name]['faces']}
            if row['vertices']==python[name]['vertices']:
                report[name]['maximum_point_error']=max(abs(a-b) for pa,pb in zip(row['points'],python[name]['points'])
                                                       for a,b in zip(pa,pb))
    target=ROOT/('validation/results/fit-auto-place-diagnostic-v3/shoulder-comparison.json' if stage else
                'validation/results/fit-auto-place-diagnostic-v2/checkpoints.json')
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
