"""Native Fit scene import roles and merge choices, MEL 50539–50797."""
from enum import Enum
from dataclasses import dataclass


class SourceFitMergePolicy(str, Enum):
    EXISTING = 'existing'
    IMPORTED = 'imported'
    BOTH = 'both'


@dataclass(frozen=True, slots=True)
class SourceFitPreparation:
    skin: str = ''
    all_objects: str = ''
    right_eye: str = ''
    left_eye: str = ''
    game_engine: bool = False
    use_offset_parent_matrix: bool = False
    sub_controllers: bool = False
    extra_controllers: bool = False

    def __post_init__(self):
        for name in ('skin','all_objects','right_eye','left_eye'):
            if not isinstance(getattr(self,name),str):
                raise ValueError('Preparation 输入必须是原版对象名称文本')
        for name in ('game_engine','use_offset_parent_matrix','sub_controllers','extra_controllers'):
            if type(getattr(self,name)) is not bool:
                raise ValueError('Preparation 构建选项必须是布尔值')

    @property
    def fit_values(self):
        return (('objectsSkin',self.skin),('objectsAll',self.all_objects),
            ('objectsRightEye',self.right_eye),('objectsLeftEye',self.left_eye),
            ('gameEngine',self.game_engine),('useOffsetParentMatrix',self.use_offset_parent_matrix),
            ('subControllers',self.sub_controllers),('extraControllers',self.extra_controllers))

    @property
    def preferences(self):
        return (('asBodyPreGameEngine',self.game_engine),
            ('asBodyPreOPM',self.use_offset_parent_matrix),
            ('asBodyPreSub',self.sub_controllers),('asBodyPreExtra',self.extra_controllers))


SOURCE_FIT_REPLACE_ROLES = (
    'FitSkeleton','FitSkeletonVisualizers','cylinders','boxes','locators','directions',
    'asRedSG','asRed2SG','asGreenSG','asGreen2SG','asBlueSG','asBlue2SG',
    'asBlackSG','asWhiteSG','asBonesSG','asRed','asRed2','asGreen','asGreen2',
    'asBlue','asBlue2','asBlack','asWhite','asBones',
)


def source_fit_import_rename(name, exists):
    """Native 1..98 candidate loop; no invented fallback naming scheme."""
    candidate = name
    if exists(name):
        for index in range(1,99):
            candidate = name+str(index)
            if not exists(candidate):
                break
    return candidate
