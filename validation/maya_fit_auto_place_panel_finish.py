"""The two public Fit buttons finish guides before resolving optional fields."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from maya_fit_auto_place_lifecycle import fixture
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
    from adv_py.core.preparation_objects import PreparationObjectRole as Role
    from adv_py.product.maya_panel_controller import MayaPanelController
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'running','cases':[]}
    for method in ('fit_auto_place','fit_auto_scale'):
        row={'button':method};report['cases'].append(row)
        try:
            skin,all_objects=fixture('ordinary')
            eye=c.polyCube(name='OptionalEyeModel')[0]
            records=MayaPreparationObjectsHost(':')
            records.write_objects(Role.SKIN,tuple(c.ls(skin,long=True)))
            records.write_objects(Role.ALL,tuple(c.ls(all_objects,long=True)))
            records.write_objects(Role.RIGHT_EYE,tuple(c.ls(eye,long=True)))
            c.delete(eye,*all_objects)
            # Strict reads stay strict when starting a new operation.
            try:records.read_objects(Role.RIGHT_EYE)
            except ValueError:pass
            else:raise AssertionError('Deleted eye record unexpectedly resolved')
            controller=MayaPanelController(host_factory=MayaFitJointHost)
            def model_check(**kwargs):raise AssertionError('Finish called model checker')
            controller.model_check=model_check
            result=getattr(controller,method)(':',interactive=False)
            assert result.finished and not c.objExists('AutoPlacing')
            assert c.getAttr(skin[0]+'.visibility') and c.getAttr('Root.visibility')
            c.undo();assert c.objExists('AutoPlacing')
            c.redo();assert not c.objExists('AutoPlacing')
            row.update(status='passed',missing_eye_ignored=True,missing_all_ignored=True,
                       undo_redo=True)
        except Exception:row.update(status='failed',error=traceback.format_exc())
    report['status']='passed' if all(row['status']=='passed' for row in report['cases']) else 'failed'
    (output/'panel.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
