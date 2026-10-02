"""Namespaced prop failure rollback and shared full-biped rebuild regression."""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main():
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_one_joint_prop import MayaOneJointPropHost
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.one_joint_prop import BuildOneJointProp
    from adv_py.application.character_rebuild import RebuildBodyCharacter
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from adv_py.core.body_build_options import BodyBuildOptions
    report={}
    output=ROOT/'validation/results/one-joint-prop-source'
    try:
        c.file(new=True,force=True)
        c.namespace(add='model')
        mesh=c.polyCube(name='model:PropMesh',width=4,height=6,depth=2)[0]
        c.move(0,5,-2,mesh)
        c.namespace(add='hero')
        sentinel=c.createNode('transform',name='tempMatrixTransform')
        sentinel_uuid=c.ls(sentinel,uuid=True)[0]
        before=set(c.ls(uuid=True))
        for fault_stage in ('skins-bound','geometry-parented'):
            def fail(stage):
                if stage==fault_stage: raise RuntimeError('injected '+stage)
            try:
                BuildOneJointProp(MayaOneJointPropHost(namespace='hero')).apply(
                    ('|model:PropMesh',),(),build_options=BodyBuildOptions(
                        use_offset_parent_matrix=True),on_stage=fail)
            except RuntimeError as error:
                assert str(error)=='injected '+fault_stage
            else: raise AssertionError('failure did not roll back')
            assert set(c.ls(uuid=True))==before
            assert c.objExists('|model:PropMesh')
        report['two_late_failures_restore_all_nodes']=True
        c.undoInfo(state=True)
        host=MayaOneJointPropHost(namespace='hero')
        result=BuildOneJointProp(host).apply(('|model:PropMesh',),(),
            build_options=BodyBuildOptions(use_offset_parent_matrix=True))
        control=host.scene_address(result.control)
        c.undoInfo(stateWithoutFlush=False)
        initial=c.xform('model:PropMesh.vtx[*]',q=True,ws=True,t=True)
        c.setAttr(control+'.translateX',2)
        moved=c.xform('model:PropMesh.vtx[*]',q=True,ws=True,t=True)
        assert max(abs(b-a-(2 if i%3==0 else 0)) for i,(a,b) in enumerate(zip(initial,moved)))<1e-5
        c.setAttr(control+'.translateX',0)
        c.undoInfo(stateWithoutFlush=True)
        c.undo()
        assert not c.objExists('hero:Group')
        c.redo()
        assert c.objExists('hero:Root_M')
        assert c.ls(sentinel_uuid)
        report['namespaced_external_model_build_undo_redo']=True
        # Exercise the shared internal Fit staging change on a complete
        # existing source biped, without rerunning its 71-pose source suite.
        scene=ROOT/'validation/results/biped-source-bendy-parent-v5-nonopm/original-biped-current.mb'
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        body=MayaBodyBuildHost(namespace='')
        registration=body.read_character_registration()
        preserved=CaptureBodyCharacterPreservation(body).execute()
        # Owned controller/solver curve skins are rebuilt along with their
        # graph. Only retained authored geometry belongs to this contract.
        skins=tuple(skin.uuid for skin in preserved.skins)
        fit=registration.container
        fit_uuid=c.ls(fit,uuid=True)[0]
        curves=c.xform(fit+'.cv[*]',q=True,os=True,t=True)
        RebuildBodyCharacter(body).apply('PropRegressionRebuild')
        assert c.ls(fit_uuid)
        assert all(c.ls(uid) for uid in skins)
        assert max(abs(a-b) for a,b in zip(curves,c.xform(fit+'.cv[*]',q=True,os=True,t=True)))<1e-8
        assert len(body.read_character_registration().body)==len(registration.body)
        report['full_biped_shared_rebuild']=True
        report['status']='passed'
    except Exception:
        report['status']='failed'
        report['traceback']=traceback.format_exc()
    finally:
        output.mkdir(parents=True,exist_ok=True)
        (output/'isolation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2))
        maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
