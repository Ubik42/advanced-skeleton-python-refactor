"""Capture all source Fit prebuild decisions and final frames."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main(source,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    cmds.file(str(source.resolve()),open=True,force=True,executeScriptNodes=False)
    host=MayaBodyBuildHost()
    with host.transaction('Inspect source Fit prebuild'):
        with host.fit_manual_update_channels('FitSkeleton'):
            inspect_fit(host,output)

def inspect_fit(host,output):
    from dataclasses import asdict
    from adv_py.core.fit_orientation import FitOrientationRequest,select_fit_orientation_child
    from adv_py.application.fit_orientation_auto import OrientFitJoints
    from adv_py.application.registered_body_build import _prepare_fit_for_body
    snapshot=host.capture_fit_orientation('FitSkeleton')
    targets=tuple(node.path for node in snapshot.hierarchy.joints if select_fit_orientation_child(snapshot,node.path) is not None)
    plan=OrientFitJoints(host).plan(FitOrientationRequest(targets),'FitSkeleton')
    report=dict(snapshot=asdict(snapshot),plan=asdict(plan))
    _prepare_fit_for_body(host,'FitSkeleton','y')
    report['after']=asdict(host.capture_fit_orientation('FitSkeleton'))
    output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    for row in plan.changes:
        if row.joint.rsplit('|',1)[-1] in ('Wrist','Ankle'):print(row)

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
