"""Run unchanged ADV AutoScale and Python in Maya GUI on identical Fit inputs.

Launch through a deferred maya.exe -script entry. This exercises the original
UI-dependent procedure, not a substituted reference formula.
"""
from pathlib import Path
import hashlib,json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/fit-auto-scale-source-parity'
SOURCE=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
FIT=ROOT/'validation/results/source-spline-multi.ma'


def fixture(case):
    from maya import cmds as c
    c.file(str(FIT),open=True,force=True,executeScriptNodes=False)
    mesh=c.polyCube(name='ScaleBody',width=8,height=20,depth=5,subdivisionsY=5)[0]
    c.move(0,10,0,mesh)
    c.makeIdentity(mesh,apply=True,translate=True,rotate=True,scale=True)
    c.delete(mesh,constructionHistory=True)
    c.xform(mesh,pivots=(0,0,0),worldSpace=True)
    skins=[mesh]
    extra=c.polyCube(name='ScaleAccessory',width=1,height=1,depth=1)[0]
    c.move(0,25,0,extra);c.makeIdentity(extra,apply=True,translate=True,rotate=True,scale=True)
    c.delete(extra,constructionHistory=True)
    eye=[]
    if case in ('eye_object','eye_components'):
        ball=c.polySphere(name='ScaleEye',radius=.4,subdivisionsAxis=12,subdivisionsHeight=8)[0]
        c.move(-.5,18.2,1.5,ball);c.makeIdentity(ball,apply=True,translate=True,rotate=True,scale=True)
        c.delete(ball,constructionHistory=True)
        eye=[ball] if case=='eye_object' else [ball+'.vtx[*]']
    if case=='multiple_skin':
        second=c.polyCube(name='ScaleSecondSkin',width=3,height=3,depth=3)[0]
        c.move(0,21,0,second);c.makeIdentity(second,apply=True,translate=True,rotate=True,scale=True)
        c.delete(second,constructionHistory=True);skins.append(second)
        c.xform(second,pivots=(0,0,0),worldSpace=True)
    if case=='scaled_fit':c.setAttr('FitSkeleton.scale',2,2,2,type='double3')
    if case=='softmod':
        soft,handle=c.softMod(mesh,falloffRadius=30)
        c.setAttr(handle+'.translateY',1.5)
    c.select(mesh,replace=True)
    return tuple(skins),(extra,),tuple(eye)


def snapshot():
    from maya import cmds as c
    joints=c.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True) or []
    return {'joints':{joint:{'matrix':tuple(c.xform(joint,query=True,worldSpace=True,matrix=True)),
        'fat':c.getAttr(joint+'.fat') if c.objExists(joint+'.fat') else None} for joint in joints},
        'container_scale':c.getAttr('FitSkeleton.scale')[0],
        'icon':c.xform('FitSkeletonShape.cv[*]',query=True,objectSpace=True,translation=True),
        'display_scale':c.jointDisplayScale(query=True),
        'softmods':c.ls(type='softMod') or [],
        'selection':c.ls(selection=True,long=True),
        'body_visibility':c.getAttr('ScaleBody.visibility'),
        'extra_visibility':c.getAttr('ScaleAccessory.visibility')}


def main():
    from maya import cmds as c,mel
    from adv_py.application.fit_auto_scale import AutoScaleFit
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
    from adv_py.core.preparation_objects import PreparationObjectRole
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':[]}
    try:
        mel.eval('source "'+SOURCE.as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('AdvancedSkeleton;')
        for case in ('ordinary','scaled_fit','multiple_skin','eye_object','eye_components','softmod'):
            skin,all_objects,eye=fixture(case)
            for field,values in (('asBodySkinTextField',skin),('asBodyAllTextField',all_objects),
                                 ('asBodyRightEyeTextField',eye),('asBodyLeftEyeTextField',())):
                c.textField(field,edit=True,text=' '.join(values))
            mel.eval('asFitAutoScale;')
            native=snapshot()
            skin,all_objects,eye=fixture(case)
            if case=='ordinary':
                prep=MayaPreparationObjectsHost(':')
                for role,names in ((PreparationObjectRole.SKIN,skin),(PreparationObjectRole.ALL,all_objects)):
                    prep.write_objects(role,tuple(c.ls(names,long=True)))
                c.select(skin[0],replace=True)
                result=MayaPanelController().fit_auto_scale(':')
            else:
                result=AutoScaleFit(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects,right_eye=eye)
            python=snapshot()
            matrix=max(abs(a-b) for joint,row in native['joints'].items()
                       for a,b in zip(row['matrix'],python['joints'][joint]['matrix']))
            fat=max((abs(row['fat']-python['joints'][joint]['fat']) for joint,row in native['joints'].items()
                     if row['fat'] is not None),default=0.)
            icon=max(abs(a-b) for a,b in zip(native['icon'],python['icon']))
            errors={'matrix':matrix,'fat':fat,'icon':icon,
                'display_scale':abs(native['display_scale']-python['display_scale'])}
            report['cases'].append({'case':case,'errors':errors,'factor':result.plan.factor,
                'eye_placed':result.eye_placed,'native':native,'python':python})
            assert max(errors.values())<=1e-4,(case,errors)
            assert not python['softmods'] and python['selection']==native['selection']
            assert python['container_scale']==native['container_scale']
            assert python['body_visibility']==native['body_visibility'] and python['extra_visibility']==native['extra_visibility']
            assert not (c.ls('AdvPy_FitAutoScale*') or []),'Temporary nodes survived'
            c.undo();undone=snapshot()
            c.redo();redone=snapshot()
            assert redone['joints']==python['joints'],'Undo/redo changed Fit'
            report['cases'][-1]['undo_redo']=True
        # Invalid eye forces rollback after scaling, not merely before writes.
        skin,all_objects,_=fixture('ordinary');before=snapshot()
        try:AutoScaleFit(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects,right_eye=('ScaleBody.vtx[999999]',))
        except (RuntimeError,ValueError):pass
        else:raise AssertionError('Invalid eye did not fail')
        assert snapshot()['joints']==before['joints'],'Failure did not restore Fit'
        assert not (c.ls('AdvPy_FitAutoScale*') or []),'Failure left temporary nodes'
        report['rollback']=True
        c.file(rename=str(OUTPUT/'auto-scale.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(OUTPUT/'auto-scale.mb'),open=True,force=True,executeScriptNodes=False)
        assert snapshot()['joints']==before['joints'],'Reopen changed Fit'
        report['saved_reopened']=True
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        c.quit(force=True)
