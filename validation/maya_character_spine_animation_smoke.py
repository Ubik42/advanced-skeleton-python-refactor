"""Bake spine mode on a saved, already animated and skinned character."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(folder,output,reopen=False):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BakeBodyCharacterSpineMode, CaptureBodyCharacterAnimation
        scene=output.with_suffix('.ma') if reopen else folder/'animated.ma'
        cmds.file(str(scene),open=True,force=True);cmds.undoInfo(state=True)
        host=MayaBodyBuildHost();reg=host.read_character_registration()
        mesh=json.loads((folder/'expected.json').read_text(encoding='utf-8'))['mesh']
        def sample():
            with host._character_sampling_time() as seek:
                result=[]
                for frame in (1,6,11,16,21):
                    seek(frame)
                    result.append((host.capture_character_pose(reg).body_frames,tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))))
                return result
        def error(a,b):
            return max(max(abs(x-y) for (_,left),(_,right) in zip(pa,pb) for x,y in zip(left,right)) for (pa,_),(pb,_) in zip(a,b)),max(abs(x-y) for (_,ma),(_,mb) in zip(a,b) for x,y in zip(ma,mb))
        if reopen:
            expected=json.loads(output.with_suffix('.expected.json').read_text(encoding='utf-8'))
            errors=error(expected,sample())
            BakeBodyCharacterSpineMode(host).execute(1,21,'ik',step=5)
            next_errors=error(expected,sample())
            report={'reopened_solver_and_animation':max(errors)<1e-4,'continued_mode_conversion':max(next_errors)<1e-4,
                    'max_mesh_error':max(errors[1],next_errors[1]),'status':'passed' if max(*errors,*next_errors)<1e-4 else 'failed'}
            output.with_name(output.stem+'-read.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        before=sample();keys=host.capture_character_key_state(reg)
        shared_tolerance=cmds.getAttr('ikRPsolver.tolerance')
        selection=cmds.ls(sl=True,long=True)
        bake=BakeBodyCharacterSpineMode(host)
        ik=bake.execute(1,21,'ik',step=5)
        ik_errors=error(before,sample())
        checks={'ik_body_preserved':ik_errors[0]<1e-4,'ik_skin_preserved':ik_errors[1]<1e-4,
                'ik_all_samples':all(dict(p.channels)['spine.ik.spineIkFk']==1 for _,p in ik.samples)}
        ik_keys=host.capture_character_key_state(reg)
        cmds.undo();checks['undo_restores_curves']=host.capture_character_key_state(reg)==keys and max(error(before,sample()))<1e-4
        checks['undo_removes_private_solver']=not cmds.objExists('AdvPy_SpineRPSolver')
        cmds.redo();checks['redo_restores_curves']=host.capture_character_key_state(reg)==ik_keys and max(error(before,sample()))<1e-4
        fk=bake.execute(1,21,'fk',step=5)
        fk_errors=error(before,sample())
        checks['fk_body_preserved']=fk_errors[0]<1e-4;checks['fk_skin_preserved']=fk_errors[1]<1e-4
        checks['fk_all_samples']=all(dict(p.channels)['spine.ik.spineIkFk']==0 for _,p in fk.samples)
        class FailedHost(MayaBodyBuildHost):
            def match_body_spine(self,plan,mode):
                super().match_body_spine(plan,mode)
                raise RuntimeError('Injected animated match failure')
        current=host.capture_character_key_state(reg)
        try:
            BakeBodyCharacterSpineMode(FailedHost()).execute(1,21,'ik',step=5);checks['failure_restores_connections_and_keys']=False
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['failure_restores_connections_and_keys']=host.capture_character_key_state(reg)==current and max(error(before,sample()))<1e-4
        checks['selection_and_time_preserved']=host.capture_character_key_state(reg)[0]==keys[0] and cmds.ls(sl=True,long=True)==selection
        checks['shared_solver_unchanged']=cmds.getAttr('ikRPsolver.tolerance')==shared_tolerance
        foreign=cmds.createNode('network',name='ForeignSolverConsumer',skipSelect=True)
        cmds.addAttr(foreign,longName='input',attributeType='message')
        cmds.connectAttr('AdvPy_SpineRPSolver.message',foreign+'.input')
        try:
            host.read_character_registration();checks['solver_foreign_consumer_rejected']=False
        except ValueError:checks['solver_foreign_consumer_rejected']=True
        cmds.disconnectAttr('AdvPy_SpineRPSolver.message',foreign+'.input')
        output.with_suffix('.expected.json').write_text(json.dumps(before),encoding='utf-8')
        cmds.file(rename=str(output.with_suffix('.ma').absolute()));cmds.file(save=True,type='mayaAscii')
        report={**checks,'ik_body_error':ik_errors[0],'ik_mesh_error':ik_errors[1],'fk_body_error':fk_errors[0],'fk_mesh_error':fk_errors[1],
                'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute(),Path(sys.argv[2]),reopen='--reopen' in sys.argv[3:]))
