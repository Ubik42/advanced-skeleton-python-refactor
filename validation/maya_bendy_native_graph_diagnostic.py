"""Capture untouched native and translated Bendy driver graphs for comparison."""
from pathlib import Path
import sys,json

def main(native,python_scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    rows={}
    for label,scene in (('native',native),('python',python_scene)):
        cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
        cmds.currentTime(1,update=True)
        captured={}
        for node in cmds.ls() or []:
            if not any(stem in node for stem in ('Shoulder','Elbow','Ankle','Wrist')) or not node.endswith('_R') and not node.startswith('AdvPy_') and node not in ('Wrist','Ankle'):
                continue
            kind=cmds.nodeType(node)
            if kind not in ('transform','joint','motionPath','composeMatrix','quatToEuler','multDoubleLinear','plusMinusAverage','aimMatrix','decomposeMatrix','blendMatrix','multMatrix','orientConstraint','pointConstraint'):
                continue
            attributes=('rotate','jointOrient','rotateAxis','translate','scale','worldMatrix[0]','offsetParentMatrix','twistAmount','twistAddition') if kind in ('transform','joint') else (
                'frontAxis','upAxis','inverseFront','inverseUp','worldUpType','worldUpVector','frontTwist','upTwist','sideTwist','allCoordinates','worldUpMatrix','inputRotate','input1','input2','output','output1D','outputRotate','input1D','matrixIn','offset','constraintRotate','target','inputMatrix','primaryInputAxis','secondaryInputAxis','secondaryTargetVector','outputMatrix')
            values={};connections={}
            for attribute in attributes:
                plug=node+'.'+attribute
                if cmds.objExists(plug):
                    try:values[attribute]=cmds.getAttr(plug)
                    except Exception:pass
                    connections[attribute]=cmds.listConnections(plug,s=True,d=False,p=True) or []
            captured[node]=dict(kind=kind,values=values,inputs=connections,parent=cmds.listRelatives(node,p=True) if kind in ('transform','joint') else None)
        rows[label]=captured
    output.write_text(json.dumps(rows,indent=2),encoding='utf-8')

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
