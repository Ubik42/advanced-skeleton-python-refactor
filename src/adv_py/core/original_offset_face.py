"""Offset Face import identities and native ordered geometry policy."""
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class OriginalOffsetFaceImportOptions:
    namespace: str
    head_joint: str
    name_swap: bool = False
    search: str = '_A'
    replacement: str = '_B'

    def __post_init__(self):
        if not isinstance(self.namespace, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', self.namespace):
            raise ValueError('Offset Face 名称必须是有效且非空的 namespace')
        if not isinstance(self.head_joint, str) or not self.head_joint:
            raise ValueError('Offset Face 需要当前身体的 Head 关节')
        if type(self.name_swap) is not bool or not isinstance(self.search, str) or not isinstance(self.replacement, str):
            raise ValueError('Offset Face 名称替换参数无效')
        if self.name_swap:
            re.compile(self.search)


def original_offset_face_geometry(face, all_head):
    geometry = list(all_head.split())
    if face not in geometry:
        geometry.append(face)
    return tuple(geometry)


def original_offset_face_name_swap(name, options):
    return re.sub(options.search, options.replacement, name, count=1) if options.name_swap else name


def original_offset_face_head_choices(joints, *, has_imported_face=False):
    ordered = list(joints)
    if not has_imported_face:
        ordered.reverse()
    eligible = [joint for joint in ordered if 'MotionSystem' not in joint and 'FitSkeleton' not in joint]
    heads = [joint for joint in eligible if ':' not in joint and 'ead' in joint and 'eadEnd' not in joint]
    return tuple(heads+[joint for joint in eligible if joint not in heads])


@dataclass(frozen=True, slots=True)
class OriginalOffsetFaceLandmarks:
    vertices: tuple[str, str, str]
    max_z: int
    min_z: int
    max_y: int

    @property
    def base_vertex_indices(self):
        # Source stores selection ordinals, not mesh vertex IDs.
        return f'{self.max_z} {self.min_z} {self.max_y}'


def original_offset_face_landmarks(selection, positions):
    if not selection:
        raise ValueError('Select vertices at the center of the face')
    if any('.vtx' not in node and '.e' not in node for node in selection):
        raise ValueError('Only edges or vertices from the center of the face should be selected')
    vertices = tuple(node for node in selection if '.vtx' in node)
    if len(vertices) != 3 or len(positions) != 3:
        raise ValueError('3 vertices should be selected')
    max_y_value = max_z_value = -9999
    min_z_value = 9999
    max_y = max_z = min_z = 0
    for index, point in enumerate(positions):
        if point[1] > max_y_value:
            max_y_value, max_y = point[1], index
        if point[2] > max_z_value:
            max_z_value, max_z = point[2], index
        if point[2] < min_z_value:
            min_z_value, min_z = point[2], index
    return OriginalOffsetFaceLandmarks(vertices, max_z, min_z, max_y)
