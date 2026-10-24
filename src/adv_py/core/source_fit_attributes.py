"""Attribute menu and grouped removal in ADV 6.925, MEL 64–66/4205–4280."""

SOURCE_FIT_ATTRIBUTE_TYPES = (
    'twist/bendy', 'inbetween', 'global', 'aim', 'wheel', 'rollingBall',
    'freeOrient', 'worldOrient', 'flipOrient', 'noMirror', 'noFlip',
    'noControl', 'noSkin', 'ikLocal', 'hipSwinger', 'follow', 'follow*',
    'followSpaces', 'ikFollow', 'geoAttach', 'proximityPin', 'aimAt',
    'curveGuide', 'rootOptions', 'cog', 'segScaleComp', 'childOfPart',
    'control', 'tweakerControl', 'hipSwinger', 'parentConstraint',
    'pointConstraint', 'orientConstraint', 'scaleConstraint', 'footPivots',
)

_SOURCE_FIT_ATTRIBUTE_HELP = {
    'twist/bendy': 'TwistJoints & Bendy-limbs',
    'inbetween': 'Creates extra inbetween joints',
    'global': 'Keeps limbs orientation fixed',
    'aim': 'LookAt (AimConstraint)', 'wheel': 'Wheel Roller',
    'rollingBall': 'Auto Rool for Ball',
    'freeOrient': 'Free limb orientation',
    'worldOrient': 'Orient limb to world-space',
    'flipOrient': 'Reverse up-vector',
    'noMirror': 'For non-symmetrical limbs',
    'noFlip': 'Ignore Mirror behaviour',
    'noControl': 'Skips creating FK-control',
    'noSkin': 'Skips adding joint to DeformSet',
    'ikLocal': 'Local oriented IK-control',
    'follow': 'Follows another joint', 'follow*': 'Follows by name',
    'followSpaces': 'Follows Main,Root,etc',
    'ikFollow': 'IK Follows another joint',
    'geoAttach': 'Controller sticks to geometry',
    'proximityPin': 'Controller sticks to geometry',
    'aimAt': 'Aim at another control', 'curveGuide': 'For feather setup',
    'rootOptions': 'Options only for Root joint',
    'segScaleComp': 'sets the segmentScaleCompensate',
    'childOfPart': 'Make child of TwistJoint',
    'control': 'creates control for end-joint',
    'tweakerControl': 'Add a Tweaker Control',
    # MEL assigns hipSwinger twice: the later assignment is authoritative.
    'hipSwinger': 'For custom HipSwinger',
    'footPivots': 'Controllers for Foot-Pivots',
}


def source_fit_attribute_help(attribute):
    """asUpdateAttributeHelp, MEL 3649–3720, including wildcard suffix."""
    if attribute.endswith('Constraint'):
        return 'Constraint to other joint'
    return _SOURCE_FIT_ATTRIBUTE_HELP.get(attribute, '')

SOURCE_FIT_ATTRIBUTE_COMPANIONS = {
    'twist/bendy': ('twistJoints', 'bendyJoints', 'bendyCtrls', 'partControllers'),
    'inbetween': ('inbetweenJoints', 'unTwister', 'partControllers'),
    'geoAttach': ('geoAttachMode',),
    'proximityPin': ('proximityPinMode',),
    'global': ('globalTranslate',),
    'noMirror': ('noMirrorLeft',),
    'worldOrient': ('worldOrientUp', 'worldOrientForward'),
    'curveGuide': ('curveGuideMode',),
    'rootOptions': ('numMainExtras', 'legLock', 'centerBtwFeet', 'centerBetweenFeet'),
    'aimAt': ('aimAxis', 'aimUpAxis', 'aimUpObject'),
    'follow': ('followTranslate', 'followPivot', 'followScale',
               'followLeftRight', 'followWorld'),
    'orientConstraint': ('orientConstraintMaintainOffset',),
}
