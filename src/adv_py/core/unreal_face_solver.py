"""Native FaceRig version 2 sampling rules, MEL 60804–61933."""
from dataclasses import dataclass


TOLERANCE = .0001
SAMPLED_ON_FACE = {
    'upperLid_R': ('tx', 'ty', 'rz'),
    'lowerLid_R': ('tx', 'ty', 'rz'),
    'upperLip_M': ('tx', 'ty', 'tz', 'rx'),
    'lowerLip_M': ('tx', 'ty', 'tz', 'rx'),
    'EyeBrowInner_R': ('tx', 'ty', 'tz', 'rx', 'ry', 'rz'),
}
LOOK_AT_CONTROLS = ('Eye_R', 'Eye_L', 'AimEye_M', 'AimEye_R', 'AimEye_L')
DIRECT_FACE_CONTROLS = frozenset((
    'Eye_R', 'Eye_L', 'NoseCrease_M', 'NoseBridge_M', 'Nose_M',
    'NoseUnder_M', 'ChinCrease_M',
    *(name + '_' + side for name in (
        'NoseSide', 'Nostril', 'NoseCorner', 'SmileBulge', 'FrownBulge',
        'Cheek', 'CheekBone', 'EyeBrowMid1', 'EyeBrowMid2', 'EyeBrowMid3',
        'EyeBrowOuter') for side in ('R', 'L')),
))


def face_solver_filename(export_file: str) -> str:
    if not export_file:
        return ''
    slash = max(export_file.rfind('/'), export_file.rfind('\\'))
    dot = export_file.rfind('.')
    base = export_file
    if dot > slash:
        if export_file[dot:].lower() == '.json':
            return export_file
        base = export_file[:dot]
    return base + ('.json' if base.lower().endswith('_facerig') else '_FaceRig.json')


def channel_name(attribute: str, *, driver=False) -> str:
    for short, long, label in (('t', 'translate', 'Translation'),
                              ('r', 'rotate', 'Rotation'), ('s', 'scale', 'Scale')):
        for axis in 'XYZ':
            if attribute in (short + axis.lower(), long + axis):
                return ('Value' if driver and short == 't' else label) + '.' + axis
    return attribute


def sample_values(minimum, maximum, neutral):
    values = [minimum]
    def add(value):
        if not any(abs(existing - value) < TOLERANCE for existing in values):
            values.append(value)
    if minimum <= 0 <= maximum:
        add(0.)
    add(neutral)
    add(maximum)
    return tuple(values)


def middle_lid_index(indices):
    indices = set(index for index in indices if 0 <= index < 100)
    if not indices:
        return None
    middle = max(indices) // 2
    if middle in indices:
        return middle
    for offset in range(1, 100):
        if middle - offset in indices:
            return middle - offset
        if middle + offset in indices:
            return middle + offset
    return None


def face_control_kind(name):
    if name in ('SmilePull_R', 'SmilePull_L'):
        return 'driverAlias'
    if name == 'JawPull_M':
        return 'driverAdapter'
    if name in (*SAMPLED_ON_FACE, 'EyeBrowInner_L', 'upperLid_L', 'lowerLid_L'):
        return 'sampledDriver'
    return 'directTransform' if name in DIRECT_FACE_CONTROLS else 'unmapped'


def face_control_adapter(name):
    if name != 'JawPull_M':
        return {}
    return dict(adapter='jawPullSplit', mappings=[
        dict(source='ty', targetControl='ctrlMouth_M', targetChannel='Value.Y',
             operation='clampMax', max=0.),
        dict(source='ty', targetControl='ctrlLips_M', targetChannel='Value.Y',
             operation='clampMin', min=0.),
        dict(source='tx', targetControl='ctrlMouth_M', targetChannel='jawSide',
             operation='reuseDriver', scale=10.),
    ])


@dataclass(frozen=True)
class JointSolverSample:
    translate: tuple[float, float, float]
    scale: tuple[float, float, float]
    world_position: tuple[float, float, float]
    quaternion: tuple[float, float, float, float] = (0., 0., 0., 1.)


def positive_quaternion(values):
    return tuple(-value for value in values) if values[3] < 0 else tuple(values)


def driven_channels(joints, parents, base, samples, values):
    """Keep native local-delta precedence and row-vector rotation composition.

    Disabled joints are absent from base/samples. An affected ancestor suppresses
    inherited world translations on children with no local delta of their own.
    """
    local, rotation = {}, {}
    for joint in joints:
        if joint not in base:
            local[joint] = rotation[joint] = False
            continue
        rotation[joint] = any(abs(sample[joint].quaternion[axis] - (1. if axis == 3 else 0.)) > TOLERANCE
            for sample in samples for axis in range(4))
        local[joint] = rotation[joint] or any(
            abs(getattr(sample[joint], attr)[axis] - getattr(base[joint], attr)[axis]) > TOLERANCE
            for sample in samples for attr in ('translate', 'scale') for axis in range(3))
    result = []
    for joint in joints:
        if joint not in base:
            continue
        parent = parents.get(joint)
        ancestor_delta = False
        while parent:
            if local.get(parent, False):
                ancestor_delta = True
                break
            parent = parents.get(parent)
        for kind in ('Translation', 'Rotation', 'Scale'):
            for axis in range(1 if kind == 'Rotation' else 3):
                use_local = kind == 'Translation' and ancestor_delta and local[joint]
                if kind == 'Rotation':
                    has_delta = rotation[joint]
                    keys = [dict(x=value, value=list(sample[joint].quaternion))
                            for value, sample in zip(values, samples)]
                else:
                    deltas = []
                    for sample in samples:
                        if kind == 'Scale':
                            delta = sample[joint].scale[axis] - base[joint].scale[axis]
                        elif ancestor_delta:
                            delta = sample[joint].translate[axis] - base[joint].translate[axis] if local[joint] else 0.
                        else:
                            delta = sample[joint].world_position[axis] - base[joint].world_position[axis]
                        deltas.append(delta)
                    has_delta = any(abs(value) > TOLERANCE for value in deltas)
                    keys = [dict(x=value, y=delta) for value, delta in zip(values, deltas)]
                if not has_delta:
                    continue
                row = dict(bone=joint, channel='Rotation' if kind == 'Rotation' else kind + '.' + 'XYZ'[axis],
                    space='Local' if kind != 'Translation' or use_local else 'World',
                    mode='Additive', keys=keys)
                if kind == 'Rotation':
                    row.update(representation='quaternion', composition='restThenDelta')
                else:
                    row['multiplier'] = 1.
                result.append(row)
    return result
