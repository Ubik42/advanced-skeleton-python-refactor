"""Face Pre controls in native order, MEL 1580–1713 / 45577–45797."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OriginalFaceOption:
    attribute: str
    label: str
    default: bool | str
    items: tuple[str, ...] = ()
    advanced: bool = False


ORIGINAL_FACE_OPTIONS = (
    OriginalFaceOption('RigType', '绑定类型', 'Joints', ('Joints', 'BlendShapes', 'Mixed')),
    OriginalFaceOption('Include', '包含区域', 'Complete', (
        'Complete', 'Skip Above Eyes', 'Skip Below Eyes', 'Skip Above+Below Eyes')),
    OriginalFaceOption('LipCtrls', '嘴唇控制器数量', '12', ('12', '16', '20', '24')),
    OriginalFaceOption('NonSym', '非对称', False),
    OriginalFaceOption('SimplerEyeLid', '简化眼睑', False),
    OriginalFaceOption('EyeBase', '眼球底座', False),
    OriginalFaceOption('EyeSocket', '眼窝', False),
    OriginalFaceOption('Cyclops', '独眼', False),
    OriginalFaceOption('GameEngine', '游戏引擎', False),
    OriginalFaceOption('MultiSkinClusters', '多个 SkinCluster', False),
    OriginalFaceOption('LongSnout', '长吻部', False),
    OriginalFaceOption('Phonemes', '音素', True),
    OriginalFaceOption('Emotions', '情绪', True),
    OriginalFaceOption('ARKit', 'Apple ARKit', False),
    OriginalFaceOption('SnapChat', 'SnapChat', False),
    OriginalFaceOption('RobloxHead', 'Roblox 头部', False),
    OriginalFaceOption('UseMaxInf', '限制最大影响数', False, advanced=True),
    OriginalFaceOption('MaxInf', '最大影响数', '4', ('4', '8'), advanced=True),
    OriginalFaceOption('LegacyFaceJointOrient', '旧版面部关节朝向', False, advanced=True),
    OriginalFaceOption('SkipFaceJointOrient', '跳过面部关节朝向', False, advanced=True),
)
ORIGINAL_FACE_OPTIONS_BY_NAME = {option.attribute: option for option in ORIGINAL_FACE_OPTIONS}


def normalize_original_face_options(values, *, complete=False):
    if not isinstance(values, dict) or set(values) - set(ORIGINAL_FACE_OPTIONS_BY_NAME):
        raise ValueError('原版 Face 选项包含未知字段')
    result = ({option.attribute: option.default for option in ORIGINAL_FACE_OPTIONS}
              if complete else {})
    for name, value in values.items():
        option = ORIGINAL_FACE_OPTIONS_BY_NAME[name]
        if option.items:
            if not isinstance(value, str) or value not in option.items:
                raise ValueError('原版 Face 枚举选项无效：'+name)
        elif type(value) is not bool:
            raise ValueError('原版 Face 开关必须为布尔值：'+name)
        result[name] = value
    return result
