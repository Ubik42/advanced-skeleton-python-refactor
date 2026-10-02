"""asRlaChild / nonPartRlaChild, ADV 6.925 MEL 26125–26195."""
from fnmatch import fnmatchcase


def original_rla_child(commands, joint):
    tolerance = .01 * (commands.getAttr('FitSkeleton.sx')
                       if commands.objExists('FitSkeleton') else 1.)
    position = commands.xform(joint, query=True, worldSpace=True, translation=True)
    center = -tolerance < position[0] < tolerance
    children = commands.listRelatives(joint, children=True, type='joint') or []
    selected = ''
    for child in children:
        x = commands.xform(child, query=True, worldSpace=True, translation=True)[0]
        if center == (-tolerance < x < tolerance):
            selected = child
            break
    for marker, preferred in (('Head', 'Head'), ('Ankle', 'Toes'),
                              ('Toes', 'Toes'), ('Root', 'Spine')):
        if marker in joint:
            for child in children:
                if preferred in child:
                    selected = child
    return selected


def original_non_part_rla_child(commands, joint):
    child = original_rla_child(commands, joint)
    if not child or not fnmatchcase(child, '*Part[0-9]*'):
        return child
    # Maya allDescendents is grandchildren before children. The MEL loop
    # reverses that exact discovery order, rather than sorting by DAG path.
    descendants = commands.listRelatives(child, allDescendents=True, type='joint') or []
    return next((node for node in reversed(descendants)
                 if not fnmatchcase(node, '*Part[0-9]*')), '')
