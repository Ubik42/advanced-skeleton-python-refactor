"""Diagnose asymmetric Fit height before rebuilding any Body graph."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-current'
def main(*,standalone=False,quit_on_finish=True):
 from maya import cmds as c
 from adv_py.adapters.maya_body import MayaBodyBuildHost
 from adv_py.application.fit_skeleton_io import CreateAndImportFitSkeleton
 from adv_py.application.external_fit_export import ExportExternalFitSkeleton
 from adv_py.core.body_character_global import fit_character_height
 report=dict(status='running',pid=os.getpid())
 try:
  c.file(str(OUT/'python/original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
  host=MayaBodyBuildHost(namespace="");registration=host.read_character_registration()
  rows=host.capture_character_rebuild_fit_channels(registration.container)
  def points(h):
   nodes=h.capture_fit_hierarchy('FitSkeleton').joints
   return {node.short_name.rsplit(':',1)[-1]:list(node.world_position) for node in nodes}
  before=points(host);report['saved_main_height']=c.getAttr('AdvPy_Global.height')
  report['live_fit_height']=fit_character_height(tuple(before.values()))
  fit=OUT/'roundtrip.fit.json';fit.unlink(missing_ok=True);ExportExternalFitSkeleton(host).apply(fit,registration.container)
  with host.character_rebuild_transaction('Probe Fit roundtrip'):
   target=host.create_character_rebuild_host('Probe')
   CreateAndImportFitSkeleton(target).apply(fit)
   with target.transaction('Restore Fit channels'):
    target.restore_character_rebuild_fit_channels(rows)
   after=points(target)
  report['restored_fit_height']=fit_character_height(tuple(after.values()))
  report['position_errors']={name:max(abs(a-b) for a,b in zip(before[name],after[name])) for name in before}
  report['extrema_before']=sorted(before.items(),key=lambda v:v[1][1])[:3]+sorted(before.items(),key=lambda v:v[1][1])[-3:]
  report['extrema_after']=sorted(after.items(),key=lambda v:v[1][1])[:3]+sorted(after.items(),key=lambda v:v[1][1])[-3:]
  assert report['restored_fit_height']==report['saved_main_height']
  assert max(report['position_errors'].values())<=1e-12
  report['status']='passed'
 except Exception:report.update(status='failed',traceback=traceback.format_exc())
 finally:
  (OUT/'fit-roundtrip.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
  if completion:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
  if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
 return report
