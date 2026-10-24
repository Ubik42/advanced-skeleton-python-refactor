"""Capture native deleted Body identities and the real cached DG inputs."""
from dataclasses import dataclass
from contextlib import contextmanager
import re

from adv_py.core.character_body_retirement import (
    CharacterRetiredBodyJoint, RetiredBodyInput,
    RetiredBodyGraphNode, _REMOVED_KINDS, _SOURCE_RECORDS,
    frozen_origin,canonical_retirement_channel,
)
from adv_py.core.character_registry import CharacterRegistryError


@dataclass(frozen=True, slots=True)
class BodyRetirementCapture:
    path: str
    uuid: str
    parent: str
    matrix: tuple[float, ...]
    rotate_order: int
    body_index: int
    outgoing: tuple[tuple[str, str, str], ...]
    incoming: tuple[tuple[str,str], ...] = ()
    removed_nodes: tuple[RetiredBodyGraphNode, ...] = ()
    records: tuple[tuple[str,str], ...] = ()
    properties: tuple[tuple[str,bool], ...] = ()


def _address(host, plug):
    node, attribute = plug.split('.', 1)
    return canonical_retirement_channel(host._resolve_connected_node(node) + '.' + attribute)


def capture(host, registration, candidates):
    """Read before deletion; downstream addresses retain their UUIDs."""
    c = host._cmds
    body = {joint.path: joint for joint in registration.body}
    from adv_py.core.character_body_retirement import complete_body_bindings
    indices = {joint.path:index for index,joint in enumerate(complete_body_bindings(registration))}
    identities = {node.path: node for node in registration.nodes}
    result = []
    for candidate in candidates:
        matches = c.ls(candidate, long=True, type='joint') or ()
        if len(matches) != 1:
            raise CharacterRegistryError('末端清理候选关节不唯一：' + candidate)
        path = matches[0]
        bind, node = body.get(path), identities.get(path)
        if bind is None or node is None:
            # Auxiliary Part joints may be registered identities rather than
            # authored Body bindings; they require their own retirement path.
            raise CharacterRegistryError('末端清理候选不属于已登记 Body：' + path)
        if path == registration.body_root or (c.ls(path, uuid=True) or ()) != [node.uuid]:
            raise CharacterRegistryError('末端清理候选 Body 身份改变：' + path)
        def incoming(node):
            pairs = c.listConnections(node,source=True,destination=False,
                                     plugs=True,connections=True) or ()
            if len(pairs)%2:
                raise CharacterRegistryError('末端清理的原输入列表不完整：'+node)
            return tuple((_address(host,c.connectionInfo(destination,sourceFromDestination=True) or source),
                          _address(host,destination))
                for destination,source in zip(pairs[::2],pairs[1::2]))
        children = []
        attached = list(c.listRelatives(path,allDescendents=True,fullPath=True) or ())
        # Maya also removes an empty Spline ChestSpace transform when deleting
        # its sole constrained end target. Capture only the saved endpoint's
        # exact registered space; retain it if native deletion leaves it live.
        spaces = tuple(plan.chest_space for plan in
            (getattr(registration,'spine',None),*getattr(registration,'additional_spines',()))
            if plan is not None and plan.body_joints[-1]==path
            and plan.chest_space in identities and c.objExists(plan.chest_space))
        for space in spaces:
            attached.extend((space,*(c.listRelatives(space,allDescendents=True,fullPath=True) or ())))
        for child in dict.fromkeys(attached):
            kind = c.nodeType(child)
            if kind not in _REMOVED_KINDS and not (child in spaces and kind=='transform'):continue
            ids = c.ls(child,uuid=True) or ()
            if len(ids)!=1:raise CharacterRegistryError('末端清理的附属节点身份不唯一')
            children.append(RetiredBodyGraphNode(child,ids[0],kind,incoming(child)))
        connections = []
        for source_node in (path,*(child.path for child in children)):
            pairs = c.listConnections(source_node,source=False,destination=True,
                                     plugs=True,connections=True) or ()
            if len(pairs)%2:
                raise CharacterRegistryError('末端清理输出连接列表不完整：'+source_node)
            connections.extend(pairs)
        outgoing = []
        for index in range(0, len(connections), 2):
            source, destination = connections[index:index + 2]
            # listConnections may abbreviate instance-zero array outputs;
            # the destination's actual source retains the precise element.
            source=c.connectionInfo(destination,sourceFromDestination=True) or source
            source = _address(host, source)
            destination = _address(host, destination)
            if (source.endswith('.message')
                    and not destination.endswith('.advPySourceJoint')):
                continue
            target = destination.split('.', 1)[0]
            # instObjGroups -> objectSet.dagSetMembers is DAG membership,
            # not a numeric DG cache. Native deletion removes that member;
            # querying its now-empty Tdata slot returns None. Rebuild restores
            # membership for live nodes through the normal selection sets.
            if (c.nodeType(target)=='objectSet'
                    and re.fullmatch(r'dagSetMembers\[[0-9]+\]',destination.split('.',1)[1])):
                continue
            ids = c.ls(target, uuid=True) or ()
            if len(ids) != 1 or source.split('.', 1)[0] not in {path,*(child.path for child in children)}:
                raise CharacterRegistryError('末端清理输出来源或目标身份无效')
            outgoing.append((source, destination, ids[0]))
        records = []
        for attribute in sorted(_SOURCE_RECORDS):
            plug = path+'.'+attribute
            if not c.objExists(plug):continue
            if c.getAttr(plug,type=True)!='string' or not c.getAttr(plug,lock=True):
                raise CharacterRegistryError('末端清理前的来源图记录类型或锁定状态无效')
            records.append((attribute,c.getAttr(plug)))
        from .maya_game_scaling_state import original_segment_scale_compensate
        properties = [('segmentScaleCompensate',original_segment_scale_compensate(host,path))]
        point = path+'.advPySourceFkPoint'
        if c.objExists(point):
            if c.getAttr(point,type=True)!='bool' or not c.getAttr(point,lock=True):
                raise CharacterRegistryError('末端清理前的 FK 位置接收设置无效')
            properties.append(('advPySourceFkPoint',bool(c.getAttr(point))))
        result.append(BodyRetirementCapture(path, node.uuid, bind.parent,
            bind.matrix, int(c.getAttr(path + '.rotateOrder')), indices[path],
            tuple(dict.fromkeys(outgoing)),incoming(path),tuple(children),tuple(records),tuple(properties)))
    return tuple(result)


