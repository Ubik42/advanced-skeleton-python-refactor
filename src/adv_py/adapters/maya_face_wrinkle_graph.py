"""asWrinkleMap shader, normalized secondary drivers and layered masks."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_wrinkle_bake import MayaFaceWrinkleBakeMixin

_WRINKLE_DRIVERS = {
    "ForeHead": ("ctrlBrow{side}.ty",1,("EyeBrowOuter{side}.ty","EyeBrowInner{side}.ty"),("U1","U2")),
    "Frown": ("ctrlBrow{side}.squeeze",10,("EyeBrowInner{side}.tx",),("",)),
    "CrowsFeet": ("ctrlEye{side}.squint",10,(),("",)),
    "BunnyLines": ("ctrlNose{side}.ty",1,("NoseCorner{side}.ty",),("",)),
    "SmileLine": ("ctrlMouthCorner{side}.txPos_tyPos",1,("Lip{side}.tx","Lip{side}.ty"),("U1","U2")),
}
_UV_PLUGS = tuple(zip(("outUv","outVertexUvOne","outVertexUvTwo","outVertexUvThree","outVertexCameraOne"),
                     ("uvCoord","vertexUvOne","vertexUvTwo","vertexUvThree","vertexCameraOne")))

class MayaFaceWrinkleGraphMixin(MayaFaceWrinkleBakeMixin):
    def _original_wrinkle_uv_connections(self, texture):
        for output, destination in _UV_PLUGS:
            self._cmds.connectAttr("uvChooserFaceWrinkles."+output, texture+"."+destination)

    def create_original_face_wrinkle_map(self, *, modifier=0):
        self._require_transaction()
        c=self._cmds
        raw=getattr(c,"raw",c)
        if not c.objExists("WrinkleCurves"):
            raise FitSkeletonValidationError("请先创建 Wrinkle 曲线")
        if c.objExists("FaceWrinkleSet"):
            return self.remove_original_face_wrinkles()
        self._transaction_changed=True
        before=self.capture_face_build_node_ids()
        raw.softSelect(edit=True,softSelectEnabled=False)
        c.setAttr("WrinkleMap.modifier",int(modifier))
        self.cancel_original_face_wrinkle_edit()
        geometry,mesh=self._original_wrinkle_geometry()
        shader=c.getAttr("WrinkleMap.shader")
        c.createNode("transform",name="asWrinkleMapBuilding")
        for attr,value in (("wrinkleMapMultiply",1),("wrinkleMapOffset",0)):
            c.addAttr("ctrlBox",longName=attr,attributeType="double",defaultValue=value,keyable=True)
            c.setAttr("ctrlBox."+attr,keyable=False,channelBox=True)
        self.update_original_face_wrinkle_uv()
        if not c.objExists("uvChooserFaceWrinkles"):
            c.createNode("uvChooser",name="uvChooserFaceWrinkles")
        uv_indices=raw.getAttr(mesh+".uvSet",multiIndices=True) or []
        wrinkle_uv=next((i for i in uv_indices if raw.getAttr(mesh+".uvSet["+str(i)+"].uvSetName")=="uvFaceWrinkles"),None)
        if wrinkle_uv is None:
            raise FitSkeletonValidationError("Face 缺少 uvFaceWrinkles")
        raw.connectAttr(mesh+".uvSet["+str(wrinkle_uv)+"].uvSetName",self.scene_address("uvChooserFaceWrinkles.uvSets[0]"),force=True)
        c.shadingNode("file",asTexture=True,name="fileFaceWrinkles")
        # Maya defaultNavigation creates the native bump2d intermediary.  No ADV
        # MEL procedure is evaluated; its renderer connection policy is retained.
        raw.defaultNavigation(connectToExisting=True,source=self.scene_address("fileFaceWrinkles"),destination=shader+".normalCamera")
        bumps=raw.listConnections(shader+".normalCamera",source=True,destination=False) or []
        if len(bumps)!=1:
            raise FitSkeletonValidationError("Wrinkle 材质未生成唯一 bump2d 节点")
        raw.rename(bumps[0],self.scene_address("bump2dWrinkle"))
        self._original_wrinkle_uv_connections("fileFaceWrinkles")
        for name in ("multDoubleLinearFaceWrinkles1","multDoubleLinearFaceWrinkles2"):
            c.createNode("multDoubleLinear",name=name)
        c.connectAttr("ctrlBox.wrinkleMapMultiply","multDoubleLinearFaceWrinkles1.input1")
        c.setAttr("multDoubleLinearFaceWrinkles1.input2",.5)
        c.connectAttr("multDoubleLinearFaceWrinkles1.output","multDoubleLinearFaceWrinkles2.input2")
        c.shadingNode("plusMinusAverage",asUtility=True,name="plusMinusAverageFaceWrinkles")
        c.connectAttr("multDoubleLinearFaceWrinkles2.output","plusMinusAverageFaceWrinkles.input1D[0]")
        c.connectAttr("ctrlBox.wrinkleMapOffset","plusMinusAverageFaceWrinkles.input1D[1]")
        c.connectAttr("plusMinusAverageFaceWrinkles.output1D","bump2dWrinkle.bumpDepth",force=True)
        c.shadingNode("layeredTexture",asTexture=True,name="WrinkleMasksLayeredTexture")
        c.setAttr("WrinkleMasksLayeredTexture.alphaIsLuminance",1)
        c.connectAttr("WrinkleMasksLayeredTexture.outAlpha","multDoubleLinearFaceWrinkles2.input1")
        fit=self._fit(required=True)
        rig_type=int(c.getAttr(fit+".RigType")) if c.objExists(fit+".RigType") else 0
        layer=0
        for group_node in c.listRelatives("WrinkleCurves",children=True) or []:
            group=self._original_restore_leaf(group_node).removesuffix("Wrinkles")
            primary,amplitude,secondary,sections=_WRINKLE_DRIVERS[group]
            right_value=0.0
            for side in ("_R","_L"):
                drivers=[primary.format(side=side)]
                values=[amplitude]*len(sections)
                secondaries=[driver.format(side=side) for driver in secondary]
                if not c.objExists(group_node+".driver"):
                    c.addAttr(group_node,longName="driver",dataType="string",keyable=True)
                    c.setAttr(group_node+".driver",drivers[0],type="string")
                    for attr,value,limits in (("multiply",1,dict(minValue=0,maxValue=2)),("offset",0,{}),("start",.25,dict(minValue=0,maxValue=1))):
                        c.addAttr(group_node,longName=attr,attributeType="double",defaultValue=value,keyable=True,**limits)
                        c.setAttr(group_node+"."+attr,keyable=False,channelBox=True)
                if rig_type!=1 and secondaries:
                    if not c.objExists("WrinkleDrivers"):
                        c.createNode("transform",name="WrinkleDrivers",parent="WrinkleMap")
                        c.parentConstraint("FaceMotionSystem","WrinkleDrivers",maintainOffset=True)
                        for axis in "XYZ":
                            c.connectAttr("FaceMotionSystem.scale"+axis,"WrinkleDrivers.scale"+axis)
                    drivers=[]
                    for index,secondary_driver in enumerate(secondaries):
                        obj,attr=secondary_driver.rsplit(".",1)
                        offset=group+"Driver"+str(index+1)+"Offset"+side
                        driver=group+"Driver"+str(index+1)+side
                        c.createNode("transform",name=offset,parent="WrinkleDrivers")
                        c.createNode("transform",name=driver,parent=offset)
                        c.delete(c.parentConstraint(obj,offset))
                        if group=="SmileLine":
                            c.rotate(0,0,45,offset,relative=True,objectSpace=True)
                            c.rotate(-180,0,0,offset,relative=True,objectSpace=True)
                        if side=="_R":
                            self.edit_original_face_wrinkle(group,"Test")
                            position=c.xform(obj,query=True,worldSpace=True,translation=True)
                            self.cancel_original_face_wrinkle_edit()
                            c.xform(driver,worldSpace=True,translation=position)
                            values[index]=c.getAttr(driver+"."+attr)
                            if group=="SmileLine" and index==1:
                                values[index]=values[index-1]
                            c.setAttr(driver+"."+attr,0)
                            right_value=values[index]
                        else:
                            values[index]=right_value
                        if values[index]==0:
                            values[index]=.1
                        c.pointConstraint(obj,driver)
                        drivers.append(driver+"."+attr)
                for kind in ("t","r","s"):
                    for axis in "xyz":
                        c.setAttr(group_node+"."+kind+axis,lock=True,keyable=False)
                for index,section in enumerate(sections):
                    if side=="_R":
                        c.addAttr(group_node,longName="sections"+str(index),dataType="string")
                        c.setAttr(group_node+".sections"+str(index),section,type="string")
                    identifier=group+section+side
                    destination="WrinkleMasksLayeredTexture.inputs["+str(layer)+"]"
                    c.setAttr(destination+".color",0,0,0,type="double3")
                    c.setAttr(destination+".blendMode",4)
                    texture="fileWrinkle"+identifier
                    c.shadingNode("file",asTexture=True,name=texture)
                    self._original_wrinkle_uv_connections(texture)
                    c.connectAttr(texture+".outColor",destination+".color",force=True)
                    sr="srWrinkle"+identifier
                    uc="srWrinkleMultiplyUC"+identifier
                    c.createNode("setRange",name=sr)
                    c.setAttr(sr+".maxX",1)
                    c.setAttr(sr+".oldMaxX",1)
                    c.createNode("unitConversion",name=uc)
                    c.setAttr(uc+".conversionFactor",.5)
                    c.connectAttr(group_node+".multiply",uc+".input")
                    c.connectAttr(uc+".output",sr+".maxX")
                    c.connectAttr(group_node+".start",sr+".oldMinX")
                    c.connectAttr(group_node+".offset",sr+".minX")
                    driver=drivers[min(index,len(drivers)-1)]
                    if values[index]!=1:
                        normalize=driver.replace(".","_")
                        self._original_bs_delete_existing((normalize,))
                        c.createNode("unitConversion",name=normalize)
                        c.setAttr(normalize+".conversionFactor",1/values[index])
                        c.connectAttr(driver,normalize+".input")
                        driver=normalize+".output"
                    c.connectAttr(driver,sr+".valueX")
                    for value,tangent in ((0,"spline"),(1,"flat")):
                        c.setDrivenKeyframe(destination+".alpha",currentDriver=sr+".outValueX",driverValue=value,value=value,
                                             inTangentType=tangent,outTangentType=tangent)
                    layer+=1
        self.bake_original_face_wrinkle_maps()
        c.delete("asWrinkleMapBuilding")
        generated=[node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition")
                   and not before.intersection(c.ls(node,uuid=True) or [])]
        c.sets(generated,name="FaceWrinkleSet")
        if c.objExists("Sets"):
            c.sets("FaceWrinkleSet",add="Sets")
        c.sets("FaceWrinkleSet",add="FaceAllSet")
        duplicate=c.getAttr("WrinkleMap.duplicatedSG")
        if duplicate and raw.objExists(duplicate):
            raw.sets(duplicate,add=self.scene_address("FaceWrinkleSet"))
        for node in generated:
            if "." not in node and c.objExists(node+".isHistoricallyInteresting"):
                c.setAttr(node+".isHistoricallyInteresting",0)
        c.select("ctrlBox",replace=True)
        return {"layers":layer,"created":True}
