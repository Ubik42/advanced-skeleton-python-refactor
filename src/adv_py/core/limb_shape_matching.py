"""Scale-aware lengths and volume factors for endpoint mode matching."""
from math import copysign, sqrt
from .character_registry import CharacterRegistryError, finite, vector


def matched_local_length(parent,child,parent_matrix,axis,reference_length):
    parent=vector(parent,3);child=vector(child,3);matrix=vector(parent_matrix,16)
    reference=finite(reference_length)
    if axis not in ('X','Y','Z') or abs(reference)<=1e-8:
        raise CharacterRegistryError('IK 匹配主轴或原骨段长度无效')
    index='XYZ'.index(axis)*4
    distance=finite(sqrt(sum((a-b)*(a-b) for a,b in zip(child,parent))))
    scale=finite(sqrt(sum(v*v for v in matrix[index:index+3])))
    if min(distance,scale)<=1e-8:
        raise CharacterRegistryError('IK 匹配骨段或缩放退化')
    return finite(copysign(distance/scale,reference))


def matched_volume_factor(width,base):
    width=finite(width);base=finite(base)
    if min(width,base)<=1e-8:
        raise CharacterRegistryError('体积匹配比例退化')
    return finite(width/base)
