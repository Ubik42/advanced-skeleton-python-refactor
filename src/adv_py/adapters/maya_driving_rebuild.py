"""Carry source Fit SDK curves into the separately built replacement Body.

The original rig stays untouched. Native UUID-addressed duplication retains
the authored SDK interpolation; the existing ownership audit still compares
the complete old/new graph before any original rig node can be deleted.
"""
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistryError
from .maya_driving_registration import SDK_MARKER
from .maya_original_control_identity import leaf


@dataclass(frozen=True)
class DrivingRebuildState:
    systems: tuple
    sdk_controls: tuple[str, ...]
    controls: tuple
    graph: object = None
    pose_drivers: tuple = ()


def _bridge(host):
    from .maya_driving_systems import MayaDrivingSystemsHost
    driving = object.__new__(MayaDrivingSystemsHost)
    driving.__dict__ = host.__dict__
    return driving


def derived_property_plugs(state, registration):
    if state is None or state.graph is None:
        return frozenset()
    graph_nodes = {node.properties.path for node in state.graph.nodes}
    from .maya_driving_rebuild_graph import logical_leaf
    members = {}
    for node in registration.nodes:
        name = logical_leaf(node.path)
        if name in members:
            raise CharacterRegistryError('SDK 派生属性角色名称不唯一：' + name)
        members[name] = node.path
    return frozenset(members[logical_leaf(destination.split('.', 1)[0])] + '.'
                     + destination.split('.', 1)[1]
        for source, destination in state.graph.edges
        if logical_leaf(source.split('.', 1)[0]) in graph_nodes
        and logical_leaf(destination.split('.', 1)[0]) in members)


def capture(host, registration):
    driving = _bridge(host)
    c = host._cmds
    controls = []
    # SDK insertion order is retained by the registry member array. Nested
    # insertions therefore recreate their original parent address changes.
    sdks = tuple(node.path.rsplit('|', 1)[-1][3:]
                 for node in registration.nodes if c.objExists(node.path + '.' + SDK_MARKER))
    systems = driving.capture_original_driving_fit_restore(registration.container)
    if not sdks and not systems:
        return None
    from .maya_driving_rebuild_graph import capture as capture_graph
    graph = capture_graph(driving, registration, systems)
    from .maya_character_preservation import capture_extension
    for system in systems:
        matches = c.ls(system.control, long=True) or []
        if len(matches) != 1:
            raise CharacterRegistryError('Fit SDK 的原驱动控制器不唯一：' + system.control)
        row = capture_extension(host, matches[0])
        parents = c.listRelatives(matches[0], parent=True, fullPath=True) or []
        is_driving_control = bool(parents and parents[0].rsplit('|', 1)[-1] == 'DrivingSystem')
        driver_attributes = {curve.attribute for curve in system.curves}
        # QRotate and blended sources may expose several generated outputs;
        # install their definitions before reconnecting the copied network.
        driver_attributes.update(plug.split('.', 1)[1]
            for edge in graph.edges for plug in edge
            if leaf(plug.split('.', 1)[0]) == leaf(system.control))
        # Definitions and defaults are present before the rebuilt SDK connects
        # them. Current values and time curves transfer in the normal handoff.
        attrs = []
        for attribute in row.attributes:
            name, kind, value, locked, keyable, metadata = attribute
            if name == 'optimizedDS' or (not is_driving_control and name not in driver_attributes):
                continue  # Native source optimization regenerates this flag.
            default = dict(metadata).get('default')
            if default and (keyable or dict(metadata).get('channelBox')):
                value = default[0]
            attrs.append((name, kind, value, locked, keyable, metadata))
        controls.append(replace(row, parent=None, matrix=None,
                                attributes=tuple(attrs), connections=()))
    import shlex
    requested = {(leaf(system.control), curve.attribute)
                 for system in systems for curve in system.curves}
    pose_drivers = []
    if c.objExists('buildPose.udAttr'):
        for statement in (c.getAttr('buildPose.udAttr') or '').split(';'):
            try:
                tokens = shlex.split(statement)
                if len(tokens) != 3 or tokens[0] != 'setAttr':
                    continue
                plug, value = tokens[1], float(tokens[2])
            except ValueError:
                continue
            control, attribute = plug.split('.', 1)
            if (leaf(control), attribute) in requested:
                pose_drivers.append((leaf(control), attribute, value))
    return DrivingRebuildState(systems, sdks, tuple(controls), graph, tuple(pose_drivers))


