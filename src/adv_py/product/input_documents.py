"""Small user-authored specifications shared by product entrances."""
from __future__ import annotations

from pathlib import Path

from adv_py.core.character_registry import safe_json
from adv_py.core import (FaceLandmark, FaceShapeKind, FaceTarget,
                         FaceSurfaceAlignment)
from adv_py.core.skin_weight_io import (SkinWeightPathMapping,
    SkinWeightInfluenceMapping)
from adv_py.core.skin_weight_redistribution import (SkinWeightRedistribution,
    SkinWeightInfluenceRedistribution, SkinWeightRedistributionTarget)


def load_skin_path_mapping(path: Path) -> SkinWeightPathMapping:
    source = Path(path).expanduser()
    if source.stat().st_size > 64_000:
        raise ValueError("蒙皮映射文档超过 64 KB")
    document = safe_json(source.read_text(encoding="utf-8"), max_bytes=64_000)
    if (not isinstance(document, dict)
            or set(document) != {"target_skin", "target_mesh", "influences"}
            or not isinstance(document["influences"], list)
            or not 1 <= len(document["influences"]) <= 256):
        raise ValueError("蒙皮映射文档须包含目标 Skin、网格及 1–256 个影响关节对应")
    rows = []
    for entry in document["influences"]:
        if not isinstance(entry, dict) or set(entry) != {"source", "target"}:
            raise ValueError("影响关节映射须包含 source 和 target")
        rows.append(SkinWeightInfluenceMapping(entry["source"], entry["target"]))
    return SkinWeightPathMapping(document["target_skin"],
                                 document["target_mesh"], tuple(rows))


def load_skin_redistribution(path: Path) -> SkinWeightRedistribution:
    source = Path(path).expanduser()
    if source.stat().st_size > 512_000:
        raise ValueError("影响重分配文档超过 512 KB")
    document = safe_json(source.read_text(encoding="utf-8"), max_bytes=512_000)
    if (not isinstance(document, dict)
            or set(document) != {"target_skin", "target_mesh", "target_influences", "influences"}
            or not isinstance(document["target_influences"], list)
            or not isinstance(document["influences"], list)
            or not 1 <= len(document["target_influences"]) <= 512
            or not 1 <= len(document["influences"]) <= 512):
        raise ValueError("影响重分配文档须声明目标 Skin、网格和完整影响集合")
    rows = []
    for row in document["influences"]:
        if (not isinstance(row, dict) or set(row) != {"source", "targets"}
                or not isinstance(row["targets"], list)
                or not 1 <= len(row["targets"]) <= 512):
            raise ValueError("每个源影响关节须声明 1–512 个目标与比例")
        targets = []
        for target in row["targets"]:
            if not isinstance(target, dict) or set(target) != {"path", "fraction"}:
                raise ValueError("重分配目标须包含 path 和 fraction")
            targets.append(SkinWeightRedistributionTarget(
                target["path"], target["fraction"]))
        rows.append(SkinWeightInfluenceRedistribution(row["source"], tuple(targets)))
    return SkinWeightRedistribution(document["target_skin"], document["target_mesh"],
        tuple(document["target_influences"]), tuple(rows))


def load_surface_alignment(path: Path) -> FaceSurfaceAlignment:
    source = Path(path).expanduser()
    if source.stat().st_size > 4096:
        raise ValueError("刚体对齐文档超过 4 KB")
    spec = safe_json(source.read_text(encoding="utf-8"), max_bytes=4096)
    if (not isinstance(spec, dict)
            or set(spec) != {"pairs", "max_residual"}
            or not isinstance(spec["pairs"], list)):
        raise ValueError("刚体对齐文档须包含 pairs 和 max_residual")
    return FaceSurfaceAlignment(tuple(tuple(row) if isinstance(row, list) else row
                                     for row in spec["pairs"]), spec["max_residual"])


def _face_document(path: Path) -> dict:
    source = Path(path).expanduser()
    if source.stat().st_size > 1_000_000:
        raise ValueError("面部输入文档超过 1 MB")
    return safe_json(source.read_text(encoding="utf-8"), max_bytes=1_000_000)


def load_face_landmarks(path: Path) -> tuple[FaceLandmark, ...]:
    document = _face_document(path)
    if not isinstance(document, dict) or set(document) != {"landmarks"}:
        raise ValueError("顶点标记文档必须只含 landmarks 字段")
    rows = document["landmarks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("landmarks 须包含 1–128 个标记")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"vertex", "displacement", "radius"}:
            raise ValueError("单个标记须包含 vertex、displacement 和 radius")
        if not isinstance(row["displacement"], list):
            raise ValueError("标记位移必须是三个数值的数组")
        result.append(FaceLandmark(row["vertex"], tuple(row["displacement"]),
                                   row["radius"]))
    return tuple(result)


def load_face_build_spec(path: Path) -> tuple[str, tuple[FaceTarget, ...]]:
    document = _face_document(path)
    if (not isinstance(document, dict) or set(document) != {"neutral", "targets"}
            or not isinstance(document["neutral"], str)
            or not isinstance(document["targets"], list)
            or not 1 <= len(document["targets"]) <= 128):
        raise ValueError("面部构建文档须包含 neutral 和 1–128 个 targets")
    targets = []
    for row in document["targets"]:
        if not isinstance(row, dict) or set(row) != {"name", "kind", "mesh"}:
            raise ValueError("面部目标须包含 name、kind 和 mesh")
        targets.append(FaceTarget(row["name"], FaceShapeKind(row["kind"]),
                                  row["mesh"]))
    return document["neutral"], tuple(targets)
