"""Upgrade only the legacy mode boundary; retain the native Spline solver."""
from dataclasses import asdict, replace

from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_body_matrix import decode_source_body_matrix
from adv_py.core.source_spline_mode_upgrade import (
    plan_source_spline_mode_upgrade, upgrade_mode_channels,
)
from .maya_source_spline_mode import create as create_mode


def logical_plug(host, plug):
    node, attribute = plug.split('.', 1)
    return host._resolve_connected_node(node) + '.' + attribute


def describe(host, registration, systems=None):
    from adv_py.core.spline_control_rebuild import splines
    old = tuple(plan for plan in splines(registration) if plan.source_curve_points)
    names = {plan.system_name for plan in old}
    selected = names if systems is None else set(systems)
    if selected - names or systems is not None and len(selected) != len(systems):
        raise CharacterRegistryError('Spline 模式升级指定了不存在或重复的系统')
    hierarchy = host.capture_fit_hierarchy(registration.container)
    labels = {joint.path: host.read_joint_label(joint.path) for joint in hierarchy.joints}
    rows = []
    c = host._cmds
    for plan in old:
        if plan.system_name not in selected or plan.source_mode is not None:
            continue
        marker = plan.body_joints[0] + '.advPySourceJoint'
        start = c.getAttr(marker) if c.objExists(marker) else None
        # Some historical provenance stores only a short Fit identity.
        if start not in {joint.path for joint in hierarchy.joints}:
            start = None
        after = plan_source_spline_mode_upgrade(plan, hierarchy, labels, fit_start=start)
        if (tuple(c.attributeQuery(plan.mode_attribute, node=plan.mode_control, minimum=True) or ()) != (0.,)
                or tuple(c.attributeQuery(plan.mode_attribute, node=plan.mode_control, maximum=True) or ()) != (1.,)):
            raise CharacterRegistryError('旧 Spline 用户范围不是明确的 0–1，不能自动换算')
        for attribute in (plan.mode_attribute, 'autoVis', 'FKVis', 'IKVis'):
            plug = plan.visibility_settings + '.' + attribute
            if not c.objExists(plug) or c.getAttr(plug, lock=True):
                raise CharacterRegistryError('旧 Spline 模式或显示通道缺失、锁定：' + plug)
            source = c.connectionInfo(plug, sourceFromDestination=True)
            if source and not host._character_direct_animation(source):
                raise CharacterRegistryError('旧 Spline 通道有非原生动画输入：' + plug)
            if source:
                curve = source.split('.', 1)[0]
                if c.referenceQuery(curve, isNodeReferenced=True) or any(c.lockNode(curve, query=True, lock=True) or []):
                    raise CharacterRegistryError('旧 Spline 曲线被引用或锁定：' + curve)
                outputs = c.connectionInfo(source, destinationFromSource=True) or []
                if tuple(logical_plug(host, output) for output in outputs) != (plug,):
                    raise CharacterRegistryError('旧 Spline 曲线共享其他通道，不能直接换算：' + source)
        for name in after.source_mode.node_names:
            if host.find_name_collisions(name):
                raise CharacterRegistryError('独立 Spline FKIK 控制器名称被占用：' + name)
        rows.append((plan, after))
    return tuple(rows)


def _move_input(host, old, new, factor=1.):
    c = host._cmds
    source = c.connectionInfo(old, sourceFromDestination=True)
    value = float(c.getAttr(old))
    if source:
        c.disconnectAttr(source, old)
        if factor != 1.:
            # Native scaleKey transforms weighted tangent vectors together
            # with values, retaining UUIDs, infinity and tangent types.
            c.scaleKey(source.split('.', 1)[0], valueScale=factor, valuePivot=0.)
        c.connectAttr(source, new)
    else:
        c.setAttr(new, value * factor)


def _replace_outputs(host, old, new, overrides=()):
    c = host._cmds
    overrides = dict(overrides)
    for target in tuple(c.connectionInfo(old, destinationFromSource=True) or ()):
        target = logical_plug(host, target)
        source = overrides.get(target, new)
        locked = c.getAttr(target, lock=True)
        if locked:
            c.setAttr(target, lock=False)
        try:
            c.disconnectAttr(old, target)
            c.connectAttr(source, target)
        finally:
            if locked:
                c.setAttr(target, lock=True)


