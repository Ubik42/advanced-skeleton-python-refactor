"""Small user-authored specifications shared by product entrances."""
from __future__ import annotations

from pathlib import Path

from adv_py.core.character_registry import safe_json
from adv_py.core.skin_weight_io import (SkinWeightPathMapping,
    SkinWeightInfluenceMapping)


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
