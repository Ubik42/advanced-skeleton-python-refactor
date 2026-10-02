"""ADV asTextFromAnimCurve/asAnimCurveFromText data, MEL 5028–5259.

This is the source's comma-separated curve description, not executable MEL.
Key order, tangent names and the original missing incoming-angle defaults
remain part of that interchange format.
"""
from dataclasses import dataclass
from math import isfinite
import re


VALID_TANGENTS=frozenset(('auto','clamped','fixed','flat','linear','plateau',
                         'spline','step','stepnext'))


@dataclass(frozen=True,slots=True)
class OriginalCurveKey:
    time: float
    value: float
    in_tangent: str=''
    out_tangent: str=''
    in_angle: float=0.
    out_angle: float=0.
    in_weight: float=0.
    out_weight: float=0.


@dataclass(frozen=True,slots=True)
class OriginalCurveText:
    node_type: str
    keys: tuple[OriginalCurveKey,...]
    pre_infinity: int=0
    post_infinity: int=0


_FIELDS={'time':'time','value':'value','inTangentType':'in_tangent',
         'outTangentType':'out_tangent','inTangentAngle':'in_angle',
         'outTangentAngle':'out_angle','inTangentWeight':'in_weight',
         'outTangentWeight':'out_weight'}


def parse_original_curve_text(text):
    if not isinstance(text,str):raise ValueError('动画曲线描述必须是文本')
    text=text.strip()
    if text.startswith('("') and text.endswith('");'):
        text=text[2:-3]
    count=0
    kind=''
    current=-1
    keys={}
    pre=post=0
    for line in text.split(','):
        line=line.strip()
        marker=re.match(r'^key ([0-9]+):',line)
        if marker:
            current=int(marker.group(1));keys.setdefault(current,{})
            continue
        field,separator,value=line.partition(':')
        if not separator:continue
        value=value.strip()
        if field=='nodeType':kind=value
        elif field=='keyCount':
            count=int(value)
            if count<0:raise ValueError('动画曲线关键帧数量不能为负数')
            keys={};current=-1
        elif field in ('preInfinity','postInfinity'):
            if field=='preInfinity':pre=int(value)
            else:post=int(value)
        elif field in _FIELDS:
            if current<0:raise ValueError('动画曲线关键帧数据缺少索引')
            numeric=field not in ('inTangentType','outTangentType')
            parsed=float(value) if numeric else value
            if numeric and not isfinite(parsed):raise ValueError('动画曲线数据必须是有限数值')
            keys.setdefault(current,{})[_FIELDS[field]]=parsed
    if kind not in ('animCurveTA','animCurveTL','animCurveTT','animCurveTU',
                    'animCurveUA','animCurveUL','animCurveUT','animCurveUU'):
        raise ValueError('原版动画曲线描述的节点类型无效：'+kind)
    result=[]
    for index in range(count):
        row=keys.get(index,{})
        # MEL preallocates the times array, while an absent values entry is
        # skipped with a warning. Retain that behavior in the parsed rows.
        if 'value' not in row:continue
        result.append(OriginalCurveKey(**{'time':0.,**row}))
    return OriginalCurveText(kind,tuple(result),pre,post)


def original_curve_text(curve,*,expression=False):
    fields=['nodeType: '+curve.node_type,'keyCount: '+str(len(curve.keys))]
    for index,key in enumerate(curve.keys):
        fields.append('key '+str(index)+':')
        for external,internal in _FIELDS.items():
            fields.append(external+': '+str(getattr(key,internal)))
    fields.extend(('preInfinity: '+str(curve.pre_infinity),
                   'postInfinity: '+str(curve.post_infinity)))
    text=', '.join(fields)
    return '("'+text+'");\n' if expression else text
