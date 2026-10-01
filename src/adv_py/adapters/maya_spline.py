"""Native cubic spline IK, local curve length stretch and volume scaling."""
import json

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.body_spline import (
    current_spline_owner, spline_ik_scale_weights, spline_owner_version,
)
from adv_py.core.body_controller_layers import (
    audit_body_extra_controller, audit_body_sub_controller,
)
from .maya_adv_icons import create_adv_icon
from . import maya_chest_space
from . import maya_spline_even
from . import maya_spline_twist
from . import maya_spline_follow
from . import maya_source_spline_cv
from . import maya_source_spline_hybrid
from . import maya_source_spline_visibility


def _fk_root_source(host, plan):
    if not plan.fk_root_point_from_receiver:
        return plan.pelvis_control
    c = host._cmds
    constraints = c.ls('AdvPy_SplineBaseFKOrient',
                       type='orientConstraint') or []
    if len(constraints) != 1:
        raise FitSkeletonValidationError('Spline FK 起点朝向约束不唯一')
    targets = c.orientConstraint(
        constraints[0], query=True, targetList=True) or []
    sources = (c.ls(targets[0], long=True) or []
               if len(targets) == 1 else [])
    if len(sources) != 1:
        raise FitSkeletonValidationError('Spline FK 起点接收层不唯一')
    source_leaf = plan.body_joints[0].rsplit('|',1)[-1].rsplit(':',1)[-1]
    proxy_name = 'AdvPy_'+source_leaf+'_InbetweenFKX'
    proxy = c.ls(proxy_name, long=True, type='joint') or []
    owned_proxy = (sources == proxy
                   and len(proxy) == 1
                   and c.objExists(proxy_name + '.advPyInbetweenFkOwner')
                   and c.getAttr(proxy_name + '.advPyInbetweenFkOwner')
                   == 'adv_py.inbetween_fk.v1')
    if not (sources[0] == plan.fk_controls[0]
            or sources[0].startswith(plan.fk_controls[0] + '|')
            or owned_proxy):
        raise FitSkeletonValidationError('Spline FK 起点接收层不属于 Base FK 控制')
    return sources[0]


def prepare(host,plan):
    host._require_transaction();host._transaction_changed=True
    c=host._cmds
    c.createNode('transform',name='AdvPy_SplineMechanisms',parent=plan.root_path.rsplit('|',1)[0],skipSelect=True)
    c.addAttr(plan.root_path,longName='advPySplineOwner',dataType='string')
    c.setAttr(plan.root_path+'.advPySplineOwner',
              current_spline_owner(plan.curved, plan.even_stretch_graph,
                                   plan.twist_ramp_graph,
                                   plan.mid_follow_graph,
                                   plan.isolated_mid_follow_graph),
              type='string',lock=True)
    for joint in plan.joints:host.create_body_arm_mechanism_joint(joint)
    last=plan.joints[len(plan.body_joints)-1]
    host._spine_frame('AdvPy_SplineChestSpace',plan.chest_space.rsplit('|',1)[0],last.world_position,last.world_axes)