def restore(host, state, registration, rig, *, fit='FitSkeleton'):
    if state is None:
        return registration, rig
    host._require_transaction()
    driving = _bridge(host)
    c = host._cmds
    from .maya_character_properties import install
    from .maya_original_control_identity import leaf
    from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
    # A nested system can place an SDK over another DrivingSystem control.
    # Recreate those controls before inserting its saved SDK hierarchy.
    for row in state.controls:
        control = leaf(row.path)
        if not c.objExists(control):
            system = next(system for system in state.systems if system.control == control)
            drivens = tuple(item.driven for item in system.curves if c.objExists(item.driven))
            driving._original_create_driving_controller(control, drivens)
    from .maya_driving_registration import refresh_registered_sdks
    refresh_registered_sdks(driving)
    # Empty SDK layers are source hierarchy even without connected curves.
    for control in state.sdk_controls:
        driving.create_original_driving_sdk_layer(control)
    for row in state.controls:
        control = leaf(row.path)
        target = (c.ls(control, long=True) or [control])[0]
        # Ordinary FK/deform drivers already belong to the fresh Body. Leave
        # its generated attributes/inputs intact; absent authored definitions
        # alone are installed. DrivingSystem children start without UD attrs.
        absent = tuple(attribute for attribute in row.attributes
                       if not c.objExists(target + '.' + attribute[0]))
        install(driving, (replace(row, path=target, attributes=absent),))
    for control, attribute, value in state.pose_drivers:
        driving._original_driving_pose_registration(control, attribute, face=False, value=value)
    if state.graph is not None:
        from .maya_driving_rebuild_graph import restore as restore_graph
        restore_graph(driving, state.graph)
    restored = driving.restore_original_driving_from_fit(state.systems, fit=fit)
    if len(restored) != sum(len(system.curves) for system in state.systems):
        raise CharacterRegistryError('Fit SDK 恢复缺少原驱动目标，不能交接原绑定')
    # Imported portable Fit omits scene-bound message arrays. Restore the
    # same arrays against only the NEW curves so promotion can rehost them to
    # the retained original Fit UUID with its existing native handoff.
    if state.systems:
        if c.objExists(fit + '.drivingSystem'):
            c.deleteAttr(fit + '.drivingSystem')
        c.addAttr(fit, longName='drivingSystem', attributeType='message',
                  multi=True, indexMatters=False, keyable=False)
        index = 0
        linked = set()
        for system in state.systems:
            name = system.fit_attribute or 'drivingSystem_' + system.control
            if c.objExists(fit + '.' + name):
                c.deleteAttr(fit + '.' + name)
            c.addAttr(fit, longName=name, attributeType='bool', defaultValue=True,
                      multi=True, keyable=False)
            for number, row in enumerate(system.curves):
                if index >= len(restored):
                    raise CharacterRegistryError('Fit SDK 恢复没有生成全部原曲线')
                curve = restored[index]
                index += 1
                slot = row.fit_index if row.fit_index is not None else number
                c.connectAttr(fit + '.' + name + '[' + str(slot) + ']',
                              curve + '.' + row.attribute, force=True)
                if curve not in linked:
                    if row.message_index is None:
                        c.connectAttr(curve + '.drivingSystemOut', fit + '.drivingSystem', nextAvailable=True)
                    else:
                        c.connectAttr(curve + '.drivingSystemOut', fit + '.drivingSystem['
                                      + str(row.message_index) + ']')
                    linked.add(curve)
    from .maya_driving_registration import refresh_registered_sdks
    refresh_registered_sdks(driving)
    updated = host.read_character_registration()
    by_uuid = {node.uuid: node for node in updated.nodes}
    rewrites = []
    for node in registration.nodes:
        current = by_uuid.get(node.uuid)
        if current is None or current.node_type != node.node_type:
            raise CharacterRegistryError('SDK 重建改变了新 Body 原节点身份：' + node.path)
        if node.path != current.path:
            rewrites.append((node.path, current.path))
    paths = FitPartFinalPaths((), (), tuple(rewrites))
    return updated, rebase_plan_paths_after_parts(rig, paths)
