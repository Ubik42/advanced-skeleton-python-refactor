"""ADV 6.925 controller identity and Set Axis options, MEL 5684 / 25910.

The controller's frame is established by Maya's native aimConstraint on
CustomOrient, not by an Euler reconstruction or a rotateAxis edit.
"""
from dataclasses import dataclass


AXES = ('X', 'Y', 'Z', '-X', '-Y', '-Z')


@dataclass(frozen=True, slots=True)
class OriginalControlIdentity:
    role: str
    kind: str
    name: str
    side: str


def original_control_identity(role):
    """asInfoFromCtrl uses successive prefix tests, then MEL tokenize.

    In particular IKLocal/IKhybrid override IK and BendMid overrides Bend.
    The source takes the first two nonempty underscore tokens, even when an
    authored control name contains more; do not substitute rsplit here.
    """
    role = role.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    kind = ''
    for prefix, value in (
        ('FK', 'FK'), ('IK', 'IK'), ('IKLocal', 'IKLocal'),
        ('Root', 'Root'), ('Pole', 'Pole'), ('Bend', 'Bend'),
        ('Tweaker', 'Tweaker'), ('BendMid', 'BendMid'),
        ('IKhybrid', 'IKhybrid'), ('Micro', 'Micro'),
        ('RootX', 'Root'), ('HipSwinger', 'HipSwinger'),
    ):
        if role.startswith(prefix):
            kind = value
    if 'Extra' in role:
        kind += 'Extra'
    tokens = [token for token in role[len(kind):99].split('_') if token]
    return OriginalControlIdentity(role, kind, tokens[0] if tokens else '',
                                   '_' + tokens[1] if len(tokens) > 1 else '_')


def axis_vector(axis):
    index = AXES.index(axis)
    return tuple((-1. if index >= 3 else 1.) if component == index % 3 else 0.
                 for component in range(3))


@dataclass(frozen=True, slots=True)
class OriginalControlOrientOptions:
    primary: str = 'X'
    secondary: str = 'Y'
    world_orient: bool = False
    world_match: bool = False
    curve_unaffected: bool = False
    mirror: bool = False
    mirrored_behaviour: bool = False
    mirrored_translate: bool = False

    def __post_init__(self):
        if self.primary not in AXES or self.secondary not in AXES:
            raise ValueError('控制器轴必须为 X/Y/Z/-X/-Y/-Z')
        if AXES.index(self.primary) % 3 == AXES.index(self.secondary) % 3:
            raise ValueError('Primary 与 Secondary 不能位于同一坐标轴')

    def aim_vectors(self, *, reverse=False):
        primary = 'X' if self.world_orient or self.world_match else self.primary
        secondary = 'Z' if self.world_orient or self.world_match else self.secondary
        aim, up = axis_vector(primary), axis_vector(secondary)
        if reverse and self.mirrored_behaviour:
            if not (self.world_orient or self.world_match):
                aim = tuple(-value for value in aim)
            up = tuple(-value for value in up)
        object_up = (0., 0., 1.) if abs(aim[1]) == 1. else (0., 1., 0.)
        return aim, up, object_up