def rewrite_body_mode_records(host, registration, mapping):
    """Change exact connection sources in our closed Body matrix records."""
    c = host._cmds
    for joint in registration.body:
        for attribute in ('advPySourceFkMatrix', 'advPySourceBendyMatrix'):
            plug = joint.path + '.' + attribute
            if not c.objExists(plug):
                continue
            graph = decode_source_body_matrix(c.getAttr(plug))
            nodes = tuple(replace(node, connections=tuple(
                (mapping.get(source, source), target) for source, target in node.connections))
                for node in graph.nodes)
            if nodes == graph.nodes:
                continue
            locked = c.getAttr(plug, lock=True)
            c.setAttr(plug, lock=False)
            c.setAttr(plug, canonical(asdict(replace(graph, nodes=nodes))), type='string')
            c.setAttr(plug, lock=locked)


def install(host, registration, rows):
    host._require_transaction()
    host._transaction_changed = True
    c = host._cmds
    channels = registration.channels
    replacements = {}
    original_nodes = set(c.ls(long=True) or ())
    for before, after in rows:
        create_mode(host, after)
        default = c.attributeQuery(before.mode_attribute, node=before.mode_control,
                                   listDefault=True)[0]
        c.addAttr(after.mode_plug, edit=True, defaultValue=default * 10.)
        _move_input(host, before.mode_plug, after.mode_plug, 10.)
        condition = before.node_name('AdvPy_SplineVisibility')
        _replace_outputs(host, before.mode_plug, after.mode_weight,
                         ((condition + '.colorIfFalseR', after.mode_plug),))
        destination = condition + '.colorIfFalseG'
        source = c.connectionInfo(destination, sourceFromDestination=True)
        c.disconnectAttr(source, destination)
        c.connectAttr(after.visibility_reverse, destination)
        for attribute in ('autoVis', 'FKVis', 'IKVis'):
            old = before.visibility_settings + '.' + attribute
            new = after.visibility_settings + '.' + attribute
            default = c.attributeQuery(attribute, node=before.visibility_settings,
                                       listDefault=True)[0]
            c.addAttr(after.visibility_settings, longName=attribute,
                      attributeType='bool', defaultValue=default)
            c.setAttr(new, keyable=c.getAttr(old, keyable=True),
                      channelBox=c.getAttr(old, channelBox=True))
            _move_input(host, old, new)
            _replace_outputs(host, old, new)
            c.deleteAttr(old)
        if before.source_hybrid_graph:
            destination = before.node_name('AdvPy_SplineHybridVisibility.input1D[0]')
            source = c.connectionInfo(destination, sourceFromDestination=True)
            c.disconnectAttr(source, destination)
            c.connectAttr(condition + '.outColorR', after.source_mode.hybrid_visibility_unit + '.input')
            c.connectAttr(after.source_mode.hybrid_visibility_unit + '.output', destination)
        rewrite_body_mode_records(host, registration, {before.mode_plug: after.mode_weight})
        c.deleteAttr(before.mode_plug)
        channels = upgrade_mode_channels(channels, before, after)
        replacements[before.system_name] = after
    if not rows:
        return registration
    known = {node.path for node in registration.nodes}
    appended = set()
    for _, after in rows:
        for path in (after.source_mode.frame, after.source_mode.control):
            while path:
                if path not in known:
                    appended.add(path)
                path = path.rsplit('|', 1)[0]
    user_plugs = {row.node + '.' + row.attribute for row in channels}
    def capture(path):
        node = host._registry_node(path)
        return replace(node, inputs=tuple((attribute, source) for attribute, source in node.inputs
            if not (path + '.' + attribute in user_plugs and host._character_direct_animation(source))))
    nodes = tuple(capture(row.path) for row in registration.nodes)
    nodes += tuple(capture(path) for path in sorted(appended, key=lambda path: (path.count('|'), path)))
    result = replace(registration, channels=channels, nodes=nodes,
        spine=replacements.get(getattr(registration.spine, 'system_name', None), registration.spine),
        additional_spines=tuple(replacements.get(plan.system_name, plan)
                               for plan in registration.additional_spines))
    added = set(c.ls(long=True) or ()) - original_nodes
    if c.objExists('AllSet'):
        c.sets(tuple(sorted(added)), addElement='AllSet')
    if c.objExists('ControlSet'):
        c.sets(tuple(after.mode_control for _, after in rows), addElement='ControlSet')
    host.write_character_registration_extension(registration, result)
    return result
