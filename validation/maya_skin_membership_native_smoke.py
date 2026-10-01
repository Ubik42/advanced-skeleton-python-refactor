"""Verify native legacy/tag membership, deformation, save and transaction Undo."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost

    output.mkdir(parents=True,exist_ok=True)
    for use_tags in (False,True):
        cmds.file(new=True,force=True)
        cmds.undoInfo(state=True)
        mesh=cmds.polyCube(name='MembershipMesh')[0]
        cmds.select(clear=True)
        joint=cmds.joint(name='MembershipJoint')
        skin=cmds.skinCluster(joint,mesh,toSelectedBones=True,
                              useComponentTags=use_tags)[0]
        mesh=cmds.ls(mesh,long=True)[0]
        host=MayaBodyBuildHost()
        count=int(cmds.polyEvaluate(mesh,vertex=True))
        complete=tuple(range(count))
        members=(0,2,3)
        assert host.capture_skin_vertex_membership(skin,mesh)==complete
        with host.transaction('Restrict native Skin components'):
            host.apply_skin_vertex_membership(skin,mesh,members)
        assert host.capture_skin_vertex_membership(skin,mesh)==members
        cmds.undo()
        assert host.capture_skin_vertex_membership(skin,mesh)==complete
        with host.transaction('Restrict native Skin components'):
            host.apply_skin_vertex_membership(skin,mesh,members)
        before=tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))
        cmds.setAttr(joint+'.translateX',2)
        after=tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))
        for index in complete:
            assert abs(after[index*3]-before[index*3]-(2 if index in members else 0))<1e-6
        scene=output/('tag-members.mb' if use_tags else 'set-members.mb')
        cmds.file(rename=str(scene.resolve()))
        cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
        assert host.capture_skin_vertex_membership(skin,mesh)==members
        with host.transaction('Restore complete Skin membership'):
            host.apply_skin_vertex_membership(skin,mesh,complete)
        assert host.capture_skin_vertex_membership(skin,mesh)==complete
        print('PASS native Skin membership',dict(use_component_tags=use_tags,
            partial_deformation=True,undo=True,saved_reopened=True))


if __name__=='__main__':
    main(Path(sys.argv[1]))
