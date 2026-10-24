"""Actual Aim source-side traversal and saved channel order remain independent."""
from pathlib import Path
from types import SimpleNamespace as NS
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-fit-aim-order-current'

def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c
    from adv_py.core.body_fit_aim import plan_body_fit_aim, BodyFitAimLayout, TRANSFORM, TRANSLATION
    from adv_py.core.fit_symmetry import FitBuildSide
    from adv_py.core.fit_metadata import FitJointField
    from adv_py.adapters.maya_body_fit_aim import MayaBodyFitAimMixin
    class Host(MayaBodyFitAimMixin):
        _cmds=c
        _transaction_changed=False
        def _require_transaction(self):pass
        def _create_body_fit_aim_side(self,spec,side,**kw):
            self.trace.append((spec.stem,side.suffix))
            return super()._create_body_fit_aim_side(spec,side,**kw)
    report=dict(status='running',pid=os.getpid(),cases=[])
    OUT.mkdir(parents=True,exist_ok=True)
    try:
        # Source 80634 traverses authored Fit order for b=1, then b=-1.
        # B's independently authored L is in b=1; A's mirrored L is b=-1.
        for opm in (False,True):
          for legacy in (False,True):
            c.file(new=True,force=True)
            main=c.createNode('transform',name='Main')
            for attr in ('aimLRVis','aimFKVis'):c.addAttr(main,longName=attr,attributeType='bool',defaultValue=True)
            c.createNode('transform',name='Group')
            c.createNode('transform',name='MotionSystem',parent='Group')
            c.createNode('transform',name='AimSystem',parent='MotionSystem')
            head=c.createNode('joint',name='Head_M');c.setAttr(head+'.translate',0,5,0,type='double3')
            fitroot='|Fit';headfit=fitroot+'|Head'
            def joint(path,position,parent):return NS(path=path,short_name=path.rsplit('|',1)[-1],world_position=position,dag_parent=parent)
            b=headfit+'|B_NonSymmetry';a=headfit+'|A'
            c.createNode('transform',name='Fit')
            c.createNode('joint',name='Head',parent=fitroot)
            c.createNode('joint',name='B_NonSymmetry',parent=headfit)
            c.createNode('joint',name='BEnd_NonSymmetry',parent=b)
            c.createNode('joint',name='A',parent=headfit)
            c.createNode('joint',name='AEnd',parent=a)
            parentfit=headfit+'|Parent';cf=parentfit+'|C'
            c.createNode('joint',name='Parent',parent=headfit)
            c.createNode('joint',name='C',parent=parentfit)
            c.createNode('joint',name='CEnd',parent=cf)
            # Snapshot order is deliberately different from Maya's native order.
            hierarchy=NS(container=fitroot,joints=(joint(headfit,(0,5,0),fitroot),joint(a,(-2,6,0),headfit),joint(a+'|AEnd',(-3,6,0),a),joint(b,(2,6,0),headfit),joint(b+'|BEnd_NonSymmetry',(3,6,0),b)))
            hierarchy.joints+=(joint(parentfit,(-2,5,0),headfit),joint(cf,(-2,6,0),parentfit),joint(cf+'|CEnd',(-3,6,0),cf))
            host=Host();host.trace=[]
            source_order=host.capture_body_fit_aim_source_order(hierarchy)
            assert source_order==tuple(c.listRelatives(fitroot,allDescendents=True,type='joint',fullPath=True))
            assert source_order.index(b)<source_order.index(a)
            controls=[];instances=[];bodies=[NS(name='Head_M',path='|Head_M')]
            parent=c.createNode('joint',name='Parent_R');c.setAttr(parent+'.translate',-2,5,0,type='double3')
            bodies.append(NS(name='Parent_R',path='|Parent_R'))
            for stem,suffix,source,mirrored,position in (('A','L',a,True,(2,6,0)),('A','R',a,False,(-2,6,0)),('B','L',b,False,(2,6,0)),('C','L',cf,True,(2,6,0))):
                offset=c.createNode('transform',name='FKOffset'+stem+'_'+suffix)
                c.xform(offset,worldSpace=True,translation=position)
                aim=c.createNode('transform',name='FKAim'+stem+'_'+suffix,parent=offset)
                control=c.circle(name='FK'+stem+'_'+suffix,constructionHistory=False)[0];control=c.parent(control,aim,relative=True)[0]
                full=c.ls(control,long=True)[0];side=FitBuildSide(suffix)
                controls.append(NS(side=side,aim_path=c.ls(aim,long=True)[0],offset_path=c.ls(offset,long=True)[0],control_path=full,fit_joint_names=(source.rsplit('|',1)[-1],stem),world_position=position))
                bodies.append(NS(name=stem+'_'+suffix,path='|'+stem+'_'+suffix))
                instances.append(NS(side=side,source_joint=source,mirrored=mirrored))
            metadata=tuple(NS(joint=source,present_fields=(FitJointField.AIM,)) for source in (a,b,cf))
            saved=(BodyFitAimLayout('A',TRANSFORM+('follow',),(('L',TRANSFORM),('R',TRANSFORM))),BodyFitAimLayout('B',TRANSFORM+('follow',),(('L',TRANSFORM),)),BodyFitAimLayout('C',TRANSFORM+('follow',),(('L',TRANSFORM),))) if legacy else None
            specs=plan_body_fit_aim(hierarchy,metadata,NS(joints=tuple(bodies)),tuple(controls),instances=tuple(instances),saved_layouts=saved,fit_joint_order=source_order)
            assert [spec.stem for spec in specs]==(['A','B','C'] if legacy else ['B','A','C'])
            assert next(spec for spec in specs if spec.stem=='C').follow_joint=='|Parent_R'
            if legacy:assert tuple(side.suffix for side in specs[0].sides)==('L','R')
            c.undoInfo(openChunk=True,chunkName='SourceAimBatch')
            try:host.create_body_fit_aims(specs,global_control='|Main',use_offset_parent_matrix=opm)
            finally:c.undoInfo(closeChunk=True)
            expected=[('B','L'),('A','R'),('A','L'),('C','L')]
            assert host.trace==expected,(host.trace,expected)
            for spec in specs:assert host.capture_body_fit_aim(spec,global_control='|Main',use_offset_parent_matrix=opm)
            before={spec.stem:c.ls(spec.root,uuid=True)[0] for spec in specs}
            c.undo();assert all(not c.objExists(spec.root) for spec in specs)
            c.redo();assert {spec.stem:c.ls(spec.root,uuid=True)[0] for spec in specs}==before
            scene=OUT/f'order-{int(opm)}-{int(legacy)}.mb'
            c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            for spec in specs:assert host.capture_body_fit_aim(spec,global_control='|Main',use_offset_parent_matrix=opm)
            assert {spec.stem:c.ls(spec.root,uuid=True)[0] for spec in specs}==before
            report['cases'].append(dict(opm=opm,legacy=legacy,source_fit_order=source_order,creation_order=host.trace,registration_order=[(spec.stem,[side.suffix for side in spec.sides]) for spec in specs],undo_redo_identity=True,reopened=True))
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        full_scene=ROOT/'validation/results/source-fit-aim-provenance-lifecycle-current/traditional/original-biped-current.mb'
        assert full_scene.exists()
        report['character_source_orders']=[]
        for namespace in ('','AimOrder'):
            c.file(new=True,force=True)
            if namespace:c.file(str(full_scene),i=True,namespace=namespace,executeScriptNodes=False)
            else:c.file(str(full_scene),open=True,force=True,executeScriptNodes=False)
            bodyhost=MayaBodyBuildHost(namespace=namespace)
            snapshot=bodyhost.capture_fit_hierarchy('FitSkeleton')
            native_order=bodyhost.capture_body_fit_aim_source_order(snapshot)
            report['character_source_orders'].append(dict(namespace=namespace,count=len(native_order),native_order=native_order,snapshot_order=tuple(node.path for node in snapshot.joints)))
        assert report['character_source_orders'][0]['native_order']==report['character_source_orders'][1]['native_order']
        report['status']='passed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
