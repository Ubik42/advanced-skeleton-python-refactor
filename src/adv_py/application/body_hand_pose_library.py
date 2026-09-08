from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import unicodedata

from adv_py.application.body_hand_pose_io import (
    BodyHandPoseDocumentHost,
    BodyHandPoseExportPlan,
    BodyHandPoseExportResult,
    BodyHandPoseImportPlan,
    BodyHandPoseImportResult,
    ExportBodyHandPose,
    ImportBodyHandPose,
)
from adv_py.core.body_hand_pose_io import (
    BodyHandPoseDocument,
    BodyHandPoseDocumentValidationError,
    body_hand_pose_document_from_json,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide


BODY_HAND_POSE_PRESET_SUFFIX = ".handpose.json"
_INVALID_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset({
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
})


@dataclass(frozen=True, slots=True)
class BodyHandPosePreset:
    name: str
    path: Path
    document: BodyHandPoseDocument


@dataclass(frozen=True, slots=True)
class BodyHandPosePresetLibrary:
    directory: Path
    presets: tuple[BodyHandPosePreset, ...]


@dataclass(frozen=True, slots=True)
class BodyHandPosePresetSavePlan:
    name: str
    destination: Path
    export_plan: BodyHandPoseExportPlan


@dataclass(frozen=True, slots=True)
class BodyHandPosePresetSaveResult:
    plan: BodyHandPosePresetSavePlan
    export_result: BodyHandPoseExportResult


@dataclass(frozen=True, slots=True)
class BodyHandPosePresetApplyPlan:
    preset: BodyHandPosePreset
    import_plan: BodyHandPoseImportPlan

    @property
    def changed_channel_count(self) -> int:
        return self.import_plan.changed_channel_count


@dataclass(frozen=True, slots=True)
class BodyHandPosePresetApplyResult:
    plan: BodyHandPosePresetApplyPlan
    import_result: BodyHandPoseImportResult

    @property
    def changed_channel_count(self) -> int:
        return self.import_result.changed_channel_count


class InspectBodyHandPosePresetLibrary:
    def execute(
        self,
        directory: str | os.PathLike[str],
    ) -> BodyHandPosePresetLibrary:
        catalog = _catalog_directory(directory)
        presets = tuple(
            _load_preset(name, path)
            for name, path in _preset_entries(catalog)
        )
        return BodyHandPosePresetLibrary(catalog, presets)


class SaveBodyHandPosePreset:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._exporter = ExportBodyHandPose(host)

    def plan(
        self,
        directory: str | os.PathLike[str],
        name: str,
        **inspection_options,
    ) -> BodyHandPosePresetSavePlan:
        catalog = _catalog_directory(directory)
        canonical_name = _preset_name(name)
        destination = _new_preset_path(catalog, canonical_name)
        export_plan = self._exporter.plan(
            destination,
            **inspection_options,
        )
        return BodyHandPosePresetSavePlan(
            canonical_name,
            destination,
            export_plan,
        )

    def apply(
        self,
        directory: str | os.PathLike[str],
        name: str,
        **inspection_options,
    ) -> BodyHandPosePresetSaveResult:
        catalog = _catalog_directory(directory)
        canonical_name = _preset_name(name)
        destination = _new_preset_path(catalog, canonical_name)
        export_result = self._exporter.apply(
            destination,
            **inspection_options,
        )
        plan = BodyHandPosePresetSavePlan(
            canonical_name,
            destination,
            export_result.plan,
        )
        return BodyHandPosePresetSaveResult(plan, export_result)


class ApplyBodyHandPosePreset:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._importer = ImportBodyHandPose(host)

    def plan(
        self,
        directory: str | os.PathLike[str],
        name: str,
        *,
        keyframe: bool = False,
        target_side: FitBuildSide | None = None,
        **inspection_options,
    ) -> BodyHandPosePresetApplyPlan:
        catalog = _catalog_directory(directory)
        requested_name = _preset_name(name)
        canonical_name, path = _existing_preset_entry(
            catalog,
            requested_name,
        )
        preset = _load_preset(canonical_name, path)
        import_plan = self._importer.plan(
            path,
            keyframe=keyframe,
            target_side=target_side,
            **inspection_options,
        )
        if import_plan.document != preset.document:
            raise FitSkeletonValidationError(
                "Hand Pose 预设在应用预演期间发生变化"
            )
        return BodyHandPosePresetApplyPlan(preset, import_plan)

    def apply(
        self,
        directory: str | os.PathLike[str],
        name: str,
        *,
        keyframe: bool = False,
        target_side: FitBuildSide | None = None,
        **inspection_options,
    ) -> BodyHandPosePresetApplyResult:
        catalog = _catalog_directory(directory)
        requested_name = _preset_name(name)
        canonical_name, path = _existing_preset_entry(
            catalog,
            requested_name,
        )
        try:
            import_result = self._importer.apply(
                path,
                keyframe=keyframe,
                target_side=target_side,
                **inspection_options,
            )
        except BodyHandPoseDocumentValidationError as error:
            raise FitSkeletonValidationError(
                f"Hand Pose 命名预设损坏：{path.name}"
            ) from error
        preset = BodyHandPosePreset(
            canonical_name,
            path,
            import_result.plan.document,
        )
        plan = BodyHandPosePresetApplyPlan(preset, import_result.plan)
        return BodyHandPosePresetApplyResult(plan, import_result)


def _catalog_directory(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FitSkeletonValidationError(
            "Hand Pose 预设目录路径无效"
        ) from error
    if not path.is_dir():
        raise FitSkeletonValidationError("Hand Pose 预设目录不存在")
    return path


def _preset_name(value: str) -> str:
    if not isinstance(value, str):
        raise FitSkeletonValidationError("Hand Pose 预设名称必须是字符串")
    name = unicodedata.normalize("NFC", value)
    if not name or name != name.strip() or len(name) > 64:
        raise FitSkeletonValidationError(
            "Hand Pose 预设名称必须为 1–64 个字符且首尾无空白"
        )
    if (
        name in {".", ".."}
        or name.endswith(".")
        or any(character in _INVALID_FILENAME_CHARACTERS for character in name)
        or any(
            unicodedata.category(character) in {"Cc", "Cf"}
            for character in name
        )
    ):
        raise FitSkeletonValidationError(
            "Hand Pose 预设名称包含文件系统不安全字符"
        )
    if name.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES:
        raise FitSkeletonValidationError(
            "Hand Pose 预设名称是 Windows 保留名称"
        )
    return name


def _preset_entries(directory: Path) -> tuple[tuple[str, Path], ...]:
    entries = []
    names = set()
    suffix = BODY_HAND_POSE_PRESET_SUFFIX.casefold()
    try:
        candidates = tuple(directory.iterdir())
    except OSError as error:
        raise FitSkeletonValidationError(
            "Hand Pose 预设目录无法读取"
        ) from error
    for path in candidates:
        if not path.name.casefold().endswith(suffix):
            continue
        if path.is_symlink() or not path.is_file():
            raise FitSkeletonValidationError(
                f"Hand Pose 预设必须是目录内普通文件：{path.name}"
            )
        raw_name = path.name[:-len(BODY_HAND_POSE_PRESET_SUFFIX)]
        name = _preset_name(raw_name)
        key = name.casefold()
        if key in names:
            raise FitSkeletonValidationError(
                "Hand Pose 预设目录包含大小写或 Unicode 冲突名称"
            )
        names.add(key)
        entries.append((name, path))
    return tuple(sorted(entries, key=lambda item: (item[0].casefold(), item[0])))


def _new_preset_path(directory: Path, name: str) -> Path:
    if any(
        existing_name.casefold() == name.casefold()
        for existing_name, _path in _preset_entries(directory)
    ):
        raise FitSkeletonValidationError("Hand Pose 预设名称已存在，拒绝覆盖")
    return directory / f"{name}{BODY_HAND_POSE_PRESET_SUFFIX}"


def _existing_preset_entry(
    directory: Path,
    name: str,
) -> tuple[str, Path]:
    matches = tuple(
        (existing_name, path)
        for existing_name, path in _preset_entries(directory)
        if existing_name.casefold() == name.casefold()
    )
    if len(matches) != 1:
        raise FitSkeletonValidationError("Hand Pose 命名预设不存在")
    return matches[0]


def _load_preset(name: str, path: Path) -> BodyHandPosePreset:
    try:
        document = body_hand_pose_document_from_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise FitSkeletonValidationError(
            f"Hand Pose 命名预设损坏：{path.name}"
        ) from error
    return BodyHandPosePreset(name, path, document)
