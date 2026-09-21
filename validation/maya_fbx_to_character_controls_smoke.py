"""Export generated FBX, isolate-import it, and retarget its motion to FK controls."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output):
    output.parent.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds,mel
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapClipHost,MayaMocapControlHost,MayaMocapSourceReader
        from adv_py.application import (RegisterBodyCharacter,ImportMocapFbx,
            RetargetMocapFourLimbsToCharacter,MocapLimbSource,InspectMocapSource,
            save_mocap_mapping_preset,load_mocap_mapping_preset)
        from adv_py.core import MocapJointMapping,MocapMappingPreset
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        if not cmds.pluginInfo('fbxmaya',query=True,loaded=True):cmds.loadPlugin('fbxmaya',quiet=True)
        built=build_character(with_hand=False)
        registration=RegisterBodyCharacter(built.host).apply(built.rig)
        cmds.namespace(add='TakeA')
        root=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        spine=cmds.createNode('joint',name='TakeA:Spine',parent=root,skipSelect=True)
        chest=cmds.createNode('joint',name='TakeA:Chest',parent=spine,skipSelect=True)
        cmds.setAttr(spine+'.translateY',5.);cmds.setAttr(chest+'.translateY',5.)
        specs=[];chains=[]
        for limb,parts,attach in (('arm',('Shoulder','Elbow','Wrist'),chest),
                                  ('leg',('Hip','Knee','Ankle'),root)):
            for side in ('R','L'):
                parent=attach;chain=[]
                for part in parts:
                    parent=cmds.createNode('joint',name='TakeA:'+part+'_'+side,parent=parent,skipSelect=True)
                    cmds.setAttr(parent+'.translateX',3.)
                    chain.append(parent)
                specs.append(MocapLimbSource(limb,side,*(part+'_'+side for part in parts)))
                chains.append(tuple(chain))
        for frame,travel,amount in ((1,0.,0.),(5,4.,1.),(10,9.,2.)):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=travel)
            cmds.setKeyframe(spine,attribute='rotateZ',time=frame,value=amount*8.)
            cmds.setKeyframe(chest,attribute='rotateX',time=frame,value=amount*5.)
            for index,chain in enumerate(chains):
                sign=1. if index%2==0 else -1.
                for joint,axis,value in zip(chain,('Z','Y','X'),(10.,-14.,7.)):
                    cmds.setKeyframe(joint,attribute='rotate'+axis,time=frame,value=sign*amount*value)
        target=MayaMocapControlHost()
        before=target.capture_character_key_state(registration)
        mappings=[MocapJointMapping('Hips','Root_M',True,True),
                  MocapJointMapping('Spine','Spine1_M'),MocapJointMapping('Chest','Chest_M')]
        for spec in specs:
            parts=('Shoulder','Elbow','Wrist') if spec.limb=='arm' else ('Hip','Knee','Ankle')
            mappings.extend(MocapJointMapping(source,part+'_'+spec.side)
                            for source,part in zip((spec.upper,spec.middle,spec.end),parts))
        preset=MocapMappingPreset('Generated 15-joint control mapping',tuple(mappings),30)
        with tempfile.TemporaryDirectory(prefix='advpy-fbx-retarget-') as directory:
            fbx=Path(directory)/'generated_take.fbx'
            preset_file=Path(directory)/'mapping.json'
            save_mocap_mapping_preset(preset,preset_file)
            loaded=load_mocap_mapping_preset(preset_file)
            cmds.select(root,replace=True)
            mel.eval('FBXResetExport;')
            mel.eval('FBXExportBakeComplexAnimation -v false;')
            mel.eval('FBXExportInputConnections -v false;')
            mel.eval('FBXExportConstraints -v false;')
            cmds.file(str(fbx),force=True,options='v=0;',type='FBX export',exportSelected=True)
            imported=ImportMocapFbx(MayaMocapClipHost()).apply(fbx,namespace='ExternalTake')
            imported_root=imported.snapshot.root
            imported_valid=InspectMocapSource(MayaMocapSourceReader()).execute(imported_root).valid
            options=dict(start_frame=1,end_frame=10)
            roots,spines,limbs=RetargetMocapFourLimbsToCharacter(target).apply_with_preset(
                imported_root,loaded,**options)
        after=target.capture_character_key_state(registration)
        plans=RetargetMocapFourLimbsToCharacter(target).plan_with_preset(imported_root,loaded,**options).limbs
        incomplete=MocapMappingPreset('Missing one limb joint',loaded.mappings[:-1],30)
        try:RetargetMocapFourLimbsToCharacter(target).apply_with_preset(imported_root,incomplete,**options)
        except ValueError:bad_preset_rejected=target.capture_character_key_state(registration)==after
        else:bad_preset_rejected=False
        with target._character_sampling_time() as seek:
            errors=[]
            for plan,samples in zip(plans,limbs):
                for sample in samples:
                    seek(sample.frame)
                    for path,wanted in zip(plan.target_joints,sample.body_matrices):
                        actual=cmds.xform(path,query=True,worldSpace=True,matrix=True)
                        errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        checks={
            'external_fbx_has_fifteen_joints':len(imported.clip.joints)==15,
            'mapping_preset_round_trip':loaded==preset,
            'incomplete_preset_rejected_without_edits':bad_preset_rejected,
            'imported_source_valid':imported_valid,
            'all_control_groups_written':len(roots)==len(spines)==10 and len(limbs)==4
                and all(len(group)==10 for group in limbs),
            'imported_motion_matches_body':max(errors)<1e-4,
        }
        cmds.undo()
        checks['retarget_undo_keeps_import']=(target.capture_character_key_state(registration)==before
            and bool(cmds.ls(imported_root,long=True,type='joint')))
        cmds.undo()
        checks['import_undo_keeps_character']=(not cmds.ls(imported_root,long=True)
            and target.read_character_registration()==registration)
        cmds.redo();cmds.redo()
        checks['two_redos_restore_pipeline']=(target.capture_character_key_state(registration)==after
            and InspectMocapSource(MayaMocapSourceReader()).execute(imported_root).valid)
        scene=output.parent/'fbx-to-character-controls.ma'
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost()
        checks['reopened_pipeline']=(reopened.read_character_registration()==registration
            and InspectMocapSource(MayaMocapSourceReader()).execute(imported_root).valid)
        payload={**checks,'max_body_error':max(errors),'status':'passed' if all(checks.values()) else 'failed'}
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