def create(host,plan):
    host._require_transaction();host._transaction_changed=True
    c=host._cmds;n=len(plan.body_joints);fk=plan.joints[:n];ik=plan.joints[n:]
    for control,joint in zip(plan.fk_controls,fk):
        c.connectAttr(control+'.scale',joint.path+'.scale')
    if plan.source_hybrid_graph:
        maya_source_spline_hybrid.create(host,plan)
    if plan.isolated_mid_follow_graph:
        follow_parent=c.createNode('transform',name='AdvPy_SplineIKFollowMain',
                                   parent=plan.pelvis_control,skipSelect=True)
        c.setAttr(follow_parent+'.inheritsTransform',False,lock=True)
        for kind in ('translate','rotate','scale','shear'):
            for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')):
                c.setAttr(follow_parent+'.'+kind+axis,lock=True,keyable=False)
    for i,(target,position) in enumerate(zip(plan.targets,plan.positions)):
        offset=plan.offset_targets[i]
        parent=plan.target_parent(i)
        control_axes = plan.source_control_axes[i] if plan.source_control_axes else plan.axes
        host._spine_frame(f'AdvPy_SplineIK{i}Offset',parent,position,
                          control_axes if plan.source_ik_local else plan.axes)
        extra = plan.extra_targets[i] if plan.extra_targets else None
        if extra:
            host._create_body_extra_layer(
                offset, extra.rsplit('|', 1)[-1], extra)
        create_adv_icon(c,name=f'AdvPy_SplineIK{i}',parent=extra or offset,
                        template='IK_icon',radius=1.5,
                        fallback_normal=(1.,0.,0.))
        if extra and plan.extra_curve:
            host._add_body_extra_curve(extra, target)
        if plan.sub_targets:
            sub = plan.sub_targets[i]
            host._create_body_sub_control(
                target, sub.rsplit('|', 1)[-1], sub)
        if plan.source_control_axes and not plan.source_ik_local:
            frame = host._spine_frame(f'AdvPy_SplineIK{i}ShapeOrient',plan.root_path,
                                       (0.,0.,0.),control_axes)
            try:
                rotation = c.xform(frame,query=True,worldSpace=True,rotation=True)
                c.rotate(*rotation,target+'.cv[*]',absolute=True,worldSpace=True)
            finally:
                c.delete(frame)
        if plan.source_curve_points:
            proxy=c.createNode('transform',name=f'AdvPy_SplineIK{i}X',
                               parent=plan.driver_targets[i],skipSelect=True)
            c.parentConstraint(plan.driver_targets[i],proxy,maintainOffset=False,
                               name=f'AdvPy_SplineIK{i}XParent')
        locked=(['translate'+a for a in 'XYZ'] if i==0 else [])+(
            ['rotate'+a for a in 'XYZ']
            if 0<i<len(plan.targets)-1 and not plan.twist_ramp_graph else [])
        for attr in locked:c.setAttr(target+'.'+attr,lock=True,keyable=False)
        orientation=(plan.joints[n-1].world_axes
                     if i==len(plan.targets)-1 else plan.joints[0].world_axes)
        local=host._spine_frame(f'AdvPy_SplineIKLocalOrient{i}',
                                plan.driver_targets[i],
                                position,orientation)
        c.addAttr(local,longName='advPySplineIKLocalBind',dataType='string')
        c.setAttr(local+'.advPySplineIKLocalBind',
                  json.dumps(tuple(c.getAttr(local+'.matrix'))),
                  type='string',lock=True)
        for kind in ('translate','rotate','scale','shear'):
            for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')):
                c.setAttr(local+'.'+kind+axis,lock=True,keyable=False)
    if n>2:
        end_up=host._spine_frame('AdvPy_SplineIKEndLocalStartOrient',plan.driver_targets[-1],
                                 plan.positions[-1],plan.joints[0].world_axes)
        c.addAttr(end_up,longName='advPySplineEndUpBind',dataType='string')
        c.setAttr(end_up+'.advPySplineEndUpBind',
                  json.dumps(tuple(c.getAttr(end_up+'.matrix'))),
                  type='string',lock=True)
        for kind in ('translate','rotate','scale','shear'):
            for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')):
                c.setAttr(end_up+'.'+kind+axis,lock=True,keyable=False)
    for attribute,default,maximum,label in (
            ('spineIkFk',0.,1.,'脊柱 IK 权重'),
            ('stretchy',10.,10.,'脊柱伸展'),
            ('volume',10.,10.,'体积保持')):
        c.addAttr(plan.settings,longName=attribute,niceName=label,
                  attributeType='double',minValue=0.,maxValue=maximum,
                  defaultValue=default,keyable=True)
    if plan.source_hybrid_graph:
        maya_source_spline_hybrid.install_visibility(host,plan)
    curve=c.curve(name='AdvPy_SplineCurve',degree=plan.curve_degree,point=plan.curve_points)
    c.parent(curve,plan.root_path,relative=True)
    shapes=c.listRelatives(plan.curve,shapes=True,fullPath=True) or []
    if len(shapes)!=1:raise FitSkeletonValidationError('Spline 曲线必须只有一个形状节点')
    c.rename(shapes[0],'AdvPy_SplineCurveShape');shape=plan.curve+'|AdvPy_SplineCurveShape'
    if plan.source_curve_points:
        maya_source_spline_cv.create(host,plan,shape)
    for i,target in enumerate(() if plan.source_curve_points else plan.targets):
        matrix=f'AdvPy_SplineIK{i}Matrix';position=f'AdvPy_SplineIK{i}Position'
        c.createNode('multMatrix',name=matrix,skipSelect=True);c.createNode('decomposeMatrix',name=position,skipSelect=True)
        c.connectAttr(plan.driver_targets[i]+'.worldMatrix[0]',matrix+'.matrixIn[0]')
        c.connectAttr(plan.curve+'.worldInverseMatrix[0]',matrix+'.matrixIn[1]')
        c.connectAttr(matrix+'.matrixSum',position+'.inputMatrix')
        c.connectAttr(position+'.outputTranslate',shape+f'.controlPoints[{i}]')
    c.pointConstraint(_fk_root_source(host, plan),fk[0].path,
                      maintainOffset=False,name='AdvPy_SplineFKRootPoint')
    c.pointConstraint(plan.driver_targets[0],ik[0].path,maintainOffset=False,name='AdvPy_SplineIKRootPoint')
    handle,effector=c.ikHandle(name='AdvPy_SplineIKHandle',startJoint=ik[0].path,endEffector=ik[-1].path,
        solver='ikSplineSolver',curve=plan.curve,createCurve=False,parentCurve=False)
    c.rename(effector,'AdvPy_SplineIKEffector');c.parent(handle,plan.root_path)
    for attr,value in (('dTwistControlEnable',True),('dWorldUpType',3 if n==2 else 4),
                       ('dForwardAxis',0),('dWorldUpAxis',0)):
        c.setAttr('AdvPy_SplineIKHandle.'+attr,value)
    for attr in ('dWorldUpVector','dWorldUpVectorEnd'):c.setAttr('AdvPy_SplineIKHandle.'+attr,0.,1.,0.,type='double3')
    c.connectAttr(plan.driver_targets[0]+'|AdvPy_SplineIKLocalOrient0.worldMatrix[0]',
                  'AdvPy_SplineIKHandle.dWorldUpMatrix')
    if n>2:
        c.connectAttr(end_up+'.worldMatrix[0]',
                      'AdvPy_SplineIKHandle.dWorldUpMatrixEnd')
    c.addAttr(plan.settings,longName='noFlipAxis',attributeType='enum',
              enumName='180turn:180bend:180side:',defaultValue=0,keyable=False)
    c.createNode('setRange',name='AdvPy_SplineFlipUpAxis',skipSelect=True)
    for plug,value in (('minX',3),('maxX',0),('oldMinX',1),('oldMaxX',2)):
        c.setAttr('AdvPy_SplineFlipUpAxis.'+plug,value)
    c.connectAttr(plan.settings+'.noFlipAxis','AdvPy_SplineFlipUpAxis.valueX')
    c.connectAttr('AdvPy_SplineFlipUpAxis.outValueX',
                  'AdvPy_SplineIKHandle.dWorldUpAxis')
    c.createNode('setRange',name='AdvPy_SplineFlipVector',skipSelect=True)
    for axis,minimum,maximum in (('X',0,0),('Y',0,1),('Z',1,0)):
        c.setAttr('AdvPy_SplineFlipVector.min'+axis,minimum)
        c.setAttr('AdvPy_SplineFlipVector.max'+axis,maximum)
        c.setAttr('AdvPy_SplineFlipVector.oldMin'+axis,1)
        c.setAttr('AdvPy_SplineFlipVector.oldMax'+axis,2)
        c.connectAttr(plan.settings+'.noFlipAxis',
                      'AdvPy_SplineFlipVector.value'+axis)
        for suffix in ('','End'):
            c.connectAttr('AdvPy_SplineFlipVector.outValue'+axis,
                          'AdvPy_SplineIKHandle.dWorldUpVector'+suffix+axis)
    if plan.twist_ramp_graph:
        maya_spline_twist.create(host, plan)
    if plan.mid_follow_graph:
        maya_spline_follow.create(host, plan)
    c.orientConstraint(plan.driver_targets[-1],ik[-1].path,maintainOffset=True,name='AdvPy_SplineChestOrient')
    c.createNode('curveInfo',name='AdvPy_SplineArc',skipSelect=True)
    c.connectAttr(shape+'.local','AdvPy_SplineArc.inputCurve')
    c.createNode('multiplyDivide',name='AdvPy_SplineRatio',skipSelect=True)
    rest_arc=c.getAttr('AdvPy_SplineArc.arcLength') if plan.curved else sum(plan.lengths)
    if plan.curved:
        c.addAttr(plan.root_path,longName='advPySplineRestArc',attributeType='double')
        c.setAttr(plan.root_path+'.advPySplineRestArc',rest_arc,lock=True)
    c.setAttr('AdvPy_SplineRatio.operation',2);c.setAttr('AdvPy_SplineRatio.input2X',rest_arc)
    c.connectAttr('AdvPy_SplineArc.arcLength','AdvPy_SplineRatio.input1X')
    c.createNode('blendColors',name='AdvPy_SplineStretchBlend',skipSelect=True)
    c.connectAttr('AdvPy_SplineRatio.outputX','AdvPy_SplineStretchBlend.color1R');c.setAttr('AdvPy_SplineStretchBlend.color2R',1.)
    for attribute,node in (('stretchy','AdvPy_SplineStretchUnit'),
                           ('volume','AdvPy_SplineVolumeUnit')):
        c.createNode('unitConversion',name=node,skipSelect=True)
        c.setAttr(node+'.conversionFactor',.1)
        c.connectAttr(plan.settings+'.'+attribute,node+'.input')
    c.connectAttr('AdvPy_SplineStretchUnit.output',
                  'AdvPy_SplineStretchBlend.blender')
    c.createNode('clamp',name='AdvPy_SplineClamp',skipSelect=True)
    c.setAttr('AdvPy_SplineClamp.minR',.001);c.setAttr('AdvPy_SplineClamp.maxR',1000.)
    c.connectAttr('AdvPy_SplineStretchBlend.outputR','AdvPy_SplineClamp.inputR')
    c.createNode('multiplyDivide',name='AdvPy_SplineVolumeExponent',skipSelect=True)
    c.connectAttr('AdvPy_SplineVolumeUnit.output','AdvPy_SplineVolumeExponent.input1X')
    c.connectAttr('AdvPy_SplineStretchUnit.output','AdvPy_SplineVolumeExponent.input2X')
    c.createNode('clamp',name='AdvPy_SplineVolumeRatioClamp',skipSelect=True)
    c.setAttr('AdvPy_SplineVolumeRatioClamp.minR',.001);c.setAttr('AdvPy_SplineVolumeRatioClamp.maxR',1000.)
    c.connectAttr('AdvPy_SplineRatio.outputX','AdvPy_SplineVolumeRatioClamp.inputR')
    c.createNode('multiplyDivide',name='AdvPy_SplineVolume',skipSelect=True);c.setAttr('AdvPy_SplineVolume.operation',3)
    c.connectAttr('AdvPy_SplineVolumeRatioClamp.outputR','AdvPy_SplineVolume.input1X')
    c.setAttr('AdvPy_SplineVolume.input2X',-.5)
    c.createNode('blendTwoAttr',name='AdvPy_SplineVolumeBlend',skipSelect=True)
    c.setAttr('AdvPy_SplineVolumeBlend.input[0]',1.)
    c.connectAttr('AdvPy_SplineVolume.outputX','AdvPy_SplineVolumeBlend.input[1]')
    c.connectAttr('AdvPy_SplineVolumeExponent.outputX','AdvPy_SplineVolumeBlend.attributesBlender')
    c.createNode('addDoubleLinear',name='AdvPy_SplineVolumeDelta',skipSelect=True)
    c.connectAttr('AdvPy_SplineVolumeBlend.output','AdvPy_SplineVolumeDelta.input1')
    c.setAttr('AdvPy_SplineVolumeDelta.input2',-1.)
    for i,joint in enumerate(ik):
        blend=f'AdvPy_SplineIKScaleBlend{i}'
        relative=f'AdvPy_SplineIKScaleRelative{i}'
        decompose=f'AdvPy_SplineIKScaleDecompose{i}'
        volume=f'AdvPy_SplineIKScaleVolume{i}'
        c.createNode('blendMatrix',name=blend,skipSelect=True)
        c.createNode('multMatrix',name=relative,skipSelect=True)
        c.createNode('decomposeMatrix',name=decompose,skipSelect=True)
        c.createNode('multiplyDivide',name=volume,skipSelect=True)
        c.connectAttr(plan.scale_reference+'.worldMatrix[0]',blend+'.inputMatrix')
        for index,weight in enumerate(spline_ik_scale_weights(i,n,len(plan.targets))):
            if weight:
                c.connectAttr(plan.driver_targets[index]+f'|AdvPy_SplineIKLocalOrient{index}.worldMatrix[0]',blend+f'.target[{index}].targetMatrix')
                c.setAttr(blend+f'.target[{index}].weight',weight)
        c.connectAttr(blend+'.outputMatrix',relative+'.matrixIn[0]')
        c.connectAttr(plan.scale_reference+'.worldInverseMatrix[0]',relative+'.matrixIn[1]')
        c.connectAttr(relative+'.matrixSum',decompose+'.inputMatrix')
        c.connectAttr(decompose+'.outputScale',volume+'.input1')
        if 0<i<n-1:
            weight=f'AdvPy_SplineIKScaleWeight{i}'
            addition=f'AdvPy_SplineIKScaleAdd{i}'
            c.createNode('multiplyDivide',name=weight,skipSelect=True)
            c.createNode('addDoubleLinear',name=addition,skipSelect=True)
            fraction=2.0*(i+1)/(n+1)
            c.setAttr(weight+'.input2X',min(fraction,2.0-fraction))
            c.connectAttr('AdvPy_SplineVolumeDelta.output',weight+'.input1X')
            c.connectAttr(weight+'.outputX',addition+'.input1')
            c.setAttr(addition+'.input2',1.)
            for axis in 'XYZ':c.connectAttr(addition+'.output',volume+'.input2'+axis)
        for axis in 'XYZ':c.connectAttr(volume+'.output'+axis,joint.path+'.scale'+axis)
        if i:
            c.connectAttr(ik[i-1].path+'.scale',joint.path+'.inverseScale',force=True)
            c.createNode('multiplyDivide',name=f'AdvPy_SplineLength{i}',skipSelect=True)
            c.setAttr(f'AdvPy_SplineLength{i}.input1X',plan.lengths[i-1]);c.connectAttr('AdvPy_SplineClamp.outputR',f'AdvPy_SplineLength{i}.input2X')
            c.connectAttr(f'AdvPy_SplineLength{i}.outputX',joint.path+'.translateX')
    if plan.even_stretch_graph:
        maya_spline_even.create(host, plan, shape, ik)
    if plan.curved:
        import json
        for i in range(1,n):
            rest=c.createNode('transform',name=f'AdvPy_SplineIKRest{i}',
                              parent=plan.ik_outputs[i].rsplit('|',1)[0],
                              skipSelect=True)
            bind=c.xform(plan.body_joints[i],q=True,ws=True,matrix=True)
            c.xform(rest,ws=True,matrix=bind)
            local=tuple(c.getAttr(rest+'.matrix'))
            c.addAttr(rest,longName='advPySplineRestLocal',dataType='string')
            c.setAttr(rest+'.advPySplineRestLocal',json.dumps(local),type='string',lock=True)
            for kind in ('translate','rotate','scale','shear'):
                for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')):
                    c.setAttr(rest+'.'+kind+axis,lock=True,keyable=False)
    c.createNode('reverse',name='AdvPy_SplineReverse',skipSelect=True);c.connectAttr(plan.settings+'.spineIkFk','AdvPy_SplineReverse.inputX')
    for i in range(1,n):
        for label,command in (('Point',c.pointConstraint),('Orient',c.orientConstraint),('Scale',c.scaleConstraint)):
            node=command(fk[i].path,plan.ik_outputs[i],plan.body_joints[i],name=f'AdvPy_Spline{label}{i}',maintainOffset=False)[0]
            aliases=command(node,q=True,weightAliasList=True)
            c.connectAttr('AdvPy_SplineReverse.outputX',node+'.'+aliases[0]);c.connectAttr(plan.settings+'.spineIkFk',node+'.'+aliases[1])
            if label=='Orient':c.setAttr(node+'.interpType',2)
            if label=='Scale':
                c.connectAttr(plan.body_joints[i-1]+'.scale',plan.body_joints[i]+'.inverseScale',force=True)
                plug=node+'.constraintParentInverseMatrix'
                source=c.connectionInfo(plug,sourceFromDestination=True)
                if source:c.disconnectAttr(source,plug)
                c.setAttr(plug,1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type='matrix',lock=True)
                c.setAttr(node+'.constraintScaleCompensate',False,lock=True)
                for target_index,source_joint in enumerate((fk[i].path,plan.ik_outputs[i])):
                    world=f'AdvPy_Spline{("FK" if target_index==0 else "IK")}WorldScale{i}'
                    c.createNode('decomposeMatrix',name=world,skipSelect=True)
                    c.connectAttr(source_joint+'.worldMatrix[0]',world+'.inputMatrix')
                    c.connectAttr(world+'.outputScale',node+f'.target[{target_index}].targetScale',force=True)
                    target_parent=node+f'.target[{target_index}].targetParentMatrix'
                    source=c.connectionInfo(target_parent,sourceFromDestination=True)
                    if source:c.disconnectAttr(source,target_parent)
                    c.setAttr(target_parent,1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type='matrix',lock=True)
                    weight='AdvPy_SplineReverse.outputX' if target_index==0 else plan.settings+'.spineIkFk'
                    c.connectAttr(weight,node+f'.target[{target_index}].targetWeight',force=True)
    maya_chest_space.create(host, plan.body_joints[-1], plan.chest_space,
                           'AdvPy_SplineChestSpaceParent',
                           plan.use_offset_parent_matrix)
    c.setAttr(plan.root_path+'.visibility',False)
    audit(host,plan,source_visibility_ready=False)


