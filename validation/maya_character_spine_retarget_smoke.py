"""Generated 4-to-6 registered-character FK animation transfer."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(output):
    output = output.resolve()
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaMocapControlHost
        from adv_py.application import (CreateFitSkeleton, BuildVariableBodySourceFit,
            BuildOrientedBodySkeleton, BuildBodyCharacterRig, RegisterBodyCharacter,
            RetargetCharacterSpineFk)
        from adv_py.core.variable_body_fit import variable_axial_description

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis='z', rotateView=False)
        registrations = {}
        for namespace, segments in (('source', 4), ('target', 6)):
            cmds.namespace(addNamespace=namespace)
            host = MayaBodyBuildHost(namespace=namespace)
            CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=segments)
            BuildOrientedBodySkeleton(host).apply()
            rig = BuildBodyCharacterRig(host).apply(include_torso=True,
                include_spine_ik=True, include_control_spaces=True,
                axial_description=variable_axial_description(segments))
            registrations[namespace] = RegisterBodyCharacter(host).apply(rig)
        source = registrations['source']
        target = registrations['target']
        source_host = MayaBodyBuildHost(namespace='source')
        source_channels = {row.key: row for row in source.channels}
        for frame, amount in ((1, 0.), (5, 1.), (10, 2.)):
            for key, value in (
                ('global.translateX', amount * 3.),
                ('torso.TorsoSpine1_MFK.rotateZ', amount * 3.),
                ('torso.TorsoSpine2_MFK.rotateZ', amount * 2.),
                ('torso.TorsoChest_MFK.rotateZ', amount),
                ('arm.fk.ShoulderFK_R.rotateZ', amount * 4.),
            ):
                row = source_channels[key]
                source_host._cmds.setKeyframe(row.node,
                                              attribute=row.attribute, time=frame, value=value)
        target_host = MayaMocapControlHost(namespace='target')
        source_before = source_host.capture_character_key_state(source)
        target_before = target_host.capture_character_key_state(target)
        output.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(rename=str(output.with_name('character-spine-source.ma')))
        cmds.file(save=True, type='mayaAscii')
        class FailedHost(MayaMocapControlHost):
            calls = 0
            def write_mocap_fk_group_keys(self, plan):
                result = super().write_mocap_fk_group_keys(plan)
                self.calls += 1
                if self.calls == 3:
                    raise RuntimeError('Injected cross-spine FK failure')
                return result
        try:
            RetargetCharacterSpineFk(FailedHost(namespace='target')).apply(
                'source', start_frame=1, end_frame=10, sample_by=1)
        except RuntimeError as exc:
            if 'Injected cross-spine FK failure' not in str(exc):
                raise
            rollback_restored = (target_host.capture_character_key_state(target)
                                 == target_before)
        else:
            rollback_restored = False
        result = RetargetCharacterSpineFk(target_host).apply('source',
            start_frame=1, end_frame=10, sample_by=1)
        target_after = target_host.capture_character_key_state(target)
        source_unchanged = source_before == source_host.capture_character_key_state(source)
        bridges_gone = not (cmds.namespaceInfo(listOnlyNamespaces=True) or []) or not any(
            value.startswith('AdvPySpineBridge_') for value in
            (cmds.namespaceInfo(listOnlyNamespaces=True) or []))
        changed = target_before != target_after
        cmds.undo()
        undo_restored = target_host.capture_character_key_state(target) == target_before
        cmds.redo()
        redo_restored = target_host.capture_character_key_state(target) == target_after
        data = dict(source_spine=len(source.spine.body_joints),
            target_spine=len(target.spine.body_joints), frames=len(result[0]),
            groups=len(result[1]), changed=changed, source_unchanged=source_unchanged,
            bridges_gone=bridges_gone, undo_restored=undo_restored,
            redo_restored=redo_restored, rollback_restored=rollback_restored)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2), encoding='utf8')
        if not all((changed, source_unchanged, bridges_gone, rollback_restored,
                    undo_restored, redo_restored)):
            raise RuntimeError(data)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(Path(sys.argv[1]))
