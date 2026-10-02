"""Python port of ADV 6.925 asFitDeleteGuides, MEL 53409–53518."""
from types import SimpleNamespace
from contextlib import nullcontext
from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_FINGERS,FitGuideCleanupResult
from adv_py.core.fit_auto_scale import FitAutoScaleJoint
from .maya_fit_auto_scale import _remove_softmods,_temporary_group


def stock_wrap(host,driven,driver,arguments=None):
    """Maya's stock Wrap operation, retaining the exact source arguments."""
    from maya import mel
    c=host._cmds;raw=getattr(c,'raw',c)
    raw.select((host.scene_address(driven),host.scene_address(driver)),replace=True)
    before=set(raw.ls(type='wrap') or [])
    with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
        mel.eval('doWrapArgList "7" '+(arguments or '{ "1","0","0.1", "1", "0", "1", "1", "0" }')+';')
    created=set(raw.ls(type='wrap') or [])-before
    if len(created)!=1:raise RuntimeError('Fit 引导未生成唯一的 Wrap')
    return next(iter(created))


def update_joint_subtree(host,root,container):
    # Original asFitModeUpdateJoints takes child names and updates their RLA
    # parents. Include the root's parent, then orient its descendant parents.
    from adv_py.application.fit_orientation_auto import OrientFitJoints
    from adv_py.core.fit_orientation import FitOrientationRequest,select_fit_orientation_child
    c=host._cmds
    joints=[root]+list(reversed(c.listRelatives(root,allDescendents=True,type='joint',fullPath=True) or []))
    parents=c.listRelatives(root,parent=True,type='joint',fullPath=True) or []
    names=tuple(dict.fromkeys((*parents,*joints)))
    snapshot=host.capture_fit_orientation(container)
    paths={node.short_name:node.path for node in snapshot.hierarchy.joints}
    targets=tuple(path for name in names
                  if (path:=paths.get(name,name)) in {node.path for node in snapshot.hierarchy.joints}
                  and select_fit_orientation_child(snapshot,path) is not None)
    if targets:
        editor=OrientFitJoints(host)
        with host.fit_manual_update_channels(container):
            editor.apply_plan_in_transaction(editor.plan(FitOrientationRequest(targets),container))


def finish(host,container,skin,all_objects):
    host._require_transaction();c=host._cmds;raw=getattr(c,'raw',c)
    if not c.objExists('AutoPlacing'):return FitGuideCleanupResult(False)
    selection=raw.ls(selection=True,long=True) or []
    host._transaction_changed=True
    restored=[];arm=False;group=None
    # Capture the Fit paths before deleting any constraints or guide parents.
    joints=tuple(reversed(c.listRelatives(container,allDescendents=True,type='joint',fullPath=True) or []))
    softmods=set(c.ls(type='softMod') or [])
    for mesh in skin:
        softmods.update(node for node in raw.listHistory(host.scene_address(mesh)) or []
                        if raw.nodeType(node)=='softMod')
    try:
        if c.objExists('straightenBS'):
            for finger in FIT_AUTO_PLACE_FINGERS:
                finger_joints=[finger+'Finger'+str(i) for i in range(1,5)
                               if c.objExists(finger+'Finger'+str(i))]
                if not finger_joints:continue
                points=[c.xform(joint,query=True,worldSpace=True,translation=True) for joint in finger_joints]
                curve=c.curve(degree=1,name='FingerSimpleCurve'+finger,point=points)
                curve=c.parent(curve,'asFitPivotsFingers',absolute=True)[0]
                for joint in finger_joints:
                    constraint=joint+'_pointConstraint1'
                    if c.objExists(constraint):c.delete(constraint)
                stock_wrap(host,curve,'CombinedSkinUpper_M')
                c.setAttr('straightenBS.fingerStraight',0.)
                adjusted=[tuple(c.xform(curve+'.cv['+str(i)+']',query=True,worldSpace=True,translation=True))
                          for i in range(len(finger_joints))]
                for joint,point in zip(finger_joints,adjusted):c.xform(joint,worldSpace=True,translation=point)
                c.setAttr('straightenBS.fingerStraight',1.)
                restored.append(finger)
            if c.objExists('Wrist'):update_joint_subtree(host,'Wrist',container)
        if c.objExists('asFitShoulderStraight'):
            c.parent('asFitShoulderStraight',world=True,absolute=True)
        c.delete('AutoPlacing')
        for mesh in (*skin,*all_objects):
            try:raw.setAttr(host.scene_address(mesh)+'.visibility',True)
            except RuntimeError:pass
        if c.objExists('asFitShoulderStraight') and c.objExists('Shoulder'):
            constraint=c.parentConstraint('asFitShoulderStraight','Shoulder',maintainOffset=True)[0]
            c.setAttr('asFitShoulderStraight.rotate',0.,0.,0.,type='double3')
            c.delete(constraint)
            if c.objExists('asFitElbowStraight'):
                constraint=c.parentConstraint('asFitElbowStraight','Elbow',maintainOffset=True)[0]
                c.setAttr('asFitElbowStraight.rotate',0.,0.,0.,type='double3')
                c.delete(constraint)
            c.delete('asFitShoulderStraight')
            c.makeIdentity('Shoulder',apply=True,translate=False,rotate=True,scale=False)
            arm=True
        if softmods:
            group=_temporary_group(c,'AdvPy_FitAutoScaleCleanup_')
            states=tuple(FitAutoScaleJoint(joint,tuple(c.xform(joint,query=True,worldSpace=True,translation=True)))
                         for joint in joints)
            _remove_softmods(host,SimpleNamespace(before=SimpleNamespace(joints=states)),skin,group)
        if c.objExists('FitSkeletonVisualizers'):c.delete('FitSkeletonVisualizers')
        try:c.setAttr('Root.visibility',True)
        except RuntimeError:pass
        return FitGuideCleanupResult(True,tuple(restored),arm,len(softmods))
    finally:
        if group and c.objExists(group):c.delete(group)
        available=[node for node in selection if raw.objExists(node)]
        raw.select(available,replace=True) if available else raw.select(clear=True)
