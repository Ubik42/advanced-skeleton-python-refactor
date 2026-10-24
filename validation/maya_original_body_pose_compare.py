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


def matrix_cases():
    main=tuple(('Main.scale'+axis,'AdvPy_Global.scale'+axis,value) for axis,value in zip('XYZ',(1.2,.85,1.1)))
    mode=('FKIKSpine_M.FKIKBlend','FKIKSpine_M.FKIKBlend',10.)
    return (
        ('arm_ik_main_nonuniform',main+(('FKIKArm_R.FKIKBlend','AdvPy_ArmSettings.armIkFk_R',10.,1.),)),
        ('spine_ik_main_nonuniform',main+(mode,)),
        ('spine_ik_mid_translation',(mode,('IKSpine2_M.translateZ','AdvPy_SplineIK1.translateZ',.4))),
        ('spine_ik_mid_scale',(mode,('IKSpine2_M.scaleY','AdvPy_SplineIK1.scaleY',1.2))),
        ('neck_fk_nonuniform',(('FKNeck_M.scaleY','AdvPy_Neck_MFK.scaleY',1.3),('FKNeck_M.scaleZ','AdvPy_Neck_MFK.scaleZ',.8))),
        ('neck_part_fk',(('FKNeckPart1_M.rotateX','AdvPy_NeckPart1_M_InbetweenFK.rotateX',15.),)),
        ('neck_part_nonuniform',(('FKNeckPart1_M.scaleY','AdvPy_NeckPart1_M_InbetweenFK.scaleY',1.2),)))



def spline_cases():
    mode=('FKIKSpine_M.FKIKBlend','FKIKSpine_M.FKIKBlend',10.)
    def mid(attr,value):return ('IKSpine2_M.'+attr,'AdvPy_SplineIK1.'+attr,value)
    def end(attr,value):return ('IKSpine3_M.'+attr,'AdvPy_SplineIK2.'+attr,value)
    native=end('stretchEven',10.)
    bend=mid('translateZ',.4)
    main=tuple(('Main.scale'+axis,'AdvPy_Global.scale'+axis,value) for axis,value in zip('XYZ',(1.2,.85,1.1)))
    return (
        ('spine_native_neutral',(mode,native)),
        ('spine_native_bend',(mode,native,bend)),
        ('spine_native_mid_twist',(mode,native,mid('rotateY',25.))),
        ('spine_arc_mid_twist',(mode,mid('rotateY',25.))),
        ('spine_half_stretch',(mode,end('stretchy',5.),bend)),
        ('spine_no_stretch',(mode,end('stretchy',0.),end('translateY',.5))),
        ('spine_half_mode',(('FKIKSpine_M.FKIKBlend','FKIKSpine_M.FKIKBlend',5.),bend)),
        ('spine_first_not_fixed',(mode,('IKSpine1_M.firstJointFixed','AdvPy_SplineIK0.firstJointFixed',0.),bend)),
        ('spine_end_rotate',(mode,end('rotateX',15.))),
        ('spine_native_main_nonuniform',main+(mode,native)),
    )

def scoped_spline_cases(systems):
    """Exercise each three-control source system and their shared parent."""
    rows=[]
    simultaneous=[]
    for system in systems:
        name,side=system.rsplit('_',1)
        mode=('FKIK'+system+'.FKIKBlend','FKIK'+system+'.FKIKBlend',10.)
        def control(index,attribute,value):
            return (f'IK{name}{index+1}_{side}.{attribute}',
                    f'AdvPy_Spline_{system}_IK{index}.{attribute}',value)
        mid=control(1,'translateZ',.4)
        native=control(2,'stretchEven',10.)
        main_scale=tuple(('Main.scale'+axis,'AdvPy_Global.scale'+axis,value)
                         for axis,value in zip('XYZ',(1.2,.85,1.1)))
        cases=(('ik_neutral',(mode,)),('arc_bend',(mode,mid)),
               ('native_bend',(mode,native,mid)),
               ('native_mid_twist',(mode,native,control(1,'rotateY',25.))),
               ('arc_mid_twist',(mode,control(1,'rotateY',25.))),
               ('half_stretch',(mode,control(2,'stretchy',5.),mid)),
               ('no_stretch',(mode,control(2,'stretchy',0.),control(2,'translateY',.5))),
               ('first_not_fixed',(mode,control(0,'firstJointFixed',0.),mid)),
               ('end_rotate',(mode,control(2,'rotateX',15.))),
               ('main_nonuniform',main_scale+(mode,native)))
        rows.extend((system+'_'+name,edits) for name,edits in cases)
        simultaneous.extend((mode,mid,native))
    return tuple(rows)+(('all_splines_native_bend',tuple(simultaneous)),)


def set_edit(cmds, row, index):
    plug = row[index]
    value = row[2+index] if len(row) == 4 else row[2]
    if index == 1 and not cmds.getAttr(plug, settable=True):
        # Current source RP modes expose the original FKIKBlend 0..10
        # control. Historical tests wrote its generated normalized output.
        # Resolve only the locked, explicitly saved source mode declaration.
        from adv_py.adapters.maya_source_limb_mode import PLAN_MARKER
        from adv_py.core.source_limb_mode import decode_source_limb_mode
        marker = row[0].split('.', 1)[0] + '.' + PLAN_MARKER
        if not cmds.objExists(marker) or not cmds.getAttr(marker, lock=True):
            raise AssertionError('No declared source mode for connected test input: ' + plug)
        plan = decode_source_limb_mode(cmds.getAttr(marker))
        physical = (cmds.ls(plug.split('.', 1)[0], long=True) or [None])[0]
        mode_node = (cmds.ls(row[0].split('.', 1)[0], long=True) or [None])[0]
        if (plan.blend_plug != physical + '.' + plug.split('.', 1)[1]
                or plan.mode_plug != mode_node + '.' + row[0].split('.', 1)[1]
                or not cmds.isConnected(plan.source_mode.weight_unit + '.output', plug)
                or cmds.getAttr(plan.source_mode.weight_unit + '.conversionFactor') != .1):
            raise AssertionError('Source mode does not match historical normalized input: ' + plug)
        plug, value = plan.mode_plug, row[2]
    cmds.setAttr(plug, value)


def main(native,python_scene,reference,output,*,extended=False,source_matrices=False,source_splines=False,spline_systems=(),standalone=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds
    names=tuple(json.loads(reference.read_text())['neutral_body'])
    matrices={}
    cases=CASES+(rp_cases() if extended else ())+(matrix_cases() if source_matrices else ())+(spline_cases() if source_splines else ())+(scoped_spline_cases(spline_systems) if spline_systems else ())
    for index,(label,scene) in enumerate((('native',native),('python',python_scene))):
        matrices[label]={}
        for name,edits in cases:
            cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
            cmds.currentTime(1,update=True)
            for row in edits:
                assert cmds.objExists(row[index]),row[index]
                set_edit(cmds, row, index)
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

if __name__=='__main__':main(*(Path(arg) for arg in sys.argv[1:5]),extended='--extended' in sys.argv[5:],source_matrices='--source-matrices' in sys.argv[5:],source_splines='--source-splines' in sys.argv[5:],spline_systems=tuple(arg.split('=',1)[1] for arg in sys.argv[5:] if arg.startswith('--spline-system=')))
