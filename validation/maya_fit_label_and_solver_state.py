"""Native Fit label business and RP initial-state diagnosis in one owned Maya."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/fit-label-and-solver-state-current'


def load_label_procedures(mel):
    from adv_migration.mel_inventory import PROC_HEADER, _matching_brace
    source=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
    wanted={'asAddFitJointLabel','asRemoveFitJointLabel','asLabelCodeLookup',
            'asUpdateLabelHelp','asUpdateAttributeHelp'}
    found=set()
    for match in PROC_HEADER.finditer(source):
        if match['name'] in wanted:
            end=_matching_brace(source,match.end()-1)
            mel.eval(source[match.start():end+1])
            found.add(match['name'])
    assert found==wanted


def labels(c,mel):
    from adv_py.core.source_fit_labels import SOURCE_FIT_LABEL_CODES, source_fit_label_help
    from adv_py.core.source_fit_attributes import SOURCE_FIT_ATTRIBUTE_TYPES, source_fit_attribute_help
    from adv_py.product.maya_panel_controller import MayaPanelController
    controller=MayaPanelController()
    window=c.window()
    c.columnLayout()
    menu=c.optionMenu('asLabelType')
    for name in SOURCE_FIT_LABEL_CODES:
        c.menuItem(label=name)
    help_control=c.text('asLabelHelp')
    attribute_menu=c.optionMenu('asAttributeType')
    for attribute in SOURCE_FIT_ATTRIBUTE_TYPES:c.menuItem(label=attribute)
    attribute_help=c.text('asAttributeHelp')

    def fixture():
        c.file(new=True,force=True)
        c.namespace(add='LabelTest')
        js=[c.createNode('joint',name='LabelTest:'+name) for name in ('First','Second','Unselected')]
        nonjoint=c.createNode('transform',name='LabelTest:NotJoint')
        for joint in js:
            c.setAttr(joint+'.drawLabel',False)
            c.setAttr(joint+'.type',18)
            c.setAttr(joint+'.otherType','preserved',type='string')
        c.select(*js[:2],nonjoint,replace=True)
        return js

    def state(js):
        return [[c.getAttr(j+'.'+attr) for attr in ('drawLabel','type','otherType')] for j in js]

    rows=[]
    try:
        for attribute in SOURCE_FIT_ATTRIBUTE_TYPES:
            c.optionMenu(attribute_menu,edit=True,value=attribute)
            mel.eval('asUpdateAttributeHelp;')
            assert c.text(attribute_help,query=True,label=True)==source_fit_attribute_help(attribute)
        for name in SOURCE_FIT_LABEL_CODES:
            js=fixture()
            c.optionMenu(menu,edit=True,value=name)
            mel.eval('asUpdateLabelHelp;')
            expected_help=c.text(help_control,query=True,label=True)
            assert expected_help==source_fit_label_help(name),(name,expected_help)
            mel.eval('asAddFitJointLabel;')
            added=state(js)
            mel.eval('asRemoveFitJointLabel;')
            removed=state(js)
            js=fixture()
            assert controller.fit_source_labels(':',name)==2
            assert state(js)==added,(name,state(js),added)
            c.undo()
            assert state(js)==[[False,18,'preserved']]*3
            c.redo()
            assert state(js)==added
            assert controller.fit_source_labels(':',name,remove=True)==2
            assert state(js)==removed
            c.undo()
            assert state(js)==added
            c.redo()
            assert state(js)==removed
            rows.append(dict(label=name,add_remove_equal=True,undo_redo=True,help_equal=True))
        scene=OUT/'label-preservation.mb'
        c.file(rename=str(scene))
        c.file(save=True,type='mayaBinary',force=True)
        expected=state(js)
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        assert state(js)==expected
        c.select(clear=True)
        assert controller.fit_source_labels(':','Root')==0
        return dict(status='passed',rows=rows,save_reopen=True,empty_selection=True,
                    namespace=True,unselected_joint_and_transform_unchanged=True,
                    source_attribute_help_count=len(SOURCE_FIT_ATTRIBUTE_TYPES))
    finally:
        c.deleteUI(window)


def solver_state(c):
    from maya_rp_input_compare import snapshot
    from maya_original_body_pose_compare import set_edit
    native=ROOT/'validation/results/original-spline-multi-nonopm-reference/original-spline-multi-nonopm-reference.mb'
    python=ROOT/'validation/results/source-ik-native-creation-current/original-biped-current.mb'
    names=('Shoulder_L','Elbow_L','Wrist_L')
    rows=[]
    for label,scene in (('native',native),('python',python)):
        for case in ('baseline','forceSolver','toggleBlend','recreateHandle'):
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            c.currentTime(1)
            if case=='baseline':
                # ASCII stores raw channel values even when connections drive
                # their live values. Inspect source serialization, not getAttr.
                c.file(rename=str(OUT/(label+'-solver-inputs.ma')))
                c.file(save=True,type='mayaAscii',force=True)
            h=next(iter(snapshot(c)['handles']))
            if case=='forceSolver':
                c.ikHandle(h,edit=True,forceSolver=True)
            elif case=='toggleBlend':
                c.setAttr(h+'.ikBlend',0.)
                c.dgdirty(allPlugs=True)
                for n in names:c.xform(n,query=True,worldSpace=True,matrix=True)
                c.setAttr(h+'.ikBlend',1.)
            elif case=='recreateHandle':
                s=snapshot(c)['handles'][h]
                joint_paths=list(s['joints'])
                parent=c.listRelatives(h,parent=True,fullPath=True)[0]
                matrix=c.xform(h,query=True,worldSpace=True,matrix=True)
                twist=c.connectionInfo(h+'.twist',sourceFromDestination=True)
                old_name=h.rsplit('|',1)[-1]
                c.delete(h)
                h,e=c.ikHandle(name=old_name,startJoint=joint_paths[0],
                    endEffector=joint_paths[-1],solver='ikRPsolver',createCurve=False,numSpans=2)
                c.xform(h,worldSpace=True,matrix=matrix)
                h=c.parent(h,parent,absolute=True)[0]
                c.setAttr(h+'.poleVector',*s['poleVector'][0],type='double3')
                if twist:c.connectAttr(twist,h+'.twist')
            set_edit(c,('FKIKArm_L.FKIKBlend','AdvPy_ArmSettings.armIkFk_L',10.,1.),0 if label=='native' else 1)
            c.setAttr(('IKArm_L' if label=='native' else 'AdvPy_ArmIK_L')+'.translateZ',.7)
            c.dgdirty(allPlugs=True)
            rows.append(dict(rig=label,case=case,matrices={n:c.xform(n,query=True,worldSpace=True,matrix=True) for n in names}))
    base=next(row['matrices'] for row in rows if row['rig']=='native' and row['case']=='baseline')
    for row in rows:
        row['maximum_error']=max(abs(a-b) for n in names for a,b in zip(base[n],row['matrices'][n]))
    return dict(status='diagnostic_completed',rows=rows,
                scope='Unsaved solver-state experiments; not parity acceptance or production changes')


def solver_load_state(c):
    """Compare the same stored channel values across Maya load formats."""
    import re
    from maya_original_body_pose_compare import set_edit

    scenes={
        'native-mb':ROOT/'validation/results/original-spline-multi-nonopm-reference/original-spline-multi-nonopm-reference.mb',
        'python-mb':ROOT/'validation/results/source-ik-native-creation-current/original-biped-current.mb',
        'native-ma':OUT/'native-solver-inputs.ma',
        'python-ma':OUT/'python-solver-inputs.ma',
    }
    texts={label:scenes[label+'-ma'].read_bytes().decode('latin1') for label in ('native','python')}
    names={'native':'IKXElbow_L','python':'AdvPy_ElbowIKDriver_L'}
    seeds={}
    for label,text in texts.items():
        block=re.search(r'createNode joint -n "'+names[label]+r'"[^\n]*\n(.*?)(?=\ncreateNode)',text,re.S)
        assert block
        seeds[label]=re.search(r'setAttr "\.r" -type "double3" ([^;]+);',block.group(1)).group(1)
    for label,text in texts.items():
        other='python' if label=='native' else 'native'
        start=text.index('createNode joint -n "'+names[label]+'"')
        end=text.index('\ncreateNode',start+1)
        block=text[start:end]
        edited,n=re.subn(r'(setAttr "\.r" -type "double3" )[^;]+;',
                        lambda m:m.group(1)+seeds[other]+';',block)
        assert n==1
        path=OUT/(label+'-opposite-neutral-seed.ma')
        path.write_bytes((text[:start]+edited+text[end:]).encode('latin1'))
        scenes[label+'-opposite-seed']=path
    rows=[]
    names=('Shoulder_L','Elbow_L','Wrist_L')
    for label,scene in scenes.items():
        native=label.startswith('native')
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        set_edit(c,('FKIKArm_L.FKIKBlend','AdvPy_ArmSettings.armIkFk_L',10.,1.),0 if native else 1)
        c.setAttr(('IKArm_L' if native else 'AdvPy_ArmIK_L')+'.translateZ',.7)
        c.dgdirty(allPlugs=True)
        rows.append(dict(case=label,matrices={n:c.xform(n,query=True,worldSpace=True,matrix=True) for n in names}))
    base=rows[0]['matrices']
    for row in rows:
        row['maximum_error']=max(abs(a-b) for n in names for a,b in zip(base[n],row['matrices'][n]))
    return dict(status='diagnostic_completed',rows=rows,
                scope='Maya loading and neutral-rotation seed diagnosis; no production changes')


def main(*,standalone=False,quit_on_finish=True):
    if standalone:raise ValueError('Maya Qt session required')
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid())
    try:
        load_label_procedures(mel)
        if os.environ.get('ADV_SOLVER_ONLY')!='1':
            report['labels']=labels(c,mel)
        report['solver']=(solver_load_state(c) if os.environ.get('ADV_LOAD_STATE_ONLY')=='1' else solver_state(c))
        report['status']='passed'
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
