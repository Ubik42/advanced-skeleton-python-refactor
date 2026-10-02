"""Diagnostic copy with observation only; authoritative MEL remains untouched."""
from pathlib import Path
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
OUTPUT=ROOT/'validation/results/fit-auto-place-native-trace'


def main():
    from maya import cmds as c,mel
    from maya_original_fit_auto_place_sample import fixture
    OUTPUT.mkdir(parents=True,exist_ok=True)
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0));mel.eval('AdvancedSkeleton;')
        source=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
        start=source.index('global proc asFitAutoPlace ()')
        end=source.index('global proc asFitAutoOrbit',start)
        procedure=source[start:end]
        # Save just before the elbow scan; no writes to the rig or scan state.
        marker='\t$bbMinZ=`getAttr AutoPlacing.bbMinZ`;'
        save='\tif ($zxy[$z]=="yElbowStraight") { file -rename "'+(OUTPUT/'shoulder-checkpoint.mb').as_posix()+'"; file -save -force -type "mayaBinary"; }\n'
        procedure=procedure.replace(marker,save+marker,1)
        marker='\t\t//checks'
        trace='\t\tif ($zxy[$z]=="yElbowStraight") print ("ADV_TRACE elbow "+$i+" "+$numHits+" "+`getAttr asFitScanCurve.tx`+" "+$firstNonFingerSplitTx+"\\n");\n'
        procedure=procedure.replace(marker,trace+marker,1)
        mel.eval(procedure)
        skin=fixture()
        for field,value in (('Skin',' '.join(skin)),('All',''),('RightEye',''),('LeftEye','')):
            c.textField('asBody'+field+'TextField',edit=True,text=value)
        mel.eval('asFitAutoPlace;')
    except Exception:(OUTPUT/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:c.quit(force=True)