def _flat(value):
    if isinstance(value, (list, tuple)):
        return tuple(number for item in value for number in _flat(item))
    return (float(value),)


def cached_value(commands,plug,datatype):
    if datatype=='message':return ()
    value=commands.getAttr(plug)
    # Native deletion can leave a typed matrix slot with no MObject data.
    # Preserve that absence explicitly; neither identity nor the last live
    # evaluation is its actual stored value.
    if value is None and datatype in ('matrix','fltMatrix'):return None
    return _flat(value)


def cached_datatype(commands,plug):
    node,attribute=plug.split('.',1)
    attribute=re.sub(r'\[[0-9]+\]','',attribute.rsplit('.',1)[-1])
    kind=commands.attributeQuery(attribute,node=node,attributeType=True)
    if kind=='typed':
        from maya import cmds as native
        from maya.api import OpenMaya as om
        # Query the attribute MObject, never the evaluated plug data. Resolve
        # physical namespace/instance identity through its actual UUID.
        identities=commands.ls(node,uuid=True) or ()
        paths=native.ls(identities,long=True) or ()
        if len(identities)!=1 or len(paths)!=1:
            raise CharacterRegistryError('末端缓存属性定义节点身份不唯一：'+plug)
        selection=om.MSelectionList();selection.add(paths[0])
        definition=om.MFnDependencyNode(selection.getDependNode(0)).attribute(attribute)
        datatype=om.MFnTypedAttribute(definition).attrType()
        if datatype!=om.MFnData.kMatrix:
            raise CharacterRegistryError('末端缓存属性定义不是受支持的数值类型：'+plug)
        kind='matrix'
    return kind


def same_cached_value(actual,expected,tolerance=1e-8):
    if actual is None or expected is None:return actual is expected
    return len(actual)==len(expected) and all(abs(a-b)<=tolerance for a,b in zip(actual,expected))


def array_element_exists(commands,plug):
    node,attribute=plug.split('.',1)
    for match in re.finditer(r'\[([0-9]+)\]',attribute):
        parent=node+'.'+attribute[:match.start()]
        if int(match.group(1)) not in (commands.getAttr(parent,multiIndices=True) or ()):
            return False
    return True


