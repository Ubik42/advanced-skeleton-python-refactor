"""Continue native ImportMatcher after fitting, preserving the existing Fit."""
from dataclasses import dataclass

from .registered_body_build import BuildRegisteredBodyCharacter,_JoinedTransactionHost
from .name_matcher_animation import BakeNameMatchedAnimation


@dataclass(frozen=True, slots=True)
class SourceNameMatcherAttachment:
    joints: int
    channels: int
    connected: int
    missing: tuple[str,...]
    baked_controls: int


class AttachSourceNameMatchedFit:
    def __init__(self, host):self.host = host

    def apply(self, source_root, rows, rules):
        host = self.host
        with host.transaction('原版 NameMatcher 构建并附加外部骨架'):
            joined = _JoinedTransactionHost(host)
            animation = joined.capture_name_matcher_source_animation(source_root)
            kept = False
            if animation:
                raw = getattr(host._cmds,'raw',host._cmds)
                choice = raw.confirmDialog(title='Build ?',message='Animation detected\n\nTransfer animation to Rig ?',
                    button=('Yes','No'),defaultButton='Yes',dismissString='No')
                if choice=='Yes':
                    joined.keep_name_matcher_source_animation(source_root,animation)
                    kept = True
                else:
                    # Source removes time animation only, retaining driven keys.
                    raw.select(source_root,hierarchy=True,replace=True)
                    raw.delete(channels=True,unitlessAnimationCurves=False,hierarchy='none',
                               controlPoints=False,shape=False)
            names = joined.discover_character_registrations()
            if names:
                from .character_rebuild import RebuildBodyCharacter
                raw = getattr(host._cmds,'raw',host._cmds)
                staging,index = 'AdvPyNameMatcherRebuild',1
                while raw.namespace(exists=':'+staging):
                    index += 1
                    staging = 'AdvPyNameMatcherRebuild'+str(index)
                RebuildBodyCharacter(joined).apply(staging)
            else:
                BuildRegisteredBodyCharacter(joined).apply('FitSkeleton')
            joined.create_source_name_matcher_blend_controls()
            attachment = joined.attach_source_name_matcher_skeleton(source_root,rows,rules)
            baked = BakeNameMatchedAnimation(joined).apply(source_root,rows,rules) if kept else None
            joined.auto_scale_source_name_matcher_fk_curves()
            saved = joined.read_character_registration()
        return SourceNameMatcherAttachment(len(saved.body),len(saved.channels),
            attachment.connected,attachment.missing,baked.controls if baked else 0)
