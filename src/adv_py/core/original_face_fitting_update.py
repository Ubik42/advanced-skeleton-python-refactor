"""Native row order used by asFaceFittingUpdate, MEL 4572–4671.

The update traverses column layouts, then the optional frame columns. This
differs from section creation order, and from alphabetical order.
"""

ORIGINAL_FACE_FITTING_UPDATE_ROWS = (
    'EyeBall', 'EyeLidOuter', 'EyeLidMain', 'EyeLidInner',
    'LipOuter', 'LipMain', 'LipInner',
    'JawPivot', 'JawCorner', 'JawLine', 'Jaw', 'ChinCrease', 'Throat',
    'Cheek', 'CheekBone', 'SmileBulge', 'FrownBulge',
    'Nose', 'NoseUnder', 'NoseCorner', 'NoseSide', 'NoseBridge', 'Nostril',
    'EyeBrowInner', 'EyeBrowOuter', 'EyeBrowCenter', 'ForeHead',
    'Pupil', 'Iris', 'UpMidLo', 'EyeLidMain2', 'Tongue',
    'EyeBrowMid1', 'EyeBrowMid2', 'EyeBrowMid3',
)


def original_face_fit_row(label):
    for part in ('Outer', 'Main', 'Inner'):
        if label.endswith(part) and label.startswith(('EyeLid', 'Lip')):
            return label[:-len(part)], part
    return label, ''


def original_face_fit_reselect_node(section, part, *, has_non_sym=False, side=''):
    suffix = ''
    if section.endswith('_R'):
        section = section.replace('_R', '', 1)
    elif has_non_sym and side == 'Left':
        suffix = 'Left'
    return 'FaceFit' + section + part + suffix


ORIGINAL_FACE_FITTING_MANUAL_TRANSFORMS = (
    'FitEyeBall', 'FaceFitTongueLoc',
    *(f'Tongue{index}' for index in range(99)),
    'upperFace', 'middleFace', 'lowerFace',
)
