"""Retain the original main-control/end-scale contract in saved source rigs."""
from adv_py.core.character_registry import canonical, CharacterRegistryError
from adv_py.core.source_limb_scale import source_limb_scale_axes,decode_source_limb_scale


def configure(host,limb,side,ik, *,use_offset_parent_matrix):
    c = host._cmds
    outputs=[]
    for axis in 'XYZ':
        source,target = ik.wrist_control_path+'.scale'+axis,ik.chain[-1]+'.scale'+axis
        c.connectAttr(source,target)
        outputs.append((source,target))
    if not use_offset_parent_matrix:
        end = next(joint for joint in side.joints if joint.ik_driver==ik.chain[-1])
        node = end.constraint_name+'Scale'
        old = c.connectionInfo(node+'.color1',sourceFromDestination=True)
        if old:
            c.disconnectAttr(old,node+'.color1')
        for axis,component in zip(source_limb_scale_axes(limb.label,
                use_offset_parent_matrix=False,ik_local_mode=ik.ik_local_mode),'RGB'):
            target = node+'.color1'+component
            old = c.connectionInfo(target,sourceFromDestination=True)
            if old:c.disconnectAttr(old,target)
            source=ik.wrist_control_path+'.scale'+axis
            c.connectAttr(source,target)
            outputs.append((source,target))
    plug = ik.wrist_control_path+'.advPySourceRpScaleLayout'
    c.addAttr(ik.wrist_control_path,longName='advPySourceRpScaleLayout',dataType='string')
    c.setAttr(plug,canonical(dict(version=1,label=limb.label,side=side.side.value,
        control=ik.wrist_control_path,end=ik.chain[-1],outputs=outputs)),type='string',lock=True)


def audit(host,registration):
    c = host._cmds
    for binding in registration.source_limbs:
        plug = binding.ik_control+'.advPySourceRpScaleLayout'
        if not c.objExists(plug):
            if binding.ik_scale_axes is not None:
                raise CharacterRegistryError('来源 RP 末端缩放图登记缺失')
            continue  # Saved graphs preceding this source correction.
        if not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源 RP 末端缩放登记已解锁')
        record = decode_source_limb_scale(c.getAttr(plug))
        if ((record['label'],record['side'],record['control'],record['end'])!=
                (binding.label,binding.side,binding.ik_control,
                 binding.joints[binding.primary_count-1].ik_driver)):
            raise CharacterRegistryError('来源 RP 末端缩放图与动画登记不一致')
        if any(not c.isConnected(source,target) for source,target in record['outputs']):
            raise CharacterRegistryError('来源 RP 末端缩放连接变化')
        if binding.ik_scale_axes is not None and len(record['outputs'])==6:
            axes=tuple(source.rsplit('scale',1)[-1] for source,_ in record['outputs'][3:])
            if axes!=binding.ik_scale_axes:
                raise CharacterRegistryError('来源 RP 末端缩放轴向与动画登记不一致')
