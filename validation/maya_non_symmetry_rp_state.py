"""Reuse complete asymmetric rigs to locate RP input/output differences."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-current'
def main(*,standalone=False,quit_on_finish=True):
 from maya import cmds as c
 report=dict(status='running',pid=os.getpid(),states={})
 pairs={'control':('IKArm_L','AdvPy_ArmIK_L'),'offset':('IKOffsetArm_L','AdvPy_ArmIKOffset_L'),
  'pole':('PoleArm_L','AdvPy_ArmPV_L'),'pole_offset':('PoleOffsetArm_L','AdvPy_ArmPVOffset_L'),
  'handle':('IKArmHandle_L','AdvPy_ArmIKHandle_L'),
  **{role+joint:(({'ik':'IKX','fk':'FKX','body':''}[role])+joint+'_L',
     ('AdvPy_'+joint+{'ik':'IKDriver','fk':'FKDriver'}[role]+'_L') if role!='body' else joint+'_L')
     for role in ('ik','fk','body') for joint in ('Shoulder','Elbow','Wrist')}}
 def state(mode):
  result={}
  for key,pair in pairs.items():
   node=pair[mode]
   if not c.objExists(node):result[key]={'missing':node};continue
   result[key]=dict(node=node,parent=(c.listRelatives(node,parent=True,fullPath=True) or [''])[0],
    world=c.xform(node,q=True,ws=True,matrix=True),
    attrs={a:c.getAttr(node+'.'+a) for a in ('translate','rotate','scale','jointOrient','rotateAxis',
     'preferredAngle','rotateOrder','segmentScaleCompensate','poleVector','twist','ikBlend') if c.objExists(node+'.'+a)})
  return result
 try:
  for mode,scene in enumerate((OUT/'native-body.mb',OUT/'python/original-biped-current.mb')):
   label=('native','python')[mode];report['states'][label]={}
   for pose in ('fk','ik_neutral','ik_y'):
    c.file(str(scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
    if pose!='fk':c.setAttr('FKIKArm_L.FKIKBlend',10.)
    if pose=='ik_y':c.setAttr(pairs['control'][mode]+'.translateY',.3)
    report['states'][label][pose]=state(mode)
  report['differences']={pose:{key:max(abs(a-b) for a,b in zip(
    report['states']['native'][pose][key]['world'],report['states']['python'][pose][key]['world']))
    for key in pairs if 'world' in report['states']['native'][pose][key]
                    and 'world' in report['states']['python'][pose][key]}
    for pose in ('fk','ik_neutral','ik_y')}
  report['status']='passed'
 except Exception:report.update(status='failed',traceback=traceback.format_exc())
 finally:
  (OUT/'rp-state.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
  if completion:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
  if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
 return report
