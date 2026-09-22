"""Append-only, content-addressed library for portable face target assets."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import tempfile

from adv_py.core.character_registry import canonical, digest, exact, safe_json
from adv_py.core.face_target_asset import (FaceTargetAsset,
    FACE_TARGET_ASSET_MAX_BYTES, face_target_asset_from_json,
    face_target_asset_to_json)


_RELEASE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?")
_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_REF_FORMAT = "adv_py_face_asset_library_ref"


@dataclass(frozen=True, slots=True)
class FaceAssetLibraryEntry:
    name: str
    kind: str | None
    release: str
    object_sha256: str | None
    valid: bool
    reason: str | None = None


class FaceAssetLibrary:
    def __init__(self, directory: Path):
        self.root = Path(directory).expanduser().resolve()
        self.objects = self.root / "objects"
        self.refs = self.root / "refs"

    def _paths(self, name: str, release: str) -> Path:
        if (not isinstance(name, str) or not _NAME.fullmatch(name)
                or not isinstance(release, str) or len(release) > 64
                or not _RELEASE.fullmatch(release)):
            raise ValueError("资产名称或语义版本无效")
        return self.refs / name / (release + ".json")

    def _inside(self, path: Path) -> None:
        if path.is_symlink() or not path.parent.resolve().is_relative_to(self.root):
            raise ValueError("资产目录路径越过指定根目录")

    def _publish(self, path: Path, data: bytes) -> bool:
        self._inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._inside(path)
        handle, temporary_name = tempfile.mkstemp(prefix=".face-lib-",
            suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
                return True
            except FileExistsError:
                return False
        finally:
            temporary.unlink(missing_ok=True)

    def _reference(self, name: str, kind: str, release: str,
                   object_sha256: str) -> bytes:
        payload = {"name": name, "kind": kind, "release": release,
                   "object_sha256": object_sha256}
        return (canonical({"format": _REF_FORMAT, "version": 1,
            "payload": payload, "digest": digest(payload)}) + "\n").encode("utf-8")

    def _read(self, name: str, release: str) -> tuple[FaceAssetLibraryEntry,
                                                       FaceTargetAsset]:
        path = self._paths(name, release)
        self._inside(path)
        if path.stat().st_size > 1_000_000:
            raise ValueError("资产版本引用文件过大")
        document = exact(safe_json(path.read_text(encoding="utf-8"),
                                   max_bytes=1_000_000),
                         ("format", "version", "payload", "digest"))
        if (document["format"] != _REF_FORMAT
                or type(document["version"]) is not int
                or document["version"] != 1):
            raise ValueError("资产版本引用格式无效")
        payload = exact(document["payload"],
                        ("name", "kind", "release", "object_sha256"))
        object_hash = payload["object_sha256"]
        if (payload["name"] != name or payload["release"] != release
                or payload["kind"] not in ("expression", "viseme")
                or not isinstance(object_hash, str)
                or not _DIGEST.fullmatch(object_hash)
                or document["digest"] != digest(payload)):
            raise ValueError("资产版本引用摘要、路径或语义无效")
        object_path = self.objects / (object_hash + ".json")
        self._inside(object_path)
        if object_path.stat().st_size > FACE_TARGET_ASSET_MAX_BYTES:
            raise ValueError("资产对象文件超过 64 MB")
        raw = object_path.read_bytes()
        if sha256(raw).hexdigest() != object_hash:
            raise ValueError("资产对象文件内容摘要不匹配")
        asset = face_target_asset_from_json(raw.decode("utf-8"))
        if asset.name != name or asset.kind.value != payload["kind"]:
            raise ValueError("资产对象与版本引用的通道语义不一致")
        return FaceAssetLibraryEntry(name, asset.kind.value, release,
                                     object_hash, True), asset

    def list(self) -> tuple[FaceAssetLibraryEntry, ...]:
        if not self.refs.exists():
            return ()
        if not self.refs.is_dir():
            raise NotADirectoryError(self.refs)
        entries = []
        for directory in sorted(self.refs.iterdir()):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                name, release = directory.name, path.stem
                try:
                    entry, _ = self._read(name, release)
                    entries.append(entry)
                except (OSError, ValueError, UnicodeError) as error:
                    entries.append(FaceAssetLibraryEntry(name, None, release,
                        None, False, str(error)))
        return tuple(entries)

    def add(self, asset: FaceTargetAsset, release: str) -> FaceAssetLibraryEntry:
        text = face_target_asset_to_json(asset)
        path = self._paths(asset.name, release)
        prior = self.list()
        if any(not entry.valid for entry in prior):
            raise ValueError("资产目录含损坏引用，先修复再添加版本")
        if any(entry.name == asset.name and entry.kind != asset.kind.value
               for entry in prior):
            raise ValueError("同名资产已有其他面部语义类别")
        if path.exists():
            entry, current = self._read(asset.name, release)
            if current == asset:
                return entry
            raise FileExistsError("同名版本已指向其他资产内容")
        data = (text + "\n").encode("utf-8")
        object_hash = sha256(data).hexdigest()
        object_path = self.objects / (object_hash + ".json")
        if not self._publish(object_path, data):
            if (object_path.stat().st_size > FACE_TARGET_ASSET_MAX_BYTES
                    or object_path.read_bytes() != data):
                raise ValueError("内容地址与现有资产对象不一致")
        reference = self._reference(asset.name, asset.kind.value,
                                    release, object_hash)
        if not self._publish(path, reference) and path.read_bytes() != reference:
            raise FileExistsError("同名版本已指向其他资产内容")
        entry, loaded = self._read(asset.name, release)
        if loaded != asset:
            raise RuntimeError("登记后的资产文件读回不一致")
        return entry

    def resolve(self, name: str, release: str) -> FaceTargetAsset:
        return self._read(name, release)[1]
