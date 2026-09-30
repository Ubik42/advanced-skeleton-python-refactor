"""Original Lip Falloff fields and controller count conventions."""
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class LipFalloffOptions:
    outer: int = 3
    inner: int = 2
    iterations: int = 5
    preview: bool = False
    update: bool = False
    multi_skin_clusters: bool = False
    def __post_init__(self):
        if any(type(value) is not int or value<0 for value in (self.outer,self.inner,self.iterations)):
            raise ValueError("Lip Falloff 次数必须是非负整数")


def lip_control_letter(index):
    if type(index) is not int or not 0<=index<26: raise ValueError("Lip 控制器编号无效")
    return chr(ord("A")+index)
