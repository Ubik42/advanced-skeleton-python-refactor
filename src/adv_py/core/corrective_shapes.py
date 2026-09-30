"""Source corrective naming, pose values and target catalogues (ADV 6.925)."""
from dataclasses import dataclass
from math import copysign, floor
import shlex

@dataclass(frozen=True,slots=True)
class CorrectiveShapeOptions:
    q_rotations: bool = True
    use_soft_mods: bool = False
    mirror: bool = True

@dataclass(frozen=True,slots=True)
class CorrectiveTarget:
    deform_object: str
    driver_object: str
    driver_attribute: str
    value: float
    weight: float
    inbetween: bool
    deletable: bool
    blendshape: str
    sdk: str


def corrective_round(value, precision=3):
    scale=10**precision
    return copysign(floor(abs(value)*scale+.5)/scale,value)


def corrective_side(value, attribute):
    return "pos" if value>=0 or "_" in attribute else "neg"


def corrective_alias(driver, attribute, value):
    return driver+"__"+attribute+"__"+corrective_side(value,attribute)


def corrective_object_name(deform, driver, attribute, value):
    return deform+"__"+corrective_alias(driver,attribute,value)


def corrective_pose_command_rows(text):
    """Read numeric setAttr/xform pose records without executing source text."""
    rows=[]
    for statement in (text or "").split(";"):
        tokens=shlex.split(statement)
        if not tokens:
            continue
        if tokens[0]=="setAttr" and len(tokens)==3:
            rows.append((tokens[1],float(tokens[2])))
        elif tokens[0]=="xform":
            node=tokens[-1]
            # Original driver discovery compares neutral t/r=0 and s=1,
            # rather than interpreting the xform's captured transform numbers.
            count=3 if len(tokens)==7 else 6 if len(tokens)==11 else 9
            attrs=("translateX","translateY","translateZ","rotateX","rotateY","rotateZ","scaleX","scaleY","scaleZ")
            rows.extend((node+"."+attr,1. if index>5 else 0.) for index,attr in enumerate(attrs[:count]))
    return tuple(rows)
