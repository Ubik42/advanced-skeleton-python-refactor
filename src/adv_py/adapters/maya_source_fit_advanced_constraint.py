"""MEL 84471–84584 native Advanced Constraint layers and reparent order."""
from dataclasses import replace
from .maya_source_fit_geo_attach import _align
from .maya_body_fit_advanced_constraint import _matrix
from adv_py.core.body_parent_constraint import plan_body_parent_constraint


def create(host,spec):
    c=host._cmds;host._transaction_changed=True
    parent=spec.fk_offset
    target=c.createNode('transform',name=spec.constraint_name+'Target',parent=parent)
    static=c.createNode('transform',name=spec.static_name,parent=parent)
    blend=c.createNode('transform',name=spec.constraint_name+'Blend',parent=parent)
    if spec.align_target:_align(c,blend,spec.target_joints[0])
    target=c.parent(target,'|Group|MotionSystem|ConstraintSystem')[0]
    command=getattr(c,spec.kind+'Constraint')
    command(spec.target_joints[0],target,maintainOffset=True,name=spec.constraint_name+'Driver')
    command(static,target,blend,name=spec.constraint_name)
    if spec.kind in ('parent','orient'):c.setAttr(spec.constraint_name+'.interpType',2)
    aliases=command(spec.constraint_name,query=True,weightAliasList=True)
    c.addAttr(spec.fk_control,longName=spec.attribute,attributeType='double',minValue=0,maxValue=10,defaultValue=10,keyable=True)
    c.createNode('unitConversion',name=spec.weight_name)
    c.setAttr(spec.weight_name+'.conversionFactor',.1)
    c.createNode('reverse',name=spec.reverse_name)
    c.connectAttr(spec.fk_control+'.'+spec.attribute,spec.weight_name+'.input')
    c.connectAttr(spec.weight_name+'.output',spec.reverse_name+'.inputX')
    c.connectAttr(spec.reverse_name+'.outputX',spec.constraint_name+'.'+aliases[0])
    c.connectAttr(spec.weight_name+'.output',spec.constraint_name+'.'+aliases[1])
    reoffset=c.createNode('transform',name=spec.constraint_name+'Offset',parent=parent)
    c.parent(reoffset,blend)
    if len(spec.target_joints)==2:
        target=c.parent(target,parent)[0]
        c.delete(spec.constraint_name+'Driver')
        frames=[]
        right=c.createNode('transform',name=spec.constraint_name+'SideR',parent=spec.target_offsets[0])
        right=c.parent(right,'|Group|MotionSystem|ConstraintSystem')[0]
        left=c.duplicate(right,name=spec.constraint_name+'SideL')[0]
        for joint,frame in zip(spec.target_joints,(right,left)):
            frame=c.ls(frame,long=True)[0]
            source=host.capture_parent_constraint_input(joint,frame,True)
            plan=plan_body_parent_constraint(replace(source,use_offset_parent_matrix=spec.use_offset_parent_matrix))
            host.preflight_parent_constraint(plan);host.create_parent_constraint(plan)
            frames.append(frame)
        command(*frames,target,name=spec.constraint_name+'Driver')
        if spec.kind in ('parent','orient'):c.setAttr(spec.constraint_name+'Driver.interpType',2)
    receiver=spec.fk_root;plug=receiver+'.offsetParentMatrix'
    previous=c.connectionInfo(plug,sourceFromDestination=True) or None
    old=_matrix(c.getAttr(plug))
    inherits=bool(c.getAttr(receiver+'.inheritsTransform'))
    moved=c.parent(receiver,reoffset)[0]
    c.parent(moved,parent,relative=True)
    bridge=c.createNode('multMatrix',name=spec.constraint_name+'Bridge')
    if previous:
        c.disconnectAttr(previous,plug);c.connectAttr(previous,bridge+'.matrixIn[0]')
    else:c.setAttr(bridge+'.matrixIn[0]',*old,type='matrix')
    if inherits:
        c.connectAttr(reoffset+'.matrix',bridge+'.matrixIn[1]')
        c.connectAttr(blend+'.matrix',bridge+'.matrixIn[2]')
    c.connectAttr(bridge+'.matrixSum',plug)


def capture(host,spec):
    c=host._cmds
    types=((spec.static_name,'transform'),(spec.constraint_name+'Target','transform'),(spec.constraint_name+'Blend','transform'),(spec.constraint_name+'Offset','transform'),(spec.constraint_name+'Bridge','multMatrix'),(spec.constraint_name,spec.kind+'Constraint'),(spec.constraint_name+'Driver',spec.kind+'Constraint'),(spec.weight_name,'unitConversion'),(spec.reverse_name,'reverse'))
    if any(not c.objExists(n) or c.nodeType(n)!=t for n,t in types):return False
    command=getattr(c,spec.kind+'Constraint')
    aliases=command(spec.constraint_name,query=True,weightAliasList=True) or []
    if len(aliases)!=2:return False
    def path(node):return c.ls(node,long=True)[0]
    def parent(node):return (c.listRelatives(node,parent=True,fullPath=True) or [None])[0]
    target=spec.constraint_name+'Target'
    blend=spec.constraint_name+'Blend'
    if (parent(spec.static_name)!=spec.fk_offset or parent(blend)!=spec.fk_offset
            or parent(spec.constraint_name+'Offset')!=path(blend)
            or parent(target)!=(spec.fk_offset if len(spec.target_joints)==2 else '|Group|MotionSystem|ConstraintSystem')):
        return False
    if [path(node) for node in command(spec.constraint_name,query=True,targetList=True)]!=[path(spec.static_name),path(target)]:return False
    driver_targets=(tuple(spec.constraint_name+'Side'+side for side in ('R','L'))
                    if len(spec.target_joints)==2 else spec.target_joints)
    if any(not c.objExists(node) for node in driver_targets):return False
    if [path(node) for node in command(spec.constraint_name+'Driver',query=True,targetList=True)]!=[path(node) for node in driver_targets]:return False
    if spec.kind in ('parent','orient') and c.getAttr(spec.constraint_name+'.interpType')!=2:return False
    # Later constraints may compose another bridge above this one.
    source=c.connectionInfo(spec.fk_root+'.offsetParentMatrix',sourceFromDestination=True)
    wanted=spec.constraint_name+'Bridge.matrixSum';visited=set()
    while source!=wanted:
        if not source:return False
        node=source.rsplit('.',1)[0]
        if node in visited or c.nodeType(node)!='multMatrix':return False
        visited.add(node)
        source=c.connectionInfo(node+'.matrixIn[0]',sourceFromDestination=True)
    if not bool(c.getAttr(spec.fk_root+'.inheritsTransform')) and any(
            c.connectionInfo(spec.constraint_name+'Bridge.matrixIn['+str(i)+']',sourceFromDestination=True) for i in (1,2)):
        return False
    links=[(spec.fk_control+'.'+spec.attribute,spec.weight_name+'.input'),(spec.weight_name+'.output',spec.reverse_name+'.inputX'),(spec.reverse_name+'.outputX',spec.constraint_name+'.'+aliases[0]),(spec.weight_name+'.output',spec.constraint_name+'.'+aliases[1])]
    if bool(c.getAttr(spec.fk_root+'.inheritsTransform')):
        links.extend(((spec.constraint_name+'Offset.matrix',spec.constraint_name+'Bridge.matrixIn[1]'),(spec.constraint_name+'Blend.matrix',spec.constraint_name+'Bridge.matrixIn[2]')))
    return all(c.isConnected(a,b) for a,b in links) and abs(c.getAttr(spec.weight_name+'.conversionFactor')-.1)<1e-8
