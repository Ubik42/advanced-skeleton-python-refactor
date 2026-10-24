"""Source Spline Body BM/ScaleBlend/OPM, after final FKX handoffs.

MEL 80507–80521 and 82728–82876 keep IK scaler output outside the IK
solver chain and put its FK/IK blend before the Body world-matrix receiver.
"""
from dataclasses import asdict,replace

from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_body_matrix import plan_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_body_matrix import _reset_body
from .maya_source_graph_connections import SourceGraphConnections


def configure(host,body,fk,splines,*,excluded=frozenset(),saved_layouts=None):
    host._require_transaction()
    c=host._cmds
    controls={control.driven_joint:control for control in fk.controls}
    result=[]
    claimed=set()
    for spline in splines:
        if not spline.source_curve_points or not spline.use_offset_parent_matrix:
            result.append(spline)
            continue
        indices=[]
        bendy_indices=[]
        from adv_py.core.source_spline_rebuild import saved_source_spline_layout
        saved=saved_source_spline_layout(spline.body_joints,saved_layouts)
        allowed=None if saved is None else frozenset(saved.source_body_matrix_indices)
        bendy_allowed=None if saved is None else frozenset(saved.source_bendy_matrix_indices)
        n=len(spline.body_joints)
        for index,target in enumerate(spline.body_joints):
            scaler=spline.node_name(f'AdvPy_SplineIKScaleVolume{index}')
            bendy_scale='AdvPy_BendySourceScale'+target.rsplit('|',1)[-1]
            if (c.objExists(target+'.advPySourceBendyMatrix') and c.objExists(bendy_scale)
                    and (bendy_allowed is None or index in bendy_allowed)
                    and c.isConnected(scaler+'.outputX',bendy_scale+'.color1R')):
                ik_joint=spline.joints[n+index].path
                for axis in 'XYZ':
                    if not c.isConnected(scaler+'.output'+axis,ik_joint+'.scale'+axis):
                        raise CharacterRegistryError('来源 Spline Bendy IK scaler 接收输入变化')
                    c.disconnectAttr(scaler+'.output'+axis,ik_joint+'.scale'+axis)
                    c.setAttr(ik_joint+'.scale'+axis,1.)
                bendy_indices.append(index)
                continue
            if allowed is not None and index not in allowed:
                continue
            if target in excluded or target in claimed:
                continue
            mechanism=spline.joints[index].path
            control=controls.get(target if index==0 else mechanism)
            # A nested start is already the upstream system's output. The
            # upstream FK mechanism remains pure FK; never overwrite it.
            if control is None or index==0 and control.driven_joint!=target:
                continue
            parent=(c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
            orient=control.constraint_name if index==0 else spline.node_name(f'AdvPy_SplineOrient{index}')
            point=control.translation_constraint_name if index==0 else spline.node_name(f'AdvPy_SplinePoint{index}')
            if (parent is None or not c.objExists(orient)
                    or c.nodeType(orient)!='orientConstraint'
                    or point is not None and (not c.objExists(point) or c.nodeType(point)!='pointConstraint')
                    or c.connectionInfo(target+'.offsetParentMatrix',isDestination=True)
                    or c.objExists(target+'.advPySourceFkMatrix')):
                raise CharacterRegistryError('来源 Spline Body 矩阵接收图不完整：'+target)
            offsets=tuple((axis,c.connectionInfo(orient+'.offset'+axis,sourceFromDestination=True))
                          for axis in 'XYZ')
            values=tuple(float(c.getAttr(orient+'.offset'+axis)) for axis in 'XYZ')
            stem=spline.node_name(f'AdvPy_SplineBody{index}')
            scale=stem+'ScaleBlend'
            receiver=control.source_override_path or control.sub_control_path or control.control_path
            ik=(spline.root_path+'|'+spline.node_name('AdvPy_SplineFirstFixedOutput')
                if index==0 else spline.ik_outputs[index])
            scale_driver=spline.node_name(f'AdvPy_SplineIKScaleVolume{index}')
            ik_joint=spline.joints[n+index].path
            for axis in 'XYZ':
                source=c.connectionInfo(ik_joint+'.scale'+axis,sourceFromDestination=True)
                if source!=scale_driver+'.output'+axis:
                    raise CharacterRegistryError('来源 Spline IK scaler 交接来源变化：'+ik_joint)
            plan=plan_source_body_matrix(stem,target,parent,
                receiver+'.worldMatrix[0]',ik+'.worldMatrix[0]',spline.mode_weight,scale,
                offset_sources=tuple((axis,source) for axis,source in offsets if source),
                offset_values=values)
            scale_node=SourceRpNode(scale,'blendColors',tuple(
                ('color2'+component,1.) for component in 'RGB'),
                ((spline.mode_weight,'blender'),)+tuple(
                    (scale_driver+'.output'+axis,'color1'+component)
                    for axis,component in zip('XYZ','RGB')))
            plan=replace(plan,nodes=(scale_node,)+plan.nodes)
            if any(host.find_name_collisions(node.name) for node in plan.nodes):
                raise CharacterRegistryError('来源 Spline Body 矩阵节点名称被占用：'+target)
            remove=[orient]+([point] if point is not None else [])
            if index:
                remove.extend(spline.node_name(f'AdvPy_Spline{label}{index}')
                              for label in ('Scale','FKWorldScale','IKWorldScale'))
                if any(not c.objExists(name) for name in remove):
                    raise CharacterRegistryError('来源 Spline 旧世界缩放图缺失：'+target)
            for axis,source in offsets:
                if source:c.disconnectAttr(source,orient+'.offset'+axis)
            c.delete(remove)
            for axis in 'XYZ':
                c.disconnectAttr(scale_driver+'.output'+axis,ik_joint+'.scale'+axis)
                c.setAttr(ik_joint+'.scale'+axis,1.)
            _reset_body(c,target)
            graph=SourceGraphConnections(host,stem)
            for node in plan.nodes:
                c.createNode(node.kind,name=node.name,skipSelect=True)
                for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
            for node in plan.nodes:
                for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
            for source,destination in plan.outputs:graph.connect(source,destination)
            plan=replace(plan,nodes=graph.describe_nodes(plan.nodes),
                         outputs=graph.describe_outputs(plan.outputs))
            c.addAttr(target,longName='advPySourceFkMatrix',dataType='string')
            c.setAttr(target+'.advPySourceFkMatrix',canonical(asdict(plan)),type='string',lock=True)
            c.addAttr(target,longName='advPySourceFkPoint',attributeType='bool')
            c.setAttr(target+'.advPySourceFkPoint',point is not None,lock=True)
            indices.append(index)
            claimed.add(target)
        result.append(replace(spline,source_body_matrix_indices=tuple(indices),
                              source_bendy_matrix_indices=tuple(bendy_indices)))
        if saved is not None and (tuple(indices)!=saved.source_body_matrix_indices
                or tuple(bendy_indices)!=saved.source_bendy_matrix_indices):
            raise CharacterRegistryError('来源 Spline 保存的矩阵交接布局无法完整重建')
    host._transaction_changed=True
    return tuple(result)


def audit(host,plan):
    """Called inside the normal Spline scope, with canonical node names."""
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    c=host._cmds
    from .maya_character_body_retirement import source_record,is_connected_or_retired
    n=len(plan.body_joints)
    for index in plan.source_bendy_matrix_indices:
        from .maya_source_bendy_body_matrix import audit_joint
        target=plan.body_joints[index]
        audit_joint(host,target)
        scale='AdvPy_BendySourceScale'+target.rsplit('|',1)[-1]
        scaler=f'AdvPy_SplineIKScaleVolume{index}'
        for axis,component in zip('XYZ','RGB'):
            if (not c.isConnected(scaler+'.output'+axis,scale+'.color1'+component)
                    or c.connectionInfo(plan.joints[n+index].path+'.scale'+axis,isDestination=True)
                    or abs(float(c.getAttr(plan.joints[n+index].path+'.scale'+axis))-1.)>1e-8):
                raise CharacterRegistryError('来源 Spline Bendy 独立缩放交接变化')
    for index in plan.source_body_matrix_indices:
        target=plan.body_joints[index]
        plug=target+'.advPySourceFkMatrix'
        saved=decode_source_body_matrix(source_record(host,target,'advPySourceFkMatrix'))
        if saved.body!=target:
            raise CharacterRegistryError('来源 Spline Body 矩阵登记身份变化')
        stem=f'AdvPy_SplineBody{index}'
        scale=stem+'ScaleBlend'
        scaler=f'AdvPy_SplineIKScaleVolume{index}'
        for axis,component in zip('XYZ','RGB'):
            if (not c.isConnected(scaler+'.output'+axis,scale+'.color1'+component)
                    or c.connectionInfo(plan.joints[n+index].path+'.scale'+axis,isDestination=True)
                    or abs(float(c.getAttr(plan.joints[n+index].path+'.scale'+axis))-1.)>1e-8
                    or abs(float(c.getAttr(scale+'.color2'+component))-1.)>1e-8):
                raise CharacterRegistryError('来源 Spline IK scaler 与 Body OPM 交接变化')
        ik=(plan.root_path+'|AdvPy_SplineFirstFixedOutput' if index==0 else plan.ik_outputs[index])
        if (not c.isConnected(plan.mode_weight,scale+'.blender')
                or not c.isConnected(plan.mode_weight,stem+'BodyBM.target[0].weight')
                or not c.isConnected(ik+'.worldMatrix[0]',stem+'BodyBM.target[0].targetMatrix')
                or not is_connected_or_retired(host,stem+'BodyMM.matrixSum',target+'.offsetParentMatrix')):
            raise CharacterRegistryError('来源 Spline Body FK／IK 矩阵混合变化')
        # Full edge/constants validation is shared with other source Body
        # records at character registration; check here too for direct audit.
        for node in saved.nodes:
            if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
                raise CharacterRegistryError('来源 Spline Body 原生矩阵节点缺失')
            for attr,value in node.values:
                if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:
                    raise CharacterRegistryError('来源 Spline Body 矩阵常量变化')
            for source,attr in node.connections:
                if not is_connected_or_retired(host,source,node.name+'.'+attr):
                    raise CharacterRegistryError('来源 Spline Body 矩阵连接变化')


def install_match_scale(host,plan,index,control):
    """Keep the existing matching extension effective with a native FKX BM.

    Its absolute matchScale replaces main-control scale, while the FKX
    matrix still carries Sub, offset, parent and inherited world transforms.
    """
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    c=host._cmds
    stem=plan.node_name(f'AdvPy_SplineBody{index}')
    blend=stem+'BodyBM'
    ratio=stem+'MatchScaleRatio'
    compose=stem+'MatchScaleCM'
    matrix=stem+'MatchScaleMM'
    plug=plan.body_joints[index]+'.advPySourceFkMatrix'
    saved=decode_source_body_matrix(c.getAttr(plug))
    source=c.connectionInfo(blend+'.inputMatrix',sourceFromDestination=True)
    if not source or any(host.find_name_collisions(name) for name in (ratio,compose,matrix)):
        raise CharacterRegistryError('来源 Spline 矩阵匹配扩展接收图无效')
    node,attribute=source.split('.',1)
    source=host._resolve_connected_node(node)+'.'+attribute
    nodes=(SourceRpNode(ratio,'multiplyDivide',(('operation',2.),),tuple(
        (control+'.matchScale'+axis,'input1'+axis) for axis in 'XYZ')+tuple(
        (control+'.scale'+axis,'input2'+axis) for axis in 'XYZ')),
        SourceRpNode(compose,'composeMatrix',connections=tuple(
            (ratio+'.output'+axis,'inputScale'+axis) for axis in 'XYZ')),
        SourceRpNode(matrix,'multMatrix',connections=(
            (compose+'.outputMatrix','matrixIn[0]'),(source,'matrixIn[1]'))))
    graph=SourceGraphConnections(host,stem+'Match')
    for spec in nodes:
        c.createNode(spec.kind,name=spec.name,skipSelect=True)
        for attr,value in spec.values:c.setAttr(spec.name+'.'+attr,value)
    for spec in nodes:
        for incoming,attr in spec.connections:graph.connect(incoming,spec.name+'.'+attr)
    c.disconnectAttr(source,blend+'.inputMatrix')
    graph.connect(matrix+'.matrixSum',blend+'.inputMatrix')
    nodes=graph.describe_nodes(nodes)
    updated=replace(saved,nodes=tuple(replace(spec,connections=tuple(
        (matrix+'.matrixSum' if spec.name==blend and attr=='inputMatrix' else incoming,attr)
        for incoming,attr in spec.connections)) for spec in saved.nodes)+nodes)
    c.setAttr(plug,lock=False)
    c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)


