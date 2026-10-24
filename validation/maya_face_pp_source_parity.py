"""Literal asCreatePP joint matrices: source scale, reflection and legacy mode."""
from pathlib import Path
import json
import os
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/face-pp-source-parity'
INPUT=ROOT/'validation/results/face-pupil-parity/ordinary-separated-input.mb'


def snapshot(c,side):
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    host=MayaOriginalFaceBuildHost();joint='ParityPPJoint'+side
    state=c.undoInfo(query=True,state=True);c.undoInfo(stateWithoutFlush=False)
    try:
        result={'offset':host.original_face_matrix_values('ParityPPJointMM'+side+'.matrixIn[0]'),'poses':{}}
        for value in (0,.25,-.25):
            c.setAttr('ParityPP'+side+'.ty',value)
            result['poses'][str(value)]={'joint':c.xform(joint,query=True,worldSpace=True,matrix=True),
                'control':c.xform('ParityPP'+side,query=True,worldSpace=True,matrix=True)}
        c.setAttr('ParityPP'+side+'.ty',0)
        return result
    finally:c.undoInfo(stateWithoutFlush=state)


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel,utils
    from maya_face_conversion_parity import compare,scene_identity
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    OUTPUT.mkdir(parents=True,exist_ok=True);report={'status':'running','pid':os.getpid(),'cases':[]}
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        for opm in (False,True):
            for legacy in (False,True):
                for side in ('_M','_R','_L'):
                    c.file(str(INPUT),open=True,force=True,executeScriptNodes=False);c.undoInfo(state=True)
                    for node in ('FaceFitSkeleton','FitSkeleton'):
                        if not c.objExists(node):c.createNode('transform',name=node)
                        for attribute,value in (('useOffsetParentMatrix',opm),('LegacyFaceJointOrient',legacy)):
                            if not c.objExists(node+'.'+attribute):c.addAttr(node,longName=attribute,attributeType='bool')
                            c.setAttr(node+'.'+attribute,value)
                    c.checkBox('asBodyOffsetParentMatrixCheckBox',edit=True,value=opm)
                    c.checkBox('asFaceLegacyFaceJointOrientCheckBox',edit=True,value=legacy)
                    position=c.createNode('transform',name='ParityPosition')
                    c.xform(position,worldSpace=True,translation=(0 if side=='_M' else (-.7 if side=='_R' else .7),3.7,1.2))
                    before=scene_identity();c.undoInfo(openChunk=True,chunkName='Source PP')
                    try:mel.eval('asCreatePP ParityPosition ParityPP "'+side+'" 1 1 0 0;')
                    finally:c.undoInfo(closeChunk=True)
                    native=snapshot(c,side);c.undo()
                    compare(before,scene_identity())
                    host=MayaOriginalFaceBuildHost()
                    with host.transaction('Python PP'):
                        # Leave legacy unspecified to test the shared Fit default.
                        host.create_original_face_pp(position,'ParityPP',side,1,create_joint=True)
                    python=snapshot(c,side);error=compare(native,python)
                    built=scene_identity();c.undo();compare(before,scene_identity());c.redo();compare(built,scene_identity())
                    redo_error=compare(python,snapshot(c,side))
                    report['cases'].append({'opm':opm,'legacy':legacy,'side':side,'error':error,'redo_error':redo_error})
        report['status']='passed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish:utils.executeDeferred(c.quit,force=True)
