"""Portable static character poses with explicit space frames and result references."""
from dataclasses import asdict, dataclass
import re

from .character_registry import canonical, digest, safe_json, exact, finite, vector, CharacterRegistryError

POSE_FORMAT = "adv_py_character_pose"
POSE_VERSION = 1
POSE_TOLERANCE = 1e-4


@dataclass(frozen=True)
class CharacterPose:
    compatibility: str
    channels: tuple[tuple[str, float], ...]
    spaces: tuple[tuple[str, str], ...]
    space_frames: tuple[tuple[str, tuple[float, ...]], ...]
    body_frames: tuple[tuple[str, tuple[float, ...]], ...]


def _rows(value, convert):
    if not isinstance(value,(list,tuple)) or not value:
        raise CharacterRegistryError("姿态数据必须是非空列表")
    rows=[]
    for row in value:
        if not isinstance(row,(list,tuple)) or len(row)!=2 or not isinstance(row[0],str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]*",row[0]):
            raise CharacterRegistryError("姿态语义字段无效")
        rows.append((row[0],convert(row[1])))
    if len({key for key,_ in rows})!=len(rows):
        raise CharacterRegistryError("姿态语义字段重复")
    return tuple(rows)


def _matrix(value):
    matrix=vector(value,16)
    if any(abs(matrix[i])>1e-9 for i in (3,7,11)) or abs(matrix[15]-1)>1e-9:
        raise CharacterRegistryError("姿态矩阵不是仿射变换")
    return matrix


def _space(value):
    if value not in ("body","global"):
        raise CharacterRegistryError("姿态空间必须是 body 或 global")
    return value


def decode_character_pose(text):
    doc=exact(safe_json(text),("format","version","payload","digest"))
    if doc["format"]!=POSE_FORMAT or type(doc["version"]) is not int or doc["version"]!=POSE_VERSION:
        raise CharacterRegistryError("不支持的全身姿态版本")
    raw=exact(doc["payload"],("compatibility","channels","spaces","space_frames","body_frames"))
    if doc["digest"]!=digest(raw) or not isinstance(raw["compatibility"],str) or not re.fullmatch(r"[0-9a-f]{64}",raw["compatibility"]):
        raise CharacterRegistryError("姿态内容或兼容摘要无效")
    return CharacterPose(raw["compatibility"],_rows(raw["channels"],finite),_rows(raw["spaces"],_space),
                         _rows(raw["space_frames"],_matrix),_rows(raw["body_frames"],_matrix))


def encode_character_pose(pose):
    payload=asdict(pose)
    text=canonical({"format":POSE_FORMAT,"version":POSE_VERSION,"payload":payload,"digest":digest(payload)})
    decode_character_pose(text)
    return text


def validate_character_pose(pose, registration):
    # Validate programmatic callers as strictly as JSON callers.
    decode_character_pose(encode_character_pose(pose))
    from .character_spaces import validate_space_values
    validate_space_values(pose.channels, pose.spaces)
    if pose.compatibility!=registration.compatibility_digest:
        raise CharacterRegistryError("姿态拓扑、绑定布局或特性与角色不兼容")
    if tuple(k for k,_ in pose.channels)!=tuple(c.key for c in registration.channels):
        raise CharacterRegistryError("姿态控制通道不完整或顺序不匹配")
    if tuple(k for k,_ in pose.spaces)!=tuple(s.key for s in registration.spaces.spaces):
        raise CharacterRegistryError("姿态空间状态不完整")
    if tuple(k for k,_ in pose.space_frames)!=tuple(s.key+"."+str(i) for s in registration.spaces.spaces for i,_ in enumerate(s.targets)):
        raise CharacterRegistryError("姿态空间帧不完整")
    if tuple(k for k,_ in pose.body_frames)!=tuple(j.path.rsplit("|",1)[-1] for j in registration.body):
        raise CharacterRegistryError("姿态 Body 参考不完整")
    for channel,(_,value) in zip(registration.channels,pose.channels):
        if (channel.minimum is not None and value<channel.minimum) or (channel.maximum is not None and value>channel.maximum):
            raise CharacterRegistryError("姿态控制值超出范围："+channel.key)


def character_pose_error(expected,actual):
    if (expected.compatibility!=actual.compatibility or expected.spaces!=actual.spaces
            or any(tuple(k for k,_ in getattr(expected,field))!=tuple(k for k,_ in getattr(actual,field)) for field in ("channels","space_frames","body_frames"))):
        raise CharacterRegistryError("姿态复检结构或空间不一致")
    scalar=max(abs(a-b) for (_,a),(_,b) in zip(expected.channels,actual.channels))
    frames=max(abs(a-b) for field in ("space_frames","body_frames") for (_,left),(_,right) in zip(getattr(expected,field),getattr(actual,field)) for a,b in zip(left,right))
    return max(scalar,frames)
