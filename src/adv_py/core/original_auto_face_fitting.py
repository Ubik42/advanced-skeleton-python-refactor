"""Native known-mesh detection and ordered AutoFit recipes, MEL 51099–51738."""
from dataclasses import dataclass

from .original_auto_face_tables import AUTO_FACE_INPUT_COMPONENTS,AUTO_FACE_FIT_COMPONENTS


@dataclass(frozen=True, slots=True)
class OriginalAutoFaceProfile:
    code: str
    title: str
    geometry: str
    teeth: str
    vertex_count: int
    head_joint: str | None
    all_head: tuple[str,...]
    right_eye: tuple[str,...]
    left_eye: tuple[str,...]
    tongue_object: str | None = None


ORIGINAL_AUTO_FACE_PROFILES=(
    OriginalAutoFaceProfile('CC4','CharacterCreator4','CC_Base_Body','CC_Base_Teeth',14164,
        'CC_Base_Head',('CC_Base_Body','CC_Base_Teeth','CC_Base_Tongue'),
        ('CC_Base_Eye.f[0:319]',),('CC_Base_Eye.f[320:639]',),'CC_Base_Tongue'),
    OriginalAutoFaceProfile('MH','MetaHuman','head_lod0_mesh','teeth_lod0_mesh',24049,
        'head',('head_lod0_mesh','teeth_lod0_mesh','saliva_lod0_mesh'),
        ('eyeRight_lod0_mesh',),('eyeLeft_lod0_mesh',)),
    OriginalAutoFaceProfile('CC5','CharacterCreator5','CC_Base_Body','CC_Base_Teeth',56412,
        'CC_Base_Head',('CC_Base_Body','CC_Base_Teeth','CC_Base_Tongue'),
        ('CC_Base_Eye.f[0:1279]',),('CC_Base_Eye.f[1280:2559]',),'CC_Base_Tongue'),
    OriginalAutoFaceProfile('GNM','GoogleGNM','GNM_Head','GNM_Head',17821,
        None,('GNM_Head',),('GNM_Head.f[12782:13153]','GNM_Head.f[17278:17661]'),
        ('GNM_Head.f[12410:12781]','GNM_Head.f[16894:17277]')),
)
ORIGINAL_AUTO_FACE_EXTRAS=('Sideburns_Stubble','Circle_Sparse','Mustache_Sparse',
    'Soul_Patch_Sparse','Classic_short','CC_Base_TearLine','Kevin_Brow','Camila_Brow','Eyebrows')

# The final override is separate from the generic Tongue bounding-box fit.
ORIGINAL_AUTO_FACE_TONGUE_POINTS = {
    'CC4': ('CC_Base_Tongue', ((46, 0), (40, 0), (32, 0), (18, 0), (164, 0))),
    'CC5': ('CC_Base_Tongue', ((46, 0), (40, 0), (32, 0), (18, 0), (164, 0))),
    'MH': ('teeth_lod0_mesh', ((1284, 0), (1281, -.9), (1278, -.9), (1275, -.5), (1076, 0))),
    'GNM': ('GNM_Head', ((15197, 0), (14834, 0), (15338, 0), (15430, 0), (15394, 0))),
}


def original_auto_face_tongue_points(profile):
    mesh, points = ORIGINAL_AUTO_FACE_TONGUE_POINTS[profile.code]
    return tuple((f'{mesh}.vtx[{vertex}]', offset) for vertex, offset in points)


@dataclass(frozen=True, slots=True)
class OriginalAutoFaceStep:
    section: str
    part: str
    shading_group: str
    selection: tuple[str,...]
    batch: bool = False


def detect_original_auto_face_profile(vertex_counts):
    """Source keeps the last matching profile, including duplicate CC names."""
    counts=dict(vertex_counts)
    found=None
    for profile in ORIGINAL_AUTO_FACE_PROFILES:
        if counts.get(profile.geometry)==profile.vertex_count:found=profile
    return found


def original_auto_face_input(profile,attribute):
    names={'Mask':('mask',profile.geometry),'UpperTeeth':('upper_teeth',profile.teeth),
           'LowerTeeth':('lower_teeth',profile.teeth),'Tongue':('tongue',profile.teeth)}
    if attribute not in names:raise ValueError('原版 AutoFit 固定组件输入无效')
    table,mesh=names[attribute]
    return tuple(mesh+'.f['+index+']' for index in AUTO_FACE_INPUT_COMPONENTS[profile.code][table])


def original_auto_face_steps(profile,side):
    if side not in ('Right','Left'):raise ValueError('原版 AutoFit 侧别无效')
    suffix='_R' if side=='Right' else '_L'
    eye=('CC_Base_Eye' if profile.code in ('CC4','CC5') else 'GNM_Head'
         if profile.code=='GNM' else 'eye'+side+'_lod0_mesh')
    return tuple(OriginalAutoFaceStep(section,part,shader,tuple(
        (eye if section in ('Pupil','Iris') else profile.geometry)+'.'+kind+'['+index+']'
        for kind,index in components),section in ('EyeBall','Jaw'))
        for section,part,shader,components in AUTO_FACE_FIT_COMPONENTS[(profile.code,suffix)])
