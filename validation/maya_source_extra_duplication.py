"""Native optional controller layers versus shared helpers in placed frames."""
from pathlib import Path
import json, os, sys, traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/source-extra-duplication-current'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), cases=[], scope=
        'Unedited asCreateController Sub/Extra blocks; FK/IK, root/role namespace, '
        'Euler orders 0/3/5, Extra only and Sub+Extra. Actual curves, compound '
        'rotation, inherited flags, visibility and joint motion; not full Body.')
    try:
        text = (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
        proc = text.index('global proc asCreateController (')
        start = text.index('if ($sub)\n', proc)
        end = text.index('xform -ws -t $pos[0]', start)
        mel.eval('global proc advNativeLayers(string $type,string $name,string $side,int $sub)'
                 '{int $extra=1;' + text[start:end] + '}')
        for kind in ('FK', 'IK'):
            for ns in ('', 'OtherRig:'):
                for order in (0, 3, 5):
                    for use_sub in (False, True):
                        states = []
                        for mode in ('native', 'python'):
                            c.file(new=True, force=True)
                            if ns:
                                c.namespace(add='OtherRig')
                                c.namespace(set='OtherRig')
                            offset = c.createNode('transform', name='ProbeOffset')
                            extra = c.createNode('transform', name=kind+'ExtraProbe_R', parent=offset)
                            c.setAttr(extra+'.rotateOrder', order)
                            c.setAttr(extra+'.scale', 1, 1, 1, lock=True)
                            if mode == 'python':
                                c.xform(offset, translation=(5,-2,3), rotation=(12,-20,35), scale=(1.2,.8,1.1))
                            control = c.circle(name=kind+'Probe_R', constructionHistory=False)[0]
                            c.parent(control, extra, relative=True)
                            c.setAttr(control+'.rotateOrder', order)
                            c.setAttr(control+'.visibility', True, keyable=False, channelBox=True)
                            c.setAttr(control+'Shape.overrideEnabled', True)
                            sub = ns+kind+'SubProbe_R'
                            if mode == 'native':
                                # The original block uses unqualified names.
                                # Resolve them in its role namespace, then
                                # restore absolute names for Python/readback.
                                c.namespace(relativeNames=bool(ns))
                                try:
                                    mel.eval('advNativeLayers "'+kind+'" "Probe" "_R" '+str(int(use_sub))+';')
                                finally:c.namespace(relativeNames=False)
                            else:
                                host = MayaBodyBuildHost()
                                main = c.ls(control, long=True)[0]
                                if use_sub:
                                    host._create_body_sub_control(main, sub, main+'|'+sub)
                                host._add_body_extra_curve(c.ls(extra, long=True)[0], main)
                            if mode == 'native':
                                c.xform(offset, translation=(5,-2,3), rotation=(12,-20,35), scale=(1.2,.8,1.1))
                            c.setAttr(control+'.extraControl', True)
                            if use_sub:
                                c.setAttr(control+'.subControl', True)
                                c.setAttr(sub+'.rotate', 20,-35,15, type='double3')
                            c.setAttr(extra+'.rotate', -10,25,35, type='double3')
                            joint = c.createNode('joint', name='DrivenProbe')
                            c.orientConstraint(sub if use_sub else control, joint, maintainOffset=False)
                            shape = ns+kind+'ExtraProbe_RShape'
                            state = dict(extra=c.xform(extra, query=True, worldSpace=True, matrix=True),
                                cvs=c.xform(shape+'.cv[*]', query=True, objectSpace=True, translation=True),
                                joint=c.xform(joint, query=True, worldSpace=True, matrix=True),
                                visible=c.getAttr(shape+'.visibility'), color=c.getAttr(shape+'.overrideColor'),
                                enabled=c.getAttr(shape+'.overrideEnabled'))
                            if use_sub:
                                state['sub_cvs']=c.xform(sub+'.cv[*]', query=True, objectSpace=True, translation=True)
                            states.append(state)
                        a,b=states
                        assert a['visible']==b['visible']==True and a['color']==b['color']==29
                        assert a['enabled']==b['enabled']
                        errors={name:max(abs(x-y) for x,y in zip(a[name],b[name]))
                                for name in ('extra','cvs','joint')+ (('sub_cvs',) if use_sub else ())}
                        assert max(errors.values())<=1e-8, errors
                        report['cases'].append(dict(kind=kind, namespace=ns, rotate_order=order,
                            sub=use_sub, errors=errors, status='passed'))
        report['status']='passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        c.namespace(set=':')
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
