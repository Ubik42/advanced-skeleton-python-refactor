"""Exact GameSkeleton axis rotations from ADV 6.925 MEL 62359."""


def original_game_joint_rotations(primary, secondary):
    if primary == secondary:
        raise ValueError('Primary and Secondary Axis can not be the same')
    return {
        ('X','Z'):((-90.,0.,0.),),
        ('Y','X'):((0.,180.,-90.),),
        ('Y','Z'):((0.,-90.,-90.),),
        ('Z','X'):((0.,90.,0.), (0.,0.,90.)),
        ('Z','Y'):((0.,90.,0.),),
    }.get((primary, secondary), ())
