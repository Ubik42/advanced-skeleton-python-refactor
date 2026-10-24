"""Literal ADV 6.925 FBX preset and Mannequin export options."""
from dataclasses import dataclass
import re


MANNEQUIN_EXPORT_CLEANUP = (
    '|root', '|Geometry', 'Mannequin', 'Manny', 'Quinn', 'UE4',
    'UE5Simple', 'UE5Full', 'asMannequinExporting', 'Cages',
    'MeshGeometry', 'MeshCurves', 'NurbsGeometry',
)

FBX_PRESET_VALUES = (
    ('PresetSelected', ''), ('BakeComplexAnimation', '1'),
    ('BakeFrameStep', '1'), ('InputConnections', '0'),
    ('IncludeChildren', '1'),
)


def source_fbx_path_from_line(line: str) -> str:
    """Literal asExtractFBXPathFromLine, MEL 26616–26669.

    Use the last extension, then the nearest preceding quote, Windows drive,
    or whitespace boundary in that order. The source does not parse MEL/XML
    escapes or require a closing quote.
    """
    extension = line.lower().rfind('.fbx')
    if extension < 0:
        return ''
    end = extension + 4
    quote = line.rfind('"', 0, extension + 1)
    if quote >= 0:
        return line[quote + 1:end]
    for index in range(extension, 0, -1):
        if line[index] == ':' and line[index + 1:index + 2] in ('/', '\\'):
            return line[index - 1:end]
    for index in range(extension, -1, -1):
        if line[index] in ' \t\r\n':
            return line[index + 1:end]
    return line[:end]


def source_fbx_path_from_history(text: str) -> str:
    """Preserve the native history loop, including its final-line overwrite."""
    filename = ''
    for line in text.splitlines(keepends=True):
        if not line:
            break
        filename = source_fbx_path_from_line(line)
    return filename


def source_fbx_preset(xml: bytes) -> bytes:
    """AS_setFbxXmlValue edits the first v attribute of each matching line.

    Keep the preset's encoding and line endings. Do not serialize its XML or
    replace another preset option: the native procedure edits these five only.
    """
    result = []
    for line in xml.splitlines(keepends=True):
        for element, value in FBX_PRESET_VALUES:
            if b'<' + element.encode('ascii') + b' ' in line:
                line = re.sub(br'v="[^"]*"', lambda _: b'v="' + value.encode('ascii') + b'"', line, count=1)
        result.append(line)
    return b''.join(result)


@dataclass(frozen=True)
class MannequinExportOptions:
    template: str = 'UE5 (Simple)'
    scale_adv_to_template: bool = True
    match_template_pose: bool = True
    remove_unused_joints: bool = True
    keep_joints: bool = False
    namespace: str = ''

    def __post_init__(self):
        from .unreal_mannequin import TEMPLATES
        if self.template not in TEMPLATES:
            raise ValueError('未知 Unreal Mannequin 模板')
        if any(type(getattr(self, key)) is not bool for key in (
                'scale_adv_to_template', 'match_template_pose',
                'remove_unused_joints', 'keep_joints')):
            raise ValueError('Mannequin 导出选项必须是布尔值')
        if (not isinstance(self.namespace, str) or self.namespace.startswith(':')
                or self.namespace.endswith(':') or '::' in self.namespace
                or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', part)
                       for part in self.namespace.split(':') if part)):
            raise ValueError('Mannequin 导出命名空间无效')
