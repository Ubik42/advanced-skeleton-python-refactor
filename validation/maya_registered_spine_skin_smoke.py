"""Registered 4-to-6 spine influence transfer on animated, skinned characters."""
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
    folder.mkdir(parents=True, exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaFaceHost
        from adv_py.application import EditSkinWeights, TransferSkinWeightsBySurface
        from adv_py.core import (SkinInfluenceWeight, SkinVertexWeights,
            registered_spine_weight_redistribution)

        if mode == 'prepare':
            cmds.file(str(folder / 'character-spine-product.ma'), open=True, force=True)
            cmds.undoInfo(state=True)
            cmds.currentTime(1, edit=True)
            source_host = MayaBodyBuildHost(namespace='source')
            target_host = MayaBodyBuildHost(namespace='target')
            source = source_host.read_character_registration()
            target = target_host.read_character_registration()
            source_mesh = cmds.polyPlane(name='source:SourceMesh', width=2., height=2.,
                subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
            target_mesh = cmds.polyPlane(name='target:TargetMesh', width=2., height=2.,
                subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
            source_mesh = cmds.ls(source_mesh, long=True)[0]
            target_mesh = cmds.ls(target_mesh, long=True)[0]
            source_joints = tuple(source_host.scene_address(path)
                                  for path in source.spine.body_joints)
            target_joints = tuple(target_host.scene_address(path)
                                  for path in target.spine.body_joints)
            source_arm = next(source_host.scene_address(row.path) for row in source.body
                              if short(row.path) == 'Shoulder_R')
            target_arm = next(target_host.scene_address(row.path) for row in target.body
                              if short(row.path) == 'Shoulder_R')
            cmds.skinCluster(*source_joints, source_arm, source_mesh,
                name='source:SourceSkin', toSelectedBones=True,
                maximumInfluences=8)
            cmds.skinCluster(*target_joints, target_arm, target_mesh,
                name='target:TargetSkin', toSelectedBones=True,
                maximumInfluences=8)
            host = MayaFaceHost()
            source_skin = 'source:SourceSkin'
            target_skin = 'target:TargetSkin'
            source_state = host.capture_all_skin_weights(source_skin, source_mesh)
            by_name = {short(path): path for path in source_state.influence_paths}
            weighted = tuple(SkinVertexWeights(index,
                (SkinInfluenceWeight(by_name['Spine1_M'], .5),
                 SkinInfluenceWeight(by_name['Shoulder_R'], .5)) if index == 0 else
                (SkinInfluenceWeight(by_name['Chest_M'], 1.),))
                for index in range(source_state.vertex_count))
            EditSkinWeights(host).apply(source_skin, source_mesh, weighted)
            source_state = host.capture_all_skin_weights(source_skin, source_mesh)
            target_state = host.capture_all_skin_weights(target_skin, target_mesh)
            mapping = registered_spine_weight_redistribution(source, target,
                source_state.influence_paths, target_state.influence_paths,
                source_namespace='source', target_namespace='target',
                target_skin_name=target_skin, target_mesh_path=target_mesh)
            scene = folder / 'registered-spine-skin-before.ma'
            cmds.file(rename=str(scene))
            cmds.file(save=True, type='mayaAscii', force=True)
            result = TransferSkinWeightsBySurface(host).apply(source_skin, source_mesh,
                target_skin, target_mesh, max_distance=1e-6, redistribution=mapping)
            after = host.capture_all_skin_weights(target_skin, target_mesh)
            source_unchanged = (host.capture_all_skin_weights(source_skin, source_mesh)
                                == source_state)
            first = {short(row.influence_path): row.weight
                     for row in after.vertices[0].weights}
            split = (first.get('Spine1_M', 0.) > 0.
                     and first.get('Spine2_M', 0.) > 0.
                     and abs(first.get('Shoulder_R', 0.) - .5) < 1e-6)
            cmds.undo()
            undo = host.capture_all_skin_weights(target_skin, target_mesh) == target_state
            cmds.redo()
            redo = host.capture_all_skin_weights(target_skin, target_mesh) == after
            def vertex(frame):
                cmds.currentTime(frame, edit=True)
                return tuple(cmds.xform(target_mesh + '.vtx[0]', query=True,
                                        worldSpace=True, translation=True))
            moved = max(abs(a-b) for a, b in zip(vertex(1), vertex(10))) > 1e-4
            report = dict(changed=result.edit_result.changed_vertex_count,
                source_unchanged=source_unchanged, split=split, undo=undo,
                redo=redo, animated_mesh_moved=moved, first_weights=first)
            (folder / 'registered-spine-skin-prepare.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            if not all((report['changed'] > 0, source_unchanged, split, undo,
                        redo, moved)):
                raise RuntimeError(report)
        elif mode == 'inspect':
            scene_name = (sys.argv[3] if len(sys.argv) > 3
                          else 'registered-spine-skin-after.ma')
            cmds.file(str(folder / scene_name),
                      open=True, force=True)
            host = MayaFaceHost()
            target_mesh = '|target:TargetMesh'
            target = host.capture_all_skin_weights('target:TargetSkin', target_mesh)
            first = {short(row.influence_path): row.weight
                     for row in target.vertices[0].weights}
            if not (first.get('Spine1_M', 0.) > 0.
                    and first.get('Spine2_M', 0.) > 0.
                    and abs(first.get('Shoulder_R', 0.) - .5) < 1e-6):
                raise RuntimeError('重开后脊柱分段权重未保留：' + str(first))
            MayaBodyBuildHost(namespace='source').read_character_registration()
            MayaBodyBuildHost(namespace='target').read_character_registration()
            print('registered spine skin reopen: split influence and both characters valid')
        else:
            raise ValueError(mode)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]))
