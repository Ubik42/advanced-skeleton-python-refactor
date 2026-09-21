"""Stretched limb animation with actual Body and helper-driven skin."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(source,folder,reopen=False,advanced=False,faults=False):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import EnableBodyCharacterStretchMatching, BakeBodyCharacterLimbMode
        from adv_py.adapters.maya_limb_shape import bindings
        folder.mkdir(parents=True,exist_ok=True)
        cmds.file(str(folder/'stretched.ma' if reopen or advanced or faults else source),open=True,force=True);cmds.undoInfo(state=True)
        host=MayaBodyBuildHost();before=host.read_character_registration()
        frames=(1.,11.,21.)
        def snapshot(meshes,registration):
            with host._character_sampling_time() as seek:
                rows=[]
                for frame in frames:
                    seek(frame)
                    rows.append((host.capture_character_pose(registration).body_frames,
                        tuple(tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True)) for mesh in meshes)))
                return rows
        def errors(a,b):
            body=max(abs(x-y) for (left,_),(right,_) in zip(a,b) for (_,m),(_,n) in zip(left,right) for x,y in zip(m,n))
            skin=max(abs(x-y) for (_,left),(_,right) in zip(a,b) for m,n in zip(left,right) for x,y in zip(m,n))
            return body,skin
        if faults:
            lengths,_=bindings(host,before);binding=lengths[0];checks={}
            keys=host.capture_character_key_state(before)
            foreign=cmds.createNode('transform',name='ForeignStretchOutput',skipSelect=True)
            cmds.connectAttr(binding.node+'Out.output',foreign+'.translateX')
            try:
                host.read_character_registration();checks['foreign_output_rejected']=False
            except ValueError:checks['foreign_output_rejected']=True
            cmds.disconnectAttr(binding.node+'Out.output',foreign+'.translateX')
            factor=binding.node+'Out.conversionFactor'
            cmds.setAttr(factor,lock=False);cmds.setAttr(factor,2.)
            try:
                host.read_character_registration();checks['unit_conversion_corruption_rejected']=False
            except ValueError:checks['unit_conversion_corruption_rejected']=True
            cmds.setAttr(factor,1.,lock=True)
            class BadHelperReadbackHost(MayaBodyBuildHost):
                def sample_character_limb_helpers(self,*args):
                    rows=super().sample_character_limb_helpers(*args)
                    self.calls=getattr(self,'calls',0)+1
                    if self.calls==2:
                        frame,poses=rows[0];path,matrix=poses[0];matrix=list(matrix);matrix[12]+=.25
                        rows=((frame,((path,tuple(matrix)),)+poses[1:]),)+rows[1:]
                    return rows
            try:
                BakeBodyCharacterLimbMode(BadHelperReadbackHost()).execute(1,21,'leg','L','ik',step=10)
                checks['helper_readback_failure_rolls_back']=False
            except RuntimeError as exc:
                if 'helper' not in str(exc):raise
                checks['helper_readback_failure_rolls_back']=host.capture_character_key_state(before)==keys
            report={**checks,'status':'passed' if all(checks.values()) else 'failed'}
            (folder/'faults.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        if advanced:
            saved=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            meshes=saved['meshes'];channels={ch.key:ch for ch in before.channels}
            bake=BakeBodyCharacterLimbMode(host);checks={};maximum=(0.,0.)
            for limb,side in (('leg','L'),('arm','R')):
                bake.execute(1,21,limb,side,'ik',step=10)
                with host._character_sampling_time(preserve_modified=False) as seek:
                    for index,frame in enumerate(frames):
                        seek(frame)
                        values={f'{limb}.ikLengthWeight.{side}':0.}
                        if limb=='leg':
                            values.update({'leg.settings.legKneePin_L':.6,'leg.settings.legStretchBias_L':.2,'foot.L.footRoll':index*12.})
                        target=channels[f'{limb}.ik.{side}.translateX']
                        values[target.key]=cmds.getAttr(target.node+'.'+target.attribute)+(index+1)*(.25 if limb=='leg' else -1.5)
                        for key,value in values.items():
                            ch=channels[key];cmds.setKeyframe(ch.node,at=ch.attribute,time=frame,value=value)
                wanted=snapshot(meshes,before)
                for mode in ('fk','ik'):
                    bake.execute(1,21,limb,side,mode,step=10)
                    delta=errors(wanted,snapshot(meshes,before))
                    maximum=tuple(max(a,b) for a,b in zip(maximum,delta))
                    checks[f'{limb}_{side}_automatic_{mode}']=max(delta)<1e-4
            report={**checks,'max_body_error':maximum[0],'max_mesh_error':maximum[1],'status':'passed' if all(checks.values()) else 'failed'}
            (folder/'advanced.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        if reopen:
            saved=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            maximum=errors(saved['snapshot'],snapshot(saved['meshes'],before))
            BakeBodyCharacterLimbMode(host).execute(1,21,'arm','R','fk',step=10)
            maximum=tuple(max(a,b) for a,b in zip(maximum,errors(saved['snapshot'],snapshot(saved['meshes'],before))))
            report={'body_error':maximum[0],'body_and_helper_mesh_error':maximum[1],
                    'status':'passed' if max(maximum)<1e-4 else 'failed'}
            (folder/'read.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        body_mesh=json.loads(source.with_suffix('.expected.json').read_text(encoding='utf-8'))['mesh']
        _,volumes=bindings(host,before)
        helpers=tuple(p for b in volumes for p,_ in b.helpers)
        parts=[]
        for index,path in enumerate(helpers):
            part=cmds.polyCube(name=f'ShapeProbePart{index}',width=.3,height=.3,depth=.3,constructionHistory=False)[0]
            cmds.xform(part,worldSpace=True,matrix=host._spine_world_frame(path)[0]);parts.append(part)
        mesh=cmds.polyUnite(parts,name='ShapeProbeMesh',constructionHistory=False)[0]
        remaining=[p for p in parts if cmds.objExists(p)]
        if remaining:cmds.delete(remaining)
        skin=cmds.skinCluster(list(helpers),mesh,toSelectedBones=True,maximumInfluences=1,normalizeWeights=1,name='ShapeProbeSkin')[0]
        for index,path in enumerate(helpers):
            cmds.skinPercent(skin,mesh+f'.vtx[{index*8}:{index*8+7}]',transformValue=[(path,1.)],zeroRemainingInfluences=True)
        meshes=(body_mesh,mesh)
        marker=cmds.createNode('transform',name='StretchSelection',skipSelect=True);cmds.select(marker)
        original_time=cmds.currentTime(q=True)
        previous=snapshot(meshes,before)
        service=EnableBodyCharacterStretchMatching(host)
        cmds.file(modified=False);plan=service.plan();checks={'plan_read_only':not cmds.file(q=True,modified=True)}
        registration=service.apply()
        checks['sixteen_shape_channels']=len(registration.channels)==len(before.channels)+16
        checks['installation_preserves_both_skins']=max(errors(previous,snapshot(meshes,registration)))<1e-6
        cmds.undo();checks['upgrade_undo']=host.read_character_registration()==before
        cmds.redo();checks['upgrade_redo']=host.read_character_registration()==registration
        cmds.file(modified=False);checks['idempotent']=service.apply()==registration and not cmds.file(q=True,modified=True)
        cmds.undo()
        class BadInstallHost(MayaBodyBuildHost):
            def install_character_stretch_matching(self,before,after):
                super().install_character_stretch_matching(before,after)
                cmds.setAttr('AdvPy_ArmSettings.ikMatchLength0_R',1000.)
                cmds.setAttr('AdvPy_ArmSettings.ikMatchLengthWeight_R',1.)
        try:
            EnableBodyCharacterStretchMatching(BadInstallHost()).apply();checks['installation_readback_rolls_back']=False
        except RuntimeError as exc:
            if '世界姿态' not in str(exc):raise
            checks['installation_readback_rolls_back']=host.read_character_registration()==before and not cmds.objExists('AdvPy_ArmIKMatchLength0_R')
        registration=service.apply()
        for ch in registration.channels:
            if '.fkLength.' in ch.key:
                for frame,factor in zip(frames,(1.05,1.15,1.25)):
                    with host._character_sampling_time() as seek:
                        seek(frame);value=cmds.getAttr(ch.node+'.'+ch.attribute)
                    # Different upper/lower changes exercise more than uniform extension.
                    factor+=.03 if ch.key.endswith('.1') else 0
                    cmds.setKeyframe(ch.node,at=ch.attribute,time=frame,value=value*factor)
        wanted=snapshot(meshes,registration);maximum=(0.,0.);bake=BakeBodyCharacterLimbMode(host)
        for limb in ('arm','leg'):
            for side in ('R','L'):
                for mode in ('ik','fk'):
                    old=host.capture_character_key_state(registration)
                    bake.execute(1,21,limb,side,mode,step=10)
                    error=errors(wanted,snapshot(meshes,registration));maximum=tuple(max(a,b) for a,b in zip(maximum,error))
                    checks[f'{limb}_{side}_{mode}_stretched_skins']=max(error)<1e-4
                    if (limb,side,mode)==('arm','R','ik'):
                        current=host.capture_character_key_state(registration)
                        cmds.undo();checks['conversion_undo']=host.capture_character_key_state(registration)==old
                        cmds.redo();checks['conversion_redo']=host.capture_character_key_state(registration)==current
        bake.execute(1,21,'arm','R','ik',step=10)
        ch=next(ch for ch in registration.channels if ch.key=='arm.volumeMatch.R')
        for frame in frames:cmds.setKeyframe(ch.node,at=ch.attribute,time=frame,value=.75)
        thinner=snapshot(meshes,registration)
        bake.execute(1,21,'arm','R','fk',step=10)
        checks['ik_volume_to_fk_preserved']=max(errors(thinner,snapshot(meshes,registration)))<1e-4
        bake.execute(1,21,'arm','R','ik',step=10)
        checks['volume_roundtrip_preserved']=max(errors(thinner,snapshot(meshes,registration)))<1e-4
        class FailedHost(MayaBodyBuildHost):
            def apply_body_leg_fk_to_ik(self,plan):
                super().apply_body_leg_fk_to_ik(plan)
                raise RuntimeError('Injected stretched match failure')
        keys=host.capture_character_key_state(registration)
        try:
            BakeBodyCharacterLimbMode(FailedHost()).execute(1,21,'leg','L','ik',step=10);checks['failure_rolls_back']=False
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['failure_rolls_back']=host.capture_character_key_state(registration)==keys
        checks['selection_and_time_preserved']=cmds.currentTime(q=True)==original_time and cmds.ls(sl=True)==[marker]
        cmds.file(rename=str(folder/'stretched.ma'));cmds.file(save=True,type='mayaAscii')
        (folder/'expected.json').write_text(json.dumps({'meshes':meshes,'snapshot':thinner}),encoding='utf-8')
        report={**checks,'max_body_error':maximum[0],'max_body_and_helper_mesh_error':maximum[1],
                'channel_count':len(registration.channels),'status':'passed' if all(checks.values()) else 'failed'}
        (folder/'write.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute(),Path(sys.argv[2]).absolute(),reopen='--reopen' in sys.argv[3:],advanced='--advanced' in sys.argv[3:],faults='--faults' in sys.argv[3:]))
