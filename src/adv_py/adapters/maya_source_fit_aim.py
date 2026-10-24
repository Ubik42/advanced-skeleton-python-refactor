"""ADV 6.925 MEL 6815–7351: evaluate Fit orientation in Maya's DAG.

The native path uses the source's live aimConstraint operations. In
particular, a straight RP plane is evaluated first and corrected at its
middle rotate pivot; it is not rejected by a parallel vector solver.
"""
from contextlib import contextmanager

from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.fit_orientation import FitOrientationValidationError


AXES = ('X','Y','Z','-X','-Y','-Z')
TR = ('tx','ty','tz','rx','ry','rz')


def axis_vector(axis):
    return tuple((-1. if axis.startswith('-') else 1.) if letter==axis[-1]
                 else 0. for letter in 'XYZ')


def tertiary_axis(primary,secondary):
    """asGetTerAxis's six signed permutations, without a fallback axis."""
    table = {('X','Y'):'Z',('X','Z'):'-Y',('Y','X'):'-Z',
             ('Y','Z'):'X',('Z','X'):'Y',('Z','Y'):'-X'}
    try:result = table[(primary[-1],secondary[-1])]
    except KeyError as error:
        raise FitOrientationValidationError('原版 Fit 主轴与副轴没有第三轴') from error
    if primary.startswith('-')!=secondary.startswith('-'):
        result=result[1:] if result.startswith('-') else '-'+result
    return result


def _negative(vector):return tuple(-value for value in vector)


class DagIdentity:
    """Use UUIDs only to follow native reparenting, never to replace a node."""
    def __init__(self,host,address):
        self.c = host._cmds
        self.raw = getattr(host,'_raw_cmds',getattr(self.c,'raw',self.c))
        self.identity = CharacterIdentity(getattr(host,'namespace',None) or '')
        physical=self.identity.to_scene(address)
        ids=self.raw.ls(physical,uuid=True) or ()
        if len(ids)!=1:
            raise FitOrientationValidationError('Fit 操作节点身份不唯一：'+address)
        self.uuid=ids[0]

    @property
    def path(self):
        # Scoped ls would treat a UUID as a node name and namespace it.
        matches=self.raw.ls(self.uuid,long=True) or ()
        if len(matches)!=1:
            raise FitOrientationValidationError('Fit 操作期间节点身份消失或不唯一')
        return self.identity.to_local(matches[0])


def _temporary(host, *,parent=None,name=None):
    options={'skipSelect':True}
    if parent is not None:options['parent']=parent.path
    if name is not None:options['name']=name
    return DagIdentity(host,host._cmds.createNode('transform',**options))


def _aim(c,targets,receiver,aim,up, *,keep=False,**options):
    constraints=c.aimConstraint(*targets,receiver,aimVector=aim,upVector=up,**options)
    if not keep:c.delete(constraints)
    return constraints


@contextmanager
def native_update_context(host):
    """Source selection and Move pivot-edit restoration around the whole call."""
    c=host._cmds
    raw=getattr(host,'_raw_cmds',getattr(c,'raw',c))
    selected=tuple(c.ls(selection=True,long=True) or ())
    pivot=bool(raw.manipMoveContext('Move',query=True,editPivotMode=True))
    try:yield
    finally:
        try:
            c.select(selected,replace=True) if selected else c.select(clear=True)
        except RuntimeError:pass  # Native catchQuiet(select(oldSelection)).
        if pivot and not raw.manipMoveContext('Move',query=True,editPivotMode=True):
            from maya import mel
            mel.eval('EnterEditMode;')


