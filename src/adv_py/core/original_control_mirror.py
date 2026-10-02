"""asMirror's source ordering and local-channel signs, MEL 12345–12630."""
from fnmatch import fnmatchcase


def original_mirror_order(roles, *, stiff=frozenset()):
    roles = sorted(roles)
    result = ['Main', 'RootX_M', 'RootExtraX_M'] if 'Main' in roles else []
    def append(pattern, *, only_stiff=False, exclude=None):
        result.extend(role for role in roles if fnmatchcase(role, pattern)
            and (not only_stiff or role in stiff)
            and (exclude is None or not fnmatchcase(role, exclude)))
    append('IKhybrid*')
    append('IK*Spine*', only_stiff=True)
    append('IK*Spine*')
    result.extend(role for role in roles if fnmatchcase(role, 'FK*Spine*')
                  or role in ('FKRoot_M', 'FKChest_M'))
    append('IK*', only_stiff=True, exclude='IK*Spine*')
    append('Pivot*')
    result.extend(role for role in roles if fnmatchcase(role, 'IK*Leg*')
                  or fnmatchcase(role, 'IK*Arm*'))
    append('Pole*')
    append('Roll*Heel*')
    append('Roll*ToesEnd*')
    append('Roll*Toes*')
    for index in range(10, 0, -1):
        append('Roll*' + str(index) + '*')
    append('IK*Toes_*')
    result.extend(role for role in roles if role not in result)
    return tuple(result)


def original_mirror_sign(role, attribute, *, positive_scale=True,
                         local_custom=False, ik_local=False, face=False,
                         axes_z_minus_y=False):
    if not positive_scale or face:
        return 1.
    fk = any(fnmatchcase(role, prefix + '*_' + side)
             for prefix in ('FK', 'Bend', 'Micro') for side in ('R', 'L'))
    if fk or ik_local or local_custom:
        return -1. if attribute in ('tx', 'ty', 'tz') else 1.
    return -1. if attribute in (('tx', 'ry', 'rz') if axes_z_minus_y
                               else ('tz', 'rx', 'ry')) else 1.
