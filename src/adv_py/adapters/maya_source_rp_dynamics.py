"""Create the original native RP dynamics after final solver/Foot parenting."""
from adv_py.core.source_rp_dynamics import plan_source_rp_dynamics
from adv_py.core.character_registry import CharacterRegistryError
from dataclasses import asdict,replace


def create(host,body,limbs,global_control,internal_local=(),root_follow=None, *,source_pole_targets=True):
    host._require_transaction()
    c=host._cmds
    plans=[]
    deferred=[]
    # Preserve the MEL's explicit scene lookup for ...ConstrainToLeg_<side>.
    # This is not inferred from arbitrary Foot labels or other RP systems.
    leg_targets={ik.side.value:ik.handle_parent+'|AdvPy_Leg_RP_'+ik.side.value+'_Target'
                 for limb in limbs if limb.label=='Leg' for ik in limb.ik.limbs}
    by_body={joint.path:joint for joint in body.joints}
    for limb in limbs:
        for ik in limb.ik.limbs:
            stem='AdvPy_'+limb.label+'_RP_'+ik.side.value
            start_name=stem+'_Start'
            target_name=stem+'_Target'
            start_path=limb.mechanisms.root_path+'|'+start_name
            target_parent=ik.handle_parent
            target_path=target_parent+'|'+target_name
            chain=tuple(c.ikHandle(ik.handle_name,query=True,jointList=True) or ())
            chain=tuple(host._resolve_connected_node(path) for path in chain)
            if not chain or chain[0]!=ik.chain[0]:
                raise CharacterRegistryError('来源 RP solver 链起点不一致')
            chain+= (ik.chain[-1],)
            translations=tuple(tuple(float(v) for v in c.getAttr(joint+'.translate')[0])
                               for joint in chain[1:])
            plan=plan_source_rp_dynamics(limb.label,ik.side.value,
                ik.wrist_control_path,ik.pole_control_path,start_path,target_path,
                global_control.control_path+'.worldInverseMatrix[0]',
                global_control.effective_scale_source('Y'),chain,translations,
                source_pole_targets=source_pole_targets,pole_end_anchor=leg_targets.get(ik.side.value))
            if any(host.find_name_collisions(name) for name in
                   (start_name,target_name,*(node.name for node in plan.nodes))):
                raise CharacterRegistryError('来源 RP 拉伸网络名称被占用：'+limb.label)
            attributes=(('stretchy',0.,0.,10.),('antiPop',0.,0.,10.),('volume',10.,None,None))
            attributes+=tuple((segment.length_attribute,1.,None,None) for segment in plan.segments)
            attributes+=tuple((segment.fatness_attribute,0.,None,None) for segment in plan.segments)
            if any(c.objExists(ik.wrist_control_path+'.'+attr) for attr,_,_,_ in attributes):
                raise CharacterRegistryError('来源 RP 拉伸属性已存在')
            if c.objExists(ik.pole_control_path+'.lock'):
                raise CharacterRegistryError('来源 RP Pole.lock 已存在')
            for segment in plan.segments:
                if c.listConnections(segment.joint+'.translate',source=True,destination=False):
                    raise CharacterRegistryError('来源 RP solver 位移已有输入：'+segment.joint)
            start_source=next((spec.control_path for spec in internal_local
                               if spec.target==ik.chain[0]),None)
            if start_source is None:
                start_body=next(joint.source_joint for joint in limb.mechanisms.joints
                                if joint.path==ik.chain[0])
                parent=by_body[start_body].parent_path
                while parent in by_body and 'Part' in by_body[parent].name:
                    parent=by_body[parent].parent_path
                start_source=root_follow if parent==body.root and root_follow else parent
            start=c.createNode('transform',name=start_name,parent=limb.mechanisms.root_path,skipSelect=True)
            c.xform(start,worldSpace=True,translation=c.xform(ik.chain[0],query=True,worldSpace=True,translation=True))
            if start_source:
                c.parentConstraint(start_source,start,maintainOffset=True,
                    name=stem+'_StartFollow',skipRotate=('x','y','z'))
            c.setAttr(start+'.visibility',False)
            target=c.createNode('transform',name=target_name,parent=target_parent,skipSelect=True)
            c.xform(target,worldSpace=True,translation=c.xform(ik.handle_name,query=True,worldSpace=True,translation=True))
            c.setAttr(target+'.visibility',False)
            for attr,default,minimum,maximum in attributes:
                args=dict(longName=attr,attributeType='double',defaultValue=default,keyable=True)
                if minimum is not None:args['minValue']=minimum
                if maximum is not None:args['maxValue']=maximum
                if attr=='volume':args.update(softMinValue=0.,softMaxValue=10.)
                c.addAttr(ik.wrist_control_path,**args)
            c.addAttr(ik.pole_control_path,longName='lock',attributeType='double',
                      minValue=0.,maxValue=10.,defaultValue=0.,keyable=True)
            for node in plan.nodes:
                c.createNode(node.kind,name=node.name,skipSelect=True)
                for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
            rest=plan.rest_length
            for curve,keys in ((plan.normal_curve,((rest,rest,'spline','linear'),(rest*1.2,rest*1.2,'spline','spline'))),
                (plan.anti_pop_curve,((rest*.1,rest,'spline','spline'),(rest*.7,rest,'linear','spline'),
                (rest*.85,rest*.9,'spline','spline'),(rest,rest,'spline','linear'),
                (rest*1.2,rest*1.2,'spline','spline')))):
                for driver,value,in_tangent,out_tangent in keys:
                    c.setKeyframe(curve,float=driver,value=value,
                                  inTangentType=in_tangent,outTangentType=out_tangent)
                c.setAttr(curve+'.postInfinity',1)
            for node in plan.nodes:
                for source,attribute in node.connections:
                    target=node.name+'.'+attribute
                    if source.split('.',1)[0] in leg_targets.values() and not c.objExists(source):
                        deferred.append((source,target))
                    else:c.connectAttr(source,target)
            for source,destination in plan.outputs:
                c.connectAttr(source,destination)
            # Original volume goes to ScaleBlend, not solver joint scales:
            # joint scaling would double-count length in the IK solve.
            primary=[joint for joint in limb.mechanisms.joints if joint.side is ik.side
                     and joint.role.value=='ik' and joint.source_joint.rsplit('|',1)[-1]
                     .rsplit('_',1)[0] in limb.joint_names]
            outputs=list(plan.outputs)
            for joint in primary[:-1]:
                blend_joint=next(row for side in limb.blend.sides if side.side is ik.side
                                 for row in side.joints if row.ik_driver==joint.path)
                scale=blend_joint.constraint_name+'Scale'
                compound=c.connectionInfo(scale+'.color1',sourceFromDestination=True)
                if compound:c.disconnectAttr(compound,scale+'.color1')
                fat_index=next((index for index,segment in enumerate(plan.segments,1)
                                if segment.previous==joint.path),None)
                for axis,component in zip('XYZ','RGB'):
                    destination=scale+'.color1'+component
                    source=c.connectionInfo(destination,sourceFromDestination=True)
                    if source:c.disconnectAttr(source,destination)
                    output=(stem+'_Fatness'+str(fat_index)+'.output1D'
                            if axis in ('Y','Z') and fat_index is not None else plan.volume)
                    c.connectAttr(output,destination)
                    outputs.append((output,destination))
            plan=replace(plan,outputs=tuple(outputs))
            from adv_py.core.character_registry import canonical
            c.addAttr(start,longName='advPySourceRpDynamics',dataType='string')
            c.setAttr(start+'.advPySourceRpDynamics',canonical(asdict(plan)),type='string',lock=True)
            if source_pole_targets:
                c.addAttr(start,longName='advPySourceRpPoleSources',attributeType='bool',defaultValue=True)
                c.setAttr(start+'.advPySourceRpPoleSources',True,lock=True)
            plans.append(plan)
    for source,target in deferred:c.connectAttr(source,target)
    host._transaction_changed=True
    return tuple(plans)


