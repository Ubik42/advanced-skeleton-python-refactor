"""Finish source RP Body OPM after Part twist and scale receivers exist."""
from dataclasses import replace,asdict
from adv_py.core.source_body_matrix import plan_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from adv_py.core.character_registry import CharacterRegistryError,canonical
from .maya_source_graph_connections import SourceGraphConnections


def _reset_body(c,target):
    for attr in ('translate','rotate','scale','jointOrient'):
        compound=target+'.'+attr
        source=c.connectionInfo(compound,sourceFromDestination=True)
        if source:c.disconnectAttr(source,compound)
        for axis in 'XYZ':
            source=c.connectionInfo(compound+axis,sourceFromDestination=True)
            if source:c.disconnectAttr(source,compound+axis)
        value=1. if attr=='scale' else 0.
        c.setAttr(compound,value,value,value,type='double3')


def configure_fk(host,body,fk, *,excluded=frozenset()):
    from adv_py.core.source_body_matrix import plan_source_fk_body_matrix
    host._require_transaction()
    c=host._cmds
    paths={joint.path for joint in body.joints}
    for control in fk.controls:
        target=control.driven_joint
        if target not in paths or target==body.root or target in excluded:
            continue
        if not c.objExists(target+'.advPySourceJoint'):
            continue
        parent=(c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
        orient=control.constraint_name
        point=control.translation_constraint_name
        if (parent is None or not c.objExists(orient) or c.nodeType(orient)!='orientConstraint'
                or point is not None and (
                    not c.objExists(point) or c.nodeType(point)!='pointConstraint')
                or c.connectionInfo(target+'.offsetParentMatrix',isDestination=True)):
            raise CharacterRegistryError('来源 FK Body OPM 接收图不完整：'+target)
        offsets=tuple((axis,c.connectionInfo(orient+'.offset'+axis,sourceFromDestination=True)) for axis in 'XYZ')
        values=tuple(float(c.getAttr(orient+'.offset'+axis)) for axis in 'XYZ')
        receiver=control.source_override_path or control.sub_control_path or control.control_path
        plan=plan_source_fk_body_matrix('AdvPy_'+target.rsplit('|',1)[-1]+'_Source',
            target,parent,receiver+'.worldMatrix[0]',offset_sources=tuple(
                (axis,source) for axis,source in offsets if source),offset_values=values)
        if any(host.find_name_collisions(node.name) for node in plan.nodes):
            raise CharacterRegistryError('来源 FK Body OPM 节点名称被占用：'+target)
        graph=SourceGraphConnections(host,'AdvPy_'+target.rsplit('|',1)[-1]+'_Source')
        for axis,source in offsets:
            if source:c.disconnectAttr(source,orient+'.offset'+axis)
        remove=[orient]
        if point and c.objExists(point):remove.append(point)
        c.delete(remove)
        _reset_body(c,target)
        for node in plan.nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
            for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for node in plan.nodes:
            for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
        for source,target_plug in plan.outputs:graph.connect(source,target_plug)
        plan=replace(plan,nodes=graph.describe_nodes(plan.nodes),outputs=graph.describe_outputs(plan.outputs))
        c.addAttr(target,longName='advPySourceFkMatrix',dataType='string')
        c.setAttr(target+'.advPySourceFkMatrix',canonical(asdict(plan)),type='string',lock=True)
        c.addAttr(target,longName='advPySourceFkPoint',attributeType='bool')
        c.setAttr(target+'.advPySourceFkPoint',bool(point),lock=True)
    # MEL 80564–80582: un-driven terminal joints also receive their complete
    # local transform through OPM. This includes ends without an FK control.
    parents={joint.parent_path for joint in body.joints}
    for joint in body.joints:
        target=joint.path
        if target==body.root or target in parents or target in excluded:
            continue
        if (not c.objExists(target+'.advPySourceJoint')
                or c.connectionInfo(target+'.offsetParentMatrix',isDestination=True)
                or any(c.listConnections(target+'.'+attr,source=True,destination=False)
                       for attr in ('translate','rotate','scale','jointOrient'))):
            continue
        matrix=tuple(float(v) for v in c.getAttr(target+'.matrix'))
        _reset_body(c,target)
        c.setAttr(target+'.offsetParentMatrix',*matrix,type='matrix')
        c.addAttr(target,longName='advPySourceEndMatrix',dataType='string')
        c.setAttr(target+'.advPySourceEndMatrix',canonical(dict(body=target,matrix=matrix)),type='string',lock=True)
    host._transaction_changed=True


def audit_fk(host,registration):
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    c=host._cmds
    for joint in registration.body:
        end_plug=joint.path+'.advPySourceEndMatrix'
        if c.objExists(end_plug):
            from adv_py.core.character_registry import safe_json,exact,path,vector
            raw=exact(safe_json(c.getAttr(end_plug)),('body','matrix'))
            matrix=vector(raw['matrix'],16)
            if (not c.getAttr(end_plug,lock=True) or path(raw['body'])!=joint.path
                    or c.connectionInfo(joint.path+'.offsetParentMatrix',isDestination=True)
                    or any(abs(a-b)>1e-8 for a,b in zip(matrix,c.getAttr(joint.path+'.offsetParentMatrix')))):
                raise CharacterRegistryError('来源末端 Body OPM 静态矩阵变化：'+joint.path)
            for attr,value in (('translate',0.),('rotate',0.),('jointOrient',0.),('scale',1.)):
                if any(abs(float(v)-value)>1e-8 for v in c.getAttr(joint.path+'.'+attr)[0]):
                    raise CharacterRegistryError('来源末端 Body OPM 本地变换变化：'+joint.path)
        plug=joint.path+'.advPySourceFkMatrix'
        if not c.objExists(plug):continue
        if not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源 FK Body 矩阵登记已解锁')
        point_plug=joint.path+'.advPySourceFkPoint'
        if (not c.objExists(point_plug) or c.getAttr(point_plug,type=True)!='bool'
                or not c.getAttr(point_plug,lock=True)):
            raise CharacterRegistryError('来源 FK Body 位置接收登记无效：'+joint.path)
        plan=decode_source_body_matrix(c.getAttr(plug))
        if plan.body!=joint.path:
            raise CharacterRegistryError('来源 FK Body 矩阵登记身份变化')
        for node in plan.nodes:
            if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
                raise CharacterRegistryError('来源 FK Body 矩阵节点缺失：'+node.name)
            for attr,value in node.values:
                if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:
                    raise CharacterRegistryError('来源 FK Body 矩阵常量变化：'+node.name+'.'+attr)
            for source,attr in node.connections:
                if not c.isConnected(source,node.name+'.'+attr):
                    raise CharacterRegistryError('来源 FK Body 矩阵连接变化：'+node.name+'.'+attr)
        for source,target in plan.outputs:
            if not c.isConnected(source,target):
                raise CharacterRegistryError('来源 FK Body 矩阵输出变化：'+target)
        for attr,value in (('translate',0.),('rotate',0.),('jointOrient',0.),('scale',1.)):
            if any(abs(float(v)-value)>1e-8 for v in c.getAttr(plan.body+'.'+attr)[0]):
                raise CharacterRegistryError('来源 FK Body OPM 本地变换变化：'+plan.body)


def rebase_fk_records(host,registration,rewrites):
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    from adv_py.core.fit_part import FitPartFinalPaths,rebase_plan_paths_after_parts
    paths=FitPartFinalPaths((),(),tuple(rewrites))
    c=host._cmds
    for joint in registration.body:
        body=rebase_plan_paths_after_parts(joint.path,paths)
        end_plug=body+'.advPySourceEndMatrix'
        if c.objExists(end_plug):
            from adv_py.core.character_registry import safe_json,exact
            raw=exact(safe_json(c.getAttr(end_plug)),('body','matrix'))
            updated=rebase_plan_paths_after_parts(raw,paths)
            if updated!=raw:
                c.setAttr(end_plug,lock=False)
                c.setAttr(end_plug,canonical(updated),type='string',lock=True)
        plug=body+'.advPySourceFkMatrix'
        if not c.objExists(plug):continue
        plan=decode_source_body_matrix(c.getAttr(plug))
        updated=rebase_plan_paths_after_parts(plan,paths)
        if plan==updated:continue
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)


