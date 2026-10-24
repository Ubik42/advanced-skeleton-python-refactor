"""Original Spline physical Part parent and Fit follow-level matrix batch."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as Row
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-spline-parent-follow-current'

@dataclass(frozen=True)
class FixturePlan:
    body_joints: tuple
    settings: str
    hybrid_constrained: str
    hybrid_follow: str
    source_controls_root: str
    use_offset_parent_matrix: bool
    system_name: str = ''
    targets: tuple = ('|A','|B')
    sub_targets: tuple = ()
    source_follow_parent: str | None = None
    source_follow_targets: tuple = ()
    source_native_follow: bool = False
    def target_parent(self,index):return '|PControls'


def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_source_spline_follow import create,audit
    from adv_py.core.source_spline_follow import configure_source_spline_follow
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[])
    def matrix(node):return tuple(c.xform(node,query=True,worldSpace=True,matrix=True))
    def transform(name,parent=None):
        flags=dict(name=name,skipSelect=True)
        if parent:flags['parent']=parent
        return c.ls(c.createNode('transform',**flags),long=True)[0]
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        for opm in (True,False):
            for part in (False,True):
                for non_symmetry in (False,True):
                    c.file(new=True,force=True)
                    side='L' if non_symmetry else 'R'
                    fit=transform('FitSkeleton')
                    c.addAttr(fit,longName='useOffsetParentMatrix',attributeType='bool',defaultValue=opm)
                    ui=c.window();c.columnLayout();c.checkBox('asBodyOffsetParentMatrixCheckBox',value=opm)
                    # Actual MEL label analysis: a two-joint custom Spline below Head.
                    fit_nodes=[];parent=fit
                    for name,label in (('Root','Root'),('Chest','Chest'),('Head','Head'),('Tail','0Tail'),('TailEnd','1Tail')):
                        node=c.createNode('joint',name=name,parent=parent,skipSelect=True)
                        c.setAttr(node+'.type',18);c.setAttr(node+'.otherType',label,type='string');c.setAttr(node+'.drawLabel',True)
                        parent=c.ls(node,long=True)[0]
                        fit_nodes.append(Row(path=parent,short_name=name,dag_parent=parent.rsplit('|',1)[0]))
                    fit_start=fit_nodes[3].path
                    if non_symmetry:
                        parent=fit
                        for name,label in (('Head_NonSymmetry','Head'),('Tail_NonSymmetry','0Tail'),('TailEnd_NonSymmetry','1Tail')):
                            node=c.createNode('joint',name=name,parent=parent,skipSelect=True)
                            c.setAttr(node+'.type',18);c.setAttr(node+'.otherType',label,type='string');c.setAttr(node+'.drawLabel',True)
                            parent=c.ls(node,long=True)[0]
                            fit_nodes.append(Row(path=parent,short_name=name,dag_parent=parent.rsplit('|',1)[0]))
                            if name=='Tail_NonSymmetry':fit_start=parent
                    c.addAttr('Root',longName='numMainExtras',attributeType='long',defaultValue=2)
                    extra2=transform('MainExtra2');extra1=transform('MainExtra1',extra2);main=transform('Main',extra1)
                    root_x=transform('RootX_M',main)
                    root_body=transform('Root_M');chest=transform('Chest_M',root_body);head=transform('Head_'+side,chest)
                    c.setAttr(head+'.translate',2,3,1,type='double3')
                    parent=transform('HeadPart1_'+side,head) if part else head
                    if part:c.setAttr(parent+'.translateY',.7)
                    tail=transform('Tail_'+side,parent)
                    native_root=transform('IKHandle');native_constrained=transform('IKOffsetConstrainedTail1_'+side,native_root)
                    native_follow=transform('IKhybridFollowTail1_'+side,native_root)
                    native_settings=transform('IKTail2_'+side)
                    c.addAttr(native_settings,longName='stiff',attributeType='double',defaultValue=0.)
                    p_root=transform('PControls');c.setAttr(p_root+'.inheritsTransform',False,lock=True)
                    constrained=transform('PConstrained',p_root);follow=transform('PFollow',p_root);settings=transform('PSettings')
                    for node in (native_follow,follow):c.setAttr(node+'.translate',1,2,3,type='double3')
                    body=Row(root=root_body,joints=tuple(Row(name=path.rsplit('|',1)[-1],path=path,parent_path=up)
                        for path,up in ((root_body,'|'),(chest,root_body),(head,chest),(tail,head))))
                    fk=Row(controls=(Row(driven_joint=root_body,control_path=root_x,source_override_path=None),))
                    globals=Row(control_path=main,extra_control_paths=(extra1,extra2))
                    plan=configure_source_spline_follow(FixturePlan((tail,),settings,constrained,follow,p_root,opm),
                        body,fk,globals,root_control_path=root_x,root_follow_path=root_x,
                        hierarchy=Row(joints=tuple(fit_nodes)),instances=(Row(output_name='Tail_'+side,source_joint=fit_start),))
                    assert plan.source_follow_parent==parent
                    assert [label for label,_,_ in plan.source_follow_targets]==['MainExtra2','MainExtra1','Main','Root']+([] if non_symmetry else ['Chest'])+['Head']
                    mel.eval('asParentConstraint "'+parent.rsplit('|',1)[-1]+'" "IKOffsetConstrainedTail1_'+side+'" "";')
                    if not opm:
                        c.delete('IKOffsetConstrainedTail1_'+side+'_scaleConstraint1')
                        c.scaleConstraint('Main',native_constrained)
                    mel.eval('asFollowLevels "IKTail2_'+side+'" "IKhybridFollowTail1_'+side+'" "'+fit_start.rsplit('|',1)[-1]+'";')
                    c.setAttr(native_settings+'.followRoot',10.)
                    host=MayaBodyBuildHost()
                    with host.transaction('Source Spline Part parenting fixture'):
                        create(host,plan);audit(host,plan)
                    for label,_,default in plan.source_follow_targets:
                        assert c.attributeQuery('follow'+label,node=native_settings,listDefault=True)==c.attributeQuery('follow'+label,node=settings,listDefault=True),label
                        assert c.getAttr(native_settings+'.follow'+label)==default, (label,c.getAttr(native_settings+'.follow'+label),default,mel.eval('asAdvJointIKInfo "'+fit_start.rsplit('|',1)[-1]+'";'))
                    for weight in (0.,5.,10.):
                        for scale in ((1.,1.,1.),(1.2,.9,1.4)):
                            c.setAttr(main+'.scale',*scale,type='double3')
                            c.setAttr(main+'.rotateY',17.)
                            c.setAttr(head+'.rotateZ',23.)
                            if part:c.setAttr(parent+'.rotateX',13.)
                            for target in (native_settings,settings):
                                c.setAttr(target+'.followHead',weight)
                                if not non_symmetry:c.setAttr(target+'.followChest',5.)
                                c.setAttr(target+'.followMainExtra1',2.)
                            errors={kind:max(abs(a-b) for a,b in zip(matrix(a_node),matrix(b_node)))
                                for kind,a_node,b_node in (('offset',native_constrained,constrained),('follow',native_follow,follow))}
                            report['cases'].append(dict(opm=opm,part=part,non_symmetry=non_symmetry,weight=weight,scale=scale,errors=errors,maximum_error=max(errors.values())))
                    audit(host,plan)
                    c.deleteUI(ui)
        report['maximum_error']=max(row['maximum_error'] for row in report['cases'])
        report['status']='passed' if report['maximum_error']<=1e-5 else 'failed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
