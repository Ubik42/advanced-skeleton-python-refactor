"""Native asMappingUIFunction MoCapConnect, in original joint command order."""
from adv_py.core.name_matcher_mocap import source_mocap_operations


def _pole(host, c, group, pole, root):
    parents = c.listRelatives(pole.middle_joint, parent=True, fullPath=True) or ()
    children = c.listRelatives(pole.middle_joint, children=True, fullPath=True) or ()
    hip, ankle = parents[0], children[0]
    positions = [c.xform(node, query=True, worldSpace=True, translation=True)
                 for node in (hip, pole.middle_joint, ankle)]
    def distance(a,b):
        return sum((float(x)-float(y))**2 for x,y in zip(a,b))**0.5
    dist_a = distance(positions[0],positions[1])
    dist_b = distance(positions[1],positions[2])
    # Original names concatenate the entire deform name and side, including
    # the duplicated suffix. Keep actual source_joint when the plan has it.
    deform = (pole.source_joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
              if pole.source_joint else ('Elbow' if pole.limb=='arm' else 'Knee')
              + '_' + pole.control.rsplit('_',1)[-1])
    suffix = deform + '_' + deform.rsplit('_',1)[-1]
    a = c.createNode('transform', parent=group,
        name=host.scene_address('PoleVectorLocatorOffsetA'+suffix))
    b = c.createNode('transform', parent=a,
        name=host.scene_address('PoleVectorLocatorOffsetB'+suffix))
    locator = c.createNode('transform', parent=b,
        name=host.scene_address('PoleVectorLocator'+suffix))
    c.pointConstraint(hip,a,weight=dist_b)
    c.pointConstraint(ankle,a,weight=dist_a)
    c.orientConstraint(host.scene_address(root),a)
    c.setAttr(b+'.translateZ',(dist_a+dist_b)/(-10.0 if pole.limb=='leg' else 10.0))
    c.aimConstraint(pole.middle_joint,b,aimVector=(1,0,0),upVector=(0,1,0),
                    worldUpType='vector',worldUpVector=(0,1,0))
    c.select(hip,ankle,replace=True)
    c.setAttr(locator+'.translateX',dist_a+dist_b)
    control = host.scene_address(pole.control)
    point = c.pointConstraint(locator,control,maintainOffset=True)[0]
    c.connectAttr(group+'.disableConstraints',point+'.nodeState')
    return control,point,None


def connect(host,plan):
    host._require_transaction()
    host.preflight_name_matcher_mocap(plan)
    # Validate the full schedule before any native command mutates the graph.
    operations = source_mocap_operations(plan)
    # The original creates MoCapConstraints only when a native output is made.
    # An empty mapping remains a no-op, with no ownership group to save.
    if not operations:
        return ()
    from maya import cmds as c
    from .maya_original_transform_channels import lock_original_transform_channels
    group = host.scene_address('MoCapConstraints')
    host._transaction_changed = True
    from .maya_source_native_animation import reconnect_records
    reconnect_records(host,plan,remove=True)
    c.createNode('transform',name=group,skipSelect=True)
    lock_original_transform_channels(c,group,True,True,True,True)
    c.addAttr(group,longName='advPyNameMatcher',attributeType='bool',defaultValue=True)
    c.setAttr(group+'.advPyNameMatcher',lock=True)
    c.addAttr(group,longName='disableConstraints',attributeType='bool',keyable=True)
    links = [None]*len(plan.links)
    poles = [None]*len(plan.poles)
    for kind,index in operations:
        if kind=='pole':
            poles[index] = _pole(host,c,group,plan.poles[index],plan.root_control)
            continue
        link = plan.links[index]
        control = host.scene_address(link.control)
        # Source changes Chest follow settings immediately before its own
        # constraints. Its intended world-frame change is not an error.
        if link.control==plan.spine_control:
            for attribute in ('followRoot','ikHybridVis'):
                if c.attributeQuery(attribute,node=control,exists=True):
                    c.setAttr(control+'.'+attribute,0)
        point = (c.pointConstraint(link.external_joint,control,maintainOffset=True)[0]
                 if link.point else None)
        if point:
            c.connectAttr(group+'.disableConstraints',point+'.nodeState')
        orient = (c.orientConstraint(link.external_joint,control,maintainOffset=True)[0]
                  if link.orient else None)
        if orient:
            c.connectAttr(group+'.disableConstraints',orient+'.nodeState')
        links[index] = control,point,orient
    result = tuple((*links,*poles))
    host.verify_name_matcher_mocap(plan,result)
    from .maya_source_name_matcher_session import remember
    remember(host,result)
    return result
