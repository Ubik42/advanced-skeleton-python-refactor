"""Literal name rules shared by the ADV 6.925 Game Engine operations."""
from fnmatch import fnmatchcase
import re


def original_part_joint(name):
    return fnmatchcase(name.rsplit('|', 1)[-1].rsplit(':', 1)[-1], '*Part[0-9]*')


def original_part_number(name):
    """asPartNrFromPartName (7646), including MEL's empty numeric result."""
    bare = name.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    if not original_part_joint(bare):
        return 0
    stem = next((part for part in bare.split('_') if part), '')
    digits = re.search(r'[0-9]+$', stem)
    return int(digits.group()) if digits else 0


def original_twist_base(name):
    """The source uses the first two nonempty underscore fields only."""
    bare = name.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    fields = tuple(part for part in bare.split('_') if part)
    return fields[0], '_' + fields[1] if len(fields) > 1 else '_'
