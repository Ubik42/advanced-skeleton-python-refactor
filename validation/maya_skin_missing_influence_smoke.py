"""Import weights into a skin that omits only an unused source influence."""
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(folder):
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import ExportSkinWeights,ImportSkinWeights
        from adv_py.core import SkinWeightInfluenceMapping,SkinWeightPathMapping,SkinWeightValidationError

        c.file(new=True,force=True);c.undoInfo(state=True)
        a=c.joint(name='JointA',position=(0,0,0));b=c.joint(name='JointB',position=(0,1,0))
        c.select(clear=True)
        source=c.polyCube(name='SourceMesh',constructionHistory=False)[0]
        target=c.polyCube(name='TargetMesh',constructionHistory=False)[0]
        source=c.ls(source,long=True)[0];target=c.ls(target,long=True)[0]
        src_skin=c.skinCluster(a,b,source,toSelectedBones=True,maximumInfluences=2,
                               normalizeWeights=1,name='SourceSkin')[0]
        dst_skin=c.skinCluster(a,target,toSelectedBones=True,maximumInfluences=2,
                               normalizeWeights=1,name='TargetSkin')[0]
        for index in range(8):
            c.skinPercent(src_skin,source+f'.vtx[{index}]',transformValue=((a,1.),(b,0.)))
        host=MayaBodyBuildHost()
        source_state=host.capture_all_skin_weights(src_skin,source)
        mapping=SkinWeightPathMapping(dst_skin,target,
                (SkinWeightInfluenceMapping(source_state.influence_paths[0],source_state.influence_paths[0]),))
        path=folder/'unused-influence.json'
        ExportSkinWeights(host).apply(src_skin,source,path)
        rejected_by_default=False
        try:ImportSkinWeights(host).plan(path,mapping=mapping)
        except SkinWeightValidationError:rejected_by_default=True
        imported=ImportSkinWeights(host).apply(path,mapping=mapping,allow_unweighted_missing=True)
        target_state=host.capture_all_skin_weights(dst_skin,target)
        accepted=(imported.plan.target_document.influence_paths==target_state.influence_paths
                  and target_state.vertices==imported.plan.target_document.vertices)
        c.skinPercent(src_skin,source+'.vtx[0]',transformValue=((a,.7),(b,.3)))
        weighted=folder/'weighted-influence.json'
        ExportSkinWeights(host).apply(src_skin,source,weighted)
        before=host.capture_all_skin_weights(dst_skin,target)
        rejected_weighted=False
        try:ImportSkinWeights(host).apply(weighted,mapping=mapping,allow_unweighted_missing=True)
        except SkinWeightValidationError:rejected_weighted=True
        unchanged=host.capture_all_skin_weights(dst_skin,target)==before
        report=dict(rejected_by_default=rejected_by_default,accepted=accepted,
                    rejected_weighted=rejected_weighted,unchanged=unchanged)
        report['passed']=all(report.values())
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report),flush=True)
        return 0 if report['passed'] else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
