"""Native RP FKIK controller, normalized solver bridge and source visibility."""
from dataclasses import asdict,replace
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_limb_mode import decode_source_limb_mode
from .maya_source_spline_mode import create as create_mode

MARKER='advPySourceRpMode'
UNIT_MARKER='advPySourceRpModeUnit'
PLAN_MARKER='advPySourceRpModePlan'
REVERSE_MARKER='advPySourceRpModeReverse'


def create(host,plan):
    host._require_transaction();c=host._cmds
    mode=plan.source_mode
    reverse='FKIKBlend'+mode.token+'Reverse'
    if any(host.find_name_collisions(name) for name in (plan.condition,reverse)):
        raise CharacterRegistryError('来源 RP FKIK 显隐或权重节点名称被占用')
    create_mode(host,plan,hybrid_unit=False)
    # asUnitConvertAndReverse always creates this reverse, including RP.
    c.createNode('reverse',name=reverse,skipSelect=True)
    c.connectAttr(mode.weight_unit+'.output',reverse+'.inputX')
    # Replacing the last transitional FK constraint can make Maya prune its
    # upstream reverse. Retain the native asUnitConvertAndReverse node through
    # bookkeeping ownership, as for the source Spline mode reverse.
    c.addAttr(mode.control,longName=REVERSE_MARKER,attributeType='message')
    c.connectAttr(reverse+'.message',mode.control+'.'+REVERSE_MARKER)
    c.setAttr(mode.control+'.'+REVERSE_MARKER,lock=True)
    for node,marker in ((mode.control,MARKER),(mode.weight_unit,UNIT_MARKER)):
        c.addAttr(node,longName=marker,attributeType='bool',defaultValue=True)
        c.setAttr(node+'.'+marker,True,lock=True)
    for attribute in ('autoVis','FKVis','IKVis'):
        c.addAttr(mode.control,longName=attribute,attributeType='bool',defaultValue=True,
                  keyable=attribute!='autoVis')
        c.setAttr(mode.control+'.'+attribute,channelBox=True)
    c.createNode('condition',name=plan.condition,skipSelect=True)
    for source,target in ((mode.control+'.autoVis',plan.condition+'.firstTerm'),
        (mode.control+'.IKVis',plan.condition+'.colorIfTrueR'),
        (mode.control+'.FKVis',plan.condition+'.colorIfTrueG'),
        (plan.mode_plug,plan.condition+'.colorIfFalseR'),
        (mode.visibility_range+'.outValueX',plan.condition+'.colorIfFalseG'),
        (mode.weight_unit+'.output',plan.blend_plug)):
        c.connectAttr(source,target)
    c.setAttr(plan.blend_plug,keyable=False,channelBox=False)
    c.addAttr(mode.control,longName=PLAN_MARKER,dataType='string')
    c.setAttr(mode.control+'.'+PLAN_MARKER,canonical(asdict(plan)),type='string',lock=True)
    host._transaction_changed=True


def connect_visibility(host,plan,limb,fk):
    """MEL routes RP visibility to offsets; keep Sub/Extra shape flags intact."""
    c=host._cmds
    side=next(side for side in limb.blend.sides if side.side.value==plan.side)
    drivers={joint.fk_driver for joint in side.joints}
    for control in fk.controls:
        if control.driven_joint not in drivers or control.control_path in fk.hidden_controls:
            continue
        for node in (control.control_path,control.sub_control_path,
                     control.extra_path if control.extra_curve else None):
            if not node:
                continue
            for shape in c.listRelatives(node,shapes=True,noIntermediate=True,
                                         fullPath=True,type='nurbsCurve') or ():
                plug=shape+'.visibility'
                source=c.connectionInfo(plug,sourceFromDestination=True)
                if source==side.reverse_name+'.outputX':
                    c.disconnectAttr(source,plug)
                    c.setAttr(plug,True)
                elif source:
                    gate=shape.rsplit('|',1)[-1]+'IKFKVisibility'
                    if (source==gate+'.output' and c.nodeType(gate)=='multDoubleLinear'
                            and c.isConnected(side.reverse_name+'.outputX',gate+'.input2')):
                        flag=c.connectionInfo(gate+'.input1',sourceFromDestination=True)
                        c.disconnectAttr(source,plug)
                        c.connectAttr(flag,plug)
                        c.delete(gate)
    for role,path in plan.visibility_targets:
        c.connectAttr(plan.visibility_fk if role=='fk' else plan.visibility_ik,
                      path+'.visibility',force=True)
    host._transaction_changed=True


