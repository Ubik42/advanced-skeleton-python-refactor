"""Locate which real Mixed stage cannot restore its input graph with native undo."""
from pathlib import Path
from contextlib import contextmanager
import json,os,traceback

def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c,mel,utils
    from maya_face_mixed_parity import load_project_native_plugin
    load_project_native_plugin()
    import maya_face_conversion_parity as suite
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_conversion import ConvertOriginalFaceToBlendShapes
    output=suite.OUTPUT/'stage-undo.json'
    report={'status':'running','pid':os.getpid(),'stages':[]}
    def save():output.write_text(json.dumps(report,indent=2),encoding='utf8')
    try:
        attachers_only=os.environ.get('ADV_FACE_ATTACHERS_ONLY')=='1'
        if not attachers_only:
            mel.eval('source "'+(suite.ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
            c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        reuse=os.environ.get('ADV_FACE_STAGE_REUSE')=='1'
        c.file(str(suite.OUTPUT/('mixed-attachers-input.mb' if attachers_only else 'mixed-local-input.mb' if reuse else 'mixed-input.mb')),open=True,force=True,executeScriptNodes=False)
        c.undoInfo(state=True)
        host=MayaOriginalFaceBuildHost()
        @contextmanager
        def isolated_transaction(label):
            host._transaction_active=True;host._transaction_changed=False
            try:yield
            finally:host._transaction_active=False;host._transaction_changed=False
        host.transaction=isolated_transaction
        def wrap(method,name):
            def stage(*args,**kwargs):
                if name=='create_original_face_bs_attachers':
                    (suite.OUTPUT/'mixed-attachers-source.json').write_text(json.dumps(args[0]),encoding='utf8')
                    c.file(rename=str(suite.OUTPUT/'mixed-attachers-input.mb'));c.file(save=True,type='mayaBinary',force=True)
                before=suite.scene_identity()
                c.undoInfo(openChunk=True,chunkName=name)
                chunk_names=[c.undoInfo(query=True,chunkName=True)]
                try:value=method(*args,**kwargs)
                finally:
                    chunk_names.append(c.undoInfo(query=True,chunkName=True))
                    c.undoInfo(closeChunk=True)
                    chunk_names.append(c.undoInfo(query=True,chunkName=True))
                built=suite.scene_identity()
                c.undo();undone=suite.scene_identity()
                row={'name':name,'chunk_names':chunk_names,'before':len(before),'built':len(built),'undone':len(undone),
                     'undo_enabled':c.undoInfo(query=True,state=True),'queue_empty':c.undoInfo(query=True,undoQueueEmpty=True),
                     'extra':[v['name'] for k,v in undone.items() if k not in before],
                     'missing':[v['name'] for k,v in before.items() if k not in undone],
                     'changed':sum(before[k]!=undone[k] for k in before.keys()&undone.keys())}
                report['stages'].append(row);save()
                assert before==undone,row['name']
                c.redo();assert built==suite.scene_identity(),name+' redo identity'
                row['redo_identity_restored']=True;save()
                return value
            return stage
        original_mixed=host.make_original_face_bs_mixed_local
        def save_mixed_input(source):
            (suite.OUTPUT/'mixed-local-source.json').write_text(json.dumps(source),encoding='utf8')
            c.file(rename=str(suite.OUTPUT/'mixed-local-input.mb'));c.file(save=True,type='mayaBinary',force=True)
            return original_mixed(source)
        host.make_original_face_bs_mixed_local=save_mixed_input
        for name in ('prepare_original_face_bs_layers','sample_original_face_bs_targets',
                     'remove_original_face_bs_driving_graph','rebuild_original_face_bs_up_mid_lo',
                     'create_original_face_bs_attachers','finish_original_face_bs_conversion'):
            setattr(host,name,wrap(getattr(host,name),name))
        if attachers_only:
            source=json.loads((suite.OUTPUT/'mixed-attachers-source.json').read_text(encoding='utf8'))
            with host.transaction('Isolate attachers'):
                host.create_original_face_bs_attachers(source)
        elif reuse:
            source=json.loads((suite.OUTPUT/'mixed-local-source.json').read_text(encoding='utf8'))
            with host.transaction('Isolate Mixed local'):
                host.make_original_face_bs_mixed_local(source)
        else:
            ConvertOriginalFaceToBlendShapes(host).apply(keep_joints=True,keep_targets=False)
        report['status']='passed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        save()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish:utils.executeDeferred(c.quit,force=True)
