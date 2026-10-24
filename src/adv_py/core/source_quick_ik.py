"""Closed identities for the temporary graph created by original asQuickIK."""
from copy import deepcopy
from .character_registry import CharacterRegistryError, safe_json, exact

ATTRIBUTE = 'advPyOriginalQuickIK'
FORMAT = 'adv_py_original_quick_ik'


def _identity(row):
    if not all(isinstance(row.get(key), str) and row[key] for key in ('path', 'uuid')):
        raise CharacterRegistryError('QuickIK 节点路径或 UUID 无效')


def _inputs(rows):
    if not isinstance(rows, list):
        raise CharacterRegistryError('QuickIK 输入记录无效')
    destinations = set()
    for edge in rows:
        exact(edge, ('destination', 'source', 'source_uuid'))
        if not all(isinstance(value, str) and value for value in edge.values()):
            raise CharacterRegistryError('QuickIK 输入端口记录无效')
        if edge['destination'] in destinations or '.' not in edge['source']:
            raise CharacterRegistryError('QuickIK 输入端口重复或来源无效')
        destinations.add(edge['destination'])


def decode_quick_ik(text):
    value = safe_json(text)
    version=value.get('version') if isinstance(value,dict) else None
    exact(value, ('format', 'version', 'group', 'nodes', 'constraints', 'receivers')
          + (('blend_settings',) if version==2 else ()))
    if value['format'] != FORMAT or type(version) is not int or version not in (1,2):
        raise CharacterRegistryError('QuickIK 原生图记录版本无效')
    exact(value['group'], ('path', 'uuid'))
    _identity(value['group'])
    if not isinstance(value['nodes'], list) or not value['nodes']:
        raise CharacterRegistryError('QuickIK 原生节点记录为空')
    nodes = {}
    for row in value['nodes']:
        exact(row, ('path', 'uuid', 'kind', 'parent', 'inputs'))
        _identity(row)
        if not isinstance(row['kind'], str) or not row['kind'] or row['uuid'] in nodes:
            raise CharacterRegistryError('QuickIK 原生节点类型无效或身份重复')
        if row['parent'] is not None and (not isinstance(row['parent'], str) or not row['parent']):
            raise CharacterRegistryError('QuickIK 原生父级身份无效')
        _inputs(row['inputs'])
        nodes[row['uuid']] = row
    group = nodes.get(value['group']['uuid'])
    if group is None or group['path'] != value['group']['path'] or group['kind'] != 'transform':
        raise CharacterRegistryError('QuickIK 临时组不在原生节点记录中')
    constraints = value['constraints']
    if (not isinstance(constraints, list) or any(not isinstance(item, str) for item in constraints)
            or len(set(constraints)) != len(constraints) or not set(constraints) <= nodes.keys()
            or any(nodes[item]['kind'] != 'orientConstraint' for item in constraints)):
        raise CharacterRegistryError('QuickIK 输出约束身份无效')
    if not isinstance(value['receivers'], list):
        raise CharacterRegistryError('QuickIK 接收控制器记录无效')
    receivers = set()
    for row in value['receivers']:
        exact(row, ('path', 'uuid', 'inputs'))
        _identity(row)
        _inputs(row['inputs'])
        if row['uuid'] in receivers:
            raise CharacterRegistryError('QuickIK 接收控制器身份重复')
        receivers.add(row['uuid'])
        for edge in row['inputs']:
            if edge['source_uuid'] not in nodes or edge['destination'] not in tuple(
                    kind + axis for kind in ('translate', 'rotate') for axis in 'XYZ'):
                raise CharacterRegistryError('QuickIK 接收端口超出原生混合输出')
    if version==2:
        settings=value['blend_settings']
        if not isinstance(settings,list):
            raise CharacterRegistryError('QuickIK pairBlend 缓存记录无效')
        ids=set()
        allowed=tuple('in'+kind+axis+number for kind in ('Translate','Rotate') for number in ('1','2') for axis in 'XYZ')
        allowed+=('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
        for record in settings:
            exact(record,('uuid','settings'))
            if record['uuid'] in ids or record['uuid'] not in nodes or nodes[record['uuid']]['kind']!='pairBlend':
                raise CharacterRegistryError('QuickIK pairBlend 缓存所属身份无效')
            ids.add(record['uuid'])
            seen=set()
            if not isinstance(record['settings'],list):
                raise CharacterRegistryError('QuickIK pairBlend 缓存列表无效')
            for row in record['settings']:
                exact(row,('attribute','value'))
                if row['attribute'] not in allowed or row['attribute'] in seen:
                    raise CharacterRegistryError('QuickIK pairBlend 缓存属性无效或重复')
                seen.add(row['attribute'])
                from .character_registry import finite
                finite(row['value'])
        if ids!={row['uuid'] for row in nodes.values() if row['kind']=='pairBlend'}:
            raise CharacterRegistryError('QuickIK pairBlend 缓存身份记录不完整')
    return value


def rebase_quick_ik(value, replacements):
    """Only an audited UUID pairing may change an original scene address."""
    result = deepcopy(value)
    def identity(row):
        old = row['uuid']
        if old not in replacements:
            raise CharacterRegistryError('QuickIK 交接缺少节点 UUID 对应：' + old)
        row['path'], row['uuid'] = replacements[old]
    identity(result['group'])
    for row in (*result['nodes'], *result['receivers']):
        identity(row)
        if row.get('parent') is not None:
            row['parent'] = replacements[row['parent']][1]
        for edge in row['inputs']:
            path, new = replacements[edge['source_uuid']]
            edge['source'] = path + '.' + edge['source'].split('.', 1)[1]
            edge['source_uuid'] = new
    result['constraints'] = [replacements[old][1] for old in result['constraints']]
    for row in result.get('blend_settings',()):
        row['uuid']=replacements[row['uuid']][1]
    return result
