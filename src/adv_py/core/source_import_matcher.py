"""Native template gate and first external hip detection, MEL 50883."""
from dataclasses import dataclass
from fnmatch import fnmatchcase


@dataclass(frozen=True, slots=True)
class SourceImportMatcherDetection:
    joint: str
    source_root: str
    template: str | None


def source_import_matcher_joint(template, joints, *, importing=False):
    if importing or not fnmatchcase(template,'biped*'):return None
    for joint in joints:
        if fnmatchcase(joint,'*DHIbody:*'):continue
        if any(fnmatchcase(joint,pattern) for pattern in ('*Hip*','*hip*','*pelvis*')):
            return joint
    return None
