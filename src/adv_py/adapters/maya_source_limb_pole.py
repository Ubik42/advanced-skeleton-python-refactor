"""Native ADV RP Pole placer, MEL 80837–80877.

The pure planner supplies a preview; this host boundary uses the actual
source joints and Maya constraints for the final controller position.
"""
from math import dist


def _temporary_id(commands, node):
    # UUID survives Maya parenting even if the old full DAG path no longer
    # exists. UUID lookup itself must bypass character name prefixing.
    return commands.ls(node, uuid=True)[0]


def _delete_temporary(commands, uuid):
    if uuid is None:
        return
    raw = getattr(commands, 'raw', commands)
    nodes = raw.ls(uuid, long=True) or []
    if nodes:
        raw.delete(nodes)


def _mocap_matching_shift(host, binding, root, height):
    """MEL 10860–10900: 15-degree bend determines the backwards shift axis."""
    c = host._cmds
    middle = binding.joints[binding.middle_index]
    end = binding.joints[binding.primary_count - 1]
    first = c.spaceLocator()[0]
    first_id = _temporary_id(c, first)
    second = None
    second_id = None
    try:
        first = c.parent(first, middle.fk_driver, relative=True)[0]
        second = c.spaceLocator()[0]
        second_id = _temporary_id(c, second)
        second = c.parent(second, end.fk_driver, relative=True)[0]
        second = c.parent(second, first, absolute=True)[0]
        position = tuple(c.getAttr(second + '.translate')[0])
        magnitude = tuple(abs(value) for value in position)
        primary = 'X'
        if magnitude[1] > magnitude[0] and magnitude[1] > magnitude[2]:primary = 'Y'
        if magnitude[2] > magnitude[0] and magnitude[2] > magnitude[1]:primary = 'Z'
        orient = tuple(c.getAttr(middle.body + '.jointOrient')[0])
        if (c.objExists('FitSkeleton.useOffsetParentMatrix')
                and c.getAttr('FitSkeleton.useOffsetParentMatrix')):
            from .maya_original_transform_channels import original_matrix_transform_values
            orient = original_matrix_transform_values(c, middle.body, 'offsetParentMatrix', 'rotate')
        largest = 0.
        # Strict comparisons retain MEL's tie behavior; no invented fallback
        # axis or angle is substituted for an authored zero/ambiguous bend.
        for index,value in enumerate(orient):
            if all(abs(value) > abs(other) for j,other in enumerate(orient) if j != index):
                largest = value
        factor = 15. / abs(largest)
        c.setAttr(first + '.rotate', *(value * factor for value in orient), type='float3')
        second = c.parent(second, world=True, absolute=True)[0]
        c.setAttr(first + '.rotate', 0., 0., 0., type='float3')
        second = c.parent(second, first, absolute=True)[0]
        c.setAttr(second + '.translate' + primary, 0.)
        position = tuple(c.getAttr(second + '.translate')[0])
        magnitude = tuple(abs(value) for value in position)
        shift = 'Y'
        if magnitude[0] > magnitude[1] and magnitude[0] > magnitude[2]:shift = 'X'
        if magnitude[2] > magnitude[0] and magnitude[2] > magnitude[1]:shift = 'Z'
        polarity = -1. if c.getAttr(second + '.translate' + shift) < 0 else 1.
        root = c.parent(root, middle.fk_driver, absolute=True)[0]
        c.setAttr(root + '.translate', 0., 0., 0., type='float3')
        c.setAttr(root + '.translate' + shift, height / 10. * polarity)
        return c.parent(root, world=True, absolute=True)[0]
    finally:
        _delete_temporary(c, second_id)
        _delete_temporary(c, first_id)


