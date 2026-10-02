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


def capture(host,container,skin,all_objects,right_eye):
    host._require_transaction();c=host._cmds
    fit=_one(c,container,'transform')
    joints=c.listRelatives(fit,allDescendents=True,fullPath=True,type='joint') or []
    if not joints:raise ValueError('请先导入含关节的 FitSkeleton')
    if not skin:raise ValueError('请先在 Body / Pre 记录 Skin 模型')
    if c.objExists('AutoPlacing'):
        raise ValueError('请先结束当前 AutoPlace 引导编辑，再缩放 Fit')
    meshes=tuple(dict.fromkeys(_mesh(c,name) for name in skin))
    for name in all_objects:_one(c,name)
    for name in right_eye:
        if not c.ls(name,long=True):raise ValueError('眼球输入不存在：'+name)
    curves=c.listRelatives(fit,shapes=True,noIntermediate=True,fullPath=True,type='nurbsCurve') or []
    if len(curves)!=1:raise ValueError('自动缩放需要原版 FitSkeleton 容器曲线')
    # listRelatives -ad returns descendants first. MEL reverses this list for
    # both capture and writes so descendants keep their planned world points.
    host._transaction_changed=True
    c.currentTime(1)
    ordered=tuple(reversed(joints))
    states=tuple(FitAutoScaleJoint(joint,tuple(c.xform(joint,query=True,worldSpace=True,translation=True)),
        float(c.getAttr(joint+'.fat')) if c.objExists(joint+'.fat') else None) for joint in ordered)
    group=None
    selection=c.ls(selection=True,long=True) or []
    try:
        host._transaction_changed=True
        group=_temporary_group(c,'AdvPy_FitAutoScaleTemp_')
        copies=[]
        for mesh in meshes:
            clone=c.duplicate(mesh,name='AdvPy_FitAutoScaleMesh_'+uuid4().hex[:10],returnRootsOnly=True)[0]
            clone=c.parent(clone,group,absolute=True)[0]
            copies.append(clone)
        combined=(copies[0] if len(copies)==1 else
                  c.polyUnite(copies,constructionHistory=False,mergeUVSets=0)[0])
        if len(copies)>1:combined=c.parent(combined,group,absolute=True)[0]
        maximum=float(c.getAttr(combined+'.boundingBoxMaxY'))
        return FitAutoScaleSnapshot(fit,states,float(c.getAttr(fit+'.scaleY')),maximum,
            float(c.getAttr(curves[0]+'.boundingBoxMaxX')))
    finally:
        if group and c.objExists(group):c.delete(group)
        c.select(selection,replace=True) if selection else c.select(clear=True)


def _eye_geometry(c,eye,group):
    objects=[name for name in eye if '.' not in name]
    if objects:
        clone=c.duplicate(_mesh(c,objects[0]),name='AdvPy_FitAutoScaleMesh_'+uuid4().hex[:10],returnRootsOnly=True)[0]
    else:
        source=_mesh(c,eye[0].split('.',1)[0])
        if any(_one(c,name.split('.',1)[0])!=source for name in eye):
            raise ValueError('眼球组件必须来自同一网格')
        import re
        counts={'vtx':int(c.polyEvaluate(source,vertex=True)),
                'e':int(c.polyEvaluate(source,edge=True)),
                'f':int(c.polyEvaluate(source,face=True))}
        expanded=c.ls(eye,flatten=True) or []
        if not expanded:raise ValueError('眼球组件不存在')
        # Maya can discard invalid indices while expanding components and then
        # convert the surviving object into every face. Validate explicit input
        # indices as well as the expanded selection before converting it.
        for component in (*eye,*expanded):
            match=re.search(r'\.(vtx|e|f)\[(\d+)\]$',component)
            if match and int(match[2])>=counts[match[1]]:
                raise ValueError('眼球组件索引超出网格范围：'+component)
        faces=c.ls(c.polyListComponentConversion(eye,toFace=True),flatten=True) or []
        if not faces:raise ValueError('眼球组件没有可用的面')
        kept={face.split('.',1)[1] for face in faces}
        clone=c.duplicate(source,name='AdvPy_FitAutoScaleMesh_'+uuid4().hex[:10],returnRootsOnly=True)[0]
        count=int(c.polyEvaluate(clone,face=True))
        remove=[clone+'.f['+str(index)+']' for index in range(count) if 'f['+str(index)+']' not in kept]
        if remove:c.delete(remove)
    clone=c.parent(clone,group,absolute=True)[0]
    c.setAttr(clone+'.visibility',True)
    c.xform(clone,centerPivots=True)
    position=tuple(c.xform(clone,query=True,worldSpace=True,pivots=True)[:3])
    box=tuple(c.xform(clone,query=True,worldSpace=True,boundingBox=True))
    return position,(box[5]-box[2])/2.


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
    points=[c.xform(joint,query=True,worldSpace=True,translation=True) for joint in joints]
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
    for joint,position in zip(joints,adjusted):c.xform(joint,worldSpace=True,translation=position)
    c.delete(tuple(created))
    raw.delete(softmods)


