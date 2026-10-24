"""Native pairBlends that survive original MoCap Disconnect, without a group."""
from copy import deepcopy

from .character_registry import CharacterRegistryError, canonical, exact, safe_json, finite
from .character_body_retirement import retirement_plug
from .source_name_matcher_session import _identity, _name, channel_plugs

ATTRIBUTE = 'advPyNativeAnimationDocument'
FORMAT = 'adv_py_native_mocap_animation'


def decode_native_animation(text):
    value = safe_json(text)
    exact(value,('format','version','origin','node','settings','receivers'))
    if value['format'] != FORMAT or type(value['version']) is not int or value['version'] != 1:
        raise CharacterRegistryError('原生动捕动画记录格式或版本无效')
    _identity(value['origin'])
    node = value['node']
    exact(node,('path','uuid','kind','parent','inputs'))
    _name(node['path']); _identity(node['uuid'])
    if node['kind'] != 'pairBlend' or node['parent'] is not None:
        raise CharacterRegistryError('原生动捕动画只能保留实际 pairBlend')
    if not isinstance(node['inputs'],list) or len(node['inputs']) > 1024:
        raise CharacterRegistryError('原生动捕动画输入数量无效')
    destinations = set()
    for edge in node['inputs']:
        exact(edge,('destination','source','source_uuid'))
        if not isinstance(edge['destination'],str):
            raise CharacterRegistryError('原生动捕动画输入端口无效')
        retirement_plug(node['path']+'.'+edge['destination'])
        retirement_plug(edge['source']); _identity(edge['source_uuid'])
        if edge['destination'] in destinations:
            raise CharacterRegistryError('原生动捕动画输入端口重复')
        destinations.add(edge['destination'])
    if not isinstance(value['settings'],list) or len(value['settings']) > 32:
        raise CharacterRegistryError('原生动捕动画设置数量无效')
    names = set()
    for item in value['settings']:
        exact(item,('attribute','value'))
        attribute = item['attribute']
        allowed = tuple('in'+kind+axis+index
            for kind in ('Translate','Rotate') for index in ('1','2') for axis in 'XYZ')
        allowed += ('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
        if attribute not in allowed or attribute in names or attribute in destinations:
            raise CharacterRegistryError('原生动捕动画缓存属性重复、受驱动或无效')
        if type(item['value']) not in (int,float,bool):
            raise CharacterRegistryError('原生动捕动画缓存值无效')
        finite(float(item['value'])); names.add(attribute)
    if not isinstance(value['receivers'],list) or not 1 <= len(value['receivers']) <= 4096:
        raise CharacterRegistryError('原生动捕动画接收器数量无效')
    receiver_ids, ports = set(),set()
    for row in value['receivers']:
        exact(row,('path','uuid','inputs'))
        _name(row['path']); _identity(row['uuid'])
        if row['uuid'] in receiver_ids or row['uuid'] == node['uuid']:
            raise CharacterRegistryError('原生动捕动画接收身份重复')
        receiver_ids.add(row['uuid'])
        if not isinstance(row['inputs'],list) or not 1 <= len(row['inputs']) <= 6:
            raise CharacterRegistryError('原生动捕动画接收端口数量无效')
        for edge in row['inputs']:
            exact(edge,('destination','source','source_uuid'))
            attribute = edge['destination']
            if attribute not in tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'):
                raise CharacterRegistryError('原生动捕动画只能驱动原平移和旋转通道')
            prefix = 'outTranslate' if attribute.startswith('translate') else 'outRotate'
            if (edge['source_uuid'] != node['uuid'] or edge['source'] not in tuple(
                    node['path']+'.'+plug for plug in channel_plugs(prefix,attribute[-1]))):
                raise CharacterRegistryError('原生动捕动画输出轴向或身份不一致')
            port = row['uuid'],attribute
            if port in ports:
                raise CharacterRegistryError('原生动捕动画接收端口重复')
            ports.add(port)
    return value


def encode_native_animation(value):
    text = canonical(value)
    decode_native_animation(text)
    return text


def rebase_native_animation(value,replacements):
    saved = decode_native_animation(encode_native_animation(value))
    updated = deepcopy(saved)
    if not isinstance(replacements,dict):
        raise CharacterRegistryError('原生动捕动画需要明确的 UUID 交接表')
    for identity,row in replacements.items():
        _identity(identity)
        if not isinstance(row,tuple) or len(row) != 2:
            raise CharacterRegistryError('原生动捕动画 UUID 交接项无效')
        _name(row[0]); _identity(row[1])
    node = saved['node']
    if node['uuid'] in replacements and replacements[node['uuid']][1] != node['uuid']:
        raise CharacterRegistryError('原生动捕动画不能替换已有 pairBlend')
    for row in (updated['node'],*updated['receivers']):
        if row['uuid'] in replacements:
            row['path'],row['uuid'] = replacements[row['uuid']]
        for edge in row['inputs']:
            if edge['source_uuid'] in replacements:
                path,identity = replacements[edge['source_uuid']]
                edge['source'] = path+'.'+edge['source'].split('.',1)[1]
                edge['source_uuid'] = identity
    return decode_native_animation(encode_native_animation(updated))
