"""Native Maya implementation of ADV's Fit automatic scaling phase."""
from uuid import uuid4
from adv_py.core.fit_auto_scale import FitAutoScaleJoint, FitAutoScaleSnapshot


def _one(c,name,kind=None):
    nodes=c.ls(name,long=True,type=kind) if kind else c.ls(name,long=True)
    if len(nodes or [])!=1:
        raise ValueError('自动缩放来源不存在或不唯一：'+name)
    return nodes[0]


def _mesh(c,name):
    node=_one(c,name)
    if c.nodeType(node)=='mesh':
        node=(c.listRelatives(node,parent=True,fullPath=True) or [None])[0]
    if c.nodeType(node)!='transform' or not c.listRelatives(node,shapes=True,noIntermediate=True,type='mesh'):
        raise ValueError('自动缩放需要多边形 Skin 模型：'+name)
    return node


def _temporary_group(c,prefix):
    group=c.createNode('transform',name=prefix+uuid4().hex[:10],skipSelect=True)
    # polyUnite -ch 0 deletes an emptied source parent. Original AutoPlacing
    # has many other child groups; retain one empty child for the same reason.
    c.createNode('transform',name='AdvPy_FitAutoScaleKeep',parent=group,skipSelect=True)
    return group


def capture_combined(host,container,combined):
    """AutoPlace samples its actual CombinedSkin after creating scan groups.

    Do not duplicate the models a second time or validate optional All/eye
    inputs here: original asFitAutoPlace samples them at their own source steps.
    """
    host._require_transaction()
    c=host._cmds
    fit=_one(c,container,'transform')
    joints=c.listRelatives(fit,allDescendents=True,fullPath=True,type='joint') or []
    ordered=tuple(reversed(joints))
    states=tuple(FitAutoScaleJoint(joint,tuple(c.xform(joint,query=True,worldSpace=True,translation=True)),
        float(c.getAttr(joint+'.fat')) if c.objExists(joint+'.fat') else None) for joint in ordered)
    curves=c.listRelatives(fit,shapes=True,noIntermediate=True,fullPath=True,type='nurbsCurve') or []
    if len(curves)!=1:raise ValueError('自动缩放需要原版 FitSkeleton 容器曲线')
    return FitAutoScaleSnapshot(fit,states,float(c.getAttr(fit+'.scaleY')),
        float(c.getAttr(combined+'.boundingBoxMaxY')),float(c.getAttr(curves[0]+'.boundingBoxMaxX')))


def _eye_geometry(c,eye,group=None):
    """Source first-object / native component-face extraction, 51967–51993."""
    from .maya_fit_auto_place_mesh import cast, invert
    from contextlib import nullcontext
    from maya import mel
    raw = getattr(c, 'raw', c)
    scope = c._creation_namespace if hasattr(c, '_creation_namespace') else nullcontext
    objects = [name for name in eye if name and '.' not in name]
    if not objects and any('.' in name for name in eye):
        source = _mesh(c, eye[0].split('.',1)[0])
        c.select(source, replace=True)
        with scope():
            clone = raw.duplicate(fullPath=True)[0]
        clone = c.rename(clone, 'asDuplicatedEye')
        components = cast(tuple(c.ls(eye, flatten=True) or ()), clone)
        c.select(components, replace=True)
        with scope():mel.eval('ConvertSelectionToFaces;')
        invert(c)
        removed = raw.ls(selection=True) or []
        if removed:raw.delete(removed)
        objects = [clone]
    if not objects:return None
    clone = c.duplicate(objects[0], name='tempEye')[0]
    if c.listRelatives(clone, parent=True):clone = c.parent(clone, world=True)[0]
    c.setAttr(clone + '.visibility', 1)
    c.select(clone, replace=True)
    with scope():mel.eval('CenterPivot;')
    position = tuple(c.xform(clone, query=True, worldSpace=True, pivots=True)[:3])
    box = c.xform(clone, query=True, worldSpace=True, boundingBox=True)
    c.delete(clone)
    return position, (box[5]-box[2])/2.


def _combined_sample(c,meshes,group):
    copies=[]
    for mesh in meshes:
        clone=c.duplicate(_mesh(c,mesh),name='AdvPy_FitAutoScaleMesh_'+uuid4().hex[:10],returnRootsOnly=True)[0]
        copies.append(c.parent(clone,group,absolute=True)[0])
    if len(copies)==1:return copies[0]
    result=c.polyUnite(copies,constructionHistory=False,mergeUVSets=0)[0]
    return c.parent(result,group,absolute=True)[0]


