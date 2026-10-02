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
    parts=[part for part in curve.rsplit("|",1)[-1].rsplit(":",1)[-1].split("_") if part]
    name="_".join(parts[:-1])
    if name.startswith("SDK"):return name[3:]
    if name.startswith("bw"):return parts[0][2:]+"_"+parts[1]
    return name


def original_sdk_attribute(curve):
    parts=[part for part in curve.rsplit("|",1)[-1].rsplit(":",1)[-1].split("_") if part]
    return parts[2] if parts[0].startswith("bw") else re.sub(r"[0-9]+$","",parts[-1])


@dataclass(frozen=True,slots=True)
class DrivingCreateOptions:
    control: str = ""
    attribute: str = ""
    mirror: bool = True
    q_rotations: bool = True
    drive_from_selected: bool = False


@dataclass(frozen=True,slots=True)
class DrivenChannel:
    control: str
    attribute: str
    neutral: float
    value: float
    animation: str = ""
    editing: bool = False

    @property
    def plug(self):return self.control+"."+self.attribute


def driving_pose_command_rows(source):
    """asDsCreate reads actual xform translation/rotation, with scale neutral 1."""
    import shlex
    rows=[]
    for statement in (source or "").split(";"):
        tokens=shlex.split(statement)
        if not tokens:continue
        if tokens[0]=="setAttr" and len(tokens)==3:
            rows.append((tokens[1],float(tokens[2])))
        elif tokens[0]=="xform":
            node=tokens[-1]
            for flags,channel in ((("-t","-translation"),"translate"),(("-ro","-rotation"),"rotate"),(("-s","-scale"),"scale")):
                index=next((tokens.index(flag) for flag in flags if flag in tokens),None)
                if index is not None:
                    values=(1.,1.,1.) if channel=="scale" else tuple(float(value) for value in tokens[index+1:index+4])
                    rows.extend((node+"."+channel+axis,value) for axis,value in zip("XYZ",values))
    return tuple(rows)
