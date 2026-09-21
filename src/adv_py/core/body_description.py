"""Explicit axial chains, independent of scene traversal and joint counts."""
from dataclasses import dataclass
import re

from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True)
class BodyAxialDescription:
    spine: tuple[str,...] = ('Root_M','Spine1_M','Chest_M')
    neck: tuple[str,...] = ('Neck_M','Head_M')
    scapulae: tuple[str,str] = ('Scapula_R','Scapula_L')

    def __post_init__(self):
        if (not all(isinstance(chain,tuple) for chain in (self.spine,self.neck,self.scapulae))
                or not 2<=len(self.spine)<=64 or not 1<=len(self.neck)<=32 or len(self.scapulae)!=2):
            raise FitSkeletonValidationError('身体描述需要 2..64 个脊柱节点、1..32 个颈头节点和两个肩胛节点')
        names=self.spine+self.neck+self.scapulae
        if any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',n) for n in names) or len(set(names))!=len(names):
            raise FitSkeletonValidationError('身体描述关节名必须唯一且不包含路径或命名空间')

    @property
    def parents(self):
        chain=self.spine+self.neck
        return ((chain[0],None),*zip(chain[1:],chain),*((name,self.spine[-1]) for name in self.scapulae))

    def validate(self,body):
        joints={joint.name:joint for joint in body.joints}
        if len(joints)!=len(body.joints) or any(name not in joints for name,_ in self.parents):
            raise FitSkeletonValidationError('Body 缺少身体描述中的唯一关节')
        if joints[self.spine[0]].path!=body.root:
            raise FitSkeletonValidationError('身体描述的骨盆必须为 Body 根')
        for name,parent in self.parents:
            if joints[name].parent_path!=(joints[parent].path if parent else None):
                raise FitSkeletonValidationError('身体描述父链不匹配：'+name)
        return joints
