"""Chest-space follow for fixed and variable Body spine mechanisms."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_parent_constraint import (
    audit_body_parent_constraint, plan_body_parent_constraint,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


def _matrix_plan(host, driver: str, driven: str):
    from .maya_character_body_retirement import retired_joint
    retired = retired_joint(host,driver) if not host._cmds.objExists(driver) else None
    if retired is None:
        source = host.capture_parent_constraint_input(driver, driven, False)
    else:
        from adv_py.core.body_parent_constraint import BodyParentConstraintInput, _node_stem
        c = host._cmds
        stem,suffix = _node_stem(driven)
        source = BodyParentConstraintInput(driver,driven,
            (c.listRelatives(driven,parent=True,fullPath=True) or [None])[0],
            c.nodeType(driven)=='joint',int(c.getAttr(driven+'.rotateOrder')),True,
            existing_mult_matrix=c.objExists(stem+'MM'+suffix),
            existing_pick_matrix=c.objExists(stem+'PM'+suffix))
    return plan_body_parent_constraint(replace(
        source, use_offset_parent_matrix=True, skip_scale=True,
        include_pick_matrix=True))


def create(host, driver: str, driven: str, name: str,
           use_offset_parent_matrix: bool) -> None:
    if not use_offset_parent_matrix:
        nodes = host._cmds.parentConstraint(
            driver, driven, maintainOffset=False, name=name)
        if len(nodes) != 1:
            raise FitSkeletonValidationError("Chest Space 父约束创建失败")
        return
    plan = _matrix_plan(host, driver, driven)
    host.preflight_parent_constraint(plan)
    host.create_parent_constraint(plan)
    audit(host, driver, driven, name, True)


def audit(host, driver: str, driven: str, name: str,
          use_offset_parent_matrix: bool) -> None:
    from .maya_character_body_retirement import removed_graph_node,is_connected_or_retired
    removed_space=removed_graph_node(host,driven,'transform') if not host._cmds.objExists(driven) else None
    if removed_space is not None:
        # Maya deletes an otherwise empty space along with its sole target.
        # Its captured exact input edges replace only those deleted identities;
        # the retirement audit still checks every surviving numeric cache.
        if not use_offset_parent_matrix:
            removed_constraint=removed_graph_node(host,name,'parentConstraint')
            if (removed_constraint is None
                    or not removed_constraint.path.startswith(removed_space.path+'|')
                    or not is_connected_or_retired(host,driver+'.parentMatrix[0]',
                        removed_constraint.path+'.target[0].targetParentMatrix')):
                raise FitSkeletonValidationError('已清理 Chest Space 缺少原父约束来源记录')
        else:
            from adv_py.core.body_parent_constraint import _node_stem
            stem,suffix=_node_stem(driven)
            mm,pm=stem+'MM'+suffix,stem+'PM'+suffix
            if (not host._cmds.objExists(mm) or host._cmds.nodeType(mm)!='multMatrix'
                    or not host._cmds.objExists(pm) or host._cmds.nodeType(pm)!='pickMatrix'
                    or not host._cmds.isConnected(mm+'.matrixSum',pm+'.inputMatrix')
                    or not is_connected_or_retired(host,driver+'.worldMatrix[0]',mm+'.matrixIn[0]')
                    or not is_connected_or_retired(host,pm+'.outputMatrix',driven+'.offsetParentMatrix')):
                raise FitSkeletonValidationError('已清理 Chest Space 缺少原矩阵来源记录')
        return
    if not use_offset_parent_matrix:
        from .maya_character_body_retirement import retired_joint,_canonical_plug
        retired=retired_joint(host,driver) if not host._cmds.objExists(driver) else None
        removed_constraint=removed_graph_node(host,name,'parentConstraint') if not host._cmds.objExists(name) else None
        if retired is not None and removed_constraint is not None:
            edges=((driver+'.parentMatrix[0]',removed_constraint.path+'.target[0].targetParentMatrix'),
                   *((removed_constraint.path+'.constraint'+kind+axis,driven+'.'+kind.lower()+axis)
                     for kind in ('Translate','Rotate') for axis in 'XYZ'))
            if not all(is_connected_or_retired(host,source,target) for source,target in edges):
                raise FitSkeletonValidationError('Chest Space 已删除父约束缺少原输入或缓存输出')
            return
        actual = host._cmds.parentConstraint(name, query=True,
                                             targetList=True) or []
        targets = tuple(host._resolve_connected_node(node) for node in actual)
        if retired is not None:
            # Native deletion removes the target's message identity but keeps
            # the actual constraint, with its evaluated target inputs cached.
            constraint=_canonical_plug(host,name+'.message').split('.',1)[0]
            cached=tuple(item for item in retired.frozen_inputs
                if item.destination.split('.',1)[0]==constraint)
            if (targets or not cached or host._cmds.nodeType(name)!='parentConstraint'
                    or not any(item.source in (retired.path+'.parentMatrix[0]',
                                               retired.path+'.worldMatrix[0]')
                               and '.target[' in item.destination for item in cached)):
                raise FitSkeletonValidationError('Chest Space 原末端约束没有完整的清理记录')
            return
        if targets != (driver,):
            raise FitSkeletonValidationError("Chest Space 父约束来源改变")
        return
    plan = _matrix_plan(host, driver, driven)
    state = host.capture_parent_constraint_state(plan)
    from .maya_character_body_retirement import is_connected_or_retired
    inputs = dict(state.matrix_inputs)
    for index,expected in plan.matrix_inputs:
        if (isinstance(expected,str) and not host._cmds.objExists(expected)
                and is_connected_or_retired(host,expected,plan.mult_matrix+'.matrixIn['+str(index)+']')):
            inputs[index] = expected
    state = replace(state,matrix_inputs=tuple(sorted(inputs.items())))
    issues = audit_body_parent_constraint(plan,state)
    if issues:
        raise FitSkeletonValidationError(
            "Chest Space OPM 跟随图不符：" + "；".join(issues))
