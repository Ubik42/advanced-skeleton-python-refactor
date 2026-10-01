"""Compare full Python Bake outputs with measured unmodified original Bake.

This does not replace or weaken the strict source/destination equality smoke.
The native GUI report supplies every vertex at all six sampled poses.
"""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene,reference,output,animated=False,converted=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    from maya_original_corrective_bake_smoke import create_bake_fixture
    native=json.loads(reference.read_text(encoding='utf-8'))
    assert native['status']=='original_bake_measured'
    assert native['stages']==['original_ui_loaded','unmodified_original_six_axis_bake']
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    host=MayaCorrectiveShapesHost();controller=MayaPanelController()
    control=create_bake_fixture(cmds,host)
    original_curves={}
    if animated:
        for frame,rotation in ((0,(0,0,0)),(10,(0,0,12))):
            cmds.currentTime(frame);cmds.setAttr(control+'.rotate',*rotation,type='double3');cmds.setKeyframe(control+'.rotate')
        time_curves=cmds.listConnections(control,s=True,d=False,type='animCurveTA') or []
        if converted:
            for curve in time_curves:
                destination=cmds.listConnections(curve+'.output',s=False,d=True,p=True)[0]
                conversion=cmds.createNode('unitConversion',name=curve+'PoseUnits')
                cmds.disconnectAttr(curve+'.output',destination)
                cmds.connectAttr(curve+'.output',conversion+'.input')
                cmds.connectAttr(conversion+'.output',destination)
            cmds.dgdirty(allPlugs=True)
            assert abs(cmds.getAttr(control+'.rz')-12)<1e-7
        for curve in time_curves:
            original_curves[curve]={'uuid':cmds.ls(curve,uuid=True)[0],'times':cmds.keyframe(curve,q=True,timeChange=True),'values':cmds.keyframe(curve,q=True,valueChange=True),'destinations':cmds.listConnections(curve+'.output',s=False,d=True,p=True)}
    report={'status':'running','source_sha256':native['source_sha256'],'samples':[],'stages':[]}
    def points(node):
        cmds.dgdirty(allPlugs=True)
        return tuple(cmds.xform(node+'.vtx[*]',q=True,ws=True,t=True))
    def difference(a,b):
        assert len(a)==len(b)
        return max(abs(x-y) for x,y in zip(a,b))
    def compare():
        samples=[]
        for sample in native['samples']:
            axis=sample['axis'];amount=sample['amount']
            cmds.setAttr(control+'.rotate',0,0,0,type='double3')
            cmds.setAttr(control+'.r'+axis,amount)
            source=points('BakeSource');destination=points('BakeDestination')
            source_error=difference(source,sample['source_vertices'])
            parity_error=difference(destination,sample['destination_vertices'])
            assert source_error<1e-5,(axis,amount,'source',source_error)
            assert parity_error<1e-5,(axis,amount,'port vs native',parity_error)
            samples.append({'axis':axis,'amount':amount,'source_fixture_error':source_error,'native_destination_parity_error':parity_error,'source_destination_error':difference(source,destination)})
        return samples
    try:
        if not converted:cmds.setAttr(control+'.rz',12)
        cmds.select(control,r=True)
        result=controller.original_corrective_shapes(':','bake',source='BakeSource',destination='BakeDestination',axes=(True,)*6,q_rotations=True,mirror=False)
        assert len(result)==6
        aliases=cmds.aliasAttr('BakeDestinationCorrective',q=True)[::2]
        assert sorted(aliases)==sorted(native['target_aliases'])
        assert abs(cmds.getAttr(control+'.rz')-12)<1e-7 and cmds.ls(sl=True)==[control]
        cmds.undo();assert not cmds.objExists('BakeDestinationCorrective')
        cmds.redo();assert len(controller.original_corrective_targets(':'))==6
        report['stages'].append('six_targets_pose_selection_restore_undo_redo')
        if animated:
            for curve,data in original_curves.items():
                assert cmds.ls(curve,uuid=True)==[data['uuid']]
                assert cmds.keyframe(curve,q=True,timeChange=True)==data['times']
                assert cmds.keyframe(curve,q=True,valueChange=True)==data['values']
                assert cmds.listConnections(curve+'.output',s=False,d=True,p=True)==data['destinations']
            with host.transaction('Compare keyed bake poses'):
                pose=host.capture_original_control_pose()
                with host.original_driver_animation_scope(pose):
                    report['samples']=compare()
                    host.restore_original_control_pose(pose)
            report['stages'].append('original_animation_curve_identity_keys_connections')
        else:report['samples']=compare()
        report['stages'].append('six_pose_all_vertex_original_parity')
        path=output/'source-parity-bake.mb';cmds.file(rename=str(path));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(path),open=True,force=True,executeScriptNodes=False)
        if animated:
            with host.transaction('Compare reopened keyed bake poses'):
                pose=host.capture_original_control_pose()
                with host.original_driver_animation_scope(pose):
                    compare();host.restore_original_control_pose(pose)
            cmds.currentTime(0);cmds.dgdirty(allPlugs=True);assert abs(cmds.getAttr(control+'.rz'))<1e-7
            cmds.currentTime(10);cmds.dgdirty(allPlugs=True);assert abs(cmds.getAttr(control+'.rz')-12)<1e-7
            for curve,data in original_curves.items():
                assert cmds.ls(curve,uuid=True)==[data['uuid']]
                assert cmds.listConnections(curve+'.output',s=False,d=True,p=True)==data['destinations']
            # A late native failure must restore the same time inputs and
            # leave no half-constructed corrective graph after transaction undo.
            before={curve:cmds.listConnections(curve+'.output',s=False,d=True,p=True) for curve in original_curves}
            try:
                with host.transaction('Injected keyed pose failure'):
                    with host.original_driver_animation_scope(host.capture_original_control_pose()):
                        cmds.setAttr(control+'.rz',55)
                        raise RuntimeError('Injected after time inputs detached')
            except RuntimeError as error:assert str(error)=='Injected after time inputs detached'
            cmds.dgdirty(allPlugs=True)
            assert abs(cmds.getAttr(control+'.rz')-12)<1e-7
            assert all(cmds.listConnections(curve+'.output',s=False,d=True,p=True)==links for curve,links in before.items())
            report['stages'].append('keyed_pose_failure_restores_connections')
        else:compare()
        report['stages'].append('save_reopen_original_parity')
        report['strict_source_destination_equality']=all(row['source_destination_error']<.003 for row in report['samples'])
        report['status']='passed_source_parity'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'bake-parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'bake-parity-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve(),'--animated' in sys.argv or '--converted' in sys.argv,'--converted' in sys.argv)
