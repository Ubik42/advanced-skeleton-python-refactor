"""Fit the native variable-control spline to a representable body pose."""
from math import pi,sqrt
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.body_spline import spline_owner_version
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.least_squares import least_squares


def match_ik(host, registration, before,*,_scoped=False):
    if registration.additional_spines:
        for plan in (registration.spine,)+registration.additional_spines:
            match_ik(host,replace(registration,spine=plan,additional_spines=()),before)
        return
    if getattr(registration.spine,'system_name','') and not _scoped:
        from .maya_spline_scope import spline_scope
        with spline_scope(host,registration.spine,localize=False):
            return match_ik(host,registration,before,_scoped=True)
    from .maya_spline_matching import enabled
    if not enabled(registration):
        raise CharacterRegistryError('先启用曲线脊柱动画匹配通道')
    c = host._cmds
    plan = registration.spine
    wanted = dict(before.body_frames)
    matrices = tuple(wanted[node.rsplit('|',1)[-1]] for node in plan.body_joints)
    root_matrix = host._spine_world_frame(plan.root_path)[0]
    scale = sqrt(sum(value*value for value in root_matrix[:3]))
    length = sum(plan.lengths)
    if scale<1e-8:raise CharacterRegistryError('曲线脊柱机制组缩放无效')
    ratios = tuple(sqrt(sum((a-b)**2 for a,b in zip(left[12:15],right[12:15])))/(rest*scale)
                   for left,right,rest in zip(matrices,matrices[1:],plan.lengths))
    scaled_pose = (max(ratios)-min(ratios)>1e-5 or
        any(abs(sqrt(sum(value*value for value in matrix[start:start+3]))-scale)>1e-5
            for matrix in matrices[1:] for start in (0,4,8)))
    parameters = []
    for index,control in enumerate(plan.driver_targets):
        if index or plan.source_first_translate:
            parameters.extend((control+'.translate'+axis,length,None,None) for axis in 'XYZ')
        if index in (0,len(plan.targets)-1) or plan.twist_ramp_graph:
            parameters.extend((control+'.rotate'+axis,180./pi,None,None) for axis in 'XYZ')
        if index and scaled_pose:
            for axis in 'XYZ':
                plug = control+'.scale'+axis
                if not c.getAttr(plug, settable=True):
                    raise CharacterRegistryError(
                        '曲线 IK 缩放控制通道被占用：'+plug)
                parameters.append((plug,1.,.001,None))
        if 0<index<len(plan.targets)-1 and plan.mid_follow_graph:
            parameters.append((plan.targets[index]+'.followEnd',10.,0.,1.))
    try:
        original_range=spline_owner_version(c.getAttr(
            plan.root_path+'.advPySplineOwner'))>=8
    except FitSkeletonValidationError as exc:
        raise CharacterRegistryError('曲线脊柱求解图所有权无效') from exc
    settings_attributes = (('stretchy','volume') if original_range
                           else ('stretch','volume'))
    if plan.even_stretch_graph:
        settings_attributes += ('stretchEven',)
    parameters.extend((plan.settings+'.'+attribute,10. if original_range else 1.,0.,1.)
                      for attribute in settings_attributes)
    initial = tuple(c.getAttr(plug)/unit for plug,unit,_,_ in parameters)
    bounds = tuple((low,high) for _,_,low,high in parameters)
    c.setAttr(plan.settings+'.spineIkFk',1.)
    components = (0,1,2,4,5,6,8,9,10,12,13,14)
    def evaluate(values):
        for value,(plug,unit,_,_) in zip(values,parameters):c.setAttr(plug,value*unit)
        rows = []
        start=0 if plan.source_first_translate else 1
        for node,target in zip(plan.body_joints[start:],matrices[start:]):
            actual = host._spine_world_frame(node)[0]
            rows.extend((actual[index]-target[index])/(scale*(length if index>=12 else 1.)) for index in components)
        return tuple(rows)
    result = least_squares(evaluate,initial,bounds=bounds,tolerance=1e-7,max_iterations=70,step=1e-4)
    if not result.converged:
        # Advanced-twist evaluation is noisy immediately around zero angles.
        # Try exact neutral values, accepting them only against the same residual gate.
        from dataclasses import replace
        snapped=tuple(0. if abs(value)<1e-4 else value for value in result.parameters)
        residual=evaluate(snapped)
        if max(abs(value) for value in residual)<=1e-7:
            result=replace(result,parameters=snapped,residual=residual,converged=True,evaluations=result.evaluations+1)
        else:
            evaluate(result.parameters)
    if not result.converged:
        raise CharacterRegistryError('曲线 IK 拟合未达到无跳变要求，已撤销转换；最大归一化残差：'+str(max(abs(v) for v in result.residual))+f' frame={c.currentTime(q=True)} iterations={result.iterations} evaluations={result.evaluations}')
