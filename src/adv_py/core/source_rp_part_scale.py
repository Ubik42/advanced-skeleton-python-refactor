"""Original Inbetween ScaleBlend and OPM Body matrix insertion.

MEL 80507–80521, 80620–80634, 82728–82765 and 84370–84379.
Twist Parts share their starting joint scale; Inbetween Parts are solver
joints with individual Fatness channels and their own FK/IK scale selection.
"""
from dataclasses import dataclass
from .source_rp_dynamics import SourceRpNode


@dataclass(frozen=True,slots=True)
class SourceRpPartScalePlan:
    body: str
    constraint: str
    use_offset_parent_matrix: bool
    nodes: tuple[SourceRpNode,...]
    outputs: tuple[tuple[str,str],...]
    twist_source: str | None = None


def plan_source_rp_part_scale(stem,index,body,parent,fk_driver,ik_driver,
                              fk_control,mode,volume,fatness, *,
                              use_offset_parent_matrix,twist_source=None):
    if (type(index) is not int or index<1 or type(use_offset_parent_matrix) is not bool
            or not all(isinstance(p,str) and p for p in
                       (stem,body,parent,fk_driver,ik_driver,fk_control,mode,volume,fatness))):
        raise ValueError('来源 RP Inbetween 缩放身份不完整')
    prefix=stem+'_Part'+str(index)
    blend=prefix+'ScaleBlend'
    def node(name,kind,values=(),edges=()):
        return SourceRpNode(name,kind,tuple(values),tuple(edges))
    edges=[(volume,'color1R'),(fatness,'color1G'),(fatness,'color1B'),(mode,'blender')]
    values=[]
    if use_offset_parent_matrix:
        # FK scale is already carried by FKX.worldMatrix in the original OPM
        # branch. Feeding FK.scale here as well would apply it twice.
        values.extend(('color2'+component,1.) for component in 'RGB')
    else:
        edges.append((fk_control+'.scale','color2'))
    nodes=[node(blend,'blendColors',values,edges)]
    constraint='AdvPy_'+body.rsplit('|',1)[-1]+'_InbetweenIKFKOrient'
    if not use_offset_parent_matrix:
        return SourceRpPartScalePlan(body,constraint,False,tuple(nodes),
                                     ((blend+'.output',body+'.scale'),))
    compose=prefix+'ScaleCM'
    world=prefix+'BodyBM'
    matrix=prefix+'BodyMM'
    nodes.append(node(compose,'composeMatrix',edges=tuple(
        (blend+'.output'+component,'inputScale'+axis)
        for axis,component in zip('XYZ','RGB'))))
    nodes.append(node(world,'blendMatrix',edges=(
        (fk_driver+'.worldMatrix[0]','inputMatrix'),
        (ik_driver+'.worldMatrix[0]','target[0].targetMatrix'),
        (mode,'target[0].weight'))))
    matrix_edges=[(compose+'.outputMatrix','matrixIn[0]')]
    if twist_source:
        twist=prefix+'TwistCM'
        nodes.append(node(twist,'composeMatrix',edges=((twist_source,'inputRotateX'),)))
        matrix_edges.append((twist+'.outputMatrix','matrixIn[1]'))
    offset=len(matrix_edges)
    matrix_edges.extend(((world+'.outputMatrix','matrixIn['+str(offset)+']'),
                         (parent+'.worldInverseMatrix[0]','matrixIn['+str(offset+1)+']')))
    nodes.append(node(matrix,'multMatrix',edges=matrix_edges))
    return SourceRpPartScalePlan(body,constraint,True,tuple(nodes),
        ((matrix+'.matrixSum',body+'.offsetParentMatrix'),),twist_source)
