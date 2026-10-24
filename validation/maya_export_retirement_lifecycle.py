"""Native DeleteUnusedJoints followed by preserved-data Body rebuilding."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/export-retirement-current'
SOURCE = ROOT / 'validation/results/source-body-current-parity/original-biped-current.mb'


def snapshot(c):
    enabled=bool(c.undoInfo(query=True,state=True))
    c.undoInfo(stateWithoutFlush=False)
    try:
        return _snapshot(c)
    finally:
        c.undoInfo(stateWithoutFlush=enabled)


def _snapshot(c):
    joints = c.listRelatives('DeformationSystem', allDescendents=True, type='joint', fullPath=True) or []
    meshes = [c.listRelatives(shape, parent=True, fullPath=True)[0]
              for shape in c.ls(type='mesh', noIntermediate=True, long=True)]
    samples = {}
    for frame in (1, 3, 5):
        c.currentTime(frame)
        c.dgdirty(allPlugs=True)
        samples[frame] = dict(joints={node: tuple(c.xform(node, query=True, worldSpace=True, matrix=True))
                                     for node in joints},
                             vertices={mesh: tuple(c.xform(mesh+'.vtx[*]', query=True, worldSpace=True,
                                                           translation=True)) for mesh in meshes})
    c.currentTime(1)
    skins = {}
    for skin in c.ls(type='skinCluster'):
        skins[skin] = dict(uuid=c.ls(skin, uuid=True)[0],
            slots={index: dict(matrix=c.getAttr(skin+'.matrix['+str(index)+']'),
                               source=c.connectionInfo(skin+'.matrix['+str(index)+']', sourceFromDestination=True))
                   for index in c.getAttr(skin+'.matrix', multiIndices=True) or []})
    return dict(samples=samples, skins=skins)


def difference(before, after):
    errors = []
    for frame, sample in before['samples'].items():
        for kind, rows in sample.items():
            actual = after['samples'][frame][kind]
            assert rows.keys() == actual.keys(), (frame,kind,'identity set changed')
            for name, values in rows.items():
                assert len(values) == len(actual[name])
                errors.extend(abs(a-b) for a,b in zip(values,actual[name]))
    return max(errors, default=0.)



def rebuild_saved(c,report,save,cleaned,after_cleanup,removed):
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from adv_py.product.maya_panel_controller import MayaPanelController
    import adv_py.adapters.maya_body_retirement_rebuild as retirement_rebuild
    original_capture,original_finish=retirement_rebuild.capture,retirement_rebuild.finish
    def graph_state(host,label):
        report.setdefault('rebuild_graph',{})[label]=dict(
            pid=os.getpid(),namespace=host.namespace,scale_blends=host._cmds.ls('*ScaleBlend*',long=True) or [])
        save()
    def capture_graph(host,*args,**kwargs):
        graph_state(host,'before-delete')
        if os.environ.get('ADV_RETIREMENT_SAVE_STAGE')=='1':
            path=OUT/'retired-stage-before.mb'
            c.file(rename=str(path));c.file(save=True,type='mayaBinary',force=True)
            report['prepared_stage_scene']=str(path)
            report['rebuild_graph']['before-delete']['end_scale_edges']={
                name:host._cmds.listConnections(name,source=False,destination=True,
                    plugs=True,connections=True) or []
                for name in host._cmds.ls('*Body2ScaleBlend',long=True) or []}
            save()
        return original_capture(host,*args,**kwargs)
    def finish_graph(host,*args,**kwargs):
        graph_state(host,'after-delete')
        return original_finish(host,*args,**kwargs)
    retirement_rebuild.capture,retirement_rebuild.finish=capture_graph,finish_graph
    try:
        MayaPanelController().body_rebuild(':','RetiredReplacement')
    finally:
        retirement_rebuild.capture,retirement_rebuild.finish=original_capture,original_finish
    retained = CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()
    rebuilt = snapshot(c)
    rebuild_error = difference(after_cleanup,rebuilt)
    assert rebuild_error <= 1e-4, rebuild_error
    assert {row.uuid for row in cleaned.curves} == {row.uuid for row in retained.curves}
    for skin in cleaned.skins:
        actual = next(row for row in retained.skins if row.uuid == skin.uuid)
        assert (skin.weights,skin.blend_weights,skin.component_memberships,skin.cached_matrices) == (
            actual.weights,actual.blend_weights,actual.component_memberships,actual.cached_matrices)
    assert all(not c.objExists(path) for path in removed)
    c.undo()
    assert MayaBodyBuildHost().read_character_registration() == cleaned.registration
    c.redo()
    assert MayaBodyBuildHost().read_character_registration() == retained.registration
    c.currentTime(1)
    after_file = OUT/'retired-after.mb'
    c.file(rename=str(after_file));c.file(save=True,type='mayaBinary',force=True)
    c.file(str(after_file),open=True,force=True,executeScriptNodes=False)
    assert MayaBodyBuildHost().read_character_registration() == retained.registration
    report.update(status='passed',stage='complete',rebuild_maximum_error=rebuild_error,
                  skin_animation_cache_preserved=True,rebuild_undo_redo=True,reopened_rebuild=True)

def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c, mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_original_export_preparation import MayaOriginalExportPreparationHost
    from adv_py.application.original_export_preparation import PrepareOriginalExport
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from adv_py.product.maya_panel_controller import MayaPanelController
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid())
    def save():
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        if os.environ.get('ADV_RETIREMENT_REBUILD_ONLY')=='1':
            previous=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
            assert previous.get('cleanup_undo_redo') and previous.get('reopened_cleanup')
            assert previous['cleanup_maximum_error']<=1e-4
            report.update(previous,status='running',pid=os.getpid(),stage='retired-rebuild',
                          resumed_from_pid=previous['pid'],
                          cleanup_evidence_pid=previous.get('cleanup_evidence_pid',
                              previous.get('resumed_from_pid',previous['pid'])))
            report.pop('traceback',None)
            report.pop('rebuild_graph',None)
            c.file(str(OUT/'retired-before.mb'),open=True,force=True,executeScriptNodes=False)
            c.currentTime(1);c.undoInfo(state=True)
            cleaned=CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()
            removed={row.path for row in cleaned.registration.retired_body}
            after_cleanup=snapshot(c)
            save()
            rebuild_saved(c,report,save,cleaned,after_cleanup,removed)
            return 0
        report['stage'] = 'saved-source-layouts'
        save()
        report['legacy_spline_scenes'] = []
        for folder in ('biped-source-bendy-parent-v7-nonopm',):
            path = ROOT/'validation/results'/folder/'original-biped-current.mb'
            if not path.exists():
                continue
            c.file(str(path), open=True, force=True, executeScriptNodes=False)
            row = dict(scene=str(path))
            try:
                registry = MayaBodyBuildHost().read_character_registration()
                row['layouts'] = [(plan.system_name,plan.source_alignment_frames)
                                  for plan in (registry.spine,*registry.additional_spines) if plan]
                row['status'] = 'read'
            except Exception:
                row.update(status='unreadable',traceback=traceback.format_exc())
            report['legacy_spline_scenes'].append(row)
        report['stage'] = 'native-cleanup'
        save()
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.file(str(SOURCE),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        # Give removable ends genuine production influences. The saved smoke
        # mesh otherwise binds only live torso/limb joints and cannot exercise
        # what native deletion does to end-joint Skin inputs.
        skins=c.ls(type='skinCluster') or []
        assert skins
        skin=skins[0]
        geometry=(c.skinCluster(skin,query=True,geometry=True) or [])[0]
        weighted_ends=('HeadEnd_M','ToesEnd_L','Tail2_L')
        for index,joint in enumerate(weighted_ends):
            c.skinCluster(skin,edit=True,addInfluence=joint,weight=0.,lockWeights=False)
            c.skinPercent(skin,geometry+'.vtx['+str(index)+']',transformValue=[(joint,.35)],normalize=True)
        input_file=OUT/'retirement-input.mb'
        c.file(rename=str(input_file));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(input_file),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        report['weighted_end_influences']=weighted_ends
        source_registration = MayaBodyBuildHost().read_character_registration()
        native_before=snapshot(c)
        source_joints = set(c.listRelatives('DeformationSystem',allDescendents=True,type='joint',fullPath=True) or [])
        outputs = {joint: tuple(c.listConnections(joint,source=False,destination=True,
                   plugs=True) or ()) for joint in source_joints}
        mel.eval('asDeleteUnusedJoints;')
        native = snapshot(c)
        native_repeat=snapshot(c)
        report['native_repeated_sample_error']=difference(native,native_repeat)
        report['native_repeat_first_vertices']={str(frame):sample['vertices']
            for frame,sample in native_repeat['samples'].items()}
        removed = source_joints - set(native['samples'][1]['joints'])
        assert removed, 'Fixture must contain removable native terminal joints'
        report['native_removed'] = sorted(removed)
        report['native_removed_registered_nodes'] = [row.path for row in source_registration.nodes
                                                     if not c.objExists(row.path)]
        report['source_spline_spaces'] = [plan.chest_space for plan in
            (source_registration.spine,*source_registration.additional_spines) if plan]
        report['native_disconnected_outputs'] = {}
        for joint in removed:
            for destination in outputs[joint]:
                if not c.objExists(destination) or c.connectionInfo(destination,sourceFromDestination=True):
                    continue
                datatype = c.getAttr(destination,type=True)
                try:
                    value = None if datatype=='message' else c.getAttr(destination)
                    row = dict(datatype=datatype,value=value)
                except Exception as error:
                    row = dict(datatype=datatype,error=str(error))
                report['native_disconnected_outputs'][destination] = row
        save()
        c.file(str(input_file),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        c.undoInfo(state=True)
        python_before=snapshot(c)
        report['input_sample_error']=difference(native_before,python_before)
        assert report['input_sample_error']<=1e-8,report['input_sample_error']
        export_host=MayaOriginalExportPreparationHost()
        import adv_py.adapters.maya_character_body_retirement as retirement
        original_capture,original_finish=retirement.capture,retirement.finish
        original_value,original_datatype=retirement.cached_value,retirement.cached_datatype
        original_remember=export_host._remember_export_preparation
        report['operation_trace']={}
        report['cache_read_trace']=[]
        def observe_cache(kind,plug):
            error=max((abs(a-b) for name,values in native['samples'][1]['vertices'].items()
                for a,b in zip(values,c.xform(name+'.vtx[*]',query=True,worldSpace=True,translation=True))),default=0.)
            report['cache_read_trace'].append(dict(kind=kind,plug=plug,maximum_vertex_error=error))
            save()
        def traced_value(commands,plug,datatype):
            result=original_value(commands,plug,datatype)
            observe_cache('value',plug)
            return result
        def traced_datatype(commands,plug):
            result=original_datatype(commands,plug)
            observe_cache('type',plug)
            return result
        def observe(label):
            sample=snapshot(c)
            error=max((abs(a-b) for frame,rows in native['samples'].items()
                for name,values in rows['vertices'].items()
                for a,b in zip(values,sample['samples'][frame]['vertices'][name])),default=0.)
            report['operation_trace'][label]=dict(error_from_native=error,
                first_vertices={name:values[:9] for name,values in sample['samples'][1]['vertices'].items()})
            save()
        def traced_capture(*args,**kwargs):
            result=original_capture(*args,**kwargs)
            observe('after-capture-before-delete')
            return result
        def traced_finish(*args,**kwargs):
            observe('after-delete-before-cache-read')
            result=original_finish(*args,**kwargs)
            observe('after-cache-read')
            return result
        def traced_remember(*args,**kwargs):
            result=original_remember(*args,**kwargs)
            observe('after-registration-write')
            return result
        tracing=os.environ.get('ADV_RETIREMENT_TRACE')=='1'
        if tracing:
            retirement.capture,retirement.finish=traced_capture,traced_finish
            retirement.cached_value,retirement.cached_datatype=traced_value,traced_datatype
            export_host._remember_export_preparation=traced_remember
        try:
            deleted = PrepareOriginalExport(export_host).apply('delete_unused_end_joints')
        finally:
            retirement.capture,retirement.finish=original_capture,original_finish
            retirement.cached_value,retirement.cached_datatype=original_value,original_datatype
        after_cleanup = snapshot(c)
        assert set(deleted) == removed
        cleanup_error = difference(native,after_cleanup)
        report['cleanup_maximum_error']=cleanup_error
        report['native_skins']=native['skins']
        report['python_skins']=after_cleanup['skins']
        report['cleanup_sample_errors']={frame:{kind:max((abs(a-b) for name,values in rows.items()
            for a,b in zip(values,after_cleanup['samples'][frame][kind][name])),default=0.)
            for kind,rows in sample.items()} for frame,sample in native['samples'].items()}
        report['cleanup_vertex_differences']={str(frame):{
            name:dict(maximum_error=max((abs(a-b) for a,b in zip(values,after_cleanup['samples'][frame]['vertices'][name])),default=0.),
                      native=values[:9],python=after_cleanup['samples'][frame]['vertices'][name][:9])
            for name,values in sample['vertices'].items()}
            for frame,sample in native['samples'].items()}
        save()
        assert cleanup_error <= 1e-4, cleanup_error
        report['native_skins']=native['skins']
        report['python_skins']=after_cleanup['skins']
        save()
        assert native['skins'].keys()==after_cleanup['skins'].keys()
        skin_error=0.
        for name,skin in native['skins'].items():
            actual=after_cleanup['skins'][name]
            assert skin['uuid']==actual['uuid'] and skin['slots'].keys()==actual['slots'].keys()
            for index,slot in skin['slots'].items():
                other=actual['slots'][index]
                assert slot['source']==other['source']
                if slot['matrix'] is None or other['matrix'] is None:
                    assert slot['matrix'] is other['matrix']
                    continue
                assert len(slot['matrix'])==len(other['matrix'])
                skin_error=max(skin_error,max(abs(a-b) for a,b in zip(slot['matrix'],other['matrix'])))
        # Connected matrices are evaluated afresh; compare with the existing
        # numeric cache audit tolerance, rather than Python float equality.
        assert skin_error<=1e-8,skin_error
        report['cleanup_skin_matrix_error']=skin_error
        cleanup_host = MayaBodyBuildHost()
        cleaned = CaptureBodyCharacterPreservation(cleanup_host).execute()
        assert {row.path for row in cleaned.registration.retired_body} == removed
        c.undo()
        assert MayaBodyBuildHost().read_character_registration() == source_registration
        c.redo()
        assert MayaBodyBuildHost().read_character_registration() == cleaned.registration
        before_file = OUT/'retired-before.mb'
        c.file(rename=str(before_file));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(before_file),open=True,force=True,executeScriptNodes=False)
        assert CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute() == cleaned
        report.update(stage='retired-rebuild',cleanup_maximum_error=cleanup_error,
                      retired_joints=len(removed),cleanup_undo_redo=True,reopened_cleanup=True)
        save()
        rebuild_saved(c,report,save,cleaned,after_cleanup,removed)
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc())
    finally:
        save()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (standalone or quit_on_finish):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
