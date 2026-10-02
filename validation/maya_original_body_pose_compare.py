"""Compare whole native Body graph output under representative control edits."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
CASES=(('neutral',()),
       ('shoulder_fk',(('FKShoulder_R.rotateZ','AdvPy_Shoulder_RFK.rotateZ',30.),)),
       ('wrist_fk',(('FKWrist_R.rotateX','AdvPy_Wrist_RFK.rotateX',25.),)),
       ('bendy_twist',(('BendShoulder_R.rotateX','BendShoulder_R.rotateX',30.),)),
       ('bendy_translation',(('BendElbow_R.translateY','BendElbow_R.translateY',.3),)),
       ('global_scale',tuple(('Main.scale'+axis,'AdvPy_Global.globalScale',1.25) for axis in 'XYZ')),
       ('root_leg_lock',(('FKRoot_M.legLock','AdvPy_Root_MFK.legLock',0.),
                         ('RootX_M.rotateY','AdvPy_RootX_M.rotateY',30.))))

def rp_cases():
    arm=('FKIKArm_R.FKIKBlend','AdvPy_ArmSettings.armIkFk_R',10.,1.)
    left=('FKIKArm_L.FKIKBlend','AdvPy_ArmSettings.armIkFk_L',10.,1.)
    def a(attr,value):return ('IKArm_R.'+attr,'AdvPy_ArmIK_R.'+attr,value)
    def l(attr,value):return ('IKLeg_R.'+attr,'AdvPy_LegIK_R.'+attr,value)
    def p(attr,value):return ('PoleArm_R.'+attr,'AdvPy_ArmPV_R.'+attr,value)
    return (
        ('main_nonuniform',tuple(('Main.scale'+axis,'AdvPy_Global.scale'+axis,value) for axis,value in zip('XYZ',(1.2,.85,1.1)))),
        ('arm_ik_neutral',(arm,)),
        ('arm_ik_move',(arm,a('translateY',1.),a('translateZ',.5))),
        ('arm_ik_swivel',(arm,a('swivel',20.))),
        ('arm_stretch',(arm,a('translateX',-2.),a('stretchy',10.))),
        ('arm_anti_pop',(arm,a('translateX',1.),a('antiPop',10.))),
        ('arm_length',(arm,a('Lenght1',1.2))),
        ('arm_pole_lock',(arm,p('lock',5.))),
        ('arm_half_blend',(('FKIKArm_R.FKIKBlend','AdvPy_ArmSettings.armIkFk_R',5.,.5),a('translateY',.5))),
        ('left_arm_ik',(left,('IKArm_L.translateZ','AdvPy_ArmIK_L.translateZ',.7))),
        ('leg_move',(l('translateZ',.5),)),
        ('leg_swivel',(l('swivel',25.),)),
        ('foot_roll_low',(l('roll',25.),)),
        ('foot_roll_middle',(l('roll',45.),)),
        ('foot_roll_high',(l('roll',75.),)),
        ('foot_rock_positive',(l('rock',15.),)),
        ('foot_rock_negative',(l('rock',-15.),)),
        ('arm_follow_root',(arm,a('followMain',0.),a('followRoot',10.),('RootX_M.rotateZ','AdvPy_RootX_M.rotateZ',20.))),
        ('arm_follow_chest',(arm,a('followMain',0.),a('followChest',10.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',15.))),
        ('pole_follow_arm',(arm,p('followArm',10.),a('translateY',.5))),
        ('pole_leg_free',(('PoleLeg_R.followLeg','AdvPy_LegPV_R.followLeg',0.),l('translateX',.3))),
        ('nonuniform_shoulder',(('FKShoulder_R.scaleY','AdvPy_Shoulder_RFK.scaleY',1.3),('FKShoulder_R.scaleZ','AdvPy_Shoulder_RFK.scaleZ',.8))),
        ('nonuniform_wrist',(('FKWrist_R.scaleY','AdvPy_Wrist_RFK.scaleY',1.2),('FKWrist_R.scaleZ','AdvPy_Wrist_RFK.scaleZ',.7))))


def main(native,python_scene,reference,output,*,extended=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    names=tuple(json.loads(reference.read_text())['neutral_body'])
    matrices={}
    cases=CASES+(rp_cases() if extended else ())
    for index,(label,scene) in enumerate((('native',native),('python',python_scene))):
        matrices[label]={}
        for name,edits in cases:
            cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
            cmds.currentTime(1,update=True)
            for row in edits:
                assert cmds.objExists(row[index]),row[index]
                cmds.setAttr(row[index],row[2+index] if len(row)==4 else row[2])
            cmds.dgdirty(allPlugs=True)
            matrices[label][name]={node:cmds.xform(node,q=True,ws=True,m=True) for node in names}
    rows=[]
    for name,edits in cases:
        errors={node:max(abs(a-b) for a,b in zip(matrices['native'][name][node],matrices['python'][name][node])) for node in names}
        rows.append(dict(case=name,maximum_error=max(errors.values()),errors=errors,
                         largest=sorted(errors.items(),key=lambda row:row[1],reverse=True)[:8]))
    passed=all(row['maximum_error']<=1e-4 for row in rows)
    report=dict(status='passed' if passed else 'failed',scope=f'{len(names)} Body/Part joints, {len(cases)} representative control cases',tolerance=1e-4,rows=rows,matrices=matrices)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print([(row['case'],row['maximum_error'],row['largest'][:2]) for row in rows])
    if not passed:raise AssertionError('Whole Body pose comparison failed')

if __name__=='__main__':main(*(Path(arg) for arg in sys.argv[1:5]),extended='--extended' in sys.argv[5:])
