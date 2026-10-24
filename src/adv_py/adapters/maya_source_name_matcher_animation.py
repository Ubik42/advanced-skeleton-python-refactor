"""Original BakeFromKeepAnimationSkeleton, MEL 21396 and 21737–21760."""
from adv_py.core.source_name_matcher import source_name_matcher_targets
from adv_py.core.source_control_identity import source_fk_bindings,source_leaf
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.application.name_matcher_animation import NameMatcherAnimationBakeResult
from .maya_source_name_matcher_context import mapping_action


def _node(c,address):
    paths=c.ls(address,long=True) or ()
    identities=c.ls(address,uuid=True) or ()
    if len(paths)!=1 or len(identities)!=1:
        raise FitSkeletonValidationError('NameMatcher 保留动画对象地址或 UUID 歧义：'+address)
    return paths[0],identities[0]


def _boundary(c):
    nodes=tuple(c.ls(':NameMatcherKeepAnimation:*',long=True) or ())
    if not nodes:return ()
    roots=tuple(node for node in nodes
        if c.attributeQuery('advPyKeepAnimation',node=node,exists=True)
        and c.getAttr(node+'.advPyKeepAnimation'))
    if not roots:
        raise FitSkeletonValidationError('NameMatcher 保留动画命名空间缺少实际复制来源')
    if any(not any(node==root or node.startswith(root+'|') for root in roots) for node in nodes):
        raise FitSkeletonValidationError('NameMatcher 保留动画命名空间有未归属的对象')
    rows=[]
    for node in nodes:
        path,identity=_node(c,node)
        parents=c.listRelatives(path,parent=True,fullPath=True) or ()
        parent=_node(c,parents[0])[1] if parents else None
        rows.append((path,identity,c.nodeType(path),parent))
    return tuple(rows)


def _skins(c, ignored_roots=()):
    """Compare production Skin endpoints, excluding the retained DAG copy.

    duplicate -inputConnections can share an existing Skin output with copied
    geometry. Deleting that copy must not look like a production-mesh change.
    Only geometry below the specifically captured copy roots is excluded.
    """
    def production_geometry(node):
        path,identity=_node(c,node)
        return None if any(path==root or path.startswith(root+'|')
                           for root in ignored_roots) else identity
    return tuple(sorted((
        _node(c,skin)[1],
        tuple(sorted(_node(c,node)[1] for node in c.skinCluster(skin,query=True,influence=True) or ())),
        tuple(sorted(identity for node in c.skinCluster(skin,query=True,geometry=True) or ()
                     if (identity:=production_geometry(node)) is not None)))
        for skin in c.ls(type='skinCluster') or ()))


def keep(host,source_root,inputs):
    """Native asKeepAnimationSkeleton, including the Yes/No branch."""
    host._require_transaction()
    c=getattr(host._cmds,'raw',host._cmds)
    if host.capture_name_matcher_source_animation(source_root)!=inputs:
        raise FitSkeletonValidationError('NameMatcher 来源动画在保留前变化')
    root,source_uuid=_node(c,source_root)
    if c.nodeType(root) not in ('joint','transform'):
        raise FitSkeletonValidationError('NameMatcher 保留动画需要来源顶层骨架')
    selection=tuple(c.ls(selection=True,long=True) or ())
    host._transaction_changed=True
    c.select(root,hierarchy=True,replace=True)
    # asKeepAnimationSkeleton selects the source hierarchy before detecting
    # animation. Its no-animation return leaves that selection in place.
    if not inputs:return '',0
    choice=c.confirmDialog(title='Build ?',message='Animation detected\n\nTransfer animation to Rig ?',
        button=('Yes','No'),defaultButton='Yes',dismissString='No')
    if choice!='Yes':
        c.select(root,hierarchy=True,replace=True)
        c.delete(channels=True,unitlessAnimationCurves=False,hierarchy='none',controlPoints=False,shape=False)
        return '',0
    if not c.namespace(exists=':NameMatcherKeepAnimation'):
        c.namespace(addNamespace=':NameMatcherKeepAnimation')
    c.namespace(setNamespace=':NameMatcherKeepAnimation')
    try:
        duplicate=c.duplicate(root,inputConnections=True)[0]
    finally:
        # Original returns to root namespace, not to an invented target scope.
        c.namespace(setNamespace=':')
    clone,_=_node(c,duplicate)
    c.addAttr(clone,longName='advPyKeepAnimation',attributeType='bool',defaultValue=True)
    c.setAttr(clone+'.advPyKeepAnimation',lock=True)
    c.addAttr(clone,longName='advPySourceUUID',dataType='string')
    c.setAttr(clone+'.advPySourceUUID',source_uuid,type='string',lock=True)
    c.select(root,hierarchy=True,replace=True)
    c.delete(channels=True,unitlessAnimationCurves=False,hierarchy='none',controlPoints=False,shape=False)
    c.select(selection,replace=True) if selection else c.select(clear=True)
    return clone,len(inputs)


