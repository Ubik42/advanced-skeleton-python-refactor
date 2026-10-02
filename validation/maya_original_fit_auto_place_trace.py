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
        # Observe procedure locals without evaluating geometry or saving the
        # scene before the selection has been computed.
        arm_start=procedure.index('//find $armVtxs')
        arm_end=procedure.index('//split Left/Right',arm_start)
        arm=procedure[arm_start:arm_end]
        trace_path=(OUTPUT/'arm-selection.txt').as_posix()
        sample_marker='$closestVtxIndex=`getAttr closestSampler.closestVertexIndex`;'
        sample_trace=('\n\t\t\t\tint $advTraceFile=`fopen "'+trace_path+'" "w"`; '
            'fprint $advTraceFile ("sample "+$closestVtxIndex+" "+$pos[0]+" "+$pos[1]+" "+$pos[2]+"\\n"); '
            'fprint $advTraceFile (`polySelectConstraint -q -sts`+"\\n"); '
            'fprint $advTraceFile ("mask "+`selectType -q -pv`+" "+`selectMode -q -object`+"\\n"); fclose $advTraceFile;')
        arm=arm.replace(sample_marker,sample_marker+sample_trace,1)
        selection_marker='$armVtxs=`ls -sl -fl`;'
        selection_trace=('\n\t\t\t\t$advTraceFile=`fopen "'+trace_path+'" "a"`; '
            'fprint $advTraceFile ("count "+size($armVtxs)+"\\n"); '
            'for ($advTraceIndex=0;$advTraceIndex<size($armVtxs);$advTraceIndex++) '
            'fprint $advTraceFile ($armVtxs[$advTraceIndex]+"\\n"); fclose $advTraceFile;')
        arm=arm.replace(selection_marker,selection_marker+'\nint $advTraceIndex;'+selection_trace,1)
        procedure=procedure[:arm_start]+arm+procedure[arm_end:]
        mel.eval(procedure)
        skin=fixture()
        for field,value in (('Skin',' '.join(skin)),('All',''),('RightEye',''),('LeftEye','')):
            c.textField('asBody'+field+'TextField',edit=True,text=value)
        mel.eval('asFitAutoPlace;')
    except Exception:(OUTPUT/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:c.quit(force=True)
