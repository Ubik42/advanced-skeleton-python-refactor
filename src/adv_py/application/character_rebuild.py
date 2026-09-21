"""Build and verify a replacement rig before transferring any original data."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.character_preservation import CharacterPreservation,validate_rebuild_layout
from .character_preservation import CaptureBodyCharacterPreservation
from .fit_skeleton_io import ExportFitSkeleton,CreateAndImportFitSkeleton
from .oriented_body_skeleton import BuildOrientedBodySkeleton
from .body_character_rig import BuildBodyCharacterRig
from .character_registry import RegisterBodyCharacter
from .character_limb_animation import EnableBodyCharacterLimbAnimation
from .character_stretch_matching import EnableBodyCharacterStretchMatching
from .character_spaces import EnableBodyCharacterSpaceAnimation


@dataclass(frozen=True)
class StagedCharacterRebuild:
    original: CharacterPreservation
    namespace: str
    registration: CharacterRegistration


class StageBodyCharacterRebuild:
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        host.preflight_character_rebuild_namespace(namespace)
        original=CaptureBodyCharacterPreservation(host).execute(extensions=extensions)
        with TemporaryDirectory(prefix='adv-py-rebuild-') as directory:
            fit=Path(directory)/'source.fit.json'
            ExportFitSkeleton(host).apply(fit,original.registration.container)
            with host.transaction('Stage replacement character'):
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('重建暂存前原角色发生变化')
                stage=host.create_character_rebuild_host(namespace)
                CreateAndImportFitSkeleton(stage).apply(fit)
                BuildOrientedBodySkeleton(stage).apply()
                rig=BuildBodyCharacterRig(stage).apply(include_torso=True,include_spine_ik=True,include_control_spaces=True)
                registration=RegisterBodyCharacter(stage).apply(rig)
                keys={channel.key for channel in original.registration.channels}
                if any('.ikOrientation.' in key for key in keys):registration=EnableBodyCharacterLimbAnimation(stage).apply()
                if any('.ikLengthWeight.' in key for key in keys):registration=EnableBodyCharacterStretchMatching(stage).apply()
                if any(key.startswith('space.') for key in keys):registration=EnableBodyCharacterSpaceAnimation(stage).apply()
                validate_rebuild_layout(original.registration,registration)
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('暂存构建改写了原角色，已回滚')
        return StagedCharacterRebuild(original,namespace,registration)
