"""Original build-time Pole placer and straight-chain preferred angle.

MEL 80832–80896 uses a length-weighted start/end baseline, aims from there
at the selected middle joint, then moves by the total authored chain length.
The no-middle branch keeps the temporary placer's world Z axis.
"""
from math import sqrt,isfinite


def source_limb_build_pole(points,middle_index,start_axes):
    if (len(points)<2 or type(middle_index) is not int or not 0<=middle_index<len(points)-1
            or any(len(p)!=3 or any(not isfinite(v) for v in p) for p in points)):
        raise ValueError('来源 RP Pole 定位需要完整的 Fit 骨链')
    def length(v):return sqrt(sum(x*x for x in v))
    def sub(a,b):return tuple(x-y for x,y in zip(a,b))
    total=sum(length(sub(b,a)) for a,b in zip(points,points[1:]))
    if total<=1e-8:
        raise ValueError('来源 RP Pole 骨链长度退化')
    start,middle,end=points[0],points[middle_index],points[-1]
    if middle_index==0:
        return (start[0],start[1],start[2]+total),False
    first,second=length(sub(middle,start)),length(sub(end,middle))
    if first+second<=1e-8:
        raise ValueError('来源 RP Pole 中间关节权重退化')
    base=tuple((a*second+b*first)/(first+second) for a,b in zip(start,end))
    direction=sub(middle,base)
    straight=length(direction)<.001
    if straight:
        # The MEL parents the placer to the start joint and shifts local Y
        # by -1 world unit before reevaluating the middle aim constraint.
        y=start_axes[1]
        norm=length(y)
        if norm<=1e-8:
            raise ValueError('来源 RP Pole 起点 Y 轴退化')
        base=tuple(v-a/norm for v,a in zip(base,y))
        direction=sub(middle,base)
    norm=length(direction)
    if norm<=1e-8:
        raise ValueError('来源 RP Pole 瞄准方向退化')
    return tuple(v+a*total/norm for v,a in zip(base,direction)),straight
