"""Original RP end scaling, including the non-OPM T-pose axis swaps.

MEL 82804–82838 deliberately takes the main IK control's local scale. Sub,
Extra and the aligned orientation receiver do not replace that source.
"""


def source_limb_scale_axes(label, *,use_offset_parent_matrix,ik_local_mode):
    if use_offset_parent_matrix or ik_local_mode:
        return ('X','Y','Z')
    if 'Leg' in label:
        return ('Y','Z','X')
    if 'Arm' in label:
        return ('X','Z','Y')
    return ('X','Y','Z')


def decode_source_limb_scale(text):
    from .character_registry import safe_json,exact,path,identifier,CharacterRegistryError
    raw = exact(safe_json(text),('version','label','side','control','end','outputs'))
    if type(raw['version']) is not int or raw['version']!=1 or raw['side'] not in ('R','L','M'):
        raise CharacterRegistryError('来源 RP 末端缩放登记版本或侧别无效')
    identifier(raw['label'])
    path(raw['control'])
    path(raw['end'])
    if not isinstance(raw['outputs'],list) or len(raw['outputs']) not in (3,6):
        raise CharacterRegistryError('来源 RP 末端缩放输出数量无效')
    destinations=[]
    for row in raw['outputs']:
        if not isinstance(row,list) or len(row)!=2:
            raise CharacterRegistryError('来源 RP 末端缩放输出记录无效')
        if row[0] not in tuple(raw['control']+'.scale'+axis for axis in 'XYZ'):
            raise CharacterRegistryError('来源 RP 末端缩放来源不属于主 IK 控制器')
        node,attribute = row[1].rsplit('.',1)
        if node.startswith('|'):
            if path(node)!=raw['end'] or attribute not in ('scaleX','scaleY','scaleZ'):
                raise CharacterRegistryError('来源 RP 末端缩放关节目标无效')
        else:
            identifier(node)
            if '.' in node or attribute not in ('color1R','color1G','color1B'):
                raise CharacterRegistryError('来源 RP 末端缩放混合目标无效')
        destinations.append(row[1])
    if len(set(destinations))!=len(destinations):
        raise CharacterRegistryError('来源 RP 末端缩放输入重复')
    return raw
