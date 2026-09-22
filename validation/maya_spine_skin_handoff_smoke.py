"""Retain original mesh and skinCluster while changing registered influences."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def short(path):
    return path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def main(mode, folder):
    folder = folder.resolve()
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaSpineSkinHandoffHost, MayaBodyBuildHost
        from adv_py.application import HandoffRegisteredSpineSkinCluster
        skin = 'source:SourceSkin'
        mesh = '|source:SourceMesh'
        if mode == 'exercise':
            cmds.file(str(folder / 'registered-spine-skin-before.ma'),
                      open=True, force=True)
            cmds.undoInfo(state=True)
            cmds.currentTime(1, edit=True)
            cmds.deltaMush(mesh, name='source:SourceDeltaMush',
                           smoothingIterations=2)
            cmds.file(rename=str(folder / 'spine-skin-handoff-before.ma'))
            cmds.file(save=True, type='mayaAscii', force=True)
            host = MayaSpineSkinHandoffHost()
            before = host.capture_all_skin_weights(skin, mesh)
            boundary = host.capture_skin_handoff_boundary(skin, mesh)
            deformer_present = any(cmds.nodeType(node) == 'deltaMush' for node in
                (cmds.listHistory(mesh, pruneDagObjects=True) or []))
            before_geometry = host.capture_face_mesh(mesh).points
            class FailedHost(MayaSpineSkinHandoffHost):
                def remove_skin_handoff_influences(self, *args):
                    super().remove_skin_handoff_influences(*args)
                    raise RuntimeError('Injected original Skin handoff failure')
            try:
                HandoffRegisteredSpineSkinCluster(FailedHost()).apply(
                    'source', 'target', skin, mesh)
            except RuntimeError as exc:
                if 'Injected original Skin handoff failure' not in str(exc):
                    raise
                rollback = (host.capture_all_skin_weights(skin, mesh) == before
                    and host.capture_skin_handoff_boundary(skin, mesh) == boundary)
            else:
                rollback = False
            result = HandoffRegisteredSpineSkinCluster(host).apply(
                'source', 'target', skin, mesh)
            after = host.capture_all_skin_weights(skin, mesh)
            first = {short(row.influence_path): row.weight
                     for row in after.vertices[0].weights}
            transferred = (abs(first.get('Spine1_M', 0.) - .25) < 1e-6
                           and abs(first.get('Spine2_M', 0.) - .25) < 1e-6
                           and abs(first.get('Shoulder_R', 0.) - .5) < 1e-6)
            target_only = (all(':target:' in path or '|target:' in path
                               for path in after.influence_paths)
                           and not any(':source:' in path or '|source:' in path
                                       for path in after.influence_paths))
            pose = (cmds.listConnections(skin + '.bindPose', source=True,
                                        destination=False) or [None])[0]
            def old_pose_edges():
                return tuple(path for path in (cmds.listConnections(pose,
                    source=True, destination=False, plugs=True) or [])
                    if path.startswith('source:'))
            pose_released = not old_pose_edges()
            same_node = host.capture_skin_handoff_boundary(skin, mesh) == boundary
            neutral = host.capture_face_mesh(mesh).points == before_geometry
            cmds.undo()
            undo = (host.capture_all_skin_weights(skin, mesh) == before
                    and bool(old_pose_edges()))
            cmds.redo()
            redo = (host.capture_all_skin_weights(skin, mesh) == after
                    and not old_pose_edges())
            def vertex(frame):
                cmds.currentTime(frame, edit=True)
                return tuple(cmds.xform(mesh + '.vtx[0]', query=True,
                                        worldSpace=True, translation=True))
            moved = max(abs(a-b) for a, b in zip(vertex(1), vertex(10))) > 1e-4
            report = dict(vertices=result.vertex_count,
                target_influences=result.target_influence_count,
                rollback=rollback, transferred=transferred, target_only=target_only,
                pose_released=pose_released, same_node=same_node,
                neutral=neutral, moved=moved, deformer_present=deformer_present,
                undo=undo, redo=redo)
            (folder / 'spine-skin-handoff.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            if not all((report['vertices'] == 4, rollback, transferred,
                        target_only, pose_released, same_node, neutral,
                        deformer_present,
                        moved, undo, redo)):
                raise RuntimeError(report)
            cmds.file(rename=str(folder / 'spine-skin-handoff.ma'))
            cmds.file(save=True, type='mayaAscii', force=True)
        elif mode == 'inspect':
            scene_name = (sys.argv[3] if len(sys.argv) > 3
                          else 'spine-skin-handoff.ma')
            cmds.file(str(folder / scene_name), open=True, force=True)
            host = MayaSpineSkinHandoffHost()
            state = host.capture_all_skin_weights(skin, mesh)
            first = {short(row.influence_path): row.weight
                     for row in state.vertices[0].weights}
            MayaBodyBuildHost(namespace='source').read_character_registration()
            MayaBodyBuildHost(namespace='target').read_character_registration()
            if not (all('|target:' in path for path in state.influence_paths)
                    and abs(first.get('Spine1_M', 0.) - .25) < 1e-6
                    and abs(first.get('Spine2_M', 0.) - .25) < 1e-6):
                raise RuntimeError('重开后原 Skin 影响交接丢失')
            pose = (cmds.listConnections(skin + '.bindPose', source=True,
                                        destination=False) or [None])[0]
            if any(path.startswith('source:') for path in
                   (cmds.listConnections(pose, source=True,
                                         destination=False, plugs=True) or [])):
                raise RuntimeError('重开后 bindPose 仍连接旧骨架')
            if not any(cmds.nodeType(node) == 'deltaMush' for node in
                       (cmds.listHistory(mesh, pruneDagObjects=True) or [])):
                raise RuntimeError('重开后 DeltaMush 变形历史丢失')
            print('original skinCluster handoff reopen: target influences retained')
        else:
            raise ValueError(mode)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]))
