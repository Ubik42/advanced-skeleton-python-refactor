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
    # asFitDeleteGuides calls asFitModeUpdateJoints Wrist 1. Use that shared
    # per-child native sequence, including recursive ordering and source RLA
    # parent handling; a batch parent-orientation plan samples different frames.
    return host.update_source_fit_orientations((root,),container=container,recursive=True)


def finish(host,container,skin,all_objects):
    host._require_transaction();c=host._cmds;raw=getattr(c,'raw',c)
    if not c.objExists('AutoPlacing'):return FitGuideCleanupResult(False)
    selection=raw.ls(selection=True,long=True) or []
    host._transaction_changed=True
    restored=[];arm=False;group=None
    # Capture the Fit paths before deleting any constraints or guide parents.
    joints=tuple(c.listRelatives(container,allDescendents=True,type='joint',fullPath=True) or [])
    softmods=set(c.ls(type='softMod') or [])
    for mesh in skin:
        softmods.update(node for node in raw.listHistory(host.scene_address(mesh)) or []
                        if raw.nodeType(node)=='softMod')
    try:
        if c.objExists('straightenBS'):
            for finger in FIT_AUTO_PLACE_FINGERS:
                finger_joints=[finger+'Finger'+str(i) for i in range(1,5)
                               if c.objExists(finger+'Finger'+str(i))]
                points=[]
                for joint in finger_joints:
                    # Source samples each segment and immediately releases its
                    # constraint before sampling the next child.
                    position=c.xform(joint,query=True,worldSpace=True,translation=True)
                    # MEL concatenates floats into its curve command with ten
                    # significant digits before eval parses them back.
                    points.append(tuple(float(format(value,'.10g')) for value in position))
                    constraint=joint+'_pointConstraint1'
                    if c.objExists(constraint):c.delete(constraint)
                curve='FingerSimpleCurve'+finger
                c.curve(degree=1,name=curve,point=points)
                # MEL addresses the requested name even if Maya generated a
                # suffixed duplicate. Keep the same retry/collision behavior.
                c.parent(curve,'asFitPivotsFingers',absolute=True)
                stock_wrap(host,curve,'CombinedSkinUpper_M')
                c.setAttr('straightenBS.fingerStraight',0.)
                # MEL uses the original segment number as the CV index even
                # when a Fit segment is absent. Retain that addressing and
                # its failure behavior rather than packing surviving joints.
                for segment in range(1,5):
                    joint=finger+'Finger'+str(segment)
                    if not c.objExists(joint):continue
                    point=c.xform(curve+'.cv['+str(segment-1)+']',query=True,worldSpace=True,translation=True)
                    c.xform(joint,worldSpace=True,translation=point)
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
            c.parentConstraint('asFitShoulderStraight','Shoulder',maintainOffset=True)
            c.setAttr('asFitShoulderStraight.rotate',0.,0.,0.,type='float3')
            c.delete('Shoulder_parentConstraint1')
            if c.objExists('asFitElbowStraight'):
                c.parentConstraint('asFitElbowStraight','Elbow',maintainOffset=True)
                c.setAttr('asFitElbowStraight.rotate',0.,0.,0.,type='float3')
                c.delete('Elbow_parentConstraint1')
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
        try:
            raw.select(available,replace=True) if available else raw.select(clear=True)
        except RuntimeError:
            # Original catchQuiet(select(oldSelection)) does not replace a
            # completed cleanup with an error from a stale selection.
            pass
