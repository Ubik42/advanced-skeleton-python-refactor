"""Locate native/Python differences for the unchanged Main scale input."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
BASE=ROOT/'validation/results/source-non-symmetry-follow-opm-current'
OUT=ROOT/'validation/results/source-follow-scale-diagnosis-current'

def main(standalone=False,quit_on_finish=True):
 from maya import cmds as c
 from maya_source_rp_sub_constructor import snapshot
 OUT.mkdir(parents=True,exist_ok=True)
 report=dict(status='running',pid=os.getpid(),rows={})
 def detail(node):
  result={}
  for attr in ('matrix','offsetParentMatrix','worldMatrix[0]','translate','rotate','scale','jointOrient','segmentScaleCompensate','inverseScale','inheritsTransform'):
   if c.objExists(node+'.'+attr):
    result[attr]=c.getAttr(node+'.'+attr)
    result[attr+'_source']=c.listConnections(node+'.'+attr,source=True,destination=False,plugs=True) or []
  return result
 try:
  poses={}
  for label,scene,main in (('native',BASE/'native.mb','Main'),('python',BASE/'python/original-biped-current.mb','AdvPy_Global')):
   c.file(str(scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
   c.setAttr(main+'.scaleX',1.2)
   poses[label]=snapshot()
   report['rows'][label]={name:detail(name) for name in poses[label]}
   report['systems_'+label]={node:detail(node) for node in ('FKSystem','IKSystem','FKIKSystem','IKJoints','BendSystem','BendJoints','TwistSystem','DeformationSystem',main,'MainScaleMultiplyDivide') if c.objExists(node)}
  report['errors']=sorted(((name,max(abs(a-b) for a,b in zip(poses['native'][name],poses['python'][name]))) for name in poses['native']),key=lambda x:x[1],reverse=True)
  report['status']='captured'
 except Exception:report.update(status='failed',traceback=traceback.format_exc())
 finally:
  (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
  if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status='passed' if report['status']=='captured' else 'failed')),encoding='utf-8')
  if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
 return 0 if report['status']=='captured' else 1
