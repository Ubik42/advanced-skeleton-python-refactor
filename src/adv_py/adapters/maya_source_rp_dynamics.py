"""Create the original native RP dynamics after final solver/Foot parenting."""
from adv_py.core.source_rp_dynamics import plan_source_rp_dynamics
from adv_py.core.character_registry import CharacterRegistryError
from dataclasses import asdict,replace


def rebase_records(host,roots,rewrites):
    """Keep the saved native graph addresses after Body root parenting."""
    from adv_py.core.fit_part import FitPartFinalPaths,rebase_plan_paths_after_parts
    from adv_py.core.source_rp_dynamics import decode_source_rp_dynamics
    from adv_py.core.character_registry import canonical
    paths=FitPartFinalPaths((),(),tuple(rewrites))
    c=host._cmds
    for root in dict.fromkeys(root for root in roots if root):
        current=rebase_plan_paths_after_parts(root,paths)
        plug=current+'.advPySourceRpDynamics'
        if not c.objExists(plug) or not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源 RP 重定位缺少锁定的驱动登记')
        old=decode_source_rp_dynamics(c.getAttr(plug))
        updated=rebase_plan_paths_after_parts(old,paths)
        if old==updated:
            continue
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)


def create(host,body,limbs,global_control,internal_local=(),root_follow=None, *,
           source_pole_targets=True,source_x_translation=True,source_part_scale=True,
           instances=(),inbetween_segments=(),source_start_frame=True):
    host._require_transaction()
    c=host._cmds
    plans=[]
    graphs=[]
    deferred=[]
    # Preserve the MEL's explicit scene lookup for ...ConstrainToLeg_<side>.
    # This is not inferred from arbitrary Foot labels or other RP systems.
    leg_targets={ik.side.value:ik.handle_parent+'|AdvPy_Leg_RP_'+ik.side.value+'_Target'
                 for limb in limbs if limb.label=='Leg' for ik in limb.ik.limbs}
    by_body={joint.path:joint for joint in body.joints}
    # MEL analyzes listRelatives -ad, then creates all source-side handles
    # before the mirrored side. Alphabetical limb planning is a different
    # order and changes objExists-based Pole.lock targets.
    source_by_output={instance.output_name:instance.source_joint for instance in instances}
    fit_roots={instance.source_joint.split('|')[1] for instance in instances
               if instance.source_joint.startswith('|')}
    source_order={}
    for root_name in fit_roots:
        for index,path in enumerate(c.listRelatives('|'+root_name,allDescendents=True,
                                                   type='joint',fullPath=True) or ()):
            source_order[path]=index
    pairs=[(limb,ik) for limb in limbs for ik in limb.ik.limbs]
    def source_key(pair):
        limb,ik=pair
        end=next(joint.source_joint for joint in limb.mechanisms.joints if joint.path==ik.chain[-1])
        source=source_by_output.get(end.rsplit('|',1)[-1])
        return (ik.side.value=='L',source_order.get(source,len(source_order)))
    pairs.sort(key=source_key)
    for limb,ik in pairs:
        stem='AdvPy_'+limb.label+'_RP_'+ik.side.value
        from .maya_source_graph_connections import SourceGraphConnections
        connections=SourceGraphConnections(host,stem)
        start_name=stem+'_Start'
        target_name=stem+'_Target'
        frame=next((frame for frame in limb.root_frames if frame.joint==ik.chain[0]),None) if source_start_frame else None
        start_parent=frame.frame if frame is not None else limb.mechanisms.root_path
        start_path=start_parent+'|'+start_name
        target_parent=ik.handle_parent
        target_path=target_parent+'|'+target_name
        chain=tuple(c.ikHandle(ik.handle_name,query=True,jointList=True) or ())
        chain=tuple(host._resolve_connected_node(path) for path in chain)
        if not chain or chain[0]!=ik.chain[0]:
            raise CharacterRegistryError('来源 RP solver 链起点不一致')
        chain+= (ik.chain[-1],)
        translations=tuple(tuple(float(v) for v in c.getAttr(joint+'.translate')[0])
                           for joint in chain[1:])
        from adv_py.core.source_fit_identity import source_fit_side_sign
        end_body=next(joint.source_joint for joint in limb.mechanisms.joints
                      if joint.path==ik.chain[-1])
        plan=plan_source_rp_dynamics(limb.label,ik.side.value,
            ik.wrist_control_path,ik.pole_control_path,start_path,target_path,
            global_control.control_path+'.worldInverseMatrix[0]',
            global_control.effective_scale_source('Y'),chain,translations,
            source_pole_targets=source_pole_targets,pole_end_anchor=(leg_targets.get(ik.side.value)
                if leg_targets.get(ik.side.value) and c.objExists(leg_targets[ik.side.value]) else None),
            source_x_translation=source_x_translation,
            pole_sign=source_fit_side_sign(end_body.rsplit('|',1)[-1],instances),
            allow_shortening=ik.chain[0]==ik.chain[1])
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
        # MEL 80458: IKMessureFrom is a sibling of IKXOffset below the
        # source parent frame. A separate maintain-offset position constraint
        # computes a different point under Main's nonuniform scale.
        start=c.createNode('transform',name=start_name,parent=start_parent,skipSelect=True)
        if frame is not None:
            c.xform(start,worldSpace=True,matrix=c.xform(frame.offset,query=True,worldSpace=True,matrix=True))
            from .maya_source_limb_root_frame import attach_measurement
            attach_measurement(host,frame,start)
        else:
            c.xform(start,worldSpace=True,translation=c.xform(ik.chain[0],query=True,worldSpace=True,translation=True))
        if start_source and frame is None:
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
        shortening=ik.chain[0]==ik.chain[1]
        normal_keys=((rest,rest,'spline','linear'),(rest*1.2,rest*1.2,'spline','spline'))
        for curve,keys in ((plan.normal_curve,((rest,rest,'spline','linear'),(rest*1.2,rest*1.2,'spline','spline'))),
            (plan.anti_pop_curve,normal_keys if shortening else ((rest*.1,rest,'spline','spline'),(rest*.7,rest,'linear','spline'),
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
                    deferred.append((connections,source,target))
                else:connections.connect(source,target)
        for source,destination in plan.outputs:
            connections.connect(source,destination)
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
                connections.connect(output,destination)
                outputs.append((output,destination))
        if source_part_scale:
            from .maya_source_rp_part_scale import configure
            part_nodes,part_outputs=configure(host,plan,limb,ik,inbetween_segments,connections)
            plan=replace(plan,nodes=plan.nodes+part_nodes)
            outputs.extend(part_outputs)
        plan=replace(plan,outputs=tuple(outputs))
        if source_pole_targets:
            c.addAttr(start,longName='advPySourceRpPoleSources',attributeType='bool',defaultValue=True)
            c.setAttr(start+'.advPySourceRpPoleSources',True,lock=True)
        if source_x_translation:
            c.addAttr(start,longName='advPySourceRpXTranslation',attributeType='bool',defaultValue=True)
            c.setAttr(start+'.advPySourceRpXTranslation',True,lock=True)
        if source_part_scale:
            c.addAttr(start,longName='advPySourceRpPartScale',attributeType='bool',defaultValue=True)
            c.setAttr(start+'.advPySourceRpPartScale',True,lock=True)
        plans.append(plan)
        graphs.append(connections)
    for connections,source,target in deferred:connections.connect(source,target)
    from adv_py.core.character_registry import canonical
    plans=tuple(replace(plan,nodes=connections.describe_nodes(plan.nodes),
                        outputs=connections.describe_outputs(plan.outputs))
                for plan,connections in zip(plans,graphs))
    for plan in plans:
        c.addAttr(plan.start_anchor,longName='advPySourceRpDynamics',dataType='string')
        c.setAttr(plan.start_anchor+'.advPySourceRpDynamics',canonical(asdict(plan)),type='string',lock=True)
    host._transaction_changed=True
    return plans


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
                plug=node.name+'.'+attribute
                # Native clamp/setRange constants are float32; MEL setAttr
                # rounds them too. Compare against the value Maya can store,
                # while retaining the planned double in persisted metadata.
                expected=value
                if c.getAttr(plug,type=True)=='float':
                    from struct import pack,unpack
                    expected=unpack('f',pack('f',value))[0]
                if abs(float(c.getAttr(plug))-expected)>1e-8:
                    raise CharacterRegistryError('来源 RP 原生驱动常量变化：'+node.name+'.'+attribute)
        for source,destination in plan.outputs:
            if not c.isConnected(source,destination):
                raise CharacterRegistryError('来源 RP 拉伸或体积输出变化：'+destination)
        if c.objExists(plan.start_anchor+'.advPySourceRpXTranslation'):
            for segment in plan.segments:
                for axis,value in zip('YZ',segment.translation[1:]):
                    plug=segment.joint+'.translate'+axis
                    if (c.connectionInfo(plug,isDestination=True)
                            or abs(float(c.getAttr(plug))-value)>1e-8):
                        raise CharacterRegistryError('来源 RP FreeOrient 侧向位移变化：'+plug)
        for _,destination in plan.outputs:
            if destination.endswith('.offsetParentMatrix'):
                joint=destination.removesuffix('.offsetParentMatrix')
                for attr,expected in (('translate',0.),('rotate',0.),('scale',1.),('jointOrient',0.)):
                    if any(abs(float(v)-expected)>1e-8 for v in c.getAttr(joint+'.'+attr)[0]):
                        raise CharacterRegistryError('来源 RP Inbetween OPM 本地变换未归零：'+joint)
        rest=plan.rest_length
        shortening=any(node.name==plan.normal_curve and ('preInfinity',1.) in node.values
                       for node in plan.nodes)
        for curve,drivers,values in (
                (plan.normal_curve,(rest,rest*1.2),(rest,rest*1.2)),
                (plan.anti_pop_curve,(rest,rest*1.2) if shortening else (rest*.1,rest*.7,rest*.85,rest,rest*1.2),
                 (rest,rest*1.2) if shortening else (rest,rest,rest*.9,rest,rest*1.2))):
            actual=tuple(float(v) for v in c.keyframe(curve,query=True,floatChange=True) or ())
            actual_values=tuple(float(v) for v in c.keyframe(curve,query=True,valueChange=True) or ())
            if (len(actual)!=len(drivers) or len(actual_values)!=len(values)
                    or any(abs(a-b)>1e-6 for a,b in zip(actual,drivers))
                    or any(abs(a-b)>1e-6 for a,b in zip(actual_values,values))
                    or c.getAttr(curve+'.postInfinity')!=1):
                raise CharacterRegistryError('来源 RP 抗弹跳曲线变化：'+curve)
