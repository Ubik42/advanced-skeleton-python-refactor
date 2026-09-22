"""Portable 4-to-6 spine influence transfer through the headless product entry."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
from product_entry_smoke import _hash,_run


def main(mayapy:Path,report:Path)->int:
    report.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='advpy-spine-skin-',
                                     dir=report.parent.resolve()) as directory:
        folder=Path(directory)
        script=ROOT/'validation'/'maya_spine_skin_redistribution_scene.py'
        def scene_task(mode):
            return subprocess.run([str(mayapy),str(script),mode,str(folder)],
                cwd=ROOT,capture_output=True,text=True,encoding='utf-8',
                errors='replace',timeout=120)
        source=scene_task('source')
        target=scene_task('target') if source.returncode==0 else None
        before=folder/'target_before.ma'
        original_hash=_hash(before) if before.exists() else None
        output=folder/'target_after.ma'
        transfer=(_run(mayapy,'skin-surface-transfer',str(before),
            '--namespace',':','--source-asset',str(folder/'source_asset.json'),
            '--target-skin','TargetSkin','--target-mesh','|TargetMesh',
            '--redistribution',str(folder/'redistribution.json'),
            '--max-distance','0.000001','--output',str(output))
            if before.exists() else (1,None,'target scene missing'))
        inspection=scene_task('inspect') if output.exists() else None
        inspected=(json.loads((folder/'inspection.json').read_text(encoding='utf-8'))
            if (folder/'inspection.json').exists() else None)
        native=(json.loads((folder/'native.json').read_text(encoding='utf-8'))
            if (folder/'native.json').exists() else None)
        refused_path=folder/'refused.ma'
        refused=(1,None,'redistribution missing')
        if (folder/'redistribution.json').exists():
            invalid=json.loads((folder/'redistribution.json').read_text(encoding='utf-8'))
            invalid['influences'][1]['targets'][0]['fraction']=.2
            bad=folder/'invalid.json'
            bad.write_text(json.dumps(invalid),encoding='utf-8')
            refused=_run(mayapy,'skin-surface-transfer',str(before),
                '--namespace',':','--source-asset',str(folder/'source_asset.json'),
                '--target-skin','TargetSkin','--target-mesh','|TargetMesh',
                '--redistribution',str(bad),'--max-distance','0.000001',
                '--output',str(refused_path))
        checks={
            'source_and_target_independent_scenes':source.returncode==0
                and target is not None and target.returncode==0,
            'product_transfer_saved_scene':transfer[0]==0 and output.exists()
                and transfer[1] is not None and transfer[1].get('vertices')==9,
            'reopened_weights_match_spine_split':inspection is not None
                and inspection.returncode==0 and inspected is not None
                and inspected.get('status')=='passed',
            'single_native_undo_redo':native is not None
                and native.get('changed_vertices',0)>0
                and native.get('undo_restored') and native.get('redo_restored'),
            'panel_controller_native_transfer':native is not None
                and native.get('panel_controller_matches_application')
                and native.get('panel_controller_single_undo'),
            'rejects_fraction_loss_without_output':refused[0]==2
                and not refused_path.exists(),
            'target_source_scene_unchanged':original_hash is not None
                and _hash(before)==original_hash,
        }
        payload={**checks,'status':'passed' if all(checks.values()) else 'failed'}
        if not all(checks.values()):
            payload['diagnostics']={'source':source.stderr[-900:],
                'target':target.stderr[-900:] if target else None,
                'transfer':transfer[2][-900:],
                'inspection':inspection.stderr[-900:] if inspection else None,
                'inspected':inspected,'refused':refused[2][-900:]}
            payload['diagnostics']['native']=native
    report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if all(checks.values()) else 1


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
