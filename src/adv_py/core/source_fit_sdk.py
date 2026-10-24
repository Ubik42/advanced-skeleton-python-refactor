"""Native Fit SDK pose differences; numeric pose text is data, never code."""
from dataclasses import dataclass
from math import isfinite
import re

from .corrective_shapes import corrective_round


@dataclass(frozen=True, slots=True)
class SourceFitSDKDriven:
    joint: str
    attribute: str
    default_value: float
    posed_value: float

    @property
    def plug(self):
        return self.joint+'.'+self.attribute


@dataclass(frozen=True, slots=True)
class SourceFitSDKPlan:
    control: str
    selection: tuple[str, ...]
    driven: tuple[SourceFitSDKDriven, ...]

    @property
    def suggested_attribute(self):
        name = self.driven[0].joint
        if 'Finger' not in name and 'Toe' not in name:
            return ''
        name = re.sub('[0-9]', '', name, count=1)
        name = name.replace('Finger', '', 1).replace('Toe', '', 1)
        return name[:1].lower()+name[1:]+'Curl'

    @property
    def message(self):
        return 'Create Set-Driven-Key for these ?\n\n'+''.join(
            f'{row.plug} = {corrective_round(row.posed_value, 3):g}\n'
            for row in self.driven)


@dataclass(frozen=True, slots=True)
class SourceFitSDKOptions:
    attribute: str
    driver_value: float = 10.
    soft_min: float | None = 0.
    soft_max: float | None = 10.

    def __post_init__(self):
        # MEL rejects empty names and spaces; Maya handles its remaining
        # attribute-name syntax. Do not impose a new identifier convention.
        if not self.attribute or ' ' in self.attribute:
            raise ValueError('Not a valid attribute name')
        for value in (self.driver_value, self.soft_min, self.soft_max):
            if value is not None and not isfinite(value):
                raise ValueError('Fit SDK 数值必须有限')


def source_fit_sdk_driven(default_pose, samples, *, map_address=lambda value: value):
    """Native TRS/sample then command order, strict ±0.001 comparison."""
    commands = []
    for statement in default_pose.split(';'):
        # Keep native exact prefix matching: leading whitespace is not fixed.
        if not statement.startswith('setAttr '):
            continue
        tokens = statement.split()
        if len(tokens) < 3:
            continue
        address = map_address(tokens[1])
        try:
            value = float(tokens[2])
        except ValueError:
            continue
        commands.append((address, value))
    rows = []
    for joint, attribute, current in samples:
        plug = joint+'.'+attribute
        for address, default in commands:
            if address != plug:
                continue
            if current > default+.001 or current < default-.001:
                rows.append(SourceFitSDKDriven(joint, attribute, default, current))
    return tuple(rows)


def source_fit_sdk_prompt(message, *, max_lines=35):
    # MEL tokenize ignores empty lines, and truncates only when over 35.
    lines = tuple(line for line in message.split('\n') if line)
    if len(lines) <= max_lines:
        return message
    return '\n'.join(lines[:max_lines])+'\n...And '+str(len(lines)-max_lines)+' more..'
