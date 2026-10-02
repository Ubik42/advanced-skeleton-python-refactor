"""Results and source constants for the Fit AutoPlace editing lifecycle."""
from dataclasses import dataclass

FIT_AUTO_PLACE_AXES=('z','x','yArmStraight','yElbowStraight','y','zLoft','yLoft')
FIT_AUTO_PLACE_FINGERS=('Index','Middle','Ring','Pinky')
FIT_AUTO_PLACE_GROUPS=('asFitOrbitA','asFitScanCurves','asFitHandles',
    'asFitProjections','asFitPivots','asFitConstraints','asFitCombinedSkins',
    'asFitCombinedLofts','asFitAutoPlaceJoints','asFitNCloth')


@dataclass(frozen=True,slots=True)
class FitGuideCleanupResult:
    finished: bool
    restored_fingers: tuple[str,...]=()
    restored_arm: bool=False
    removed_softmods: int=0


@dataclass(frozen=True,slots=True)
class FitAutoPlaceResult:
    joints: int
    axes_completed: tuple[str,...]
    finger_detected: bool
    guides_active: bool


@dataclass(frozen=True,slots=True)
class FitProjectionBounds:
    name: str
    minimum: tuple[float,float,float]
    maximum: tuple[float,float,float]
    spans: int=1


def choose_fit_projected_curve(bounds,group_min,group_max,find,*,closest_position=None):
    """Exact ordered selection rules of MEL asGetProjectedCurve, 53534."""
    bounds=tuple(bounds)
    if not bounds:raise ValueError('扫描投影没有生成曲线')
    axis=2 if group_max[2]-group_min[2]>group_max[0]-group_min[0] else 0
    center=right=front=widest=0
    center_x=right_x=999.
    front_z=-999.
    center_width=max_width=0.
    for index,row in enumerate(bounds):
        if row.spans==0:continue
        x=(row.minimum[0]+row.maximum[0])/2.
        z=(row.minimum[2]+row.maximum[2])/2.
        width=row.maximum[axis]-row.minimum[axis]
        if abs(x)<center_x and width>center_width:
            center_x,center_width,center=abs(x),width,index
        if x<right_x:right_x,right=x,index
        if z>front_z:front_z,front=z,index
        if width>max_width:max_width,widest=width,index
    if len(find)==1 and find.isdigit():return bounds[int(find)].name
    indices={'center':center,'right':right,'front':front,'widest':widest}
    if find in indices:return bounds[indices[find]].name
    if find.startswith('closestTo'):
        if closest_position is None:raise ValueError('最近曲线选择缺少目标位置')
        minimum=999.
        result=''
        for row in bounds:
            distance=sum((closest_position[i]-(row.minimum[i]+row.maximum[i])/2.)**2
                         for i in range(3))**.5
            if distance<minimum:minimum,result=distance,row.name
        return result
    return ''