def sample_original_matching_pole(host, binding, weights, *, baking_mocap=False):
    """asAlignFKIK FK2IK Pole, MEL 10859–10912, evaluated by Maya.

    This is distinct from build placement: the source samples Body middle
    distance and uses Main.height / 3.333 in the world locator frame. It
    does not multiply that reach by Main's evaluated scale or invent an
    alternate aim axis for a straight FK pose.
    """
    host._require_transaction()
    c = host._cmds
    start = binding.joints[0].fk_driver
    middle = binding.joints[binding.middle_index].fk_driver
    end = binding.joints[binding.primary_count - 1].fk_driver
    root = c.spaceLocator()[0]
    root_id = _temporary_id(c, root)
    child = None
    child_id = None
    try:
        constraint = c.pointConstraint(start, end, root)[0]
        aliases = c.pointConstraint(constraint, query=True, weightAliasList=True)
        if weights is None:
            # Legacy records did not include the authored FKOffset pair.
            # Their existing distance weights remain the compatibility input.
            a = c.xform(start, query=True, worldSpace=True, translation=True)
            b = c.xform(middle, query=True, worldSpace=True, translation=True)
            d = c.xform(end, query=True, worldSpace=True, translation=True)
            weights = (dist(a, b), dist(b, d))
        c.setAttr(constraint + '.' + aliases[0], abs(weights[1]))
        c.setAttr(constraint + '.' + aliases[1], abs(weights[0]))
        c.delete(constraint)
        height = float(c.getAttr(binding.global_control + '.height'))
        if baking_mocap:
            root = _mocap_matching_shift(host, binding, root, height)
        c.aimConstraint(middle, root, aimVector=(1., 0., 0.))
        child = c.spaceLocator()[0]
        child_id = _temporary_id(c, child)
        child = c.parent(child, root, absolute=True)[0]
        c.setAttr(child + '.translate', 0., 0., 0., type='float3')
        baseline = c.xform(child, query=True, worldSpace=True, translation=True)
        body_middle = c.xform(binding.joints[binding.middle_index].body,
                              query=True, worldSpace=True, translation=True)
        reach = height / 3.333 + dist(baseline, body_middle)
        c.setAttr(child + '.translate', reach, 0., 0., type='float3')
        return tuple(c.xform(child, query=True, worldSpace=True, translation=True))
    finally:
        _delete_temporary(c, child_id)
        _delete_temporary(c, root_id)


def place_original_limb_pole(host, spec):
    host._require_transaction()
    c = host._cmds
    joints = spec.source_pole_joint_paths
    start, middle, end = joints[0], joints[spec.source_pole_middle_index], joints[-1]
    root = c.createNode("transform", name="tempPoleVecPlacer1")
    root_id = _temporary_id(c, root)
    try:
        aim = c.createNode("transform", name="tempPoleVecPlacer2", parent=root)
        point = c.createNode("transform", name="tempPoleVecPlacer3", parent=aim)
        constraint = c.pointConstraint(start, end, root)[0]
        aliases = c.pointConstraint(constraint, query=True, weightAliasList=True)
        middle_position = c.xform(middle, query=True, worldSpace=True, translation=True)
        end_position = c.xform(end, query=True, worldSpace=True, translation=True)
        c.setAttr(constraint + "." + aliases[0], dist(middle_position, end_position))
        start_position = c.xform(start, query=True, worldSpace=True, translation=True)
        c.setAttr(constraint + "." + aliases[1], dist(start_position, middle_position))
        if middle != start:
            c.aimConstraint(middle, aim, aimVector=(1, 0, 0), upVector=(0, 0, 1),
                            worldUpType="object", worldUpObject=start)
            c.setAttr(point + ".tx", spec.source_pole_length)
            base_position = c.xform(aim, query=True, worldSpace=True, translation=True)
            if dist(base_position, middle_position) < .001:
                c.delete(constraint)
                c.parent(root, start)
                c.move(0, -1, 0, root, relative=True, localSpace=True,
                       worldSpaceDistance=True)
                c.setAttr(spec.chain[1] + ".preferredAngle", 0, 0, -90, type="float3")
        else:
            c.setAttr(point + ".tz", spec.source_pole_length)
        position = tuple(c.xform(point, query=True, worldSpace=True, translation=True))
    finally:
        _delete_temporary(c, root_id)
    c.xform(spec.pole_offset_path, worldSpace=True, translation=position)
    host._transaction_changed = True
    return position
