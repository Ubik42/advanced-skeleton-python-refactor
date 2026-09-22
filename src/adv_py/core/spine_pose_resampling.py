"""DCC-neutral world-frame resampling for changed spine segment counts."""
from __future__ import annotations

from bisect import bisect_right
from math import acos, cos, isfinite, sin, sqrt


class SpinePoseResamplingError(ValueError):
    pass


def _unit_quaternion(matrix):
    rows=tuple(tuple(float(matrix[4*i+j]) for j in range(3)) for i in range(3))
    lengths=tuple(sqrt(sum(value*value for value in row)) for row in rows)
    scale=sum(lengths)/3
    if (not isfinite(scale) or scale<=1e-9
            or any(not isfinite(length) or abs(length-scale)>scale*1e-5
                   for length in lengths)):
        raise SpinePoseResamplingError('脊柱世界矩阵需要正值等比缩放')
    rows=tuple(tuple(value/scale for value in row) for row in rows)
    if (any(abs(sum(a*b for a,b in zip(rows[i],rows[j])))>1e-5
            for i in range(3) for j in range(i+1,3))
            or abs(sum(rows[0][i]*(rows[1][(i+1)%3]*rows[2][(i+2)%3]
                -rows[1][(i+2)%3]*rows[2][(i+1)%3]) for i in range(3))-1)>1e-5):
        raise SpinePoseResamplingError('脊柱世界矩阵包含 shear、镜像或非正交旋转')
    # Maya's row-vector basis is transposed into the conventional column basis.
    r=tuple(tuple(rows[j][i] for j in range(3)) for i in range(3))
    trace=r[0][0]+r[1][1]+r[2][2]
    if trace>0:
        s=2*sqrt(trace+1)
        q=((r[2][1]-r[1][2])/s,(r[0][2]-r[2][0])/s,
           (r[1][0]-r[0][1])/s,s/4)
    else:
        i=max(range(3),key=lambda index:r[index][index])
        j=(i+1)%3;k=(i+2)%3
        s=2*sqrt(max(0.,1+r[i][i]-r[j][j]-r[k][k]))
        if s<=1e-12:raise SpinePoseResamplingError('脊柱旋转无法转换为四元数')
        xyz=[0.,0.,0.]
        xyz[i]=s/4
        xyz[j]=(r[i][j]+r[j][i])/s
        xyz[k]=(r[i][k]+r[k][i])/s
        q=(*xyz,(r[k][j]-r[j][k])/s)
    length=sqrt(sum(value*value for value in q))
    return tuple(value/length for value in q),scale


def _slerp(left,right,t):
    dot=sum(a*b for a,b in zip(left,right))
    if dot<0:
        right=tuple(-value for value in right)
        dot=-dot
    dot=min(1.,max(-1.,dot))
    if dot>.9995:
        values=tuple((1-t)*a+t*b for a,b in zip(left,right))
    else:
        theta=acos(dot)
        denominator=sin(theta)
        values=tuple((sin((1-t)*theta)*a+sin(t*theta)*b)/denominator
                     for a,b in zip(left,right))
    length=sqrt(sum(value*value for value in values))
    return tuple(value/length for value in values)


def _matrix(quaternion,scale,position):
    x,y,z,w=quaternion
    column=((1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)),
            (2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)),
            (2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)))
    return tuple(scale*column[j][i] if j<3 else 0.
                 for i in range(3) for j in range(4))+(*position,1.)


def _positions(values,count,label):
    if (not isinstance(values,tuple) or len(values)!=count
            or any(isinstance(value,bool) or not isinstance(value,(int,float))
                   or not isfinite(value) for value in values)
            or values[0]!=0 or values[-1]!=1
            or any(a>=b for a,b in zip(values,values[1:]))):
        raise SpinePoseResamplingError(label+'须从 0 到 1 严格递增')
    return values


def resample_spine_world_matrices(source_matrices: tuple[tuple[float,...],...],
        target_positions: tuple[float,...], *,
        source_positions: tuple[float,...] | None = None
        ) -> tuple[tuple[float,...],...]:
    """Interpolate rigid/uniform-scale world frames along a source spine polyline."""
    if (not isinstance(source_matrices,tuple) or not 2<=len(source_matrices)<=64
            or not isinstance(target_positions,tuple)
            or not 2<=len(target_positions)<=64):
        raise SpinePoseResamplingError('源和目标脊柱各需 2–64 个世界姿态')
    frames=[]; rotations=[]; scales=[]; points=[]
    for matrix in source_matrices:
        if (not isinstance(matrix,(tuple,list)) or len(matrix)!=16
                or any(isinstance(value,bool) or not isinstance(value,(int,float))
                       or not isfinite(value) for value in matrix)
                or any(abs(matrix[index])>1e-8 for index in (3,7,11))
                or abs(matrix[15]-1)>1e-8):
            raise SpinePoseResamplingError('脊柱世界姿态须为有限仿射 4×4 矩阵')
        frame=tuple(float(value) for value in matrix)
        rotation,scale=_unit_quaternion(frame)
        frames.append(frame);rotations.append(rotation);scales.append(scale)
        points.append(frame[12:15])
    if source_positions is None:
        lengths=[sqrt(sum((a-b)**2 for a,b in zip(left,right)))
                 for left,right in zip(points,points[1:])]
        total=sum(lengths)
        if (not isfinite(total) or total<=1e-9
                or any(not isfinite(length) or length<=1e-9 for length in lengths)):
            raise SpinePoseResamplingError('源脊柱相邻关节距离必须为正')
        running=0.; source_positions=[0.]
        for length in lengths:
            running+=length
            source_positions.append(running/total)
        source_positions[-1]=1.
        source_positions=tuple(source_positions)
    source_positions=_positions(source_positions,len(frames),'源脊柱位置')
    target_positions=_positions(target_positions,len(target_positions),'目标脊柱位置')
    result=[]
    for position in target_positions:
        index=min(bisect_right(source_positions,position)-1,len(frames)-1)
        if index==len(frames)-1 or position==source_positions[index]:
            result.append(frames[index]);continue
        fraction=(position-source_positions[index])/(
            source_positions[index+1]-source_positions[index])
        point=tuple((1-fraction)*a+fraction*b for a,b in zip(points[index],points[index+1]))
        scale=(1-fraction)*scales[index]+fraction*scales[index+1]
        result.append(_matrix(_slerp(rotations[index],rotations[index+1],fraction),
                              scale,point))
    return tuple(result)