def audit(host,registration):
    """Require persisted native graphs through save, namespace and rebuild."""
    from adv_py.core.source_rp_dynamics import decode_source_rp_dynamics
    c=host._cmds
    for binding in registration.source_limbs:
        if not binding.dynamics_root:
            continue
        plug=binding.dynamics_root+'.advPySourceRpDynamics'
        if not c.objExists(plug) or not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源 RP 拉伸网络登记缺失或解锁')
        plan=decode_source_rp_dynamics(c.getAttr(plug))
        if ((plan.label,plan.side,plan.control,plan.pole,plan.start_anchor,plan.ratio)!=
                (binding.label,binding.side,binding.ik_control,binding.pole_control,
                 binding.dynamics_root,binding.ratio_node)):
            raise CharacterRegistryError('来源 RP 拉伸图与角色登记不一致')
        for node in plan.nodes:
            if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
                raise CharacterRegistryError('来源 RP 原生驱动节点缺失：'+node.name)
            for source,attribute in node.connections:
                if not c.isConnected(source,node.name+'.'+attribute):
                    raise CharacterRegistryError('来源 RP 原生驱动连接变化：'+node.name+'.'+attribute)
            for attribute,value in node.values:
                if abs(float(c.getAttr(node.name+'.'+attribute))-value)>1e-8:
                    raise CharacterRegistryError('来源 RP 原生驱动常量变化：'+node.name+'.'+attribute)
        for source,destination in plan.outputs:
            if not c.isConnected(source,destination):
                raise CharacterRegistryError('来源 RP 拉伸或体积输出变化：'+destination)
        rest=plan.rest_length
        for curve,drivers,values in (
                (plan.normal_curve,(rest,rest*1.2),(rest,rest*1.2)),
                (plan.anti_pop_curve,(rest*.1,rest*.7,rest*.85,rest,rest*1.2),
                 (rest,rest,rest*.9,rest,rest*1.2))):
            actual=tuple(float(v) for v in c.keyframe(curve,query=True,floatChange=True) or ())
            actual_values=tuple(float(v) for v in c.keyframe(curve,query=True,valueChange=True) or ())
            if (len(actual)!=len(drivers) or len(actual_values)!=len(values)
                    or any(abs(a-b)>1e-6 for a,b in zip(actual,drivers))
                    or any(abs(a-b)>1e-6 for a,b in zip(actual_values,values))
                    or c.getAttr(curve+'.postInfinity')!=1):
                raise CharacterRegistryError('来源 RP 抗弹跳曲线变化：'+curve)
