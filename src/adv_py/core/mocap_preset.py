"""Portable, closed MoCap-to-Body joint mapping presets."""
from dataclasses import dataclass
from hashlib import sha256
import json

from .mocap_mapping import MocapJointMapping, MocapMappingValidationError


PRESET_FORMAT='adv_py_mocap_mapping'
PRESET_SCHEMA=1


@dataclass(frozen=True, slots=True)
class MocapMappingPreset:
    name: str
    mappings: tuple[MocapJointMapping,...]
    expected_body_joint_count: int = 30

    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.strip() or len(self.name)>120:
            raise MocapMappingValidationError('动捕映射预设名称无效')
        if (isinstance(self.expected_body_joint_count,bool) or not isinstance(self.expected_body_joint_count,int)
                or not 1<=self.expected_body_joint_count<=512):
            raise MocapMappingValidationError('动捕映射预设 Body 关节数无效')
        if not isinstance(self.mappings,tuple) or not 1<=len(self.mappings)<=512 or any(
                not isinstance(item,MocapJointMapping) for item in self.mappings):
            raise MocapMappingValidationError('动捕映射预设关节条目无效')
        if (len({item.source_name for item in self.mappings})!=len(self.mappings)
                or len({item.target_name for item in self.mappings})!=len(self.mappings)):
            raise MocapMappingValidationError('动捕映射预设来源或目标关节重复')


def _payload(preset):
    return dict(format=PRESET_FORMAT,schema_version=PRESET_SCHEMA,name=preset.name,
                expected_body_joint_count=preset.expected_body_joint_count,
                mappings=[dict(source_name=row.source_name,target_name=row.target_name,
                               transfer_translation=row.transfer_translation,
                               transfer_rotation=row.transfer_rotation) for row in preset.mappings])


def encode_mocap_mapping_preset(preset: MocapMappingPreset) -> str:
    if not isinstance(preset,MocapMappingPreset):
        raise MocapMappingValidationError('动捕映射预设类型无效')
    payload=_payload(preset)
    canonical=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
    payload['content_sha256']=sha256(canonical).hexdigest()
    return json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n'


def decode_mocap_mapping_preset(text: str) -> MocapMappingPreset:
    try:raw=json.loads(text)
    except (TypeError,ValueError) as exc:
        raise MocapMappingValidationError('动捕映射预设不是有效 JSON') from exc
    if not isinstance(raw,dict) or set(raw)!={'format','schema_version','name','expected_body_joint_count','mappings','content_sha256'}:
        raise MocapMappingValidationError('动捕映射预设字段集合无效')
    if raw['format']!=PRESET_FORMAT or type(raw['schema_version']) is not int or raw['schema_version']!=PRESET_SCHEMA:
        raise MocapMappingValidationError('动捕映射预设格式或版本不受支持')
    if not isinstance(raw['mappings'],list):
        raise MocapMappingValidationError('动捕映射预设映射条目必须为数组')
    rows=[]
    for item in raw['mappings']:
        if not isinstance(item,dict) or set(item)!={'source_name','target_name','transfer_translation','transfer_rotation'}:
            raise MocapMappingValidationError('动捕映射预设映射条目字段无效')
        rows.append(MocapJointMapping(**item))
    preset=MocapMappingPreset(raw['name'],tuple(rows),raw['expected_body_joint_count'])
    expected_digest=json.loads(encode_mocap_mapping_preset(preset))['content_sha256']
    if raw['content_sha256']!=expected_digest:
        raise MocapMappingValidationError('动捕映射预设内容摘要不匹配')
    return preset
