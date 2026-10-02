"""Original expanded-chain Spline Part scale interpolation and Body OPM."""
from dataclasses import replace
from .source_body_matrix import plan_source_body_matrix
from .source_rp_dynamics import SourceRpNode
from .body_spline import spline_ik_scale_weights


def plan_spline_part_matrix(stem,body,parent,fk,ik,mode,reference,targets,index,count,volume_delta,*,offset_sources=(),offset_values=(0.,0.,0.),ik_scale_plug=None):
    scale=stem+'ScaleBlend';blend=stem+'IKScaleBM';relative=stem+'IKScaleMM';decompose=stem+'IKScaleDM';volume=stem+'IKScaleVolume'
    weights=spline_ik_scale_weights(index,count,len(targets))
    nodes=[SourceRpNode(blend,'blendMatrix',tuple((f'target[{i}].weight',w) for i,w in enumerate(weights) if w),
        ((reference+'.worldMatrix[0]','inputMatrix'),)+tuple((target+'.worldMatrix[0]',f'target[{i}].targetMatrix') for i,(target,w) in enumerate(zip(targets,weights)) if w)),
        SourceRpNode(relative,'multMatrix',connections=((blend+'.outputMatrix','matrixIn[0]'),(reference+'.worldInverseMatrix[0]','matrixIn[1]'))),
        SourceRpNode(decompose,'decomposeMatrix',connections=((relative+'.matrixSum','inputMatrix'),))]
    multiplier=()
    if 0<index<count-1:
        weight=stem+'IKScaleWeight';add=stem+'IKScaleAdd';fraction=2.*(index+1)/(count+1)
        nodes.extend((SourceRpNode(weight,'multiplyDivide',(('operation',1.),('input2X',min(fraction,2.-fraction))),((volume_delta,'input1X'),)),
                      SourceRpNode(add,'addDoubleLinear',(('input2',1.),),((weight+'.outputX','input1'),))))
        multiplier=tuple((add+'.output','input2'+axis) for axis in 'XYZ')
    nodes.extend((SourceRpNode(volume,'multiplyDivide',(('operation',1.),),((decompose+'.outputScale','input1'),)+multiplier),
        SourceRpNode(scale,'blendColors',tuple(('color2'+axis,1.) for axis in 'RGB'),
            ((mode,'blender'),)+tuple((volume+'.output'+axis,'color1'+component) for axis,component in zip('XYZ','RGB')))))
    if ik_scale_plug is not None:
        # The expanded native plan already owns the original IKScaler graph.
        # Feed its result to ScaleBlend instead of duplicating its computation.
        nodes=[SourceRpNode(scale,'blendColors',tuple(('color2'+axis,1.) for axis in 'RGB'),
            ((mode,'blender'),)+tuple((ik_scale_plug+axis,'color1'+component) for axis,component in zip('XYZ','RGB')))]
    body_graph=plan_source_body_matrix(stem,body,parent,fk+'.worldMatrix[0]',ik+'.worldMatrix[0]',mode,scale,
                                      offset_sources=offset_sources,offset_values=offset_values)
    return replace(body_graph,nodes=tuple(nodes)+body_graph.nodes)