@mapping_action
def bake(host,source_root,rows,rules):
    """Resolve kept joint names directly, as the original mapping UI does.

    Do not require the original skeleton to survive a preceding Skin transfer,
    reconstruct copied curves, resample the clip, or delete arbitrary curves.
    Original source hierarchy and target-removal behavior belong to Maya.
    """
    host._require_transaction()
    c=getattr(host._cmds,'raw',host._cmds)
    kept=_boundary(c)
    if not kept:return NameMatcherAnimationBakeResult(0,-1.,-1.,())
    registration=host.read_character_registration()
    copy_roots=tuple(row[0] for row in kept
        if c.attributeQuery('advPyKeepAnimation',node=row[0],exists=True)
        and c.getAttr(row[0]+'.advPyKeepAnimation'))
    skins=_skins(c,copy_roots)
    fk={}
    for joint,control in source_fk_bindings(registration):
        if joint in fk and fk[joint]!=control:
            raise FitSkeletonValidationError('NameMatcher FK 控制身份不唯一：'+joint)
        fk[joint]=control
    joints=host._cmds.listRelatives('DeformationSystem',allDescendents=True,type='joint',fullPath=True) or ()
    pairs=[];missing=[]
    for joint,target in source_name_matcher_targets(joints,rows,rules,namespace='NameMatcherKeepAnimation'):
        # Source addresses FK + the full deform joint name literally. Resolve
        # that role to the saved Python control, without substituting RootX.
        control=fk.get(source_leaf(joint))
        if control is None:
            native='FK'+source_leaf(joint)
            if host._cmds.objExists(native):control=native
        if control is None or not c.objExists(target):
            missing.append(target if not c.objExists(target) else source_leaf(joint));continue
        target,target_id=_node(c,target)
        destination,destination_id=_node(c,host.scene_address(control))
        pairs.append((target,target_id,destination,destination_id))
    if _boundary(c)!=kept or _skins(c,copy_roots)!=skins:
        raise FitSkeletonValidationError('NameMatcher 保留动画来源在执行前变化')
    host._transaction_changed=True
    # Original creates constraints before collecting timeline keys and before
    # changing the FKIK modes. Preserve maintainOffset at that actual time.
    for target,_,control,_ in pairs:
        c.parentConstraint(target,control,maintainOffset=True)
    nodes=tuple(row[0] for row in kept)
    c.select(nodes,hierarchy=True,replace=True)
    times=tuple(sorted(float(time) for time in c.keyframe(query=True,timeChange=True) or ()))
    if not times:
        # MEL leaves the kept skeleton and constraints when there are no keys.
        # Do not invent a clip or clear source assets in that branch.
        return NameMatcherAnimationBakeResult(0,-1.,-1.,tuple(dict.fromkeys(missing)))
    first,last=-1.,float(int(times[-1]))
    c.playbackOptions(minTime=first,animationStartTime=first,maxTime=last,animationEndTime=last)
    c.select(clear=True)
    for control in host._cmds.sets('ControlSet',query=True) or ():
        if host._cmds.attributeQuery('FKIKBlend',node=control,exists=True):
            host._cmds.setAttr(control+'.FKIKBlend',0)
    if host._cmds.objExists('HipSwinger_M.stabilize'):
        host._cmds.setAttr('HipSwinger_M.stabilize',0)
    controls=tuple(row[2] for row in pairs)
    c.bakeResults(controls,simulation=True,time=(first,last),sampleBy=1,
        disableImplicitControl=True,preserveOutsideKeys=False,sparseAnimCurveBake=False,
        removeBakedAttributeFromLayer=False,bakeOnOverrideLayer=False,controlPoints=False,shape=False)
    c.currentTime(-1)
    c.select(controls,replace=True)
    c.delete(controls,staticChannels=True,unitlessAnimationCurves=False,
        hierarchy='none',controlPoints=False,shape=True)
    c.delete(nodes)
    c.namespace(removeNamespace=':NameMatcherKeepAnimation')
    if _skins(c,copy_roots)!=skins:
        raise RuntimeError('NameMatcher 原版动画烘焙改变了 Skin、影响关节或模型身份')
    return NameMatcherAnimationBakeResult(len(controls),first,last,tuple(dict.fromkeys(missing)))
