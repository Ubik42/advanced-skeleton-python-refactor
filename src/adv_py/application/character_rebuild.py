"""Build and verify a replacement rig before transferring any original data."""
from dataclasses import dataclass,replace
from pathlib import Path
from tempfile import TemporaryDirectory

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.character_preservation import CharacterPreservation,RebuildOwnership,validate_rebuild_layout,character_transfer_error
from .character_preservation import CaptureBodyCharacterPreservation
from .fit_skeleton_io import ExportFitSkeleton,CreateAndImportFitSkeleton
from .oriented_body_skeleton import BuildOrientedBodySkeleton
from .body_character_rig import BuildBodyCharacterRig
from .character_registry import RegisterBodyCharacter
from .character_limb_animation import EnableBodyCharacterLimbAnimation
from .character_stretch_matching import EnableBodyCharacterStretchMatching
from .character_spaces import EnableBodyCharacterSpaceAnimation
from adv_py.core.character_registry import CharacterRegistryError


@dataclass(frozen=True)
class StagedCharacterRebuild:
    original: CharacterPreservation
    namespace: str
    registration: CharacterRegistration
    custom_properties: tuple = ()
    ownership: RebuildOwnership | None = None


class StageBodyCharacterRebuild:
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        host.preflight_character_rebuild_namespace(namespace)
        original=CaptureBodyCharacterPreservation(host).execute(extensions=extensions)
        with TemporaryDirectory(prefix='adv-py-rebuild-') as directory:
            fit=Path(directory)/'source.fit.json'
            ExportFitSkeleton(host).apply(fit,original.registration.container)
            with host.character_rebuild_transaction('Stage replacement character'):
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
                host.match_character_rebuild_solver(stage,registration)
                validate_rebuild_layout(original.registration,registration)
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('暂存构建改写了原角色，已回滚')
                properties=host.plan_character_property_transfer(original,namespace)
                staged=StagedCharacterRebuild(original,namespace,registration,properties)
                staged=replace(staged,ownership=host.audit_character_rebuild_ownership(staged))
        return staged


class TransferStagedBodyCharacterData:
    def __init__(self,host):self._host=host

    def apply(self,staged):
        host=self._host
        original=staged.original
        extensions=tuple(row.path for row in original.extensions)
        if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
            raise CharacterRegistryError('原角色与暂存时的保留数据不同，请重新暂存')
        host.preflight_character_transfer(staged)
        if staged.ownership is not None and host.audit_character_rebuild_ownership(staged)!=staged.ownership:
            raise CharacterRegistryError('暂存后的 Rig 归属或连接已变化，请重新暂存')
        keys=sorted({original.current_time,*[t for curve in original.curves for t in curve.times]})
        frames=tuple(sorted({*keys,*[(a+b)/2 for a,b in zip(keys,keys[1:])]}))
        if len(frames)>2000:raise CharacterRegistryError('交接复检采样最多 2000 帧，需要分段验证策略')
        before=host.sample_character_transfer(staged,frames)
        with host.character_rebuild_transaction('Transfer preserved data to replacement rig'):
            host.transfer_character_data(staged)
            host.verify_character_retained_data(staged)
            after=host.sample_character_transfer(staged,frames,target=True)
            error=character_transfer_error(before,after)
            if error>1e-4:
                raise RuntimeError('交接改变身体、控制空间、蒙皮或用户附件；最大误差：'+str(error))
        return staged


class RebuildBodyCharacter:
    """Same-layout replacement, including creation and cleanup in one Undo."""
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        with host.transaction('Rebuild character preserving user data'):
            staged=StageBodyCharacterRebuild(host).apply(namespace,extensions=extensions)
            TransferStagedBodyCharacterData(host).apply(staged)
            keys=sorted({staged.original.current_time,*[t for curve in staged.original.curves for t in curve.times]})
            frames=tuple(sorted({*keys,*[(a+b)/2 for a,b in zip(keys,keys[1:])]}))
            before=host.sample_character_transfer(staged,frames,target=True)
            promoted=host.promote_character_rebuild(staged)
            after=host.sample_character_transfer(promoted,frames,target=True)
            if character_transfer_error(before,after)>1e-4:
                raise RuntimeError('原位替换改变身体、蒙皮或用户数据')
        return promoted
