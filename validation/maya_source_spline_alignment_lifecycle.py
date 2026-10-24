"""Migrate real saved pre-AlignIKTo Spline data with retained production data."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT = ROOT/'validation/results/spline-alignment-current'
SOURCE = ROOT/'validation/results/biped-source-bendy-parent-v7-nonopm/original-biped-current.mb'


def main(*,standalone=False,quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from adv_py.application.source_spline_alignment_upgrade import UpgradeSourceSplineAlignment
    from adv_py.core.source_spline_alignment_upgrade import audit_source_spline_alignment_upgrade
    from adv_py.adapters.maya_source_spline_alignment import read
    from maya_export_retirement_lifecycle import snapshot,difference
    OUT.mkdir(parents=True,exist_ok=True)
    report = dict(status='running',pid=os.getpid(),stage='saved-legacy-scene')
    def save():
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        c.file(str(SOURCE),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        c.undoInfo(state=True)
        original = CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()
        layouts = tuple(plan for plan in (original.registration.spine,*original.registration.additional_spines) if plan)
        assert len(layouts)==4 and all(not plan.source_alignment_frames for plan in layouts)
        before = snapshot(c)
        report.update(stage='alignment-rebuild',systems=[plan.system_name for plan in layouts])
        save()
        result = UpgradeSourceSplineAlignment(MayaBodyBuildHost(namespace='')).apply('AlignmentReplacement')
        retained = CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()
        assert result.systems==tuple(plan.system_name for plan in layouts)
        audit_source_spline_alignment_upgrade(original.registration,retained.registration,result.systems)
        frames = {}
        host = MayaBodyBuildHost()
        for plan in (retained.registration.spine,*retained.registration.additional_spines):
            rows = read(host,plan)
            assert len(rows)==2
            frames[plan.system_name] = [row.target for row in rows]
        error = difference(before,snapshot(c))
        assert error<=1e-4,error
        assert {row.uuid for row in original.curves}=={row.uuid for row in retained.curves}
        for skin in original.skins:
            actual = next(row for row in retained.skins if row.uuid==skin.uuid)
            assert (skin.weights,skin.blend_weights,skin.component_memberships)==(
                actual.weights,actual.blend_weights,actual.component_memberships)
        report.update(stage='alignment-undo',frames=frames,maximum_error=error,
                      skin_animation_preserved=True)
        save()
        c.undo()
        assert MayaBodyBuildHost().read_character_registration()==original.registration
        c.redo()
        assert MayaBodyBuildHost().read_character_registration()==retained.registration
        c.currentTime(1)
        path = OUT/'aligned-after.mb'
        c.file(rename=str(path));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(path),open=True,force=True,executeScriptNodes=False)
        assert CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()==retained
        noop = UpgradeSourceSplineAlignment(MayaBodyBuildHost(namespace='')).apply('UnusedReplacement')
        assert noop.systems==() and noop.rebuild is None
        report.update(status='passed',stage='complete',frames=frames,maximum_error=error,
                      skin_animation_preserved=True,undo_redo=True,reopened=True,idempotent=True)
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


if __name__=='__main__':
    raise SystemExit(main(standalone=True))
