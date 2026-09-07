from __future__ import annotations
import json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
import maya.standalone
def close(a,b,t=1e-3):return all(abs(x-y)<=t for x,y in zip(a,b))
def main(output):
    started=time.perf_counter();maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmRig,BuildOrientedBodySkeleton,BuildSyntheticBodySourceFit,CreateFitSkeleton,InspectBodyRebuildSafety
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis="z",rotateView=False)
        marker=cmds.createNode("transform",name="PortableCompleteArmRigSelection",skipSelect=True);host=MayaBodyBuildHost()
        container=CreateFitSkeleton(host).apply().state.path;BuildSyntheticBodySourceFit(host).apply(container);body=BuildOrientedBodySkeleton(host).apply(container).snapshot;fit=host.capture_fit_orientation(container);cmds.select(marker,replace=True)
        use=BuildBodyArmRig(host);cmds.file(modified=False);preview=use.plan(container,control_radius=2);clean=not cmds.file(q=True,modified=True);result=use.apply(container,control_radius=2)
        selection=(cmds.ls(sl=True)or[])==[marker];settings=result.blend.settings_path;rw=next(j.path for j in body.joints if j.name=="Wrist_R");re=next(j.world_position for j in body.joints if j.name=="Elbow_R");bind=cmds.xform(rw,q=True,ws=True,t=True)
        fk=next(s.control_path for s in result.fk_controls.controls if s.control_path.endswith("AdvPy_ShoulderFK_R"));ik=next(s.wrist_control_path for s in result.ik.limbs if s.side.value=="R")
        cmds.undoInfo(stateWithoutFlush=False);cmds.setAttr(fk+".rotateZ",20);fk_ok=not close(cmds.xform(rw,q=True,ws=True,t=True),bind);cmds.setAttr(fk+".rotateZ",0);cmds.setAttr(settings+".armIkFk_R",1);target=tuple(w+(e-w)*.25 for w,e in zip(bind,re));cmds.xform(ik,ws=True,t=target);ik_ok=close(cmds.xform(rw,q=True,ws=True,t=True),target);cmds.setAttr(settings+".armIkFk_R",0);cmds.xform(ik,ws=True,t=bind);cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo();roots_removed=all(not cmds.objExists(path) for path in ("|AdvPy_ArmMechanisms","|AdvPy_ArmFKControls","|AdvPy_ArmIKControls","|AdvPy_ArmSettings"));body_ok=host.capture_body_skeleton("Root_M")==body;fit_ok=host.capture_fit_orientation(container)==fit;safe=InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        cmds.delete("|Root_M",container,marker);remaining=cmds.ls("Root_M","FitSkeleton","AdvPy_Arm*",marker,long=True)or[]
        checks=dict(preview_ready=preview.ready,preview_clean=clean,mechanism_count=len(result.mechanisms.joints)==12,fk_control_count=len(result.fk_controls.controls)==6,ik_side_count=len(result.ik.limbs)==2,blend_constraint_count=sum(len(s.joints)for s in result.blend.sides)==6,fk_drives_body=fk_ok,ik_drives_body=ik_ok,selection_preserved=selection,single_undo_removed_complete_arm_rig=roots_removed,body_restored=body_ok,fit_preserved=fit_ok,body_rebuild_safe_after_undo=safe,cleanup=not remaining)
        passed=all(checks.values());payload={"host":"maya","version":str(cmds.about(version=True)),"pid":os.getpid(),"slice":"complete_body_arm_rig_atomic",**checks,"remaining_nodes":remaining,"duration_seconds":round(time.perf_counter()-started,3),"status":"passed"if passed else"failed"};output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return 0 if passed else 1
    finally:maya.standalone.uninitialize()
if __name__=="__main__":raise SystemExit(main(Path(sys.argv[1])))
