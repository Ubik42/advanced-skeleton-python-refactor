"""Run the original Face stage entry on native symmetric eyelid Fit input.

A connected double eye-ring proxy validates the source graph, not appearance.
No original ADV procedure is evaluated and reference assets are never modified.
"""
from pathlib import Path
from collections import defaultdict
from math import hypot
import json, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def ring_edges(cmds,om,mesh):
    selection=om.MSelectionList(); selection.add(mesh)
    fn=om.MFnMesh(selection.getDagPath(0))
    groups=defaultdict(set)
    for index in range(fn.numVertices):
        p=fn.getPoint(index,om.MSpace.kWorld)
        if p.x<0: groups[(round(hypot(p.x+.8,p.y-3.1),4),round(p.z,4))].add(index)
    rings=[]
    for (radius,_),vertices in groups.items():
        edges=tuple(i for i in range(fn.numEdges) if set(fn.getEdgeVertices(i)).issubset(vertices))
        if len(edges)==16: rings.append((radius,edges))
    unique=[]
    for radius,edges in sorted(rings,reverse=True):
        if not unique or abs(radius-unique[-1][0])>1e-4: unique.append((radius,edges))
    assert len(unique)>=3,unique
    return unique[0][1],unique[len(unique)//2][1],unique[-1][1]

def validate_motion(cmds):
    def position(component):
        return tuple(cmds.pointPosition(component,world=True))
    def delta(first,second):
        return max(abs(a-b) for a,b in zip(first,second))
    report={}
    face_before=[position('FaceMesh'+f'.vtx[{i}]') for i in range(cmds.polyEvaluate('FaceMesh',vertex=True))]
    for side in ('_R','_L'):
        eye='EyeRight' if side=='_R' else 'EyeLeft'
        before=position(eye+'.vtx[0]')
        cmds.setAttr('ctrlEye'+side+'.tx',.5)
        moved=position(eye+'.vtx[0]')
        assert delta(before,moved)>1e-5,(side,'eye did not move')
        cmds.setAttr('ctrlEye'+side+'.tx',0)
        report['eye'+side]=delta(before,moved)
        component='upperLidMainCurve'+side+'.cv[3]'
        before=position(component)
        for driver in ('blink','wide','squint'):
            cmds.setAttr('ctrlEye'+side+'.'+driver,10)
            moved=position(component)
            assert delta(before,moved)>1e-5,(side,driver,'lid did not move')
            report[driver+side]=delta(before,moved)
            if driver=='blink':
                face_after=[position('FaceMesh'+f'.vtx[{i}]') for i in range(len(face_before))]
                skin_motion=max(delta(a,b) for a,b in zip(face_before,face_after))
                assert skin_motion>1e-5,(side,'eyelid skin did not deform')
                report['skin_blink'+side]=skin_motion
            cmds.setAttr('ctrlEye'+side+'.'+driver,0)
        assert delta(before,position(component))<1e-5
    before=position('FaceMesh.vtx[0]')
    cmds.setAttr('Head_M.translateX',2)
    moved=position('FaceMesh.vtx[0]')
    assert abs(moved[0]-before[0]-2)<1e-4,(before,moved)
    cmds.setAttr('Head_M.translateX',0)
    assert delta(before,position('FaceMesh.vtx[0]'))<1e-5
    report['head_follow']=True
    return report

def main(output,*,full=False,rebuild=False,opm=False,simpler=False,eye_base=False,socket=False,multi=False,namespace=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    raw=cmds
    from maya.api import OpenMaya as om
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.core.face_original_build import ORIGINAL_FACE_BUILD_STEPS
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(new=True,force=True); cmds.undoInfo(state=True)
    character='FaceActor' if namespace else ':'
    if namespace:
        from adv_py.adapters.maya_namespace import MayaCharacterCommands
        raw.namespace(add=character)
        cmds=MayaCharacterCommands(raw,character)
    def address(node):
        return cmds.identity.to_scene(node) if namespace else node
    cmds.select(clear=True); head=cmds.joint(name='Head_M',position=(0,3,0))
    if multi:
        cmds.createNode('transform',name='DeformationSystem')
    pieces=[]
    for side,x in (('Right',-.8),('Left',.8)):
        mesh=raw.polyTorus(name=address('Ring'+side),radius=.45,sectionRadius=.08,subdivisionsAxis=16,subdivisionsHeight=8,constructionHistory=False)[0]
        cmds.xform(mesh,rotation=(90,0,0),translation=(x,3.1,1.1),worldSpace=True); pieces.append(mesh)
        eye=cmds.polySphere(name='Eye'+side,radius=.31,subdivisionsX=16,subdivisionsY=12,constructionHistory=False)[0]
        cmds.xform(eye,translation=(x,3.1,1.1),worldSpace=True)
        cmds.skinCluster(head,eye,toSelectedBones=True,name=eye+'HeadSkin')
    mesh=cmds.polyUnite(pieces,name='FaceMesh',constructionHistory=False)[0]
    remaining=[p for p in pieces if cmds.objExists(p)]
    if remaining: cmds.delete(remaining)
    cmds.skinCluster(head,mesh,toSelectedBones=True,name='HeadSkin')
    controller=MayaPanelController()
    cmds.select(mesh+'.f[*]',replace=True); controller.face_pre_record_mask(character)
    for role in ('Face','AllHead'):
        cmds.select([mesh,'EyeRight','EyeLeft'] if role=='AllHead' else [mesh],replace=True)
        controller.face_pre_record_objects(character,role,head)
    controller.face_fit_eye_ball(character,'|EyeRight',head)
    fit='FaceFitSkeleton'
    for attr,value in (('RightEye','EyeRight'),('LeftEye','EyeLeft')):
        if not cmds.objExists(fit+'.'+attr): cmds.addAttr(fit,longName=attr,dataType='string')
        cmds.setAttr(fit+'.'+attr,value,type='string')
    if not cmds.objExists(fit+'.Include'): cmds.addAttr(fit,longName='Include',attributeType='enum',enumName='Complete:Skip Above Eyes:Skip Below Eyes:Skip Above+Below Eyes')
    cmds.setAttr(fit+'.Include',3)
    for attr,value in (('useOffsetParentMatrix',opm),('SimplerEyeLid',simpler),
                       ('EyeBase',eye_base),('EyeSocket',socket),('MultiSkinClusters',multi)):
        if not cmds.objExists(fit+'.'+attr): cmds.addAttr(fit,longName=attr,attributeType='bool')
        cmds.setAttr(fit+'.'+attr,value)
    for layer,edges in zip(('Outer','Main','Inner'),ring_edges(raw,om,address(mesh))):
        cmds.select([mesh+f'.e[{i}]' for i in edges],replace=True)
        controller.face_fit_eye_lid(character,layer)
    cmds.file(rename=str(output/'face-fit-input.mb')); cmds.file(save=True,type='mayaBinary',force=True)
    report={'status':'running','stages':[],'input':'symmetric eye rings','include':'Skip Above+Below Eyes',
            'full_entry':full,'opm':opm,'simpler':simpler,'eye_base':eye_base,'socket':socket,'multi':multi,'namespace':character}
    try:
        if full:
            result=controller.face_original_build(character)
            report['stages']=list(result['stages'])
            assert cmds.getAttr(fit+'.buildStep')==30
            cmds.undo(); assert not cmds.objExists('FaceMotionSystem')
            raw.redo(); assert cmds.objExists('FaceMotionSystem')
            report['single_undo_redo']=True
        else:
            for index,stage in enumerate(ORIGINAL_FACE_BUILD_STEPS,1):
                print('STAGE',index,stage,flush=True)
                controller.face_original_build(character,step=index)
                assert cmds.getAttr(fit+'.buildStep')==index
                report['stages'].append(stage)
        assert cmds.getAttr(fit+'.buildCompleted')
        assert not cmds.objExists('FaceBuildInProgress')
        report['motion']=validate_motion(cmds)
        scene=output/'face-completed.mb'
        cmds.file(rename=str(scene)); cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
        reopened=validate_motion(cmds)
        assert max(abs(reopened[k]-v) for k,v in report['motion'].items())<1e-5
        report['saved_reopened']=True
        if rebuild:
            cmds.addAttr('ctrlEye_R',longName='userStrength',attributeType='double',
                minValue=0,maxValue=1,defaultValue=.37,keyable=True)
            authored=cmds.getAttr('ctrlEye_R.userStrength')
            shape=cmds.listRelatives('ctrlEye_R',shapes=True,fullPath=True,type='nurbsCurve')[0]
            cmds.setAttr(shape+'.overrideColor',20)
            # Exercise the previously anonymous slider Shape restoration.
            cmds.move(.1,0,0,shape+'.cv[0]',relative=True,objectSpace=True)
            point=tuple(cmds.getAttr(shape+'.controlPoints[0]')[0])
            controller.face_original_build(character)
            assert not cmds.objExists('prefix_FaceGroup')
            report['rebuilt_motion']=validate_motion(cmds)
            for k,v in report['motion'].items():
                assert abs(report['rebuilt_motion'][k]-v)<1e-5,(k,v,report['rebuilt_motion'][k])
            assert abs(cmds.getAttr('ctrlEye_R.userStrength')-authored)<1e-8
            shape=cmds.listRelatives('ctrlEye_R',shapes=True,fullPath=True,type='nurbsCurve')[0]
            assert cmds.getAttr(shape+'.overrideColor')==20
            assert max(abs(a-b) for a,b in zip(point,cmds.getAttr(shape+'.controlPoints[0]')[0]))<1e-6
            report['authored_slider_shape_and_attribute']=True
            report['rebuilt']=True
        report['status']='passed'
    except Exception:
        report['status']='failed'; report['error']=traceback.format_exc()
        raise
    finally:
        (output/'face-stages.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        cmds.file(rename=str(output/'face-current.mb')); cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(),full='--full' in sys.argv,rebuild='--rebuild' in sys.argv,
         opm='--opm' in sys.argv,simpler='--simpler' in sys.argv,
         eye_base='--eye-base' in sys.argv,socket='--socket' in sys.argv,multi='--multi' in sys.argv,
         namespace='--namespace' in sys.argv)

