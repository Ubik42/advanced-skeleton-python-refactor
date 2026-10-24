"""ADV's label palette is narrower than Maya's built-in joint label enum."""

SOURCE_FIT_UI_LABELS = (
    'Root','Chest','Mid','Hip','Foot','Heel','Toes','ToesEnd','BigToe',
    'PinkyToe','LegAim','QToes','Shoulder','Hand','0','1','2','3',
)


def source_fit_label_help(text):
    """asUpdateLabelHelp, MEL 3624–3647; retain source text and empty cases."""
    for labels, help_text in (
            (('Hand','Shoulder'), 'Hand + Shoulder = Arm IK'),
            (('Hip','Foot'), 'Hip + Foot = Leg IK'),
            (('LegAim',), 'LegAim + Hip + Foot = 3 bone Leg IK'),
            (('Heel','Toes','ToesEnd'), 'Heel + Toes + ToesEnd = FootRoll'),
            (('BigToe','PinkyToe'), 'BigToe + PinkyToe = FootRock'),
            (('QToes',), 'Quadped toes'),
            (('Root','Chest','Mid'), 'Root + Chest (+ Mid) = Spine IK'),
            (('0','1','2','3'), '0,1,2, etc.. = Spline IK (tail)')):
        if text in labels:
            return help_text
    return ''

SOURCE_FIT_LABEL_CODES = {
    'None': 0, 'Root': 1, 'Hip': 2, 'Foot': 4, 'ToesEnd': 18,
    'Shoulder': 10, 'Hand': 12, 'PropA': 15, 'PropB': 16, 'PropC': 17,
    'Other': 18, 'Chest': 18, 'Mid': 18, 'Toes': 18, 'Heel': 18,
    'BigToe': 18, 'PinkyToe': 18, 'LegAim': 18, 'QToes': 18,
    'Eye': 18, 'Wheel': 18, '0': 18, '1': 18, '2': 18, '3': 18,
}
_CODE_LABELS = {}
for _label, _code in SOURCE_FIT_LABEL_CODES.items():
    _CODE_LABELS.setdefault(_code, _label)


def source_fit_label_code(text):
    """Source lookup is case-sensitive; unlisted custom labels use Other."""
    return SOURCE_FIT_LABEL_CODES.get(text, 18)


def source_fit_label_text(code, *, visible, other_type=''):
    """asLabel ignores unknown built-in codes and preserves Other literally."""
    if not visible:
        return ''
    return other_type if code == 18 else _CODE_LABELS.get(code, '')
