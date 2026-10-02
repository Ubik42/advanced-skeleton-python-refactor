"""GUI source palette/width/snap actions and Python public panel actions."""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def fixture():
    from maya import cmds as c
    c.file(new=True,force=True)
    control=c.curve(name='FKWrist_R',degree=1,
        point=((1.,2.,0.),(3.,2.,0.),(3.,4.,0.),(1.,4.,0.),(1.,2.,0.)))
    second=c.circle(name='SecondShape',radius=.5,constructionHistory=False)[0]
    shape=c.listRelatives(second,shapes=True)[0]
    c.parent(shape,control,shape=True,relative=True)
    c.delete(second)
    c.setAttr(control+'.rotate',11.,23.,-9.,type='double3')
    c.setAttr(control+'.scale',1.3,.8,1.1,type='double3')
    c.select(control,replace=True)
    return control


def snapshot(control):
    from maya import cmds as c
    return {shape:{'points':c.xform(shape+'.cv[*]',query=True,objectSpace=True,translation=True),
        'enabled':c.getAttr(shape+'.overrideEnabled'),
        'index':c.getAttr(shape+'.overrideColor'),
        'rgb_enabled':c.getAttr(shape+'.overrideRGBColors'),
        'rgb':c.getAttr(shape+'.overrideColorRGB')[0],
        'width':c.getAttr(shape+'.lineWidth')}
        for shape in c.listRelatives(control,shapes=True,fullPath=True)}


def difference(native,python):
    assert native.keys()==python.keys()
    maximum=0.
    for shape,values in native.items():
        for key,value in values.items():
            other=python[shape][key]
            if key in ('points','rgb'):
                assert len(value)==len(other)
                maximum=max(maximum,max((abs(a-b) for a,b in zip(value,other)),default=0.))
            else:assert value==other,(shape,key,value,other)
    return maximum


def main(output):
    from maya import cmds as c,mel
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'running','cases':[]}
    source=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
    mel.eval('source "'+source.as_posix()+'";')
    window=c.window()
    c.columnLayout()
    c.palettePort('asCurveColorPalettePort',dimensions=(16,2))
    c.intField('asCurveWidthIntField',value=5)
    c.floatField('ScaleCCFloatField',value=2.)
    c.optionMenu('asControllerTypeOptionMenu')
    from adv_py.core.control_curve_selection import CONTROL_CURVE_TYPES,CONTROL_CURVE_SIDES
    for value in CONTROL_CURVE_TYPES:c.menuItem(label=value)
    c.optionMenu('asControllerSideOptionMenu')
    for value in CONTROL_CURVE_SIDES:c.menuItem(label=value)
    c.showWindow(window)
    panel=MayaPanelController(host_factory=MayaBodyBuildHost)
    cases=[('indexed_color',6,None),('custom_rgb',6,(.12,.34,.56)),('zero_index_rgb',0,(.2,.4,.6)),
           ('line_width',-1,None),('line_width',7,None),
           ('snap_x','x',None),('snap_y','y',None),('snap_z','z',None)]
    cases += [('scale',2.,None),('scale',-.5,None),('scale',0.,None)]
    for case,value,rgb in cases:
        row={'case':case,'value':value};report['cases'].append(row)
        try:
            control=fixture()
            scene=output/(case+str(value)+'-input.mb')
            c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
            initial=snapshot(control)
            matrix=c.xform(control,query=True,worldSpace=True,matrix=True)
            selection=c.ls(selection=True,long=True)
            if case=='scale':
                c.sets(control,name='ControlSet')
                c.sets(empty=True,name='FaceControlSet')
                c.floatField('ScaleCCFloatField',edit=True,value=value)
                c.file(save=True,type='mayaBinary',force=True)
            if 'color' in case or 'rgb' in case:
                color=rgb if rgb is not None else c.colorIndex(value,query=True)
                c.palettePort('asCurveColorPalettePort',edit=True,rgbValue=(value,*color),setCurCell=value)
                mel.eval('asSetCurveColor;')
            elif case=='line_width':
                c.intField('asCurveWidthIntField',edit=True,value=value)
                mel.eval('asSetCurveWidth;')
            elif case=='scale':mel.eval('asScaleControlCurves;')
            else:mel.eval('asSnapRotateCurve {'+','.join('1' if axis==value else '0' for axis in 'xyz')+'};')
            native=snapshot(control)
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            c.select(control,replace=True)
            nodes=set(c.ls(uuid=True) or [])
            if 'color' in case or 'rgb' in case:panel.control_curves_palette(':',(),value,rgb=rgb)
            elif case=='line_width':panel.control_curves_width(':',(),value)
            elif case=='scale':panel.control_curves_scale(':',(),value)
            else:panel.control_curves_snap_rotate(':',(),value)
            python=snapshot(control)
            maximum=difference(native,python)
            assert maximum<=1e-6,maximum
            assert nodes==set(c.ls(uuid=True) or [])
            assert matrix==c.xform(control,query=True,worldSpace=True,matrix=True)
            assert selection==c.ls(selection=True,long=True)
            c.undo();assert difference(initial,snapshot(control))<=1e-6
            c.redo();assert difference(python,snapshot(control))<=1e-6
            row.update(status='passed',maximum_error=maximum,undo_redo=True,scene_nodes_preserved=True)
        except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'original_controller_selector'};report['cases'].append(row)
    try:
        fixture()
        names=('FKWrist_R','FKIKArm_R','IKArm_L','FKIndexFinger1_R','FKThumbFinger1_L',
               'RootX_M','BendElbow_L','FKWristExtra_R','WristSlider_R')
        for name in names[1:]:c.circle(name=name,constructionHistory=False)
        c.sets(names,name='ControlSet')
        c.createNode('transform',name='ctrlBox')
        for category in ('A','B','C','Aim'):
            c.addAttr('ctrlBox',longName=category+'CtrlVis',attributeType='bool',defaultValue=True)
            for side in ('R','L','M'):
                node=c.circle(name='Face'+category+'_'+side,constructionHistory=False)[0]
                c.connectAttr('ctrlBox.'+category+'CtrlVis',node+'.visibility')
        checked=0
        for category in CONTROL_CURVE_TYPES:
            for side in CONTROL_CURVE_SIDES:
                c.optionMenu('asControllerTypeOptionMenu',edit=True,value=category)
                c.optionMenu('asControllerSideOptionMenu',edit=True,value=side)
                mel.eval('asSelectCurve;')
                native=c.ls(selection=True,long=True) or []
                panel.select_control_curves(':',category,side)
                assert native==(c.ls(selection=True,long=True) or []),(category,side)
                checked+=1
        row.update(status='passed',source_cases=checked)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    try:
        from adv_py.product.maya_panel import create_panel
        widget=create_panel(panel)
        assert len(widget.control_curve_palette_buttons.buttons())==32
        assert widget.control_curve_width.minimum()==-1 and widget.control_curve_width.maximum()==100
        widget._select_control_curve_palette(6)
        assert widget.control_curve_palette_index==6
        widget.close();widget.deleteLater()
        report['panel_widgets']='passed'
    except Exception:report['panel_widgets']=traceback.format_exc()
    c.deleteUI(window)
    report['status']='passed' if all(r['status']=='passed' for r in report['cases']) and report['panel_widgets']=='passed' else 'failed'
    (output/'style.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report
