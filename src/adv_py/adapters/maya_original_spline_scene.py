"""Read original Spline correspondence; never manufacture a Python rig plan."""
from dataclasses import dataclass
from types import SimpleNamespace

from adv_py.core.character_registry import CharacterRegistryError


@dataclass(frozen=True)
class OriginalSplineAnimationBinding:
    label: str
    side: str
    physical_chain: tuple[str, ...]
    fk_controls: tuple[str, ...]
    fk_drivers: tuple[str, ...]
    ik_drivers: tuple[str, ...]
    ik_controls: tuple[str, ...]
    hybrid_controls: tuple[str, ...]
    endpoint_aligns: tuple[str, str]
    blend_plug: str
    mode_maximum: float = 10.
    native_scene: bool = True

    @property
    def controls(self):
        return tuple(dict.fromkeys((*self.fk_controls, *self.ik_controls, *self.hybrid_controls)))

    @property
    def blend_key(self):
        return self.blend_plug


def _chain(c, start, end):
    """asgetChainJoints: read the end's actual DAG ancestry in source order."""
    paths = c.ls(end, long=True) or ()
    if len(paths) != 1:
        raise CharacterRegistryError('原版 Spline 末端关节不存在或不唯一：' + end)
    segments = tuple(part for part in paths[0].split('|') if part)
    starts = c.ls(start, long=True) or ()
    if len(starts) != 1:
        raise CharacterRegistryError('原版 Spline 起点关节不存在或不唯一：' + start)
    start_leaf = starts[0].rsplit('|', 1)[-1]
    index = next((i for i in range(len(segments) - 1, -1, -1) if segments[i] == start_leaf), None)
    if index is None:
        raise CharacterRegistryError('原版 Spline 起点不在末端祖先链中：' + start)
    # Read addresses, not cached sample poses. Scoped commands handle namespace.
    return tuple('|' + '|'.join(segments[:i + 1]) for i in range(index, len(segments)))


def read(host, label, side):
    c = host._cmds
    suffix = '_' + side
    mode = 'FKIK' + label + suffix
    if not c.objExists(mode):
        raise ValueError('Object:"' + mode + '" does not exists !')
    start, middle, end = (c.getAttr(mode + '.' + name)
                          for name in ('startJoint', 'middleJoint', 'endJoint'))
    for node in ('Main', 'FKX' + start + suffix, 'IKX' + start + suffix, 'IKX' + middle + suffix):
        if not c.objExists(node):
            raise ValueError('Object:"' + node + '" does not exists !')
    if c.objExists('Main.version'):
        version = float(c.getAttr('Main.version'))
        if 6.240 < version < 6.261:
            raise ValueError('Detected Rig version:"' + str(version) + '" which has issues with Switch FK2Ik, Update to the latest version, and run "ReBuild AdvancedSkeleton" to fix this.')
    # The source reads height even though the spline branch does not use it.
    c.getAttr('Main.height')
    chain = _chain(c, start + suffix, end + suffix)
    names = tuple(path.rsplit('|', 1)[-1].rsplit(':', 1)[-1] for path in chain)
    ik = []
    for index in range(1, 99):
        node = 'IK' + label + str(index) + suffix
        if not c.objExists(node):
            break
        ik.append(node)
    if len(ik) < 2:
        raise CharacterRegistryError('原版 Spline 至少需要两个连续编号的 IK 控制器：' + mode)
    binding = OriginalSplineAnimationBinding(label, side, chain,
        tuple('FK' + name for name in names), tuple('FKX' + name for name in names),
        tuple('IKX' + name for name in names), tuple(ik),
        tuple('IKhybrid' + label + str(i) + suffix for i in range(1, len(ik) + 1)),
        ('AlignIKTo' + names[0], 'AlignIKTo' + names[-1]), mode + '.FKIKBlend')
    channels = []
    for control in binding.controls:
        if c.objExists(control):
            channels.extend(SimpleNamespace(key=control + '.' + attr, node=control, attribute=attr)
                            for attr in c.listAttr(control, keyable=True) or ())
    channels.append(SimpleNamespace(key=binding.blend_key, node=mode, attribute='FKIKBlend'))
    return SimpleNamespace(channels=tuple(channels), source_limbs=(), spine=None,
                           additional_spines=(), nodes=(), native_scene=True), binding