def apply(host,plan,right_eye,skin,all_objects,*,keep_guides=False):
    host._require_transaction();c=host._cmds
    host._transaction_changed=True
    selection=c.ls(selection=True,long=True) or []
    old_display=c.jointDisplayScale(query=True)
    group=None
    try:
        c.currentTime(1)
        for joint,position in plan.positions:c.xform(joint,worldSpace=True,translation=position)
        for joint,fat in plan.fats:c.setAttr(joint+'.fat',fat)
        c.setAttr(plan.before.container+'.scale',1.,1.,1.,type='double3')
        curve=(c.listRelatives(plan.before.container,shapes=True,noIntermediate=True,fullPath=True,type='nurbsCurve') or [None])[0]
        components=c.ls(curve+'.cv[0:99]',flatten=True) or []
        c.scale(plan.icon_factor,plan.icon_factor,plan.icon_factor,components,relative=True,pivot=(0.,0.,0.))
        c.jointDisplayScale(plan.joint_display_scale)
        group=_temporary_group(c,'AdvPy_FitAutoScaleEye_')
        if right_eye:
            eye=[joint.path for joint in plan.before.joints if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]=='Eye']
            if len(eye)!=1:raise ValueError('眼球输入需要唯一的 Eye Fit 关节')
            position,radius=_eye_geometry(c,right_eye,group)
            c.xform(eye[0],worldSpace=True,translation=position)
            ends=[joint.path for joint in plan.before.joints if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]=='EyeEnd']
            if len(ends)>1:raise ValueError('EyeEnd Fit 关节不唯一')
            if ends:c.setAttr(ends[0]+'.translateX',radius)
            if keep_guides:
                pivot=c.createNode('transform',name='asFitPivotEye',parent='asFitPivots',skipSelect=True)
                c.xform(pivot,worldSpace=True,translation=position)
                c.addAttr(pivot,longName='radius',attributeType='double',defaultValue=radius)
        if keep_guides:return bool(right_eye)
        _remove_softmods(host,plan,skin,group)
        for mesh in dict.fromkeys((*skin,*all_objects)):
            # Skin / All are explicit preparation inputs and can belong to an
            # external model namespace. This source action only changes their
            # visibility; retain namespace ownership checks for generated rig.
            raw=getattr(c,'raw',c)
            try:raw.setAttr(host.scene_address(mesh)+'.visibility',True)
            except RuntimeError:pass
        roots=[joint.path for joint in plan.before.joints if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]=='Root']
        if roots:
            try:c.setAttr(roots[0]+'.visibility',True)
            except RuntimeError:pass
        if c.objExists('FitSkeletonVisualizers'):c.delete('FitSkeletonVisualizers')
        return bool(right_eye)
    except Exception:
        # jointDisplayScale is a preference and is not reliably undoable.
        c.jointDisplayScale(old_display)
        raise
    finally:
        if group and c.objExists(group):c.delete(group)
        c.select(selection,replace=True) if selection else c.select(clear=True)
