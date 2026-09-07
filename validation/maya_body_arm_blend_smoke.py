from __future__ import annotations
import json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
import maya.standalone
def close(a,b,t=1e-3): return all(abs(x-y)<=t for x,y in zip(a,b))
def main(output):
    started=time.perf_counter(); maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmBlend, BuildBodyArmFkMechanismControls, BuildBodyArmIkControls, BuildBodyArmMechanisms, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton
        cmds.file(new=True,force=True); cmds.undoInfo(state=True); cmds.upAxis(axis="z",rotateView=False)
        marker=cmds.createNode("transform",name="PortableArmBlendSelection",skipSelect=True); host=MayaBodyBuildHost()
        container=CreateFitSkeleton(host).apply().state.path; BuildSyntheticBodySourceFit(host).apply(container)
        body=BuildOrientedBodySkeleton(host).apply(container).snapshot; fit=host.capture_fit_orientation(container); cmds.select(marker,replace=True)
        BuildBodyArmMechanisms(host).apply(container); fk=BuildBodyArmFkMechanismControls(host).apply(container)
        use=BuildBodyArmBlend(host); cmds.file(modified=False); preview=use.plan(container); preview_clean=not cmds.file(query=True,modified=True); blend=use.apply(container)
        ik=BuildBodyArmIkControls(host).apply(container)
        settings=blend.snapshot.settings_path; right_plug=f"{settings}.armIkFk_R"; left_plug=f"{settings}.armIkFk_L"
        right_fk=next(s.control_path for s in fk.snapshot.controls if s.control_path.endswith("AdvPy_ShoulderFK_R"))
        right_ik=next(s.wrist_control_path for s in ik.snapshot.limbs if s.side.value=="R")
        right_wrist=next(j.path for j in body.joints if j.name=="Wrist_R"); left_wrist=next(j.path for j in body.joints if j.name=="Wrist_L")
        bind_r=cmds.xform(right_wrist,q=True,ws=True,t=True); bind_l=cmds.xform(left_wrist,q=True,ws=True,t=True)
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(right_fk+".rotateZ",20); fk_pose=cmds.xform(right_wrist,q=True,ws=True,t=True); fk_drives=not close(fk_pose,bind_r)
        cmds.setAttr(right_fk+".rotateZ",0); cmds.setAttr(right_plug,1.0)
        elbow=next(j.world_position for j in body.joints if j.name=="Elbow_R"); target=tuple(w+(e-w)*.25 for w,e in zip(bind_r,elbow)); cmds.xform(right_ik,ws=True,t=target)
        ik_drives=close(cmds.xform(right_wrist,q=True,ws=True,t=True),target); left_independent=close(cmds.xform(left_wrist,q=True,ws=True,t=True),bind_l) and cmds.getAttr(left_plug)==0
        cmds.setAttr(right_plug,.5); half_weights=all(close((cmds.getAttr(c+"."+a[0]),cmds.getAttr(c+"."+a[1])),(.5,.5)) for c in [j.constraint_name for s in preview.blend.sides if s.side.value=="R" for j in s.joints] for a in [cmds.orientConstraint(c,q=True,weightAliasList=True)])
        cmds.setAttr(right_plug,0); cmds.xform(right_ik,ws=True,t=bind_r); cmds.undoInfo(stateWithoutFlush=True)
        selection=(cmds.ls(sl=True) or [])==[marker]
        cmds.undo(); ik_removed=not cmds.objExists("|AdvPy_ArmIKControls")
        cmds.undo(); blend_removed=not cmds.objExists("|AdvPy_ArmSettings") and all(not cmds.objExists(j.constraint_name) for s in preview.blend.sides for j in s.joints)
        body_survived=len(host.capture_body_skeleton("Root_M").joints)==30; fit_survived=host.capture_fit_orientation(container)==fit
        for _ in range(2): cmds.undo()
        cmds.delete("|Root_M",container,marker); remaining=cmds.ls("Root_M","FitSkeleton","AdvPy_ArmSettings","AdvPy_ArmMechanisms",marker,long=True) or []
        checks=dict(preview_ready=preview.ready,preview_clean=preview_clean,six_constraints=sum(len(s.joints) for s in blend.snapshot.sides)==6,fk_drives_body=fk_drives,ik_drives_body=ik_drives,half_weights=half_weights,left_side_independent=left_independent,selection_preserved=selection,ik_undo=ik_removed,blend_single_undo=blend_removed,body_survived=body_survived,fit_survived=fit_survived,cleanup=not remaining)
        passed=all(checks.values()); payload={"host":"maya","version":str(cmds.about(version=True)),"pid":os.getpid(),"slice":"body_arm_fk_ik_blend",**checks,"remaining_nodes":remaining,"duration_seconds":round(time.perf_counter()-started,3),"status":"passed" if passed else "failed"}
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return 0 if passed else 1
    finally: maya.standalone.uninitialize()
if __name__=="__main__": raise SystemExit(main(Path(sys.argv[1])))
