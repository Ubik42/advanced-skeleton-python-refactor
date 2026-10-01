"""Capture native OPM registration inputs before failed transaction rollback."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'validation')]
from adv_py.adapters.maya_body import MayaBodyBuildHost
original=MayaBodyBuildHost.preflight_character_registration
OUT=ROOT/'validation/results/source-body-matrix-diagnostic'
def capture(host,plan):
    from maya import cmds
    try:return original(host,plan)
    except Exception:
        OUT.mkdir(parents=True,exist_ok=True)
        records={}
        for binding in plan.source_limbs:
            records[binding.label+binding.side]=json.loads(cmds.getAttr(binding.dynamics_root+'.advPySourceRpDynamics'))
        records['conversions']={node:{'input':cmds.connectionInfo(node+'.input',sourceFromDestination=True),
                                     'output':cmds.connectionInfo(node+'.output',destinationFromSource=True),
                                     'factor':cmds.getAttr(node+'.conversionFactor')}
                                for node in cmds.ls(type='unitConversion') or []}
        (OUT/'registration-inputs.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        cmds.file(rename=str(OUT/'before-rollback.mb'));cmds.file(save=True,type='mayaBinary',force=True)
        raise
MayaBodyBuildHost.preflight_character_registration=capture
if __name__=='__main__':
    from maya_original_biped_current_smoke import main
    main(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma',OUT,opm=True)
