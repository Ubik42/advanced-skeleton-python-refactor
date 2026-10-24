"""Inspect native automatic deletion on saved weighted ends; no parity claim."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/retirement-delete-probe'

def main(*,standalone=False,quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    report=dict(status='running',pid=os.getpid(),scope='Saved-scene deletion diagnostics only')
    OUT.mkdir(parents=True,exist_ok=True)
    def save():
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        input_file=ROOT/'validation/results/export-retirement-current/retirement-input.mb'
        for variant in ('saved-weighted','without-skin','saved-stage','stage-owned'):
            if variant in ('saved-stage','stage-owned'):
                c.file(str(ROOT/'validation/results/export-retirement-current/retired-stage-before.mb'),open=True,force=True,executeScriptNodes=False)
                from adv_py.adapters.maya_namespace import MayaCharacterCommands
                commands=MayaCharacterCommands(c,'RetiredReplacement')
                if variant=='stage-owned':
                    if not commands.objExists('AllSet'):
                        commands.sets(empty=True,name='AllSet')
                    members=[member for member in c.sets('AllSet',query=True) or []
                             if commands.objExists(member)]
                    commands.sets(members,add='AllSet')
            else:
                c.file(str(input_file),open=True,force=True,executeScriptNodes=False)
                commands=c
            c.currentTime(1)
            if variant=='without-skin':
                c.delete(c.ls(type='skinCluster') or [])
            ends=set(json.loads((ROOT/'validation/results/export-retirement-current/report.json').read_text())['native_removed'])
            before={name:commands.ls(name,uuid=True)[0] for name in commands.ls('*ScaleBlend*',long=True)}
            edges={name:commands.listConnections(name,source=False,destination=True,plugs=True,connections=True) or [] for name in before if 'Body2ScaleBlend' in name}
            deleted=[]
            for address in commands.listRelatives('DeformationSystem',allDescendents=True,type='joint') or []:
                if commands.ls(address,long=True,type='joint')[0] in ends:
                    commands.delete(address)
                    deleted.append(address)
            report[variant]=dict(deleted=deleted,before_edges=edges,
                removed_scale_nodes=[name for name,identity in before.items() if not c.ls(identity,long=True)])
            save()
        import maya_rp_input_compare
        report['rp_input_exit']=maya_rp_input_compare.main(standalone=False,quit_on_finish=False)
        assert report['rp_input_exit']==0
        report['status']='passed'
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc())
    finally:
        save()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (standalone or quit_on_finish):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