def audit(host,plan,*,source_visibility_ready=True):
    c=host._cmds;n=len(plan.body_joints)
    fk=plan.joints[:n];ik=plan.joints[n:]
    maya_chest_space.audit(host, plan.body_joints[-1], plan.chest_space,
                          'AdvPy_SplineChestSpaceParent',
                          plan.use_offset_parent_matrix)
    version=spline_owner_version(c.getAttr(plan.root_path+'.advPySplineOwner'))
    if (version>=3 and bool(version%2))!=plan.curved:
        raise FitSkeletonValidationError('Spline 曲线拓扑与求解图版本不一致')
    if (version>=20)!=plan.even_stretch_graph:
        raise FitSkeletonValidationError('Spline stretchEven 计划与求解图版本不一致')
    if (version>=22)!=plan.twist_ramp_graph:
        raise FitSkeletonValidationError('Spline 中间扭转计划与求解图版本不一致')
    if (version>=24)!=plan.mid_follow_graph:
        raise FitSkeletonValidationError('Spline 中间跟随计划与求解图版本不一致')
    if (version>=26)!=plan.isolated_mid_follow_graph:
        raise FitSkeletonValidationError('Spline 独立跟随层计划与求解图版本不一致')
    new_scaling=version>=4
    oriented_scaling=version>=6
    original_range=version>=8
    terminal_without_volume=version>=10
    original_volume_graph=version>=12
    single_segment_twist=version>=18 and n==2
    end_local_start=version>=14 and not single_segment_twist
    flip_axis_graph=version>=16
    missing=tuple(name for name in plan.node_names
                  if not (version==1 and 'WorldScale' in name)
                  and not (not new_scaling and (name.startswith('AdvPy_SplineIKScale')
                                                or name=='AdvPy_SplineVolumeDelta'))
                  and not (not oriented_scaling and name.startswith('AdvPy_SplineIKLocalOrient'))
                  and not (not original_range and name in (
                      'AdvPy_SplineStretchUnit','AdvPy_SplineVolumeUnit'))
                  and not (not original_volume_graph and name in (
                      'AdvPy_SplineVolumeRatioClamp','AdvPy_SplineVolumeBlend'))
                  and not (not end_local_start and name=='AdvPy_SplineIKEndLocalStartOrient')
                  and not (not flip_axis_graph and name in (
                      'AdvPy_SplineFlipUpAxis','AdvPy_SplineFlipVector'))
                  and not (terminal_without_volume and name in (
                      f'AdvPy_SplineIKScaleWeight{n-1}',
                      f'AdvPy_SplineIKScaleAdd{n-1}'))
                  and len(c.ls(name,long=True) or [])!=1)
    if missing:raise FitSkeletonValidationError('Spline 节点缺失或名称不唯一：'+repr(missing))
    for index, target in enumerate(plan.targets):
        extra = plan.extra_targets[index] if plan.extra_targets else None
        if extra:
            issues = audit_body_extra_controller(
                plan.offset_targets[index], target, extra,
                host._capture_body_extra_layer(extra, target),
                extra_curve=plan.extra_curve)
            if issues:
                raise FitSkeletonValidationError(
                    'Spline IK Extra 层复检失败：'+'；'.join(issues))
        sub = plan.sub_targets[index] if plan.sub_targets else None
        issues = audit_body_sub_controller(
            target, sub, host._capture_body_ik_sub_control(target, sub))
        if issues:
            raise FitSkeletonValidationError(
                'Spline IK Sub 层复检失败：'+'；'.join(issues))
        expected_parent = extra or plan.offset_targets[index]
        if (c.listRelatives(target, parent=True, fullPath=True) or []) != [expected_parent]:
            raise FitSkeletonValidationError('Spline IK 主控父层改变')
    for name, command, source in (
            ('AdvPy_SplineFKRootPoint', c.pointConstraint,
             _fk_root_source(host, plan)),
            ('AdvPy_SplineIKRootPoint', c.pointConstraint,
             plan.driver_targets[0]),
            ('AdvPy_SplineChestOrient', c.orientConstraint,
             plan.driver_targets[-1])):
        actual = tuple(host._resolve_connected_node(node)
                       for node in command(name, query=True,
                                           targetList=True) or [])
        if actual != (source,):
            raise FitSkeletonValidationError('Spline IK 端点约束来源改变：'+name)
    for name, joint in (('AdvPy_SplineFKRootPoint', fk[0].path),
                        ('AdvPy_SplineIKRootPoint', ik[0].path)):
        for axis in 'XYZ':
            if not c.isConnected(
                    name + '.constraintTranslate' + axis,
                    joint + '.translate' + axis):
                raise FitSkeletonValidationError(
                    'Spline 根关节位置约束输出改变：' + name)
    if c.ikHandle('AdvPy_SplineIKHandle',q=True,solver=True)!='ikSplineSolver':raise FitSkeletonValidationError('Spline 求解器被替换')
    shape=plan.curve+'|AdvPy_SplineCurveShape'
    edges=[(shape+'.worldSpace[0]','AdvPy_SplineIKHandle.inCurve'),(shape+'.local','AdvPy_SplineArc.inputCurve'),
        ('AdvPy_SplineArc.arcLength','AdvPy_SplineRatio.input1X'),('AdvPy_SplineRatio.outputX','AdvPy_SplineStretchBlend.color1R'),
        ('AdvPy_SplineStretchBlend.outputR','AdvPy_SplineClamp.inputR'),
        (plan.settings+'.spineIkFk','AdvPy_SplineReverse.inputX'),
        ]
    if end_local_start:
        edges += [(plan.driver_targets[0]+'|AdvPy_SplineIKLocalOrient0.worldMatrix[0]',
                   'AdvPy_SplineIKHandle.dWorldUpMatrix'),
                  (plan.driver_targets[-1]+'|AdvPy_SplineIKEndLocalStartOrient.worldMatrix[0]',
                   'AdvPy_SplineIKHandle.dWorldUpMatrixEnd')]
    elif single_segment_twist:
        edges.append((plan.driver_targets[0]+'|AdvPy_SplineIKLocalOrient0.worldMatrix[0]',
                      'AdvPy_SplineIKHandle.dWorldUpMatrix'))
    else:
        edges += [(plan.driver_targets[0]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrix'),
                  (plan.driver_targets[-1]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrixEnd')]
    if flip_axis_graph:
        edges += [(plan.settings+'.noFlipAxis','AdvPy_SplineFlipUpAxis.valueX'),
                  ('AdvPy_SplineFlipUpAxis.outValueX',
                   'AdvPy_SplineIKHandle.dWorldUpAxis')]
        for axis in 'XYZ':
            edges.append((plan.settings+'.noFlipAxis',
                          'AdvPy_SplineFlipVector.value'+axis))
            for suffix in ('','End'):
                edges.append(('AdvPy_SplineFlipVector.outValue'+axis,
                              'AdvPy_SplineIKHandle.dWorldUpVector'+suffix+axis))
    if plan.even_stretch_graph:
        maya_spline_even.audit(host, plan, shape, plan.joints[n:])
    if plan.twist_ramp_graph:
        maya_spline_twist.audit(host, plan)
    if plan.mid_follow_graph:
        maya_spline_follow.audit(host, plan)
    if original_range:
        edges += [(plan.settings+'.stretchy','AdvPy_SplineStretchUnit.input'),
                  ('AdvPy_SplineStretchUnit.output','AdvPy_SplineStretchBlend.blender'),
                  (plan.settings+'.volume','AdvPy_SplineVolumeUnit.input'),
                  ('AdvPy_SplineVolumeUnit.output','AdvPy_SplineVolumeExponent.input1X')]
    else:
        edges += [(plan.settings+'.stretch','AdvPy_SplineStretchBlend.blender'),
                  (plan.settings+'.volume','AdvPy_SplineVolumeExponent.input1X')]
    if original_volume_graph:
        edges += [('AdvPy_SplineStretchUnit.output','AdvPy_SplineVolumeExponent.input2X'),
                  ('AdvPy_SplineRatio.outputX','AdvPy_SplineVolumeRatioClamp.inputR'),
                  ('AdvPy_SplineVolumeRatioClamp.outputR','AdvPy_SplineVolume.input1X'),
                  ('AdvPy_SplineVolume.outputX','AdvPy_SplineVolumeBlend.input[1]'),
                  ('AdvPy_SplineVolumeExponent.outputX','AdvPy_SplineVolumeBlend.attributesBlender'),
                  ('AdvPy_SplineVolumeBlend.output','AdvPy_SplineVolumeDelta.input1')]
    else:
        edges += [('AdvPy_SplineVolumeExponent.outputX','AdvPy_SplineVolume.input2X'),
                  ('AdvPy_SplineClamp.outputR','AdvPy_SplineVolume.input1X')]
    if plan.source_curve_points:
        maya_source_spline_cv.audit(host,plan,shape)
        for index,target in enumerate(plan.source_matrix_targets):
            name=f'AdvPy_SplineIK{index}XParent'
            sources=tuple(host._resolve_connected_node(item) for item in
                          c.parentConstraint(name,query=True,targetList=True) or [])
            if sources!=(plan.driver_targets[index],):
                raise FitSkeletonValidationError('来源 Spline IK X 父约束来源改变')
            for kind in ('Translate','Rotate'):
                for axis in 'XYZ':
                    if not c.isConnected(name+'.constraint'+kind+axis,
                                         target+'.'+kind[0].lower()+kind[1:]+axis):
                        raise FitSkeletonValidationError('来源 Spline IK X 输出连接改变')
    if plan.source_hybrid_graph:
        maya_source_spline_hybrid.audit(host,plan,visibility_ready=source_visibility_ready)
    if plan.source_curve_points and source_visibility_ready:
        maya_source_spline_visibility.audit(host,plan)
    for i,target in enumerate(() if plan.source_curve_points else plan.targets):
        edges += [(plan.driver_targets[i]+'.worldMatrix[0]',f'AdvPy_SplineIK{i}Matrix.matrixIn[0]'),
            (plan.curve+'.worldInverseMatrix[0]',f'AdvPy_SplineIK{i}Matrix.matrixIn[1]'),
            (f'AdvPy_SplineIK{i}Matrix.matrixSum',f'AdvPy_SplineIK{i}Position.inputMatrix'),
            (f'AdvPy_SplineIK{i}Position.outputTranslate',shape+f'.controlPoints[{i}]')]
    for index, (control, joint) in enumerate(zip(plan.fk_controls, plan.joints[:n])):
        matching = index > 0 and all(c.attributeQuery('matchScale' + axis,
                     node=control, exists=True) for axis in 'XYZ')
        if matching:
            edges.extend((control + '.matchScale' + axis, joint.path + '.scale' + axis)
                         for axis in 'XYZ')
            point = f'AdvPy_SplineFKMatchPoint{index}'
            if not c.objExists(point) or c.nodeType(point) != 'pointConstraint':
                raise FitSkeletonValidationError('Spline 匹配缩放缺少位置驱动')
        else:
            edges.append((control + '.scale', joint.path + '.scale'))
    for i,joint in enumerate(plan.joints[n:]):
        if new_scaling:
            blend=f'AdvPy_SplineIKScaleBlend{i}'
            relative=f'AdvPy_SplineIKScaleRelative{i}'
            decompose=f'AdvPy_SplineIKScaleDecompose{i}'
            volume=f'AdvPy_SplineIKScaleVolume{i}'
            scale_frame=(plan.scale_reference if oriented_scaling
                         else plan.pelvis_control)
            edges += [(scale_frame+'.worldMatrix[0]',blend+'.inputMatrix'),
                      (blend+'.outputMatrix',relative+'.matrixIn[0]'),
                      (scale_frame+'.worldInverseMatrix[0]',relative+'.matrixIn[1]'),
                      (relative+'.matrixSum',decompose+'.inputMatrix'),
                      (decompose+'.outputScale',volume+'.input1')]
            edges += [(volume+'.output'+axis,joint.path+'.scale'+axis)
                      for axis in 'XYZ']
            for index,weight in enumerate(spline_ik_scale_weights(i,n,len(plan.targets))):
                if weight:
                    orientation=(f'|AdvPy_SplineIKLocalOrient{index}'
                                 if oriented_scaling else '')
                    edges.append((plan.driver_targets[index]+orientation+'.worldMatrix[0]',
                                  blend+f'.target[{index}].targetMatrix'))
            if i and not (terminal_without_volume and i==n-1):
                weight=f'AdvPy_SplineIKScaleWeight{i}'
                addition=f'AdvPy_SplineIKScaleAdd{i}'
                edges += [('AdvPy_SplineVolumeDelta.output',weight+'.input1X'),
                          (weight+'.outputX',addition+'.input1')]
                edges += [(addition+'.output',volume+'.input2'+axis)
                          for axis in 'XYZ']
        else:
            edges += [('AdvPy_SplineVolume.outputX',joint.path+'.scale'+axis)
                      for axis in 'YZ']
        if i:edges += [('AdvPy_SplineClamp.outputR',f'AdvPy_SplineLength{i}.input2X'),
            (f'AdvPy_SplineLength{i}.outputX',joint.path+'.translateX'),(plan.joints[n+i-1].path+'.scale',joint.path+'.inverseScale')]
    if new_scaling:
        if not original_volume_graph:
            edges.append(('AdvPy_SplineVolume.outputX',
                          'AdvPy_SplineVolumeDelta.input1'))
    bad=[(a,b) for a,b in edges if not c.isConnected(a,b)]
    if bad:raise FitSkeletonValidationError('Spline 曲线或伸展连接被替换：'+repr(bad[:2]))
    if new_scaling and any(
            c.getAttr(target+'.scale'+axis,lock=True)
            or not c.getAttr(target+'.scale'+axis,keyable=True)
            for target in plan.targets for axis in 'XYZ'):
        raise FitSkeletonValidationError('Spline IK 缩放控制通道不可动画')
    if oriented_scaling:
        for i,target in enumerate(plan.targets):
            local=plan.driver_targets[i]+f'|AdvPy_SplineIKLocalOrient{i}'
            if (c.nodeType(local)!='transform'
                    or (c.listRelatives(local,parent=True,fullPath=True) or [])!=[plan.driver_targets[i]]
                    or not c.getAttr(local+'.advPySplineIKLocalBind',lock=True)):
                raise FitSkeletonValidationError('Spline IK 局部朝向层身份无效')
            recorded=json.loads(c.getAttr(local+'.advPySplineIKLocalBind'))
            actual=tuple(c.getAttr(local+'.matrix'))
            if (len(recorded)!=16
                    or any(abs(a-b)>1e-8 for a,b in zip(recorded,actual))
                    or any(not c.getAttr(local+'.'+kind+axis,lock=True)
                           for kind in ('translate','rotate','scale','shear')
                           for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')))):
                raise FitSkeletonValidationError('Spline IK 局部朝向绑定矩阵被修改')
    if end_local_start:
        end_up=plan.driver_targets[-1]+'|AdvPy_SplineIKEndLocalStartOrient'
        if (not c.objExists(end_up) or c.nodeType(end_up)!='transform'
                or (c.listRelatives(end_up,parent=True,fullPath=True) or [])!=[plan.driver_targets[-1]]
                or not c.getAttr(end_up+'.advPySplineEndUpBind',lock=True)):
            raise FitSkeletonValidationError('Spline 末端起点朝向层身份无效')
        recorded=json.loads(c.getAttr(end_up+'.advPySplineEndUpBind'))
        actual=tuple(c.getAttr(end_up+'.matrix'))
        if (len(recorded)!=16
                or any(abs(a-b)>1e-8 for a,b in zip(recorded,actual))
                or any(not c.getAttr(end_up+'.'+kind+axis,lock=True)
                       for kind in ('translate','rotate','scale','shear')
                       for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')))):
            raise FitSkeletonValidationError('Spline 末端起点朝向绑定矩阵被修改')
    if plan.curved and (not c.attributeQuery('advPySplineRestArc',node=plan.root_path,exists=True)
                        or not c.getAttr(plan.root_path+'.advPySplineRestArc',lock=True)):
        raise FitSkeletonValidationError('Spline 绑定曲线长度标记缺失或可写')
    rest_arc=c.getAttr(plan.root_path+'.advPySplineRestArc') if plan.curved else sum(plan.lengths)
    if rest_arc<=0:raise FitSkeletonValidationError('Spline 绑定曲线长度无效')
    constants={'AdvPy_SplineRatio.operation':2,'AdvPy_SplineRatio.input2X':rest_arc,
        'AdvPy_SplineStretchBlend.color2R':1.,'AdvPy_SplineClamp.minR':.001,'AdvPy_SplineClamp.maxR':1000.,
        'AdvPy_SplineVolumeExponent.operation':1,'AdvPy_SplineVolume.operation':3,
        'AdvPy_SplineIKHandle.dTwistControlEnable':1,
        'AdvPy_SplineIKHandle.dWorldUpType':3 if single_segment_twist else 4,
        'AdvPy_SplineIKHandle.dForwardAxis':0}
    if flip_axis_graph:
        if (not c.attributeQuery('noFlipAxis',node=plan.settings,exists=True)
                or c.getAttr(plan.settings+'.noFlipAxis',type=True)!='enum'):
            raise FitSkeletonValidationError('Spline noFlipAxis 控制属性缺失')
        constants.update({'AdvPy_SplineFlipUpAxis.minX':3,
                          'AdvPy_SplineFlipUpAxis.maxX':0,
                          'AdvPy_SplineFlipUpAxis.oldMinX':1,
                          'AdvPy_SplineFlipUpAxis.oldMaxX':2})
        for axis,minimum,maximum in (('X',0,0),('Y',0,1),('Z',1,0)):
            constants['AdvPy_SplineFlipVector.min'+axis]=minimum
            constants['AdvPy_SplineFlipVector.max'+axis]=maximum
            constants['AdvPy_SplineFlipVector.oldMin'+axis]=1
            constants['AdvPy_SplineFlipVector.oldMax'+axis]=2
    else:
        constants['AdvPy_SplineIKHandle.dWorldUpAxis']=0
    if original_range:
        constants['AdvPy_SplineStretchUnit.conversionFactor']=.1
        constants['AdvPy_SplineVolumeUnit.conversionFactor']=.1
    if original_volume_graph:
        constants.update({'AdvPy_SplineVolumeRatioClamp.minR':.001,
                          'AdvPy_SplineVolumeRatioClamp.maxR':1000.,
                          'AdvPy_SplineVolume.input2X':-.5,
                          'AdvPy_SplineVolumeBlend.input[0]':1.})
    else:
        constants['AdvPy_SplineVolumeExponent.input2X']=-.5
    if new_scaling:
        constants['AdvPy_SplineVolumeDelta.input2']=-1.
        for i in range(n):
            blend=f'AdvPy_SplineIKScaleBlend{i}'
            volume=f'AdvPy_SplineIKScaleVolume{i}'
            constants[volume+'.operation']=1
            for index,weight in enumerate(spline_ik_scale_weights(i,n,len(plan.targets))):
                if weight:
                    constants[blend+f'.target[{index}].weight']=weight
            if i and not (terminal_without_volume and i==n-1):
                fraction=2.0*(i+1)/(n+1)
                constants[f'AdvPy_SplineIKScaleWeight{i}.input2X']=min(fraction,2.0-fraction)
                constants[f'AdvPy_SplineIKScaleAdd{i}.input2']=1.
            else:
                for axis in 'XYZ':constants[volume+'.input2'+axis]=1.
    if n==2 and not single_segment_twist:
        constants.pop('AdvPy_SplineIKHandle.dTwistControlEnable')
    constants.update({f'AdvPy_SplineLength{i}.input1X':length for i,length in enumerate(plan.lengths,1)})
    changed=[(plug,c.getAttr(plug),value) for plug,value in constants.items() if abs(c.getAttr(plug)-value)>1e-6*max(1.,abs(value))]
    if changed:raise FitSkeletonValidationError('Spline 求解常量被修改：'+repr(changed[:3]))
    if version>=2:
        identity=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        for i in range(1,n):
            node=f'AdvPy_SplineScale{i}'
            plug=node+'.constraintParentInverseMatrix'
            if (not c.isConnected(plan.body_joints[i-1]+'.scale',plan.body_joints[i]+'.inverseScale')
                    or c.listConnections(plug,s=True,d=False) or tuple(c.getAttr(plug))!=identity
                    or c.getAttr(node+'.constraintScaleCompensate')):
                raise FitSkeletonValidationError('Spline 世界缩放补偿连接或常量被修改')
            for target_index,source_joint in enumerate((plan.joints[i].path,plan.ik_outputs[i])):
                world=f'AdvPy_Spline{("FK" if target_index==0 else "IK")}WorldScale{i}'
                target_parent=node+f'.target[{target_index}].targetParentMatrix'
                if (not c.isConnected(source_joint+'.worldMatrix[0]',world+'.inputMatrix')
                        or not c.isConnected(world+'.outputScale',node+f'.target[{target_index}].targetScale')
                        or c.listConnections(target_parent,s=True,d=False) or tuple(c.getAttr(target_parent))!=identity):
                    raise FitSkeletonValidationError('Spline 世界缩放读取网络被修改')
    for i in range(1,n):
        bendy_handoff = host.validate_body_bendy_handoff(plan.body_joints[i])
        for label,command,kind in (('Point',c.pointConstraint,'translate'),('Orient',c.orientConstraint,'rotate'),('Scale',c.scaleConstraint,'scale')):
            node=f'AdvPy_Spline{label}{i}'
            if label!='Scale' or version==1:
                sources=tuple(host._resolve_connected_node(p) for p in command(node,q=True,targetList=True))
                if sources!=(plan.joints[i].path,plan.ik_outputs[i]):raise FitSkeletonValidationError('Spline FK/IK 输出目标被替换')
            aliases=("target[0].targetWeight","target[1].targetWeight") if label=="Scale" and version!=1 else command(node,q=True,weightAliasList=True)
            if not c.isConnected('AdvPy_SplineReverse.outputX',node+'.'+aliases[0]) or not c.isConnected(plan.settings+'.spineIkFk',node+'.'+aliases[1]):
                raise FitSkeletonValidationError('Spline 混合权重连接无效')
            for axis in 'XYZ':
                source = node + '.constraint' + kind.title() + axis
                destination = plan.body_joints[i] + '.' + kind + axis
                if c.isConnected(source, destination):
                    continue
                if bendy_handoff:
                    if label != 'Scale':
                        continue
                    mult = 'AdvPy_BendyDeformScale' + plan.body_joints[i].rsplit('|', 1)[-1]
                    if c.objExists(mult) and (c.isConnected(source, mult + '.input1' + axis)
                            or c.isConnected(node + '.constraintScale', mult + '.input1')):
                        continue
                raise FitSkeletonValidationError('Spline Body 输出被替换')
    if plan.curved:
        import json
        for i in range(1,n):
            rest=plan.ik_outputs[i]
            if (c.nodeType(rest)!='transform' or (c.listRelatives(rest,parent=True,fullPath=True) or [])!=[rest.rsplit('|',1)[0]]
                    or not c.getAttr(rest+'.advPySplineRestLocal',lock=True)):
                raise FitSkeletonValidationError('Spline 中性姿态补偿层归属无效')
            recorded=json.loads(c.getAttr(rest+'.advPySplineRestLocal'))
            if (len(recorded)!=16 or any(abs(a-b)>1e-8 for a,b in zip(recorded,c.getAttr(rest+'.matrix')))
                    or any(not c.getAttr(rest+'.'+kind+axis,lock=True) for kind in ('translate','rotate','scale','shear')
                           for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ')))):
                raise FitSkeletonValidationError('Spline 中性姿态补偿层被修改')
