"""Original Driving Systems curve naming and numeric catalogue."""
from dataclasses import dataclass
import re

@dataclass(frozen=True,slots=True)
class DrivingAttribute:
    control: str
    attribute: str
    curves: tuple[str,...]
    values: tuple[float,...]


def original_sdk_control(curve):
    parts=curve.rsplit("|",1)[-1].rsplit(":",1)[-1].split("_")
    name="_".join(parts[:-1])
    if name.startswith("SDK"):return name[3:]
    if name.startswith("bw"):return parts[0][2:]+"_"+parts[1]
    return name


def original_sdk_attribute(curve):
    parts=curve.rsplit("|",1)[-1].rsplit(":",1)[-1].split("_")
    return parts[2] if parts[0].startswith("bw") else re.sub(r"[0-9]+$","",parts[-1])