def configure(host,body,fk,limbs,dynamics, *,excluded=frozenset()):
    host._require_transaction()
    c=host._cmds
    result=[]
    controls={control.driven_joint:control for control in fk.controls}
    for saved in dynamics:
        limb=next(limb for limb in limbs if limb.label==saved.label)
        side=next(side for side in limb.blend.sides if side.side.value==saved.side)
        graph=SourceGraphConnections(host,'AdvPy_'+saved.label+'_RP_'+saved.side+'_Body')
        nodes=[]
        outputs=[]
        for joint in side.joints:
            if joint.body_joint in excluded:
                continue
            target=joint.body_joint
            if not c.objExists(target+'.advPySourceJoint'):
                continue  # Source temporary Foot placement markers were removed.
            parent=(c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
            control=controls.get(joint.fk_driver)
            if control is None:
                # MEL skips its FKX constraint pass when that receiver is
                # absent. A no-control Foot end must not block the rig.
                continue
            if parent is None:
                raise CharacterRegistryError('来源 Body OPM 缺少实际父级或 FKX 来源：'+target)
            orient=joint.constraint_name
            point=joint.translation_constraint_name
            scale=orient+'Scale'
            if (not point or not c.objExists(orient) or not c.objExists(point)
                    or c.nodeType(orient)!='orientConstraint' or c.nodeType(point)!='pointConstraint'
                    or not c.objExists(scale) or c.nodeType(scale)!='blendColors'
                    or c.connectionInfo(target+'.offsetParentMatrix',isDestination=True)):
                raise CharacterRegistryError('来源 Body OPM 原有接收图不完整：'+target)
            offsets=tuple((axis,c.connectionInfo(orient+'.offset'+axis,sourceFromDestination=True))
                          for axis in 'XYZ')
            values=tuple(float(c.getAttr(orient+'.offset'+axis)) for axis in 'XYZ')
            receiver=control.source_override_path or control.sub_control_path or control.control_path
            plan=plan_source_body_matrix('AdvPy_'+target.rsplit('|',1)[-1]+'_Source',
                target,parent,receiver+'.worldMatrix[0]',joint.ik_driver+'.worldMatrix[0]',
                limb.blend.settings_path+'.'+side.attribute,scale,
                offset_sources=tuple((axis,source) for axis,source in offsets if source),
                offset_values=values)
            if any(host.find_name_collisions(node.name) for node in plan.nodes):
                raise CharacterRegistryError('来源 Body OPM 节点名称被占用：'+target)
            for axis,source in offsets:
                if source:c.disconnectAttr(source,orient+'.offset'+axis)
            c.delete(orient,point)
            _reset_body(c,target)
            # FKX already carries FK control and Sub scale. End IKX already
            # carries main IK scale; volume applies only before the RP end.
            for color in ('color2',)+(('color1',) if not any(
                    segment.previous==joint.ik_driver for segment in saved.segments) else ()):
                source=c.connectionInfo(scale+'.'+color,sourceFromDestination=True)
                if source:c.disconnectAttr(source,scale+'.'+color)
                for component in 'RGB':
                    plug=scale+'.'+color+component
                    source=c.connectionInfo(plug,sourceFromDestination=True)
                    if source:c.disconnectAttr(source,plug)
                    c.setAttr(plug,1.)
            scale_values=[]
            scale_edges=[]
            for attr in ('blender',*(color+component for color in ('color1','color2') for component in 'RGB')):
                source=c.connectionInfo(scale+'.'+attr,sourceFromDestination=True)
                if source:
                    name,attribute=source.split('.',1)
                    scale_edges.append((host._resolve_connected_node(name)+'.'+attribute,attr))
                else:scale_values.append((attr,float(c.getAttr(scale+'.'+attr))))
            nodes.append(SourceRpNode(scale,'blendColors',tuple(scale_values),tuple(scale_edges)))
            for node in plan.nodes:
                c.createNode(node.kind,name=node.name,skipSelect=True)
                for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
            for node in plan.nodes:
                for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
            for source,destination in plan.outputs:graph.connect(source,destination)
            nodes.extend(plan.nodes)
            outputs.extend(plan.outputs)
        updated=replace(saved,nodes=saved.nodes+graph.describe_nodes(nodes),
                        outputs=saved.outputs+graph.describe_outputs(outputs))
        c.addAttr(saved.start_anchor,longName='advPySourceBodyMatrix',attributeType='bool')
        c.setAttr(saved.start_anchor+'.advPySourceBodyMatrix',True,lock=True)
        plug=saved.start_anchor+'.advPySourceRpDynamics'
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)
        result.append(updated)
    host._transaction_changed=True
    return tuple(result)
