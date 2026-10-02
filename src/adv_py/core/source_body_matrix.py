"""MEL 80507–80521/82728–82765: source Body's complete FK/IK OPM."""
from dataclasses import dataclass
from math import isfinite
from .source_rp_dynamics import SourceRpNode


@dataclass(frozen=True,slots=True)
class SourceBodyMatrixPlan:
    body: str
    nodes: tuple[SourceRpNode,...]
    outputs: tuple[tuple[str,str],...]
    local_scale: tuple[tuple[str,str],...]=()


def _valid_offsets(sources,values):
    return (len(values)==3 and all(not isinstance(value,bool) and
        isinstance(value,(int,float)) and isfinite(value) for value in values)
        and all(axis in ('X','Y','Z') and isinstance(source,str) and bool(source)
                for axis,source in sources)
        and len({axis for axis,_ in sources})==len(sources))


def plan_source_body_matrix(prefix,body,parent,fk_world,ik_world,mode,scale, *,
                            offset_sources=(),offset_values=(0.,0.,0.)):
    if (not all(isinstance(p,str) and p for p in
                (prefix,body,parent,fk_world,ik_world,mode,scale))
            or not _valid_offsets(offset_sources,offset_values)):
        raise ValueError('来源 Body OPM 缺少完整 FK/IK 矩阵身份')
    compose=prefix+'ScaleCM'
    blend=prefix+'BodyBM'
    matrix=prefix+'BodyMM'
    nodes=[SourceRpNode(compose,'composeMatrix',connections=tuple(
        (scale+'.output'+component,'inputScale'+axis)
        for axis,component in zip('XYZ','RGB'))),
        SourceRpNode(blend,'blendMatrix',connections=(
            (fk_world,'inputMatrix'),(ik_world,'target[0].targetMatrix'),
            (mode,'target[0].weight')))]
    matrices=[compose+'.outputMatrix']
    if offset_sources or any(abs(v)>1e-8 for v in offset_values):
        twist=prefix+'TwistCM'
        connected={axis for axis,_ in offset_sources}
        nodes.append(SourceRpNode(twist,'composeMatrix',
            tuple(('inputRotate'+axis,float(value)) for axis,value in zip('XYZ',offset_values)
                  if axis not in connected),
            tuple((source,'inputRotate'+axis) for axis,source in offset_sources)))
        matrices.append(twist+'.outputMatrix')
    matrices.extend((blend+'.outputMatrix',parent+'.worldInverseMatrix[0]'))
    nodes.append(SourceRpNode(matrix,'multMatrix',connections=tuple(
        (source,'matrixIn['+str(index)+']') for index,source in enumerate(matrices))))
    return SourceBodyMatrixPlan(body,tuple(nodes),((matrix+'.matrixSum',body+'.offsetParentMatrix'),))


def plan_source_fk_body_matrix(prefix,body,parent,fk_world, *,offset_sources=(),offset_values=(0.,0.,0.)):
    """Original FK-only branch: FKX world, optional twist, parent inverse."""
    if (not all(isinstance(value,str) and value for value in (prefix,body,parent,fk_world))
            or not _valid_offsets(offset_sources,offset_values)):
        raise ValueError('来源 FK Body OPM 缺少实际父级和 FKX')
    nodes=[]
    sources=[]
    if offset_sources or any(abs(value)>1e-8 for value in offset_values):
        compose=prefix+'TwistCM'
        connected={axis for axis,_ in offset_sources}
        nodes.append(SourceRpNode(compose,'composeMatrix',
            tuple(('inputRotate'+axis,float(value)) for axis,value in zip('XYZ',offset_values)
                  if axis not in connected),
            tuple((source,'inputRotate'+axis) for axis,source in offset_sources)))
        sources.append(compose+'.outputMatrix')
    sources.extend((fk_world,parent+'.worldInverseMatrix[0]'))
    matrix=prefix+'BodyMM'
    nodes.append(SourceRpNode(matrix,'multMatrix',connections=tuple(
        (source,'matrixIn['+str(index)+']') for index,source in enumerate(sources))))
    return SourceBodyMatrixPlan(body,tuple(nodes),((matrix+'.matrixSum',body+'.offsetParentMatrix'),))


def decode_source_body_matrix(text):
    """Closed native graph record, using scene plugs rather than object loading."""
    import re
    from .character_registry import safe_json,exact,path,identifier,finite,CharacterRegistryError
    raw=safe_json(text)
    raw=exact(raw,('body','nodes','outputs','local_scale') if isinstance(raw,dict) and 'local_scale' in raw else ('body','nodes','outputs'))
    def attribute(value):
        if not isinstance(value,str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)*',value):
            raise CharacterRegistryError('来源 Body 矩阵属性地址无效')
        return value
    def plug(value):
        if not isinstance(value,str) or '.' not in value:
            raise CharacterRegistryError('来源 Body 矩阵连接地址无效')
        node,attr=value.split('.',1)
        path(node) if node.startswith('|') else identifier(node)
        attribute(attr)
        return value
    nodes=[]
    if not isinstance(raw['nodes'],list) or not 0<=len(raw['nodes'])<=64:
        raise CharacterRegistryError('来源 Body 矩阵图规模无效')
    for row in raw['nodes']:
        exact(row,('name','kind','values','connections'))
        if row['kind'] not in ('multMatrix','composeMatrix','unitConversion','blendMatrix','blendColors','multiplyDivide','pickMatrix','reverse','decomposeMatrix','addDoubleLinear','pointConstraint','scaleConstraint'):
            raise CharacterRegistryError('来源 FK Body 矩阵节点类型无效')
        values=tuple((attribute(attr),finite(value)) for attr,value in row['values'])
        edges=tuple((plug(source),attribute(attr)) for source,attr in row['connections'])
        if len({attr for attr,_ in values})!=len(values) or len({attr for _,attr in edges})!=len(edges):
            raise CharacterRegistryError('来源 FK Body 矩阵输入重复')
        nodes.append(SourceRpNode(identifier(row['name']),row['kind'],values,edges))
    outputs=tuple((plug(source),plug(target)) for source,target in raw['outputs'])
    body=path(raw['body'])
    matrix_output=bool(nodes) and len(outputs)==1 and outputs[0][1]==body+'.offsetParentMatrix'
    scale_output=(len(outputs)==3 and {target for _,target in outputs}==
                  {body+'.scale'+axis for axis in 'XYZ'})
    point_output=(bool(nodes) and len(outputs)==3 and {target for _,target in outputs}==
                  {body+'.translate'+axis for axis in 'XYZ'})
    if scale_output and not nodes:
        # FK-only Parts deliberately have no calculation nodes: the original
        # control's local scale drives the matching three Body scale axes.
        sources={source.rsplit('.',1)[0] for source,_ in outputs}
        if len(sources)!=1 or any(source.rsplit('.',1)[1]!=target.rsplit('.',1)[1]
                                 for source,target in outputs):
            raise CharacterRegistryError('来源 FK Part 直接缩放接收身份无效')
    if (len({node.name for node in nodes})!=len(nodes)
            or not (matrix_output or scale_output or point_output)):
        raise CharacterRegistryError('来源 FK Body 矩阵输出身份无效')
    local_scale=tuple((plug(source),plug(target)) for source,target in raw.get('local_scale',()))
    if local_scale and (len(local_scale)!=3 or {target for _,target in local_scale}!=
            {body+'.scale'+axis for axis in 'XYZ'}):
        raise CharacterRegistryError('来源 Bendy Part 本地缩放身份无效')
    return SourceBodyMatrixPlan(body,tuple(nodes),outputs,local_scale)