def _remove_softmods(host,plan,skin,group):
    """MEL 53484–53517: unwarp Fit points, then remove temporary SoftMods."""
    c=host._cmds
    raw=getattr(c,'raw',c)
    softmods=list(c.ls(type='softMod') or [])
    # Preparation models may be external to the rig. Include their actual
    # upstream SoftMods without discovering modifiers on unrelated characters.
    if raw is not c:
        softmods=[host.scene_address(node) for node in softmods]
        for mesh in skin:
            softmods.extend(node for node in raw.listHistory(host.scene_address(mesh)) or []
                            if raw.nodeType(node)=='softMod')
        softmods=list(dict.fromkeys(softmods))
    if not softmods:return
    before=_combined_sample(c,skin,group)
    for node in softmods:raw.setAttr(node+'.envelope',0.)
    undeformed=_combined_sample(c,skin,group)
    for node in softmods:raw.setAttr(node+'.envelope',1.)
    blend=c.blendShape(before,undeformed,frontOfChain=True,origin='world',weight=(0,1.))[0]
    joints=tuple(joint.path for joint in plan.before.joints)
    # asFitDeleteGuides builds this command by MEL float/string concatenation,
    # which retains ten significant digits rather than the full API doubles.
    points=[tuple(float(format(value,'.10g')) for value in
                  c.xform(joint,query=True,worldSpace=True,translation=True)) for joint in joints]
    curve=c.curve(degree=1,point=points)
    curve=c.parent(curve,group,absolute=True)[0]
    # Use Maya's stock Wrap command with the original arguments. No ADV MEL
    # procedure is executed in production.
    address=host.scene_address
    from maya import mel
    raw.select((address(curve),address(undeformed)),replace=True)
    before_wrap=set(raw.ls(type='wrap') or [])
    from contextlib import nullcontext
    with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
        mel.eval('doWrapArgList "7" { "1","0","0.1", "1", "0", "1", "1", "0" };')
    created=set(raw.ls(type='wrap') or [])-before_wrap
    if len(created)!=1:raise RuntimeError('自动缩放清理未生成唯一的 Wrap')
    # The Wrap base copy is parented alongside its driver; keep it inside the
    # temporary group so it cannot survive cleanup.
    c.setAttr(blend+'.weight[0]',0.)
    adjusted=[tuple(c.xform(curve+'.cv['+str(index)+']',query=True,worldSpace=True,translation=True))
              for index in range(len(joints))]
    # The source creates CVs in allDescendents order, then writes the captured
    # positions backwards so moving a parent cannot shift an already set child.
    for joint,position in reversed(tuple(zip(joints,adjusted))):
        c.xform(joint,worldSpace=True,translation=position)
    c.delete(tuple(created))
    raw.delete(softmods)


def apply_scale_and_eye(host,plan,right_eye):
    host._require_transaction();c=host._cmds
    host._transaction_changed=True
    selection=c.ls(selection=True,long=True) or []
    old_display=c.jointDisplayScale(query=True)
    group=None
    try:
        c.currentTime(1)
        fats=dict(plan.fats)
        for joint,position in plan.positions:
            c.xform(joint,worldSpace=True,translation=position)
            if joint in fats:c.setAttr(joint+'.fat',fats[joint])
        c.setAttr(plan.before.container+'.scale',1.,1.,1.,type='double3')
        curve=(c.listRelatives(plan.before.container,shapes=True,noIntermediate=True,fullPath=True,type='nurbsCurve') or [None])[0]
        components=c.ls(curve+'.cv[0:99]',flatten=True) or []
        c.scale(plan.icon_factor,plan.icon_factor,plan.icon_factor,components,relative=True,pivot=(0.,0.,0.))
        c.jointDisplayScale(plan.joint_display_scale)
        if right_eye:
            eye=[joint.path for joint in plan.before.joints if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]=='Eye']
            if len(eye)!=1:raise ValueError('眼球输入需要唯一的 Eye Fit 关节')
            position,radius=_eye_geometry(c,right_eye,group)
            ends=[joint.path for joint in plan.before.joints if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]=='EyeEnd']
            if len(ends)>1:raise ValueError('EyeEnd Fit 关节不唯一')
            pivot=c.createNode('transform',name='asFitPivotEye',parent='asFitPivots',skipSelect=True)
            c.xform(pivot,worldSpace=True,translation=position)
            c.addAttr(pivot,longName='radius',attributeType='double',defaultValue=radius)
            if c.objExists('asDuplicatedEye'):c.delete('asDuplicatedEye')
            c.delete(c.pointConstraint(pivot,eye[0],weight=1.))
            if ends:c.setAttr(ends[0]+'.translateX',radius)
        return bool(right_eye)
    except Exception:
        # jointDisplayScale is a preference and is not reliably undoable.
        c.jointDisplayScale(old_display)
        raise
    finally:
        if group and c.objExists(group):c.delete(group)
        c.select(selection,replace=True) if selection else c.select(clear=True)