def aim_joint(host,parent_path,child_path,snapshot,info,state):
    """Translate one source preferred-child operation, with evaluated frames."""
    host._require_transaction()
    c=host._cmds
    parent,child=DagIdentity(host,parent_path),DagIdentity(host,child_path)
    parent_leaf=parent_path.rsplit('|',1)[-1].rsplit(':',1)[-1]
    labels=dict(snapshot.labels)
    parent_label=labels.get(parent_path)
    parent_label=parent_label.text if parent_label is not None else ''
    child_label=labels.get(child_path)
    child_label=child_label.text if child_label is not None else ''
    nonsym=parent_leaf.endswith('_NonSymmetry')
    def attr(name,default):
        return c.getAttr(parent.path+'.'+name) if c.attributeQuery(name,node=parent.path,exists=True) else default
    free=bool(attr('freeOrient',False))
    forward=int(attr('worldOrientForward',-1))
    world_up=int(attr('worldOrientUp',attr('worldOrient',-1)))
    use_world=world_up!=-1
    worldmatch=snapshot.axis_configuration.world_match
    if worldmatch and use_world:world_up=1
    if c.attributeQuery('worldOrientForward',node=parent.path,exists=True) and forward!=6:
        if forward in (world_up,world_up+3,world_up-3):
            host._transaction_changed=True
            c.setAttr(parent.path+'.worldOrientForward',0 if world_up==5 else world_up+1)
            # MEL changes the plug but continues this iteration with the
            # previously sampled enum; do not silently change the local value.
    flip=False
    segments=parent_path.split('|')[1:]
    for index in range(len(segments)):
        ancestor='|'+'|'.join(segments[:index+1])
        if c.attributeQuery('flipOrient',node=ancestor,exists=True) and c.getAttr(ancestor+'.flipOrient'):
            flip=not flip
    # noFlip is a proc-local variable retained between source iterations.
    if c.attributeQuery('noFlip',node=parent.path,exists=True):state['no_flip']=bool(attr('noFlip',False))
    no_flip=state.get('no_flip',False)
    start=DagIdentity(host,info.start) if info is not None else None
    middle=DagIdentity(host,info.middle) if info is not None and info.middle and c.objExists(info.middle) else None
    end=DagIdentity(host,info.end) if info is not None else None
    is_start=start is not None and start.uuid==parent.uuid
    is_end=end is not None and end.uuid==parent.uuid
    terminal=not (c.listRelatives(child.path,children=True,type='joint') or ())
    before_siblings=tuple(DagIdentity(host,path) for path in
        (c.listRelatives(parent.path,children=True,type='joint',fullPath=True) or ()))
    child_index=next((index for index,node in enumerate(before_siblings) if node.uuid==child.uuid),0)
    others=tuple(DagIdentity(host,path) for path in
        (c.listRelatives(parent.path,children=True,fullPath=True) or ()) if path!=child_path)
    locks=tuple((node,tuple(bool(c.getAttr(node.path+'.'+channel,lock=True)) for channel in TR))
                for node in (child,parent))
    host._transaction_changed=True
    for node,_ in locks:
        for channel in TR:c.setAttr(node.path+'.'+channel,lock=False)
    placeholder=None
    generated=[]
    if others:
        placeholder=_temporary(host,parent=parent,name='otherChildrenPlaceHolder')
        c.parent(placeholder.path,world=True)
        for other in others:c.parent(other.path,placeholder.path)
    c.parent(child.path,world=True)
    generated_child=c.listRelatives(child.path,parent=True,fullPath=True) or ()
    if generated_child:generated.append(DagIdentity(host,generated_child[0]))
    c.setAttr(parent.path+'.rotateAxis',0.,0.,0.,type='float3')
    connections=[]
    for kind in 'trs':
        for axis in 'xyz':
            attribute=kind+axis
            sources=c.listConnections(parent.path+'.'+attribute,source=True,destination=False,plugs=True) or ()
            if sources:
                source_node,source_attribute=sources[0].split('.',1)
                connections.append((DagIdentity(host,source_node),source_attribute,attribute))
                c.disconnectAttr(sources[0],parent.path+'.'+attribute)
    position=list(c.xform(parent.path,query=True,worldSpace=True,translation=True))
    tolerance=.01*snapshot.fit_scale
    centered=-tolerance<position[0]<tolerance
    if start is not None:
        start_position=c.xform(start.path,query=True,worldSpace=True,translation=True)
        if -tolerance<start_position[0]<tolerance and not centered:
            position[0]=0.
            c.xform(parent.path,worldSpace=True,translation=position)
            centered=True
    primary=state['primary']
    secondary=state['secondary']
    if worldmatch:
        frame=_temporary(host,parent=parent,name='tempTransform1')
        c.parent(frame.path,world=True)
        c.setAttr(frame.path+'.rotate',0.,0.,0.,type='float3')
        sample=_temporary(host,parent=child,name='tempTransform2')
        c.parent(sample.path,frame.path)
        delta=c.getAttr(sample.path+'.translate')[0]
        maximum=0.
        for index,axis in enumerate('XYZ'):
            if abs(delta[index])>maximum:
                primary=axis
                maximum=abs(delta[index])
        if c.getAttr(sample.path+'.translate'+primary)<0:primary='-'+primary
        if use_world:primary='-Y'
        c.delete(frame.path)
        secondary='-Y' if primary=='Z' else 'Y' if primary=='-Z' else 'Z'
        state.update(primary=primary,secondary=secondary)
        for node in (parent,child) if terminal else (parent,):
            for attribute,axis in (('primaryAxis',primary),('secondaryAxis',secondary)):
                if not c.attributeQuery(attribute,node=node.path,exists=True):
                    c.addAttr(node.path,longName=attribute,attributeType='enum',enumName='X:Y:Z:-X:-Y:-Z:')
                c.setAttr(node.path+'.'+attribute,AXES.index(axis))
    tertiary=tertiary_axis(primary,secondary)
    tertiary_index='XYZ'.index(tertiary[-1])
    aim,up,up2=axis_vector(primary),axis_vector(secondary),axis_vector(tertiary)
    if flip or nonsym:up,up2=_negative(up),_negative(up2)
    if nonsym and not no_flip:aim=_negative(aim)
    plane=False
    hip_flip=1
    if not use_world and not free:
        if start is not None and end is not None and info.solver=='ikRPsolver' and not is_end and 'Toes' not in child_label:
            plane=True
            old_parents=c.listRelatives(parent.path,parent=True,fullPath=True) or ()
            old_parent=DagIdentity(host,old_parents[0]) if old_parents else None
            order=tuple(DagIdentity(host,path) for path in (c.listRelatives(old_parent.path,
                children=True,type='transform',fullPath=True) or ())) if old_parent else ()
            c.parent(parent.path,world=True)
            if is_start:
                start_label=labels.get(info.start)
                if start_label is not None and 'Hip' in start_label.text:
                    up=_negative(up)
                    hip_flip=-1
                if 'Finger' in child.path:
                    up=(0.,0.,-1.)
                    tertiary_index=1
                constraints=c.aimConstraint(child.path,parent.path,aimVector=aim,upVector=up,
                    worldUpType='object',worldUpObject=end.path)
                if c.objExists('tempTransform'):c.delete('tempTransform')
                sample=_temporary(host,parent=child,name='tempTransform')
                c.parent(sample.path,parent.path)
                rotation=c.getAttr(sample.path+'.rotate')[0]
                c.delete(sample.path)
                if -.001<rotation[tertiary_index]<.001 and middle is not None:
                    c.move(0.,0.,position[1]/-100.,middle.path+'.rotatePivot',worldSpace=True,relative=True)
                c.delete(constraints)
            else:
                _aim(c,(child.path,),parent.path,aim,up2,worldUpType='objectrotation',
                     worldUpObject=start.path,worldUpVector=up2)
            if old_parent:
                c.parent(parent.path,old_parent.path)
                if len(order)>1:
                    c.reorder(parent.path,front=True) if order[0].uuid==parent.uuid else c.reorder(parent.path,back=True)
            if c.objExists('tempTransform'):c.delete('tempTransform')
        elif centered:
            _aim(c,(child.path,),parent.path,aim,up2,worldUpType='vector',worldUpVector=(1.,0.,0.))
        else:
            helper=_temporary(host,parent=parent)
            multiplier=-1 if secondary.startswith('-') else 1
            c.setAttr(helper.path+'.translate'+secondary[-1],3.*multiplier*(-1 if flip or nonsym else 1))
            c.parent(helper.path,world=True)
            automatic=c.listRelatives(helper.path,parent=True,fullPath=True) or ()
            if automatic:generated.append(DagIdentity(host,automatic[0]))
            _aim(c,(child.path,),parent.path,aim,up,worldUpType='object',worldUpObject=helper.path)
            c.delete(helper.path)
        if parent_label.startswith('LegAim'):
            _aim(c,(child.path,),parent.path,aim,up2,worldUpType='objectrotation',
                 worldUpObject=child.path,worldUpVector=up2)
        if parent_leaf=='Cup' and c.objExists('RingFinger1') and c.objExists('MiddleFinger1'):
            actual_parent=c.listRelatives(parent.path,parent=True,fullPath=True) or ()
            _aim(c,('RingFinger1','MiddleFinger1'),parent.path,aim,up,
                 worldUpType='object',worldUpObject=actual_parent[0])
        if parent_leaf.startswith('Eye'):
            _aim(c,(child.path,),parent.path,aim,_negative(up),worldUpVector=(0.,1.,0.))
        if parent_leaf=='Root' and not centered:
            c.setAttr(parent.path+'.rotate',0.,0.,0.,type='float3')
            c.setAttr(parent.path+'.jointOrient',90.,0.,90.,type='float3')
        if c.attributeQuery('aimAt',node=parent.path,exists=True):
            target=c.getAttr(parent.path+'.aimAt',asString=True)
            aim_at=axis_vector('XYZ'[int(attr('aimAxis',0))])
            up_at=axis_vector('XYZ'[int(attr('aimUpAxis',0))])
            if primary.startswith('-'):aim_at=_negative(aim_at)
            childless=not (c.listRelatives(child.path,children=True) or ())
            if childless:c.parent(child.path,parent.path)
            if c.objExists(target):
                _aim(c,(target,),parent.path,aim_at,up_at,offset=(0.,0.,0.),
                     worldUpType='objectrotation',worldUpVector=(0.,1.,0.),worldUpObject=target)
            if childless:c.parent(child.path,world=True)
    if use_world:
        helper=_temporary(host,parent=child,name='tempUpVector')
        c.parent(helper.path,world=True)
        c.move(0.,1.,0.,helper.path,relative=True,worldSpace=True)
        world_aim=_negative(axis_vector(AXES[world_up]))
        # Preserve 6.925's literal table: enum 4 is assigned twice; enum 5
        # retains the proc-local preceding value. This is not an axis redesign.
        forward_vectors={0:(1.,0.,0.),1:(0.,1.,0.),2:(0.,0.,1.),3:(-1.,0.,0.),4:(0.,0.,-1.)}
        if forward in forward_vectors:state['world_forward_vector']=forward_vectors[forward]
        target=_temporary(host,parent=parent,name='tempAimAt')
        c.parent(target.path,world=True)
        c.move(0.,-1.,0.,target.path,relative=True,worldSpace=True)
        if nonsym:world_aim=_negative(world_aim)
        if forward in (-1,6):
            _aim(c,(target.path,),parent.path,world_aim,up,worldUpType='object',worldUpObject=helper.path)
        else:
            _aim(c,(target.path,),parent.path,world_aim,state.get('world_forward_vector',(0.,0.,0.)),
                 worldUpType='vector',worldUpVector=(0.,0.,1.))
        c.delete(helper.path,target.path)
    geometry_aim=parent_leaf+'Aim'
    if c.objExists(geometry_aim+'_aimConstraint1'):c.delete(geometry_aim+'_aimConstraint1')
    if c.objExists(geometry_aim):
        if plane and is_start:
            _aim(c,(child.path,),geometry_aim,(1.,0.,0.),(0.,float(hip_flip),0.),keep=True,
                 worldUpType='object',worldUpObject=end.path)
        elif plane:
            start_leaf=info.start.rsplit('|',1)[-1].rsplit(':',1)[-1]
            _aim(c,(child.path,),geometry_aim,(1.,0.,0.),(0.,1.,0.),keep=True,
                 worldUpType='objectrotation',worldUpObject=start_leaf+'Aim',worldUpVector=(0.,1.,0.))
        else:
            _aim(c,(child.path,),geometry_aim,(1.,0.,0.),(0.,1.,0.),keep=True,
                 worldUpType='objectrotation',worldUpObject=parent.path,worldUpVector=up)
    c.makeIdentity(parent.path,apply=True,translate=False,rotate=True,scale=False)
    if placeholder is not None:
        c.parent([node.path for node in others],parent.path)
        c.delete(placeholder.path)
    c.parent(child.path,parent.path)
    if len(before_siblings)>1:
        current=tuple(c.listRelatives(parent.path,children=True,type='joint',fullPath=True) or ())
        new_index=current.index(child.path)
        if new_index!=child_index:c.reorder(child.path,relative=child_index-new_index)
    for helper in generated:
        paths=helper.raw.ls(helper.uuid,long=True) or ()
        if paths:c.delete(helper.path)
    for source,attribute,destination in connections:
        try:c.connectAttr(source.path+'.'+attribute,parent.path+'.'+destination,force=True)
        except RuntimeError:c.warning('Failed: connectAttr '+source.path+'.'+attribute+' '+parent.path+'.'+destination)
    if terminal and not c.attributeQuery('control',node=child.path,exists=True):
        c.setAttr(child.path+'.jointOrient',0.,0.,0.,type='float3')
        c.setAttr(child.path+'.rotate',0.,0.,0.,type='float3')
    if c.objExists(parent_leaf+'Bone') and c.objExists(parent_leaf+'Distance'):
        c.setAttr(parent_leaf+'Bone.sx',float(c.getAttr(parent_leaf+'Distance.distance'))/snapshot.fit_scale)
    for node,values in locks:
        for channel,value in zip(TR,values):c.setAttr(node.path+'.'+channel,lock=value)
