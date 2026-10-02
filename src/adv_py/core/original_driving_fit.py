"""Original end-of-Body DrivingSystem handoff, MEL 85650–85773.

Keep source discovery order for equal nesting depth. SDK curve names retain
the source's suffix and nested blendWeighted input convention.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class OriginalDrivingFitCurve:
    source: str
    name: str
    attribute: str
    driven: str
    driven_attribute: str
    limits: tuple[float | None, float | None, float | None, float | None]
    source_uuid: str = ''
    fit_index: int | None = None
    message_index: int | None = None


@dataclass(frozen=True, slots=True)
class OriginalDrivingFitSystem:
    control: str
    curves: tuple[OriginalDrivingFitCurve, ...]
    nesting_depth: int
    fit_attribute: str = ''


def original_fit_driven_destination(curve):
    name = curve.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    name = name.replace('prefix_', '', 1)
    # MEL tokenize skips empty fields, including the trailing underscore in
    # nested names such as bwDrivingSystem1_R_driver1_input_1_.
    tokens = [token for token in name.split('_') if token]
    if len(tokens) < 2:
        raise ValueError('Fit DrivingSystem 曲线名没有被驱动属性：' + name)
    driven = tokens[0][3:] if tokens[0].startswith('SDK') else tokens[0]
    for token in tokens[1:-1]:
        if token == 'input':
            break
        driven += '_' + token
    attribute = tokens[-1]
    # MEL gmatch "[0-9]" accepts a single digit before suffix stripping.
    if re.fullmatch('[0-9]', attribute):
        attribute = 'input[' + attribute + ']'
    else:
        attribute = re.sub('[0-9]+$', '', attribute)
    # A multi-digit numeric suffix is stripped to empty by the MEL. Its
    # restore loop warns about that missing destination and continues; keep
    # that result rather than inventing input[12] or aborting discovery here.
    return name, driven, attribute


def order_original_fit_driving_systems(systems):
    # MEL's explicit 0..98 passes deliberately omit greater nesting depths.
    return tuple(sorted((system for system in systems
                         if 0 <= system.nesting_depth < 99),
                        key=lambda system: system.nesting_depth))
