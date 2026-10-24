"""Literal MEL Advanced Constraint versus native source Python layers."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-advanced-constraint-matrix-current'

def main(standalone=False,quit_on_finish=True,use_opm=True):
 from maya import cmds as c,mel
 from adv_py.adapters.maya_body import MayaBodyBuildHost
 from adv_py.core.body_fit_advanced_constraint import BodyFitAdvancedConstraintSpec
 OUT.mkdir(parents=True,exist_ok=True)
 report=dict(status='running',pid=os.getpid(),use_offset_parent_matrix=use_opm,cases=[])
 def matrix(node):return tuple(c.xform(node,q=True,ws=True,matrix=True))
 try:
  source=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
  mel.eval('source "'+source.as_posix()+'";')
  block=source.read_text(encoding='utf-8').split('//Advanced Constraint',1)[1].split('//Advanced Follow',1)[0]
  for kind in ('parent','point','orient','scale'):
   for align in (False,True):
    for central in (False,True):
     c.file(new=True,force=True)
     c.createNode('transform',name='Group');c.createNode('transform',name='MotionSystem',parent='Group')
     c.createNode('transform',name='ConstraintSystem',parent='MotionSystem')
     c.createNode('transform',name='FitSkeleton')
     c.addAttr('FitSkeleton',longName='useOffsetParentMatrix',attributeType='bool',defaultValue=use_opm)
     ui=c.window();c.columnLayout();c.checkBox('asBodyOffsetParentMatrixCheckBox',value=use_opm)
     fixtures=[];side='M' if central else 'R'
     for prefix in ('N','P'):
      parent=c.createNode('transform',name=prefix+'Parent')
      c.setAttr(parent+'.translate',1,2,3,type='double3');c.setAttr(parent+'.rotate',4,8,12,type='double3')
      offset=c.createNode('transform',name='FKOffset'+prefix+'S_'+side,parent=parent)
      c.setAttr(offset+'.translate',2,3,1,type='double3');c.setAttr(offset+'.rotate',3,7,11,type='double3')
      receiver=c.createNode('transform',name=prefix+'Receiver',parent=offset)
      c.setAttr(receiver+'.translate',.2,.3,-.1,type='double3')
      old=c.createNode('composeMatrix',name=prefix+'Old')
      c.setAttr(old+'.inputTranslate',.1,.2,-.3,type='double3');c.connectAttr(old+'.outputMatrix',receiver+'.offsetParentMatrix')
      fk=c.createNode('transform',name='FK'+prefix+'S_'+side,parent=receiver)
      fit=c.createNode('joint',name=prefix+'S');targetfit=c.createNode('joint',name=prefix+'T')
      c.setAttr(targetfit+'.translateX',-5.)
      if align:c.addAttr(fit,longName='orientConstraintMaintainOffset',attributeType='bool',defaultValue=True)
      joints=[];offsets=[]
      for s,x in (('R',-5.),('L',5.)):
       joint=c.createNode('joint',name=prefix+'T_'+s,parent=parent)
       c.setAttr(joint+'.translate',x,6.,2.,type='double3');c.setAttr(joint+'.rotate',7.,11.,13.,type='double3')
       frame=c.createNode('transform',name='FKOffset'+prefix+'T_'+s,parent=parent)
       c.xform(frame,ws=True,matrix=matrix(joint))
       joints.append(c.ls(joint,long=True)[0]);offsets.append(c.ls(frame,long=True)[0])
      fixtures.append((parent,offset,receiver,fk,fit,joints,offsets))
     values={'PaC':'','PoC':'','OC':'','SC':''};values[{'parent':'PaC','point':'PoC','orient':'OC','scale':'SC'}[kind]]='NT'
     declarations='string $fitJoints[]={"NS"};string $fitJointSide[]={"_'+side+'"};int $fitJointNoMirrorCode[]={-1};'
     declarations+=''.join('string $fitJoints'+key+'[]={"'+value+'"};' for key,value in values.items())
     declarations+='string $name,$side,$constraintTo,$constraintTos[],$constraintTypes[],$constraintType,$constraintToSide,$target,$tempString[];int $b,$i,$z,$y,$orientConstraintMaintainOffset;float $pos[],$sideTreshold=.1;'
     mel.eval('{'+declarations+block+'}')
     parent,offset,receiver,fk,fit,joints,offsets=fixtures[1]
     offset=c.ls(offset,long=True)[0];fk=c.ls(fk,long=True)[0]
     targets=tuple(joints if central else joints[:1]);frames=tuple(offsets if central else offsets[:1])
     spec=BodyFitAdvancedConstraintSpec(kind,fit,fit,targets,fk,offset,'PStatic','PWeight','PReverse','PConstraint', 'PUnusedSplit' if central else None,align,'PUnusedCorrection' if align else None,True,use_opm,frames)
     host=MayaBodyBuildHost()
     with host.transaction('Source Advanced Constraint matrix fixture'):
      host.create_body_fit_advanced_constraint(spec)
      assert host.capture_body_fit_advanced_constraint(spec)
     for weight in (0.,5.,10.):
      for prefix in ('N','P'):
       c.setAttr(prefix+'Parent.scale',1.2,.9,1.4,type='double3')
       c.setAttr(prefix+'T_R.rotateZ',31.)
       if central:c.setAttr(prefix+'T_L.translateY',8.)
       c.setAttr('FK'+prefix+'S_'+side+'.'+kind+'Constraint',weight)
      error=max(abs(a-b) for a,b in zip(matrix('FKNS_'+side),matrix('FKPS_'+side)))
      report['cases'].append(dict(kind=kind,align=align,central=central,weight=weight,maximum_error=error))
     c.deleteUI(ui)
  report['maximum_error']=max(row['maximum_error'] for row in report['cases'])
  report['status']='passed' if report['maximum_error']<=1e-5 else 'failed'
 except Exception:report.update(status='failed',traceback=traceback.format_exc())
 finally:
  (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
  if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
  if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
 return 0 if report['status']=='passed' else 1
