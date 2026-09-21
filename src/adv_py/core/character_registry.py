"""Closed, versioned scene registration schema; no Python object loader."""
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from math import isfinite
import re

from .body_spine import BodySpinePlan
from .body_spline import BodySplinePlan
from .body_control_spaces import BodyControlSpaceSpec, BodyControlSpacesPlan
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .fit_symmetry import FitBuildSide

FORMAT = "adv_py_character_registry"
VERSION = 1
REGISTRY_NAME = "AdvPy_CharacterRegistry"


class CharacterRegistryError(ValueError):
    pass


def exact(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise CharacterRegistryError("登记字段不完整或存在未知字段")
    return value


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise CharacterRegistryError("登记数值必须有限")
    return float(value)


def vector(value, count):
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise CharacterRegistryError("登记向量维度不正确")
    return tuple(finite(v) for v in value)


def path(value):
    if not isinstance(value, str) or not re.fullmatch(r"\|[A-Za-z_][A-Za-z_0-9]*(?:\|[A-Za-z_][A-Za-z_0-9]*)*", value):
        raise CharacterRegistryError("当前登记仅支持无 namespace 的明确 DAG 路径")
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]*", value):
        raise CharacterRegistryError("登记语义标识无效")
    return value


@dataclass(frozen=True)
class CharacterChannel:
    key: str
    node: str
    attribute: str
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class CharacterNode:
    path: str
    uuid: str
    node_type: str
    parent: str | None
    inputs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CharacterBindJoint:
    path: str
    parent: str | None
    matrix: tuple[float, ...]


@dataclass(frozen=True)
class CharacterRegistration:
    body_root: str
    container: str
    channels: tuple[CharacterChannel, ...]
    body: tuple[CharacterBindJoint, ...]
    nodes: tuple[CharacterNode, ...]
    spine: BodySpinePlan | BodySplinePlan
    spaces: BodyControlSpacesPlan

    @property
    def compatibility_digest(self):
        # UUIDs and absolute paths identify scene objects, not pose semantics.
        value = {"body": [(j.path.split("|")[-1], j.parent.split("|")[-1] if j.parent else None, tuple(float(v) for v in j.matrix)) for j in self.body],
                 "channels": [(c.key,float(c.minimum) if c.minimum is not None else None,float(c.maximum) if c.maximum is not None else None) for c in self.channels],
                 "lengths": tuple(float(v) for v in self.spine.lengths), "spaces": [s.key for s in self.spaces.spaces]}
        return digest(value)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CharacterRegistryError("JSON 字段重复")
        result[key] = value
    return result


def safe_json(text, *, max_bytes=2_000_000):
    if not isinstance(text, str) or len(text.encode("utf-8")) > max_bytes:
        raise CharacterRegistryError("登记 JSON 类型或大小无效")
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CharacterRegistryError("JSON 非有限数值")))
    except (ValueError, TypeError, RecursionError) as exc:
        raise CharacterRegistryError("无效登记 JSON") from exc


def encode_registration(registration):
    payload = asdict(registration)
    version = VERSION
    if isinstance(registration.spine, BodySplinePlan):
        version = 2
        payload["spine_kind"] = "spline"
    value = {"format":FORMAT,"version":version,"payload":payload,"digest":digest(payload)}
    text = canonical(value)
    decode_registration(text)
    return text


