"""Record source scan decisions and the pre-cleanup scene, without changing them."""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(output,initialize=True):
    if initialize:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.application.fit_auto_place import AutoPlaceFit
    from adv_py.adapters import maya_fit_auto_place as engine
    from adv_py.adapters import maya_fit_auto_place_fingers as fingers
    from adv_py.adapters import maya_fit_auto_place_arm_scan as arms

    output.mkdir(parents=True, exist_ok=True)
    c.file(new=True, force=True)
    c.selectMode(object=True)
    c.file(str(ROOT / 'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),
           i=True, executeScriptNodes=False)
    c.file(str(ROOT / 'validation/results/fit-auto-place-sam/sam-model.ma'),
           i=True, executeScriptNodes=False)
    skin = tuple(c.ls('AutoPlaceSample*', type='transform'))
    if not c.objExists('FitSkeleton.fitSkeletonTemplate'):
        c.addAttr('FitSkeleton', longName='fitSkeletonTemplate', dataType='string')
    c.setAttr('FitSkeleton.fitSkeletonTemplate', 'biped', type='string')
    report = {'status': 'running', 'attempts': [], 'scans': []}
    original_detect, original_finish = engine.detect_fingers, engine.finish

    def trace(frame, event, arg):
        if frame.f_code.co_filename==arms.__file__ and frame.f_code.co_name=='arm_scan' and event=='line':
            values=frame.f_locals
            if values['s'].axis=='yArmStraight' and 'vertices' in values:
                report['arm_selection']=list(values['vertices'])
            if values['s'].axis=='yArmStraight' and 'point' in values and 'vertices' not in values:
                report['arm_sample_point']=list(values['point'])
        if frame.f_code.co_filename == fingers.__file__ and frame.f_code.co_name == '_grow_finger_curve':
            if event == 'line':
                values = frame.f_locals
                state = values['s']
                if 'finger' in values:
                    current = {'finger': values['finger'], 'index': values.get('ring_index'),
                               'points': len(values.get('points', ())),
                               'average_diameter': state.average_finger_diameter,
                               'diameter': values.get('diameter'),
                               'failed': state.finger_grow_failed,
                               'knuckle': values.get('knuckle')}
                    latest[values['finger']] = current
        return trace

    latest = {}
    def detect(state):
        report['scans'].append({'axis': state.axis, 'index': state.index,
                               'hits': state.hits, 'four': state.four_fingers,
                               'failed': state.finger_grow_failed,
                               'first_split_x': state.first_split_x,
                               'scan_x': c.getAttr('asFitScanCurve.translateX')})
        candidate = state.axis == 'y' and state.hits == 4 and not state.four_fingers
        if candidate:
            latest.clear()
            sys.settrace(trace)
        try:
            return original_detect(state)
        finally:
            if candidate:
                sys.settrace(None)
                report['attempts'].append({'scan_index': state.index,
                    'hits_after': state.hits, 'four_after': state.four_fingers,
                    'failed_after': state.finger_grow_failed, 'fingers': dict(latest)})

    def finish(*args):
        c.file(rename=str(output / 'before-cleanup.mb'))
        c.file(save=True, type='mayaBinary', force=True)
        return original_finish(*args)

    engine.detect_fingers, engine.finish = detect, finish
    original_arm=engine.arm_scan
    active_arm=[None]
    raw_get_attr=c.getAttr
    def get_attr(*args,**kwargs):
        value=raw_get_attr(*args,**kwargs)
        if args and args[0]=='closestSampler.closestVertexIndex' and active_arm[0]=='yArmStraight':
            report['arm_sampler']={'index':value,'point':raw_get_attr('closestSampler.inPosition'),
                'input':c.listConnections('closestSampler.inMesh',source=True,destination=False,plugs=True),
                'mode':c.selectMode(query=True,object=True)}
        return value
    c.getAttr=get_attr
    raw_skin_percent=c.skinPercent
    def skin_percent(*args,**kwargs):
        if kwargs.get('transformValue')==[('asFitShoulderStraight',1.)]:
            report['arm_constraints']=c.polySelectConstraint(query=True,stateString=True)
            report['arm_mask']=(c.selectType(query=True,polymeshVertex=True),c.selectMode(query=True,object=True))
        return raw_skin_percent(*args,**kwargs)
    c.skinPercent=skin_percent
    def arm(state):
        active_arm[0]=state.axis
        sys.settrace(trace)
        try:result=original_arm(state)
        finally:sys.settrace(None);active_arm[0]=None
        if state.axis=='yArmStraight' and state.break_axis:
            c.file(rename=str(output/'shoulder-checkpoint.mb'))
            c.file(save=True,type='mayaBinary',force=True)
        return result
    engine.arm_scan=arm
    try:
        result = AutoPlaceFit(MayaFitJointHost()).apply(skin=skin)
        report.update(status='completed' if result.guides_active else 'not_detected',
                      axes=result.axes_completed, guides=result.guides_active)
    except Exception:
        report.update(status='failed', error=traceback.format_exc())
    finally:
        sys.settrace(None)
        engine.detect_fingers, engine.finish = original_detect, original_finish
        engine.arm_scan=original_arm
        c.skinPercent=raw_skin_percent
        c.getAttr=raw_get_attr
        (output / 'diagnostic.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('scans','arm_selection','arm_constraints')}, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