def connect_source_fk_weight(host, plan, limb):
    """Use asUnitConvertAndReverse's actual output for the existing FK edges.

    The earlier construction stage needs its normalized switch before the
    public icon exists. Transfer that reverse's complete output boundary once
    the original control is created, rather than leaving a duplicate reverse.
    """
    c=host._cmds
    side=next(side for side in limb.blend.sides if side.side.value==plan.side)
    original='FKIKBlend'+plan.source_mode.token+'Reverse'
    if c.nodeType(side.reverse_name)!='reverse':
        raise CharacterRegistryError('来源 RP 初始反向权重节点缺失')
    for axis in 'XYZ':
        source=side.reverse_name+'.output'+axis
        for destination in c.listConnections(source,source=False,destination=True,plugs=True) or []:
            c.connectAttr(original+'.output'+axis,destination,force=True)
    c.delete(side.reverse_name)
    from .maya_source_graph_records import rename_addresses
    rename_addresses(host,{side.reverse_name:original})
    return replace(limb.blend,sides=tuple(replace(row,reverse_name=original)
        if row.side is side.side else row for row in limb.blend.sides))


def public_mode_plug(c,normalized):
    source=c.connectionInfo(normalized,sourceFromDestination=True)
    if not source:
        return normalized,1.
    unit=source.rsplit('.',1)[0]
    if (source!=unit+'.output' or c.nodeType(unit)!='unitConversion'
            or not c.objExists(unit+'.'+UNIT_MARKER)
            or not c.getAttr(unit+'.'+UNIT_MARKER)
            or not c.getAttr(unit+'.'+UNIT_MARKER,lock=True)
            or abs(c.getAttr(unit+'.conversionFactor')-.1)>1e-12):
        raise CharacterRegistryError('来源 RP 模式的归一化输入改变：'+normalized)
    plug=c.connectionInfo(unit+'.input',sourceFromDestination=True)
    control,attribute=plug.rsplit('.',1) if '.' in plug else ('','')
    if (attribute!='FKIKBlend' or not c.objExists(control+'.'+MARKER)
            or not c.getAttr(control+'.'+MARKER)):
        raise CharacterRegistryError('来源 RP 模式的用户控件缺失：'+normalized)
    control=(c.ls(control,long=True) or [control])[0]
    return control+'.FKIKBlend',10.


