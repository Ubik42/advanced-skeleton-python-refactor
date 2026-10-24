"""Check the native cast journal with multiple swaps inside real GUI chunks."""
from pathlib import Path
import os, json, traceback
OUT=Path(__file__).resolve().parent/'results/native-node-cast-gui'

def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from maya_face_mixed_parity import load_project_native_plugin
    load_project_native_plugin()
    OUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running','pid':os.getpid(),'cases':[]}
    def case(casts):
        c.file(new=True,force=True); c.undoInfo(state=True)
        pairs=[]
        for index in range(casts):
            a=c.createNode('transform',name='Source%d'%index)
            b=c.createNode('transform',name='Destination%d'%index)
            c.addAttr(a,longName='authored',attributeType='double',defaultValue=.37)
            pairs.append((a,b))
        c.createNode('transform',name='OuterMarker')
        row={'casts':casts,'initial_name':c.undoInfo(query=True,undoName=True)}
        c.undoInfo(openChunk=True,chunkName='GUI cast batch')
        c.createNode('transform',name='BeforeCast')
        for a,b in pairs: c.advPyNativeNodeCast(a,b,1)
        c.createNode('transform',name='AfterCast')
        c.undoInfo(closeChunk=True)
        row['built_name']=c.undoInfo(query=True,undoName=True)
        c.undo()
        row['undone']={'before':c.objExists('BeforeCast'),'after':c.objExists('AfterCast'),
            'source_attributes':[c.objExists(a+'.authored') for a,b in pairs]}
        c.redo()
        row['redone']={'before':c.objExists('BeforeCast'),'after':c.objExists('AfterCast'),
            'destination_attributes':[c.objExists(b+'.authored') for a,b in pairs]}
        report['cases'].append(row)
        assert not row['undone']['before'] and not row['undone']['after'], row
        assert all(row['undone']['source_attributes']), row
        assert row['redone']['before'] and row['redone']['after'], row
        assert all(row['redone']['destination_attributes']), row
    try:
        for count in (0,1,3,100):case(count)
        report['status']='passed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish:utils.executeDeferred(c.quit,force=True)