def decode_registration(text):
    doc = exact(safe_json(text), ("format","version","payload","digest"))
    if doc["format"] != FORMAT or type(doc["version"]) is not int or doc["version"] not in (1, 2):
        raise CharacterRegistryError("不支持的角色登记版本")
    spline_document = doc["version"] == 2
    data = exact(doc["payload"], ("body_root","container","channels","body","nodes","spine","spaces") + (("spine_kind",) if spline_document else ()))
    if spline_document and data["spine_kind"] != "spline":
        raise CharacterRegistryError("不支持的脊柱求解类型")
    if digest(data) != doc["digest"]:
        raise CharacterRegistryError("角色登记摘要不匹配")
    try:
        root, container = path(data["body_root"]), path(data["container"])
        channels = []
        for row in data["channels"]:
            exact(row, ("key","node","attribute","minimum","maximum"))
            low = finite(row["minimum"]) if row["minimum"] is not None else None
            high = finite(row["maximum"]) if row["maximum"] is not None else None
            if low is not None and high is not None and low > high:
                raise CharacterRegistryError("通道范围无效")
            attribute = identifier(row["attribute"])
            if "." in attribute:
                raise CharacterRegistryError("通道必须是单一属性")
            channels.append(CharacterChannel(identifier(row["key"]),path(row["node"]),attribute,low,high))
        if not channels or len({c.key for c in channels}) != len(channels) or len({(c.node,c.attribute) for c in channels}) != len(channels):
            raise CharacterRegistryError("控制通道为空或重复")
        body = []
        for row in data["body"]:
            exact(row,("path","parent","matrix"))
            body.append(CharacterBindJoint(path(row["path"]),path(row["parent"]) if row["parent"] else None,vector(row["matrix"],16)))
        if (not 2 <= len(body) <= 256 if spline_document else len(body) not in (30,70)) or len({j.path for j in body}) != len(body) or {j.path for j in body if j.parent is None} != {root}:
            raise CharacterRegistryError("登记身体数量或根节点无效")
        paths = {j.path for j in body}
        if any(j.parent and (j.parent not in paths or j.path.rsplit("|",1)[0] != j.parent) for j in body):
            raise CharacterRegistryError("Body 父链无效")
        nodes = []
        for row in data["nodes"]:
            exact(row,("path","uuid","node_type","parent","inputs"))
            if row["node_type"] not in ("transform","joint") or not isinstance(row["uuid"],str) or not row["uuid"]:
                raise CharacterRegistryError("登记节点类型或 UUID 无效")
            inputs = []
            for pair in row["inputs"]:
                if not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(v,str) and v for v in pair):
                    raise CharacterRegistryError("登记输入连接无效")
                inputs.append(tuple(pair))
            if len({p[0] for p in inputs})!=len(inputs):
                raise CharacterRegistryError("登记输入连接重复")
            nodes.append(CharacterNode(path(row["path"]),row["uuid"],row["node_type"],path(row["parent"]) if row["parent"] else None,tuple(inputs)))
        if len({n.path for n in nodes}) != len(nodes) or len({n.uuid for n in nodes}) != len(nodes):
            raise CharacterRegistryError("登记节点身份重复")
        if spline_document:
            from .spline_registration import decode_spline
            spine = decode_spline(data["spine"], tuple(body))
            joints = spine.joints
            values = {"fk_controls": spine.fk_controls, "body_joints": spine.body_joints,
                      "root_path": spine.root_path, "pelvis_control": spine.pelvis_control,
                      "chest_space": spine.chest_space, "curve": spine.curve}
        else:
            raw = exact(data["spine"], (f.name for f in fields(BodySpinePlan)))
            joints = []
            for row in raw["joints"]:
                exact(row,(f.name for f in fields(BodyLimbMechanismJointSpec)))
                node = path(row["path"])
                if row["name"] != node.split("|")[-1]:
                    raise CharacterRegistryError("Spine 关节名称与路径不一致")
                axes = tuple(vector(v,3) for v in row["world_axes"])
                if len(axes) != 3:
                    raise CharacterRegistryError("Spine 朝向维度错误")
                joints.append(BodyLimbMechanismJointSpec(BodyLimbMechanismRole(row["role"]),FitBuildSide(row["side"]),path(row["source_joint"]),node,row["name"],path(row["parent_path"]),vector(row["world_position"],3),axes))
            if len(joints) != 6 or tuple(j.role.value for j in joints) != ("fk",)*3+("ik",)*3:
                raise CharacterRegistryError("Spine 机制链不完整")
            values = {k:path(v) for k,v in raw.items() if k not in ("joints","fk_controls","body_joints","pole_position","lengths")}
            for key in ("fk_controls","body_joints"):
                values[key] = tuple(path(p) for p in raw[key])
                if len(values[key]) != 3:
                    raise CharacterRegistryError("Spine 三关节合同无效")
            lengths = vector(raw["lengths"],2)
            if min(lengths) <= 0:
                raise CharacterRegistryError("Spine 骨段长度必须为正")
            spine = BodySpinePlan(**values,joints=tuple(joints),pole_position=vector(raw["pole_position"],3),lengths=lengths)
        raw_spaces = exact(data["spaces"],("body_root","spaces"))
        spaces = []
        for row in raw_spaces["spaces"]:
            exact(row,(f.name for f in fields(BodyControlSpaceSpec)))
            key = row["key"]
            if key not in ("head","hand_R","hand_L","foot_R","foot_L") or type(row["rotation_only"]) is not bool or row["rotation_only"] != (key=="head") or row["initial_mode"] not in ("body","global"):
                raise CharacterRegistryError("控制空间描述无效")
            targets = tuple(path(p) for p in row["targets"])
            if len(targets) != (1 if key=="head" else 2):
                raise CharacterRegistryError("控制空间目标不完整")
            spaces.append(BodyControlSpaceSpec(key,targets,path(row["body_source"]),path(row["global_source"]),row["rotation_only"],row["initial_mode"]))
        if len(spaces)!=5 or len({s.key for s in spaces})!=5 or raw_spaces["body_root"] != root or spine.body_joints[0] != root:
            raise CharacterRegistryError("空间或脊柱角色根不一致")
        required = {root,container,*(c.node for c in channels),*paths,*values["fk_controls"],*values["body_joints"],*(j.path for j in joints)}
        required.update(v for v in values.values() if isinstance(v,str))
        if spline_document:
            required.update(spine.targets)
            required.update(spine.ik_outputs[1:])
        required.update(p for s in spaces for p in (*s.targets,s.body_source,s.global_source))
        if not required.issubset({n.path for n in nodes}):
            raise CharacterRegistryError("登记缺少操作节点身份")
        return CharacterRegistration(root,container,tuple(channels),tuple(body),tuple(nodes),spine,BodyControlSpacesPlan(root,tuple(spaces)))
    except (TypeError, KeyError, ValueError) as exc:
        raise CharacterRegistryError(str(exc)) from exc