def local_rotation_scale(host,joint):
    """An OPM Body's TRS channels are zero; matching reads its full frame."""
    from math import degrees
    from maya.api import OpenMaya as om
    c=host._cmds
    world=om.MMatrix(c.xform(joint,q=True,worldSpace=True,matrix=True))
    parent=(c.listRelatives(joint,parent=True,fullPath=True) or [None])[0]
    if parent:
        world=world*om.MMatrix(c.xform(parent,q=True,worldSpace=True,matrix=True)).inverse()
    transform=om.MTransformationMatrix(world)
    rotation=transform.rotation(asQuaternion=False)
    rotation.reorderIt(int(c.getAttr(joint+'.rotateOrder')))
    return tuple(degrees(value) for value in (rotation.x,rotation.y,rotation.z)),tuple(
        transform.scale(om.MSpace.kTransform))


def install_bendy_match_scale(host,plan,index,control):
    """The shared Bendy ScaleBlend must follow the matching scale channel."""
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    c=host._cmds
    name='AdvPy_BendySourceScale'+plan.body_joints[index].rsplit('|',1)[-1]
    for axis,component in zip('XYZ','RGB'):
        destination=name+'.color2'+component
        source=c.connectionInfo(destination,sourceFromDestination=True)
        if source!=control+'.scale'+axis:
            raise CharacterRegistryError('来源 Spline Bendy 匹配缩放原始输入变化')
        c.disconnectAttr(source,destination)
        c.connectAttr(control+'.matchScale'+axis,destination)
    for joint in c.ls(type='joint',long=True) or []:
        plug=joint+'.advPySourceBendyMatrix'
        if not c.objExists(plug):continue
        saved=decode_source_body_matrix(c.getAttr(plug))
        if not any(node.name==name for node in saved.nodes):continue
        updated=replace(saved,nodes=tuple(replace(node,connections=tuple(
            (control+'.matchScale'+'XYZ'['RGB'.index(attr[-1])]
             if node.name==name and attr.startswith('color2') else source,attr)
            for source,attr in node.connections)) for node in saved.nodes))
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)
