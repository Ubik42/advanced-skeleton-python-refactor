"""Closed topology document for the native, live MoCap constraint session."""
from .character_registry import canonical, exact, safe_json, CharacterRegistryError
from .character_body_retirement import retirement_plug

FORMAT = 'adv_py_source_name_matcher_mocap'
ATTRIBUTE = 'advPyNameMatcherDocument'
KINDS = frozenset(('transform', 'pointConstraint', 'orientConstraint', 'aimConstraint','pairBlend'))


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise CharacterRegistryError('动捕会话节点地址无效')
    retirement_plug(value + '.message')
    return value


def _identity(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise CharacterRegistryError('动捕会话 UUID 无效')
    return value


def channel_plugs(prefix, axis):
    """Native Maya may spell a child alone or beneath its compound."""
    child = prefix + axis
    return (child, prefix + '.' + child)


def blend_input_plugs(channel, axis):
    compound = 'in' + channel + '2'
    child = 'in' + channel + axis + '2'
    return (child, compound, compound + '.' + child)


def decode_session(text):
    value = safe_json(text)
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version'] not in (1,2,3):
        raise CharacterRegistryError('动捕会话文档版本无效')
    exact(value, ('format', 'version', 'group', 'nodes', 'receivers')
          + (('output_constraints','baked','removed_blends') if value['version']>=2 else ())
          + (('static_cleaned',) if value['version']==3 else ()))
    if value['format'] != FORMAT:
        raise CharacterRegistryError('动捕会话文档格式无效')
    exact(value['group'], ('path', 'uuid'))
    _name(value['group']['path'])
    _identity(value['group']['uuid'])
    if not isinstance(value['nodes'], list) or not 1 <= len(value['nodes']) <= 4096:
        raise CharacterRegistryError('动捕会话节点数量无效')
    ids, paths = set(), set()
    for node in value['nodes']:
        exact(node, ('path', 'uuid', 'kind', 'parent', 'inputs'))
        _name(node['path'])
        _identity(node['uuid'])
        if (not isinstance(node['kind'],str) or node['kind'] not in KINDS
                or node['uuid'] in ids or node['path'] in paths):
            raise CharacterRegistryError('动捕会话节点类型或身份无效')
        ids.add(node['uuid'])
        paths.add(node['path'])
        if node['parent'] is not None:
            _identity(node['parent'])
        if not isinstance(node['inputs'], list) or len(node['inputs']) > 1024:
            raise CharacterRegistryError('动捕会话输入数量无效')
        destinations = set()
        for edge in node['inputs']:
            exact(edge, ('destination', 'source', 'source_uuid'))
            if not isinstance(edge['destination'], str):
                raise CharacterRegistryError('动捕会话输入属性无效')
            retirement_plug(node['path'] + '.' + edge['destination'])
            retirement_plug(edge['source'])
            _identity(edge['source_uuid'])
            if edge['destination'] in destinations:
                raise CharacterRegistryError('动捕会话重复输入端口')
            destinations.add(edge['destination'])
    if not isinstance(value['receivers'], list) or not 1 <= len(value['receivers']) <= 4096:
        raise CharacterRegistryError('动捕会话控制器数量无效')
    receiver_ids, plugs = set(), set()
    by_id = {node['uuid']: node for node in value['nodes']}
    if value['version']>=2:
        if type(value['baked']) is not bool:
            raise CharacterRegistryError('动捕烘焙状态无效')
        for field,kind in (('output_constraints',('pointConstraint','orientConstraint')),
                           ('removed_blends',('pairBlend',))):
            items=value[field]
            if not isinstance(items,list) or len(items)>4096:
                raise CharacterRegistryError('动捕会话输出或烘焙删除数量无效')
            for identity in items:
                _identity(identity)
                if identity not in by_id or by_id[identity]['kind'] not in kind:
                    raise CharacterRegistryError('动捕会话输出或烘焙删除身份无效')
            if len(set(items))!=len(items):raise CharacterRegistryError('动捕会话输出或烘焙删除重复')
        if value['version']==3 and type(value['static_cleaned']) is not bool:
            raise CharacterRegistryError('动捕原生静态清理状态无效')
        if not value['output_constraints'] or value['removed_blends'] and not (
                value['baked'] or value.get('static_cleaned',False)):
            raise CharacterRegistryError('动捕会话缺少输出或在烘焙前记录删除')
    for receiver in value['receivers']:
        exact(receiver, ('path', 'uuid', 'inputs'))
        _name(receiver['path'])
        _identity(receiver['uuid'])
        if receiver['uuid'] in receiver_ids or receiver['uuid'] in ids:
            raise CharacterRegistryError('动捕会话控制器身份重复或指向辅助节点')
        receiver_ids.add(receiver['uuid'])
        if not isinstance(receiver['inputs'], list) or not 1 <= len(receiver['inputs']) <= 6:
            raise CharacterRegistryError('动捕会话控制输入数量无效')
        for edge in receiver['inputs']:
            exact(edge, ('destination', 'source', 'source_uuid')
                  + (('constraint_uuid',) if value['version']>=2 else ()))
            attribute = edge['destination']
            if attribute not in tuple(kind + axis for kind in ('translate', 'rotate') for axis in 'XYZ'):
                raise CharacterRegistryError('动捕会话只能驱动平移和旋转')
            retirement_plug(edge['source'])
            _identity(edge['source_uuid'])
            source = by_id.get(edge['source_uuid'])
            prefix = 'constraintTranslate' if attribute.startswith('translate') else 'constraintRotate'
            kind = 'pointConstraint' if attribute.startswith('translate') else 'orientConstraint'
            if value['version']>=2:
                _identity(edge['constraint_uuid'])
                constraint=by_id.get(edge['constraint_uuid'])
                if (constraint is None or constraint['kind']!=kind
                        or constraint['uuid'] not in value['output_constraints']):
                    raise CharacterRegistryError('动捕接收通道没有已登记的原输出约束')
            blend=source is not None and source['kind']=='pairBlend' and value['version']>=2
            output=('outTranslate' if attribute.startswith('translate') else 'outRotate')+attribute[-1]
            blend_output=source['path']+'.'+output if blend else ''
            valid_blend=blend and edge['source'] in (blend_output,
                source['path']+'.'+output[:-1]+'.'+output)
            if (source is None or not valid_blend and (source['kind'] != kind
                    or edge['source'] not in tuple(source['path'] + '.' + plug
                        for plug in channel_plugs(prefix, attribute[-1])))):
                raise CharacterRegistryError('动捕会话输出类型、节点或轴向不一致')
            if value['version']>=2 and not blend and source['uuid']!=edge['constraint_uuid']:
                raise CharacterRegistryError('动捕直接输出不是其原约束身份')
            if valid_blend and not value['baked']:
                # Maya inserts the native pairBlend when constraint commands
                # meet animation. Prove its second input reaches this exact
                # output constraint and axis; do not authorize arbitrary blends.
                channel='Translate' if attribute.startswith('translate') else 'Rotate'
                candidates=[]
                for incoming in source['inputs']:
                    if incoming['destination'] not in blend_input_plugs(channel, attribute[-1]):
                        continue
                    upstream=by_id.get(incoming['source_uuid'])
                    if (upstream is not None and upstream['kind']==kind
                            and upstream['uuid']==edge['constraint_uuid']
                            and incoming['source'] in tuple(upstream['path']+'.'+plug
                                for plug in (*channel_plugs(prefix, attribute[-1]), prefix))):
                        candidates.append(upstream)
                if len(candidates)!=1:
                    raise CharacterRegistryError('动捕 pairBlend 缺少原输出约束或轴向输入')
            plug = receiver['uuid'], attribute
            if plug in plugs:
                raise CharacterRegistryError('动捕会话控制端口重复')
            plugs.add(plug)
    output_ids = {edge['source_uuid'] for receiver in value['receivers'] for edge in receiver['inputs']}
    if not output_ids:
        raise CharacterRegistryError('动捕会话没有输出约束')
    if value['version']>=2 and {edge['constraint_uuid'] for receiver in value['receivers']
            for edge in receiver['inputs']}!=set(value['output_constraints']):
        raise CharacterRegistryError('动捕会话接收通道与原输出约束集合不一致')
    return value


def encode_session(value):
    text = canonical(value)
    decode_session(text)
    return text


def rebase_session(value, replacements):
    """Move the recorded boundary by explicit UUID pairs, never by leaf names.

    Owned helpers and external MoCap targets retain their UUID. Only the
    independently audited generated character nodes may receive replacements.
    A path-only change uses the same UUID, for retained DAG nodes and curves.
    """
    from copy import deepcopy
    saved = decode_session(encode_session(value))
    if not isinstance(replacements, dict):
        raise CharacterRegistryError('动捕重建需要明确的 UUID 交接表')
    for identity, row in replacements.items():
        _identity(identity)
        if not isinstance(row, tuple) or len(row) != 2:
            raise CharacterRegistryError('动捕 UUID 交接项无效')
        _name(row[0]); _identity(row[1])
    owned = {saved['group']['uuid'], *(node['uuid'] for node in saved['nodes'])}
    if any(identity in owned and identity != row[1]
           for identity, row in replacements.items()):
        raise CharacterRegistryError('动捕重建不能替换原会话辅助节点')
    updated = deepcopy(saved)
    def move_edge(edge):
        replacement = replacements.get(edge['source_uuid'])
        if replacement is not None:
            edge['source'] = replacement[0] + '.' + edge['source'].split('.', 1)[1]
            edge['source_uuid'] = replacement[1]
    for row in (updated['group'], *updated['nodes'], *updated['receivers']):
        replacement = replacements.get(row['uuid'])
        if replacement is not None:
            row['path'], row['uuid'] = replacement
        if 'parent' in row and row['parent'] in replacements:
            row['parent'] = replacements[row['parent']][1]
        for edge in row.get('inputs', ()):
            move_edge(edge)
    return decode_session(encode_session(updated))
