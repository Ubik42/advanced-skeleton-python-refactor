"""Fit the native four-control spline to a representable body pose."""
from math import pi,sqrt

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.least_squares import least_squares


def match_ik(host, registration, before):
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
    # Native IK has a single longitudinal stretch ratio and no independent X scale.
    # Reject incompatible FK lengths before running an expensive numerical fit.
    ratios = tuple(sqrt(sum((a-b)**2 for a,b in zip(left[12:15],right[12:15])))/(rest*scale)
                   for left,right,rest in zip(matrices,matrices[1:],plan.lengths))
    if max(ratios)-min(ratios)>1e-5:
        raise CharacterRegistryError('当前 FK 骨段伸展比不一致，四控制点 IK 无法无跳变表达')
    if any(abs(sqrt(sum(value*value for value in matrix[:3]))-scale)>1e-5 for matrix in matrices[1:]):
        raise CharacterRegistryError('当前 FK 含独立纵向缩放，原生曲线 IK 无法无跳变表达')
    parameters = []
    for index,control in enumerate(plan.targets):
        if index:
            parameters.extend((control+'.translate'+axis,length,None,None) for axis in 'XYZ')
        if index in (0,3):
            parameters.extend((control+'.rotate'+axis,180./pi,None,None) for axis in 'XYZ')
    parameters.extend((plan.settings+'.'+attribute,1.,0.,1.) for attribute in ('stretch','volume'))
    initial = tuple(c.getAttr(plug)/unit for plug,unit,_,_ in parameters)
    bounds = tuple((low,high) for _,_,low,high in parameters)
    c.setAttr(plan.settings+'.spineIkFk',1.)
    components = (0,1,2,4,5,6,8,9,10,12,13,14)
    def evaluate(values):
        for value,(plug,unit,_,_) in zip(values,parameters):c.setAttr(plug,value*unit)
        rows = []
        for node,target in zip(plan.body_joints[1:],matrices[1:]):
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
