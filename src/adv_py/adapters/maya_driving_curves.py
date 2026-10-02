"""Original SDK curve copying, weighted inputs and scale normalization."""
from adv_py.core.driving_systems import original_sdk_control,original_sdk_attribute

class MayaDrivingCurvesMixin:
    def original_driving_curve_text(self, curve, *, expression=False):
        from adv_py.core.original_anim_curve_text import (
            OriginalCurveKey,OriginalCurveText,original_curve_text)
        c=self._cmds
        count=int(c.keyframe(curve,query=True,keyframeCount=True))
        times=c.keyframe(curve,query=True,floatChange=True) or []
        values=c.keyframe(curve,query=True,valueChange=True) or []
        incoming=c.keyTangent(curve,query=True,inTangentType=True) or []
        outgoing=c.keyTangent(curve,query=True,outTangentType=True) or []
        angles=c.keyTangent(curve,query=True,outAngle=True) or []
        weights=c.keyTangent(curve,query=True,outWeight=True) or []
        # asTextFromAnimCurve never queries incoming angles or weights.
        # The MEL's unwritten float-array elements serialize as zero.
        def element(values,index,default=0.):
            return values[index] if index<len(values) else default
        rows=tuple(OriginalCurveKey(element(times,index),element(values,index),
            element(incoming,index,''),element(outgoing,index,''),0.,
            element(angles,index),0.,element(weights,index)) for index in range(count))
        return original_curve_text(OriginalCurveText(c.nodeType(curve),rows,
            int(c.getAttr(curve+'.preInfinity')),int(c.getAttr(curve+'.postInfinity'))),
            expression=expression)

    def create_original_driving_curve_from_text(self, name, text):
        """asAnimCurveFromText uses native SDK creation and tangent setters."""
        from adv_py.core.original_anim_curve_text import parse_original_curve_text,VALID_TANGENTS
        self._require_transaction()
        c=self._cmds
        description=parse_original_curve_text(text)
        if not name:raise ValueError('动画曲线名称为空')
        self._transaction_changed=True
        unitless=description.node_type.startswith('animCurveU')
        temporary='asTempSetDrivenKeyNode'
        curve=None
        if not unitless:curve=c.createNode(description.node_type,name=name)
        if unitless and description.keys:
            if c.objExists(temporary):c.delete(temporary)
            c.createNode('transform',name=temporary)
            c.addAttr(temporary,longName='driver',attributeType='float')
        destinations={'animCurveUL':'tx','animCurveUA':'rx','animCurveUU':'sx'}
        if unitless and description.node_type not in destinations:
            raise ValueError('原版文本还原没有为 '+description.node_type+' 指定被驱动属性')
        driven=temporary+'.'+destinations.get(description.node_type,'')
        driver=temporary+'.driver'
        for index,key in enumerate(description.keys):
            if unitless:
                c.setDrivenKeyframe(driven,currentDriver=driver,
                                    driverValue=key.time,value=key.value)
                created=c.listConnections(driven,source=True,destination=False)
                curve=c.rename(created[0],name)
            else:c.setKeyframe(curve,time=key.time,value=key.value)
            incoming,outgoing=key.in_tangent,key.out_tangent
            for kind,value in (('in',incoming),('out',outgoing)):
                if value not in VALID_TANGENTS:
                    c.warning('Invalid '+kind+'TangentType '+repr(value)
                              +' at key '+str(index)+'; defaulting to linear')
            incoming=incoming if incoming in VALID_TANGENTS else 'linear'
            outgoing=outgoing if outgoing in VALID_TANGENTS else 'linear'
            address={'index':(index,index)} if unitless else {'time':(key.time,key.time)}
            c.keyTangent(curve,inTangentType=incoming,outTangentType=outgoing,**address)
            if incoming=='fixed':
                c.keyTangent(curve,inAngle=key.in_angle,inWeight=key.in_weight,**address)
            if outgoing=='fixed':
                c.keyTangent(curve,outAngle=key.out_angle,outWeight=key.out_weight,**address)
        if curve is None:
            raise ValueError('原版 unitless 动画曲线文本没有可创建的关键帧')
        # Preserve source's UA-only cleanup; UL/UU retain the temporary
        # native driver/output until their caller performs the cast.
        if description.node_type=='animCurveUA' and c.objExists(temporary):
            if c.connectionInfo(curve+'.input',isDestination=True):
                c.disconnectAttr(driver,curve+'.input')
            if c.connectionInfo(curve+'.output',isSource=True):
                c.disconnectAttr(curve+'.output',driven)
            c.delete(temporary)
        c.setAttr(curve+'.preInfinity',description.pre_infinity)
        c.setAttr(curve+'.postInfinity',description.post_infinity)
        c.select(curve,replace=True)
        return curve

    def reuse_original_driving_system(self, control, attribute, curve_name, text):
        """asDrivingSystemReUse, MEL 4762–4820, with native nodeCast."""
        from .maya_original_control_identity import source_fk_control
        from .maya_native_node_cast import native_node_cast
        from adv_py.core.original_anim_curve_text import parse_original_curve_text
        parse_original_curve_text(text)  # Parse before any native mutation.
        self._require_transaction()
        c=self._cmds
        self._transaction_changed=True
        if not c.objExists(control):self._original_create_driving_controller(control,())
        driven=original_sdk_control(curve_name)
        if driven.startswith('FK') and not c.objExists(driven):
            driven=source_fk_control(self,driven[2:])
        sdk=self.create_original_driving_sdk_layer(driven)
        attr=original_sdk_attribute(curve_name)
        destination=sdk+'.'+attr
        # Python FK names contain underscores before their terminal FK role.
        # Keep the same SDK role and suffix, using the actual scene identity.
        if curve_name.startswith('SDK'):
            suffix=curve_name.rsplit('_',1)[1]
            curve_name=sdk+'_'+suffix
        qrotate=attribute.startswith('qRotate')
        if not c.objExists(control+'.'+attribute):
            if qrotate:self.create_original_q_rotate_attrs(control)
            else:
                c.addAttr(control,longName=attribute,attributeType='double',keyable=True)
                self._original_driving_pose_registration(control,attribute,face=False)
                self.original_face_output_bw(control+'.'+attribute)
        if not c.objExists(curve_name):
            kind='animCurveUA' if attr.startswith('rotate') else (
                 'animCurveUU' if attr.startswith('scale') else 'animCurveUL')
            c.createNode(kind,name=curve_name)
            weighted=self.ensure_original_driving_weighted_input(destination)
            inputs=c.listConnections(weighted+'.input',source=True,destination=False) or []
            c.connectAttr(curve_name+'.output',weighted+'.input['+str(len(inputs))+']')
            source=(control+'.'+attribute if qrotate else
                    'bw'+control+'_'+attribute+'.output')
            c.connectAttr(source,curve_name+'.input')
        c.setKeyframe(curve_name,time=0.,value=0.)
        for value in c.keyframe(curve_name,query=True,timeChange=True) or []:
            if value!=0.:c.cutKey(curve_name,time=(value,value))
        generated=self.create_original_driving_curve_from_text(curve_name,text)
        native_node_cast(self,generated,curve_name,swap_names=True)
        c.delete(generated)
        from .maya_driving_registration import refresh_registered_sdks
        refresh_registered_sdks(self)
        return curve_name

    def original_driving_reuse_rows(self, *, selected=(), attributes=()):
        """asDrivingSystemsPrintInfo selection/attribute filtering, 4849–4900."""
        c=self._cmds
        systems=self.original_driving_systems()
        chosen=tuple(control for control in selected if control in systems)
        result=[]
        for control in chosen or systems:
            attrs=self.original_driving_attributes(control)
            if chosen and attributes:
                attrs=tuple((c.listAttr(control+'.'+attribute) or [attribute])[0]
                            for attribute in attributes)
            for attribute in attrs:
                bw='bw'+control+'_'+attribute
                if not c.objExists(bw):continue
                curves=c.listConnections(bw,source=False,destination=True,
                    skipConversionNodes=True,type='animCurve') or []
                result.extend((control,attribute,curve,self.original_driving_curve_text(curve))
                              for curve in curves)
        return tuple(result)

    def ensure_original_driving_weighted_input(self, plug):
        return self.ensure_original_face_blend_weighted(plug)

    def copy_original_driving_curve(self, source, destination):
        """asCopyAnimCurve supports unitless↔time input and keeps tangent types."""
        c=self._cmds
        source_time=c.nodeType(source).startswith("animCurveT")
        destination_time=c.nodeType(destination).startswith("animCurveT")
        values=c.keyframe(source,query=True,**({"timeChange":True} if source_time else {"floatChange":True})) or []
        outputs=c.keyframe(source,query=True,valueChange=True) or []
        # MEL selects the destination query axis from SOURCE curve type.
        # Preserve that rule, including U→U's empty time-axis query.
        previous=c.keyframe(destination,query=True,**({"floatChange":True} if source_time else {"timeChange":True})) or []
        incoming=c.keyTangent(source,query=True,inTangentType=True) or []
        outgoing=c.keyTangent(source,query=True,outTangentType=True) or []
        drivers=c.listConnections(destination+".input",source=True,destination=False,skipConversionNodes=True,plugs=True) or []
        drivens=c.listConnections(destination+".output",source=False,destination=True,skipConversionNodes=True,plugs=True) or []
        if not destination_time and (not drivers or not drivens):raise ValueError("SDK 曲线缺少输入或输出："+destination)
        for index,(value,output) in enumerate(zip(values,outputs)):
            next_nodes=c.listConnections(destination+".output",source=False,destination=True) or []
            factor=c.getAttr(next_nodes[0]+".conversionFactor") if next_nodes and c.nodeType(next_nodes[0])=="unitConversion" else 1.
            if destination_time:c.setKeyframe(destination,time=value,value=output/factor)
            else:c.setDrivenKeyframe(drivens[0],currentDriver=drivers[0],driverValue=value,value=output/factor)
            c.keyTangent(destination,index=(index,index),inTangentType=incoming[index],outTangentType=outgoing[index])
        for value in previous:
            if value not in values:
                c.selectKey(destination,keyframe=True,float=(value,value))
                if c.keyframe(query=True,selected=True):
                    c.cutKey(destination,float=(value,value))
        for attribute in ("preInfinity","postInfinity"):
            c.setAttr(destination+"."+attribute,c.getAttr(source+"."+attribute))
        return len(values)

    def normalize_original_driving_scales(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;count=0
        for curve in c.ls("SDK*","bw*",type="animCurve") or []:
            plugs=c.listConnections(curve+".output",source=False,destination=True,skipConversionNodes=True,plugs=True,type="blendWeighted") or []
            if not plugs:continue
            node,attribute=plugs[0].split(".",1)
            if "_scale" not in node or not attribute.startswith("input["):continue
            index=int(attribute.split("[",1)[1].split("]",1)[0])
            if index==0:continue
            values=c.keyframe(curve,query=True,float=(0,0),valueChange=True) or []
            if values and values[0]>0:
                c.keyframe(curve,edit=True,relative=True,option="over",valueChange=-1,includeUpperBound=True);count+=1
        return count

    def name_original_driving_sdk_curves(self):
        """asEnsureSDKcurvesNamed traverses SDK transforms and their weighted inputs."""
        self._require_transaction();self._transaction_changed=True
        return self.name_original_face_sdk_curves()

    def _original_driving_curve_destination(self, curve):
        c=self._cmds
        destinations=c.listConnections(curve+".output",source=False,destination=True,plugs=True,skipConversionNodes=True) or []
        return destinations[0] if destinations else ""