def finish(host, captured):
    """Observe the values left by deletion; do not write replacement inputs."""
    c = host._cmds
    result = []
    for row in captured:
        if c.ls(row.uuid, long=True) or c.objExists(row.path):
            raise CharacterRegistryError('原版末端清理没有删除指定 Body 身份：' + row.path)
        deleted_nodes = []
        for node in row.removed_nodes:
            alive = c.objExists(node.path) or c.ls(node.uuid,long=True)
            if alive and node.path.startswith(row.path+'|'):
                raise CharacterRegistryError('原版末端清理没有删除指定附属节点：'+node.path)
            if not alive:deleted_nodes.append(node)
        origins = {row.path:row.uuid, **{node.path:node.uuid for node in deleted_nodes}}
        frozen = []
        for source, destination, identity in row.outgoing:
            if source.split('.',1)[0] not in origins:continue
            targets = c.ls(identity, long=True) or ()
            if not targets:
                # Native deletion also removes a joint's child constraints.
                # Those disappearances are not cached, surviving DG inputs.
                continue
            node, attribute = destination.split('.', 1)
            if len(targets) != 1 or targets[0] != node:
                raise CharacterRegistryError('末端清理后的保留 DG 输入身份改变：' + destination)
            if not array_element_exists(c,destination):
                frozen.append(RetiredBodyInput(source,destination,identity,cached_datatype(c,destination),
                    None,origins[source.split('.',1)[0]],False))
                continue
            if not c.objExists(destination):
                raise CharacterRegistryError('末端清理后的保留 DG 属性改变：'+destination)
            if c.connectionInfo(destination, sourceFromDestination=True):
                raise CharacterRegistryError('末端清理后的 DG 输入被其他来源接管：' + destination)
            datatype = cached_datatype(c,destination)
            try:
                value=cached_value(c,destination,datatype)
            except (TypeError,ValueError) as error:
                raise CharacterRegistryError('末端清理后的数值缓存无效：'+source+' -> '+destination+' ('+datatype+')') from error
            frozen.append(RetiredBodyInput(source, destination, identity,datatype,value,
                                           origins[source.split('.',1)[0]]))
        result.append(CharacterRetiredBodyJoint(row.path, row.uuid, row.parent,
            row.matrix, row.rotate_order, row.body_index, tuple(frozen),row.incoming,
            tuple(deleted_nodes),row.records,row.properties))
    return tuple(result)


def audit(host, registration):
    """Strictly distinguish intentional deletion from missing live nodes."""
    c = host._cmds
    for row in registration.retired_body:
        if c.objExists(row.path) or c.ls(row.uuid, long=True):
            raise CharacterRegistryError('已清理 Body 身份重新出现，需显式恢复登记：' + row.path)
        for node in row.removed_nodes:
            if c.objExists(node.path) or c.ls(node.uuid,long=True):
                raise CharacterRegistryError('已清理 Body 的附属节点重新出现：'+node.path)
        for item in row.frozen_inputs:
            raw = getattr(c, 'raw', c)
            if raw.ls(frozen_origin(row,item), long=True):
                raise CharacterRegistryError('末端缓存值的历史来源身份重新出现：'+item.source)
            # Retained attachments can be reparented during handoff. A
            # historical display path is not their physical identity; the
            # exact destination UUID and attribute survive those DAG moves.
            targets = raw.ls(item.destination_uuid,long=True) or ()
            if len(targets)!=1:
                raise CharacterRegistryError('已清理 Body 的保留 DG 目标身份缺失或歧义：'+item.destination)
            plug = targets[0]+'.'+item.destination.split('.',1)[1]
            if not item.element_exists:
                if (array_element_exists(raw,plug) or cached_datatype(raw,plug)!=item.datatype):
                    raise CharacterRegistryError('原版已删除的数组元素重新出现或定义改变：'+item.destination)
                continue
            if ((raw.ls(targets[0], uuid=True) or ()) != [item.destination_uuid]
                    or not array_element_exists(raw,plug)
                    or not raw.objExists(plug)
                    or cached_datatype(raw,plug) != item.datatype
                    or raw.connectionInfo(plug, sourceFromDestination=True)):
                raise CharacterRegistryError('已清理 Body 的保留 DG 输入身份或连接变化：' + item.destination)
            actual = cached_value(raw,plug,item.datatype)
            if not same_cached_value(actual,item.value):
                raise CharacterRegistryError('已清理 Body 的保留 DG 输入值变化：' + item.destination)


def frozen_source(host, registration, source, destination):
    """A recorded cached input is accepted only after the full strict audit."""
    matches = tuple(item for row in registration.retired_body for item in row.frozen_inputs
                    if (item.source, item.destination) == (source, destination))
    if len(matches) != 1:
        return False
    audit(host, registration)
    return True


def cached_skin_matrix(host, skin, index, *, registration=None):
    """Read only a native disconnected Skin slot with captured provenance."""
    saved = registration if registration is not None else _registration(host)
    if saved is None:
        return None
    c = host._cmds
    identities = c.ls(skin,uuid=True) or ()
    if len(identities) != 1:
        raise CharacterRegistryError('缓存蒙皮矩阵的 Skin 身份不唯一')
    attribute = 'matrix['+str(index)+']'
    matches = tuple((row,item) for row in saved.retired_body for item in row.frozen_inputs
        if item.destination_uuid == identities[0]
        and item.destination.split('.',1)[1] == attribute)
    if not matches:
        return None
    if len(matches)!=1 or matches[0][1].datatype not in ('matrix','fltMatrix'):
        raise CharacterRegistryError('缓存蒙皮矩阵的原版删除记录无效')
    audit(host,saved)
    row,item = matches[0]
    # An absent sparse element is not a disconnected matrix influence.
    # The parent-index audit above proves absence without materializing it.
    if not item.element_exists:
        return None
    plug = skin+'.'+attribute
    if (c.connectionInfo(plug,sourceFromDestination=True)
            or cached_value(c,plug,item.datatype) != item.value):
        raise CharacterRegistryError('缓存蒙皮矩阵与原版删除后状态不同：'+plug)
    return item.value, frozen_origin(row,item)


