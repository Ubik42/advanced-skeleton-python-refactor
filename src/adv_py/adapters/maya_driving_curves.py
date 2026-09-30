"""Original SDK curve copying, weighted inputs and scale normalization."""
from adv_py.core.driving_systems import original_sdk_control,original_sdk_attribute

class MayaDrivingCurvesMixin:
    def ensure_original_driving_weighted_input(self, plug):
        c=self._cmds
        node,attribute=plug.split(".",1)
        if c.nodeType(node)=="blendWeighted":return node
        root=attribute.split("[",1)[0]
        attribute=c.attributeQuery(root,node=node,longName=True)+attribute[len(root):]
        name="bw"+node+"_"+attribute.replace(".","_").replace("[","_").replace("]","_")
        if not c.objExists(name):
            c.createNode("blendWeighted",name=name)
            for group in ("FaceAllSet","AllSet"):
                if c.objExists(group) and c.sets(node,isMember=group):
                    c.sets(name,add=group);break
            sources=c.listConnections(plug,source=True,destination=False,plugs=True) or []
            if sources:c.connectAttr(sources[0],name+".input[0]",force=True)
            c.connectAttr(name+".output",plug,force=True)
        return name

    def copy_original_driving_curve(self, source, destination):
        """asCopyAnimCurve supports unitless↔time input and keeps tangent types."""
        c=self._cmds
        source_time=c.nodeType(source).startswith("animCurveT")
        destination_time=c.nodeType(destination).startswith("animCurveT")
        values=c.keyframe(source,query=True,**({"timeChange":True} if source_time else {"floatChange":True})) or []
        outputs=c.keyframe(source,query=True,valueChange=True) or []
        previous=c.keyframe(destination,query=True,**({"timeChange":True} if destination_time else {"floatChange":True})) or []
        incoming=c.keyTangent(source,query=True,inTangentType=True) or []
        outgoing=c.keyTangent(source,query=True,outTangentType=True) or []
        next_nodes=c.listConnections(destination+".output",source=False,destination=True) or []
        factor=c.getAttr(next_nodes[0]+".conversionFactor") if next_nodes and c.nodeType(next_nodes[0])=="unitConversion" else 1.
        drivers=c.listConnections(destination+".input",source=True,destination=False,skipConversionNodes=True,plugs=True) or []
        drivens=c.listConnections(destination+".output",source=False,destination=True,skipConversionNodes=True,plugs=True) or []
        if not destination_time and (not drivers or not drivens):raise ValueError("SDK 曲线缺少输入或输出："+destination)
        for index,(value,output) in enumerate(zip(values,outputs)):
            if destination_time:c.setKeyframe(destination,time=value,value=output/factor)
            else:c.setDrivenKeyframe(drivens[0],currentDriver=drivers[0],driverValue=value,value=output/factor)
            c.keyTangent(destination,index=(index,index),inTangentType=incoming[index],outTangentType=outgoing[index])
        for value in previous:
            if value not in values:c.cutKey(destination,clear=True,**({"time":(value,value)} if destination_time else {"float":(value,value)}))
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
        c=self._cmds;renamed=[]
        for sdk in c.ls("*SDK*_*",type="transform") or []:
            path=(c.ls(sdk,long=True) or [sdk])[0].replace(self.namespace+":" if self.namespace else "","")
            if "|MotionSystem|" not in path and "|FaceMotionSystem|" not in path:continue
            group="FaceAllSet" if "|FaceMotionSystem|" in path else "AllSet"
            for weighted in c.listConnections(sdk,source=True,destination=False,skipConversionNodes=True) or []:
                destinations=c.listConnections(weighted+".output",source=False,destination=True,skipConversionNodes=True,plugs=True) or []
                if not destinations:continue
                for curve in c.listConnections(weighted,source=True,destination=False,skipConversionNodes=True) or []:
                    if not self._original_restore_leaf(curve).startswith("animCurve"):continue
                    name=c.rename(curve,destinations[0].replace(".","_"))
                    if c.objExists(group) and c.sets(sdk,isMember=group):c.sets(name,add=group)
                    renamed.append(name)
        return tuple(renamed)

    def _original_driving_curve_destination(self, curve):
        c=self._cmds
        destinations=c.listConnections(curve+".output",source=False,destination=True,plugs=True,skipConversionNodes=True) or []
        return destinations[0] if destinations else ""
