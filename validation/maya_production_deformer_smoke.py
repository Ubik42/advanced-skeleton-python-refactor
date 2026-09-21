"""Rebuild a role with asymmetric skin weights and retained mesh deformers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import maya.standalone


def main(source, folder):
    folder.mkdir(parents=True, exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import RebuildBodyCharacter, ResolveBodyCharacter, CaptureBodyCharacterPreservation
        from adv_py.adapters.maya_character_preservation import capture_skin, connections

        c.file(str((source / 'spline-4.ma').resolve()), open=True, force=True)
        c.undoInfo(state=True)
        host = MayaBodyBuildHost(namespace='hero')
        registration = ResolveBodyCharacter(host).execute()
        mesh = c.polyCube(name='hero:ProductionMesh', constructionHistory=False)[0]
        c.xform(mesh, worldSpace=True, translation=c.xform('hero:Spine2_M',query=True,worldSpace=True,translation=True))
        target = c.duplicate(mesh, name='hero:SmileTarget')[0]
        c.move(.4, target + '.vtx[0]', relative=True, moveX=True)
        blend = c.blendShape(target, mesh, frontOfChain=True, name='hero:ProductionBlend')[0]
        c.setAttr(blend + '.weight[0]', .6)
        skin = c.skinCluster('hero:Root_M', 'hero:Spine2_M', mesh,
                             toSelectedBones=True, normalizeWeights=1,
                             maximumInfluences=2, name='hero:ProductionSkin')[0]
        for index in range(8):
            chest = (.05, .25, .8, .95, .15, .45, .7, .9)[index]
            c.skinPercent(skin, mesh + f'.vtx[{index}]', transformValue=(('hero:Root_M', 1.-chest), ('hero:Spine2_M', chest)))
        mush = c.deltaMush(mesh, name='hero:ProductionMush', smoothingIterations=2)[0]
        c.setAttr(mush + '.envelope', .35)
        from maya import mel
        driver=c.duplicate(mesh,name='hero:WrapDriver')[0]
        c.select(mesh,driver,replace=True)
        c.namespace(setNamespace=':hero')
        try:mel.eval('CreateWrap')
        finally:c.namespace(setNamespace=':')
        wraps=c.ls(type='wrap') or []
        if len(wraps)!=1:raise RuntimeError('Wrap 构建未生成唯一变形器：'+repr(wraps))
        wrap=c.rename(wraps[0],'hero:ProductionWrap')
        c.setAttr(wrap+'.envelope',.2)
        c.setAttr(wrap+'.maxDistance',100.)
        c.setAttr(wrap+'.autoWeightThreshold',False)
        c.setAttr(driver+'.inflType',1)
        control = host.scene_address(registration.spine.fk_controls[2])
        def points():
            return tuple(c.xform(mesh + '.vtx[*]', query=True, worldSpace=True, translation=True))
        def error(left, right):
            return max(abs(a-b) for a,b in zip(left,right))
        c.currentTime(1)
        neutral = points()
        c.move(.15,driver+'.vtx[0]',relative=True,moveX=True)
        wrap_effect=error(neutral,points())
        c.currentTime(1,edit=True,update=True)
        neutral=points()
        c.setKeyframe(control, attribute='rotateY', time=1, value=18.)
        c.currentTime(1, edit=True, update=True)
        posed = points()
        deformation = error(neutral, posed)
        original = capture_skin(host, skin)
        preservation=CaptureBodyCharacterPreservation(host).execute()
        captured_types={item.node_type for item in preservation.deformers}
        def deformer_state():
            return (tuple(c.listHistory(mesh, pruneDagObjects=True) or []),
                    tuple((node, connections(host,node)) for node in (blend,mush,wrap)),
                    tuple((plug,c.getAttr(plug)) for plug in
                          (blend+'.envelope',blend+'.weight[0]',mush+'.envelope',mush+'.smoothingIterations',wrap+'.envelope')))
        original_deformers=deformer_state()
        uuids = tuple(c.ls(node, uuid=True)[0] for node in (mesh, blend, skin, mush,wrap))
        RebuildBodyCharacter(host).apply('replacement')
        rebuilt = error(posed, points())
        retained = tuple(c.ls(node, uuid=True)[0] for node in (mesh, blend, skin, mush,wrap)) == uuids
        skin_retained = capture_skin(host, skin) == original
        deformers_retained = deformer_state() == original_deformers
        filename=(folder/'production-deformers.ma').resolve()
        c.file(rename=str(filename));c.file(save=True,type='mayaAscii',force=True)
        c.file(str(filename),open=True,force=True)
        ResolveBodyCharacter(host).execute()
        reopened = error(posed, points())
        reopened_skin = capture_skin(host, skin) == original
        reopened_deformers = deformer_state() == original_deformers
        result=dict(deformation=deformation,wrap_effect=wrap_effect,rebuilt=rebuilt, reopened=reopened,
                    captured_types=sorted(captured_types),
                    retained=retained, skin_retained=skin_retained, deformers_retained=deformers_retained,
                    reopened_skin=reopened_skin,reopened_deformers=reopened_deformers)
        result['passed']=deformation>.001 and wrap_effect>.001 and captured_types=={'blendShape','deltaMush','wrap'} and rebuilt<1e-4 and reopened<1e-4 and all(
            (retained,skin_retained,deformers_retained,reopened_skin,reopened_deformers))
        (folder/'report.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        print(json.dumps(result),flush=True)
        return 0 if result['passed'] else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