def audit_registered(host,registration):
    c=host._cmds
    channels={ch.key:ch for ch in registration.channels}
    owned={node.path for node in registration.nodes}
    owned.update(row.path for row in registration.retired_body)
    for binding in registration.source_limbs:
        channel=channels[binding.blend_key]
        control=channel.node
        if channel.attribute!='FKIKBlend':
            continue
        if not c.objExists(control+'.'+MARKER):
            raise CharacterRegistryError('来源 RP FKIK 控件身份缺失')
        if (channel.attribute!='FKIKBlend' or not c.getAttr(control+'.'+MARKER)
                or not c.getAttr(control+'.'+MARKER,lock=True)):
            raise CharacterRegistryError('来源 RP FKIK 控件身份改变')
        record=control+'.'+PLAN_MARKER
        if not c.objExists(record) or not c.getAttr(record,lock=True):
            raise CharacterRegistryError('来源 RP FKIK 场景图登记缺失或已解锁')
        plan=decode_source_limb_mode(c.getAttr(record))
        if (plan.source_mode.control!=control or plan.side!=binding.side
                or plan.body_joints!=(binding.joints[0].body,
                    binding.joints[binding.middle_index].body,
                    binding.joints[binding.primary_count-1].body)
                or not {plan.source_mode.control,plan.source_mode.frame,
                        plan.source_mode.parent_source,*plan.body_joints,
                        *(path for _,path in plan.visibility_targets)}.issubset(owned)):
            raise CharacterRegistryError('来源 RP FKIK 保存骨链或节点归属改变')
        from .maya_source_spline_mode import audit as audit_mode
        audit_mode(host,plan,hybrid_unit=False)
        if any(not c.isConnected(plan.visibility_fk if role=='fk' else plan.visibility_ik,
                                 path+'.visibility') for role,path in plan.visibility_targets):
            raise CharacterRegistryError('来源 RP FKIK 控制层显示接线改变')
        if (plan.blend_plug.rsplit('.',1)[-1]!=binding.blend_key.rsplit('.',1)[-1]
                or not c.isConnected(plan.source_mode.weight_unit+'.output',plan.blend_plug)):
            raise CharacterRegistryError('来源 RP FKIK 内部求解接口改变')
        name=control.rsplit('|',1)[-1]
        token=name[4:];stem,side=token.rsplit('_',1)
        weight='FKIKBlend'+token+'UnitConversion'
        visibility_unit='FKIKBlend'+stem+'UnitConversion_'+side
        visibility_range='FKIKBlend'+stem+'setRange_'+side
        condition='FKIKBlend'+stem+'Condition_'+side
        if (tuple(c.attributeQuery('FKIKBlend',node=control,minimum=True))!=(0.,)
                or tuple(c.attributeQuery('FKIKBlend',node=control,maximum=True))!=(10.,)
                or c.nodeType(condition)!='condition' or c.getAttr(condition+'.operation')!=0
                or c.getAttr(condition+'.secondTerm')!=0):
            raise CharacterRegistryError('来源 RP FKIK 用户范围或显隐条件改变')
        for unit in (weight,visibility_unit):
            if c.nodeType(unit)!='unitConversion' or abs(c.getAttr(unit+'.conversionFactor')-.1)>1e-12:
                raise CharacterRegistryError('来源 RP FKIK 转换比例改变')
        if (c.nodeType(visibility_range)!='setRange' or any(
                c.getAttr(visibility_range+'.'+attr)!=value for attr,value in
                (('minX',10.),('maxX',0.),('oldMinX',0.),('oldMaxX',10.)))):
            raise CharacterRegistryError('来源 RP FKIK 自动显示范围改变')
        edges=((control+'.FKIKBlend',weight+'.input'),
            (control+'.FKIKBlend',visibility_unit+'.input'),
            (control+'.FKIKBlend',visibility_range+'.valueX'),
            (control+'.autoVis',condition+'.firstTerm'),
            (control+'.IKVis',condition+'.colorIfTrueR'),
            (control+'.FKVis',condition+'.colorIfTrueG'),
            (control+'.FKIKBlend',condition+'.colorIfFalseR'),
            (visibility_range+'.outValueX',condition+'.colorIfFalseG'))
        if any(not c.isConnected(source,target) for source,target in edges):
            raise CharacterRegistryError('来源 RP FKIK 用户值或显示接线改变')
        reverse='FKIKBlend'+token+'Reverse'
        owner=control+'.'+REVERSE_MARKER
        if c.objExists(owner) and (not c.getAttr(owner,lock=True)
                or not c.isConnected(reverse+'.message',owner)):
            raise CharacterRegistryError('来源 RP FKIK 反向权重归属改变')
        if c.nodeType(reverse)!='reverse' or not c.isConnected(weight+'.output',reverse+'.inputX'):
            raise CharacterRegistryError('来源 RP FKIK 原版反向权重接线改变')
        normalized=weight+'.output'
        targets=c.listConnections(normalized,source=False,destination=True,plugs=True) or []
        internal=[target for target in targets if target!=reverse+'.inputX']
        if (len(targets)!=2 or len(internal)!=1
                or internal[0].rsplit('.',1)[-1]!=binding.blend_key.rsplit('.',1)[-1]
                or public_mode_plug(c,internal[0])!=(control+'.FKIKBlend',10.)):
            raise CharacterRegistryError('来源 RP FKIK 归一化边界改变')
