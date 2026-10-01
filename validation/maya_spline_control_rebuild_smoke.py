"""Exercise original-style Spline count edits on a saved native biped rig."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene,output,*,fit_labels=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.core.spline_control_rebuild import splines,control_count
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    host=MayaBodyBuildHost()
    original=host.read_character_registration()
    spline=splines(original)[0]
    system=spline.system_name
    count=control_count(spline)
    cmds.setKeyframe(spline.settings,attribute='stretchy',time=1,value=5)
    cmds.setKeyframe(spline.settings,attribute='stretchy',time=5,value=8)
    cmds.setKeyframe(spline.targets[-1],attribute='translateZ',time=1,value=0)
    cmds.setKeyframe(spline.targets[-1],attribute='translateZ',time=5,value=2)
    cmds.currentTime(1)
    before=CaptureBodyCharacterPreservation(host).execute()
    skin_ids={row.uuid for row in before.skins}
    curve_ids={row.uuid for row in before.curves}
    controller=MayaPanelController()
    controller.body_rebuild(':','SplineCountStage',spline_counts=((system,count+2),))
    grown=host.read_character_registration()
    assert control_count(splines(grown)[0])==count+2
    after=CaptureBodyCharacterPreservation(host).execute()
    assert {row.uuid for row in after.skins}==skin_ids
    assert curve_ids<={row.uuid for row in after.curves}
    for old in before.skins:
        new=next(row for row in after.skins if row.uuid==old.uuid)
        assert old.weights==new.weights and old.blend_weights==new.blend_weights
        assert old.component_memberships==new.component_memberships
    assert not cmds.namespace(exists='SplineCountStage')
    cmds.undo()
    assert host.read_character_registration()==original
    cmds.redo()
    assert host.read_character_registration()==grown
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'spline-count-grown.mb'
    cmds.file(rename=str(saved.resolve()))
    cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(saved.resolve()),open=True,force=True,executeScriptNodes=False)
    assert host.read_character_registration()==grown
    # The MEL connection-reuse rule drops the output of an obsolete indexed
    # control. Keep its native curve object/data available instead of deleting
    # the user's animation when the generated controller disappears.
    last=splines(grown)[0].targets[-1]
    cmds.setKeyframe(last,attribute='translateY',time=1,value=0)
    cmds.setKeyframe(last,attribute='translateY',time=5,value=2)
    orphan=cmds.connectionInfo(last+'.translateY',sourceFromDestination=True).split('.',1)[0]
    orphan_uuid=cmds.ls(orphan,uuid=True)[0]
    orphan_values=tuple(cmds.keyframe(orphan,q=True,valueChange=True))
    user_set=cmds.sets((last,splines(grown)[0].targets[0]),name='SplineUserSelection')
    controller.body_rebuild(':','SplineCountReduce',spline_counts=((system,count),))
    reduced=host.read_character_registration()
    assert control_count(splines(reduced)[0])==count
    curve=cmds.ls(orphan_uuid)[0]
    assert tuple(cmds.keyframe(curve,q=True,valueChange=True))==orphan_values
    assert not cmds.listConnections(curve+'.output',s=False,d=True)
    assert cmds.sets(splines(reduced)[0].targets[0],isMember=user_set)
    assert len(cmds.sets(user_set,q=True))==1
    controller.body_rebuild(':','SplineSameLayout')
    assert control_count(splines(host.read_character_registration())[0])==count
    report=dict(status='passed',system=system,counts=(count,count+2,count),
        native_skin_curves_preserved=True,weights_membership_preserved=True,
        undo_redo=True,saved_reopened=True,same_layout_followup=True,
        obsolete_curve_kept_unconnected=True,user_selection_updated=True)
    if fit_labels:
        # Exercise the existing ordinary panel entry: no extra UI/count option
        # is required when an artist edits the original Fit Mid label.
        registration_now=host.read_character_registration()
        hierarchy=host.capture_fit_hierarchy(registration_now.container)
        mode=splines(registration_now)[0].source_mode
        from adv_py.core.fit_ik import fit_joint_ik_info
        labels={joint.path:host.read_joint_label(joint.path) for joint in hierarchy.joints}
        start=next(joint.path for joint in hierarchy.joints
                   if joint.short_name==mode.fit_start_joint)
        info=fit_joint_ik_info(hierarchy,labels,start)
        middle=info.joints[1]
        saved_type=cmds.getAttr(middle+'.type')
        saved_other=cmds.getAttr(middle+'.otherType')
        saved_draw=cmds.getAttr(middle+'.drawLabel')
        cmds.setAttr(middle+'.type',18)
        cmds.setAttr(middle+'.otherType','Mid',type='string')
        cmds.setAttr(middle+'.drawLabel',True)
        controller.body_rebuild(':','SplineFitLabelGrow')
        labelled=host.read_character_registration()
        assert control_count(splines(labelled)[0])==count+1
        cmds.setAttr(middle+'.type',saved_type)
        cmds.setAttr(middle+'.otherType',saved_other,type='string')
        cmds.setAttr(middle+'.drawLabel',saved_draw)
        controller.body_rebuild(':','SplineFitLabelReduce')
        assert control_count(splines(host.read_character_registration())[0])==count
        report['ordinary_fit_mid_label_rebuild']=True
    (output/'spline-count-rebuild.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS Spline count rebuild',report)


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),fit_labels='--fit-label-counts' in sys.argv[3:])