@contextmanager
def validation(host, registration):
    """Reuse the one strict deletion audit during a complete character read."""
    previous = getattr(host,'_body_retirement_registration',None)
    audit(host,registration)
    host._body_retirement_registration = registration
    try:
        yield
    finally:
        host._body_retirement_registration = previous


def _registration(host):
    active = getattr(host,'_body_retirement_registration',None)
    if active is not None:return active
    from .maya_original_control_identity import registration
    saved = registration(host)
    if saved is not None and saved.retired_body:audit(host,saved)
    return saved


def _local(host, address):
    from .maya_game_scaling_state import _scene_address
    from adv_py.core.character_identity import CharacterIdentity
    physical = _scene_address(host,address)
    return CharacterIdentity(getattr(host,'namespace',None) or '').to_local(physical)


def retired_joint(host, address):
    saved = _registration(host)
    if saved is None:return None
    local = _local(host,address)
    matches = tuple(row for row in saved.retired_body if row.path==local)
    return matches[0] if len(matches)==1 else None


def removed_graph_node(host, address, kind=None):
    """A removed node is explicit provenance, never an existing fake node."""
    saved = _registration(host)
    if saved is None:return None
    local = _local(host,address)
    # A different live node with the same planned leaf is a collision, not
    # evidence that the original attached constraint is still retired.
    if host._cmds.objExists(address):return None
    matches = tuple(node for row in saved.retired_body for node in row.removed_nodes
        if (node.path==local or '|' not in local and node.path.rsplit('|',1)[-1]==local)
        and (kind is None or node.node_type==kind))
    return matches[0] if len(matches)==1 else None


def _canonical_plug(host, plug):
    node,attribute = plug.split('.',1)
    c = host._cmds
    if c.objExists(node):return _local(host,_address(host,plug))
    removed = removed_graph_node(host,node)
    return canonical_retirement_channel((removed.path if removed else _local(host,node))+'.'+attribute)


def is_connected_or_retired(host, source, destination):
    c = host._cmds
    if c.objExists(source) and c.objExists(destination) and c.isConnected(source,destination):
        return True
    saved = _registration(host)
    if saved is None or not saved.retired_body:return False
    edge = _canonical_plug(host,source),_canonical_plug(host,destination)
    for row in saved.retired_body:
        original=(*row.incoming,*(pair for node in row.removed_nodes for pair in node.inputs))
        if any(edge==tuple(canonical_retirement_channel(plug) for plug in pair) for pair in original):
            return True
        if any(tuple(canonical_retirement_channel(plug) for plug in (item.source,item.destination))==edge
               for item in row.frozen_inputs):
            return True
    return False


def source_record(host, target, attribute):
    c = host._cmds
    plug = target+'.'+attribute
    if c.objExists(plug):
        if c.getAttr(plug,type=True)!='string' or not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源图记录类型变化或已解锁：'+plug)
        return c.getAttr(plug)
    retired = retired_joint(host,target)
    if retired is not None:
        records = dict(retired.records)
        if attribute in records:return records[attribute]
    raise CharacterRegistryError('来源图记录不存在，也没有原版末端清理记录：'+plug)


def source_property(host,target,attribute):
    """Only captured source flags can outlive an intentionally deleted Body."""
    from adv_py.core.character_body_retirement import _SOURCE_PROPERTIES
    if attribute not in _SOURCE_PROPERTIES:
        raise CharacterRegistryError('没有该来源设置的末端清理协议：'+attribute)
    c = host._cmds
    if c.objExists(target+'.'+attribute):return bool(c.getAttr(target+'.'+attribute))
    row = retired_joint(host,target)
    if row is not None and attribute in dict(row.properties):
        return dict(row.properties)[attribute]
    raise CharacterRegistryError('来源设置不存在，也没有删除前的真实设置：'+target+'.'+attribute)


def retired_message_source(host, destination):
    saved = _registration(host)
    if saved is None:return None
    plug = _canonical_plug(host,destination)
    matches = tuple(row for row in saved.retired_body for item in row.frozen_inputs
        if item.destination==plug and item.source==row.path+'.message' and item.datatype=='message')
    return matches[0] if len(matches)==1 else None
