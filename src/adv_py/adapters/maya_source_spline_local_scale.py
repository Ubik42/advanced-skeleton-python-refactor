"""MEL 82728–82876: non-OPM ScaleBlend outside the Spline solver chain."""
from dataclasses import asdict,replace
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_graph_connections import SourceGraphConnections

MARKER='advPySourceLocalScale'


def _blend(host,target,name,mode,ik,fk=None):
    c=host._cmds
    if c.objExists(target+'.'+MARKER) or host.find_name_collisions(name):
        raise CharacterRegistryError('来源 Spline 局部缩放接收被占用：'+target)
    values=tuple(('color2'+component,1.) for component in 'RGB') if fk is None else ()
    edges=((mode,'blender'),)+tuple((ik+axis,'color1'+component) for axis,component in zip('XYZ','RGB'))
    if fk is not None:
        edges+=tuple((fk+'.scale'+axis,'color2'+component) for axis,component in zip('XYZ','RGB'))
    node=SourceRpNode(name,'blendColors',values,edges)
    graph=SourceGraphConnections(host,name)
    c.createNode(node.kind,name=node.name,skipSelect=True)
    for attr,value in values:c.setAttr(name+'.'+attr,value)
    for source,attr in edges:graph.connect(source,name+'.'+attr)
    outputs=[]
    for axis,component in zip('XYZ','RGB'):
        plug=target+'.scale'+axis
        source=c.connectionInfo(plug,sourceFromDestination=True)
        if source:c.disconnectAttr(source,plug)
        source=c.connectionInfo(target+'.scale',sourceFromDestination=True)
        if source:c.disconnectAttr(source,target+'.scale')
        graph.connect(name+'.output'+component,plug)
        outputs.append((name+'.output'+component,plug))
    record=SourceBodyMatrixPlan(target,graph.describe_nodes((node,)),graph.describe_outputs(tuple(outputs)))
    c.addAttr(target,longName=MARKER,dataType='string')
    c.setAttr(target+'.'+MARKER,canonical(asdict(record)),type='string',lock=True)


def configure(host,body,fk,splines,segments,metadata,instances,*,saved_layouts=None):
    host._require_transaction();c=host._cmds
    from adv_py.core.source_fit_identity import source_fit_metadata
    from adv_py.core.source_spline_rebuild import saved_source_spline_layout
    controls={control.driven_joint:control for control in fk.controls}
    parents={joint.parent_path for joint in body.joints}
    result=[]
    for spline in splines:
        if spline.use_offset_parent_matrix or not spline.source_ik_chain:
            result.append(spline);continue
        saved=saved_source_spline_layout(spline.body_joints,saved_layouts)
        if saved is not None and not saved.source_local_scale_indices:
            result.append(spline);continue
        allowed=None if saved is None else set(saved.source_local_scale_indices)
        indices=[]
        for index,target in enumerate(spline.body_joints):
            if allowed is not None and index not in allowed:continue
            if host.validate_body_bendy_handoff(target):continue
            control=controls.get(target if index==0 else spline.joints[index].path)
            if control is None:continue # shared start remains upstream-owned
            fit=source_fit_metadata(target.rsplit('|',1)[-1],metadata,instances)
            authored=target in parents or fit is not None and fit.control
            _blend(host,target,spline.node_name(f'AdvPy_SplineBody{index}ScaleBlend'),
                   spline.mode_weight,spline.node_name(f'AdvPy_SplineIKScaleVolume{index}.output'),
                   control.control_path if authored else None)
            if index:
                obsolete=[spline.node_name(f'AdvPy_Spline{kind}{index}')
                          for kind in ('Scale','FKWorldScale','IKWorldScale')]
                c.delete([name for name in obsolete if c.objExists(name)])
            indices.append(index)
        for joint,key in zip(spline.native_ik,spline.native_keys):
            if isinstance(key,int):
                if key not in indices:continue
            else:
                target=joint.source_joint
                if host.validate_body_bendy_handoff(target):continue
                part=next((part for built in segments if built.fk.parts is not None
                           for part in built.fk.parts.parts
                           if part.part_name==target.rsplit('|',1)[-1]),None)
                if part is None:raise CharacterRegistryError('来源 Spline Part 缩放缺少控制器身份')
                part_control=host._resolve_connected_node(part.control_name)
                _blend(host,target,'AdvPy_'+part.part_name+'_SourceSplinePartScaleBlend',
                       spline.mode_weight,spline.node_name(f'AdvPy_SplineIKScaleVolume{key}.output'),part_control)
            scaler=spline.node_name(f'AdvPy_SplineIKScaleVolume{key}')
            for axis in 'XYZ':
                plug=joint.path+'.scale'+axis
                if not c.isConnected(scaler+'.output'+axis,plug):
                    raise CharacterRegistryError('来源 Spline 独立 IKScaler 输入变化')
                c.disconnectAttr(scaler+'.output'+axis,plug);c.setAttr(plug,1.)
        if allowed is not None and set(indices)!=allowed:
            raise CharacterRegistryError('来源 Spline 保存的局部缩放布局无法完整重建')
        result.append(replace(spline,source_local_scale_indices=tuple(indices)))
    host._transaction_changed=True
    return tuple(result)


def audit_target(host,target):
    c=host._cmds;plug=target+'.'+MARKER
    from .maya_character_body_retirement import source_record,is_connected_or_retired
    saved=decode_source_body_matrix(source_record(host,target,MARKER))
    if saved.body!=target or {destination for _,destination in saved.outputs}!={target+'.scale'+axis for axis in 'XYZ'}:
        raise CharacterRegistryError('来源局部缩放登记身份变化')
    for node in saved.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
            raise CharacterRegistryError('来源局部缩放节点缺失')
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:
                raise CharacterRegistryError('来源局部缩放常量变化')
        for source,attr in node.connections:
            if not is_connected_or_retired(host,source,node.name+'.'+attr):raise CharacterRegistryError('来源局部缩放输入变化')
    for source,destination in saved.outputs:
        from .maya_game_scaling_state import original_scale_connection
        if not (is_connected_or_retired(host,source,destination)
                or original_scale_connection(host,source,destination)):
            raise CharacterRegistryError('来源局部缩放输出变化')


def audit(host,plan):
    c=host._cmds
    for joint,key in zip(plan.native_ik,plan.native_keys):
        if isinstance(key,int) and key not in plan.source_local_scale_indices:continue
        target=joint.source_joint
        if not isinstance(key,int) and not c.objExists(target+'.'+MARKER):continue
        audit_target(host,target)
        from .maya_character_body_retirement import retired_joint
        retired = retired_joint(host,target) if not c.objExists(target) else None
        parent = None if retired else (c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
        if (parent and c.nodeType(parent)=='joint' and c.getAttr(target+'.segmentScaleCompensate')
                and not c.isConnected(parent+'.scale',target+'.inverseScale')):
            raise CharacterRegistryError('来源 Spline 缩放补偿未读取实际 Part 父级')
        for axis in 'XYZ':
            if (c.connectionInfo(joint.path+'.scale'+axis,isDestination=True)
                    or abs(float(c.getAttr(joint.path+'.scale'+axis))-1.)>1e-8):
                raise CharacterRegistryError('来源独立 IKScaler 污染了求解骨链')
