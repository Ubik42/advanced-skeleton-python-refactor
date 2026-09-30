"""asWmBake: UV-space wrinkle ribbons, feathered masks and native sampling."""
from pathlib import Path
import secrets
import string
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFaceWrinkleBakeMixin:
    def _original_wrinkle_ramp(self, name):
        c=self._cmds
        c.shadingNode("ramp",asTexture=True,name=name)
        place=c.shadingNode("place2dTexture",asUtility=True,name=name+"Place2dTexture")
        c.connectAttr(place+".outUV",name+".uv")
        c.connectAttr(place+".outUvFilterSize",name+".uvFilterSize")
        return name

    def _original_wrinkle_color(self, ramp, index, value, position=None):
        c=self._cmds
        plug=ramp+".colorEntryList["+str(index)+"]"
        c.setAttr(plug+".color",value,value,value,type="double3")
        if position is not None:
            c.setAttr(plug+".position",position)

    def _original_wrinkle_surface_shader(self, name, geometry):
        c=self._cmds
        shader=c.shadingNode("surfaceShader",asShader=True,name=name)
        group=c.sets(renderable=True,noSurfaceShader=True,empty=True,name=name+"SG")
        c.connectAttr(shader+".outColor",group+".surfaceShader",force=True)
        c.sets(geometry,edit=True,forceElement=group)
        return shader

    def _original_wrinkle_offset(self, curve, name, distance):
        return self._cmds.offsetCurve(curve,name=name,constructionHistory=True,range=False,
            connectBreaks=2,stitch=True,cutLoop=True,cutRadius=0,distance=distance,
            tolerance=.01,subdivisionDensity=5,useGivenNormal=True,normal=(0,90,0))

    def _original_wrinkle_polygon(self, surface, name, *, mask=False):
        return self._cmds.nurbsToPoly(surface,name=name,matchNormalDir=True,constructionHistory=False,
            format=1 if mask else 2,polygonType=1,polygonCount=200,chordHeightRatio=.9,
            fractionalTolerance=.01,minEdgeLength=.001,delta=.1,uType=1,uNumber=3 if mask else 20,
            vType=1,vNumber=3 if mask else 21,useChordHeight=False,useChordHeightRatio=False,
            chordHeight=.2 if mask else .01,edgeSwap=False,normalizeTrimmedUVRange=False,
            matchRenderTessellation=False,useSurfaceShader=True)

    def _original_wrinkle_sample(self, source, target, filename, extension, width, height, output):
        c=self._cmds
        raw=getattr(c,"raw",c)
        raw.surfaceSampler(filename=str(filename),fileFormat=extension,
            target=self.scene_address(target),uvSet="map1",searchOffset=0,maxSearchDistance=0,
            searchCage="",source=self.scene_address(source),mapOutput=output,mapWidth=width,
            mapHeight=height,max=1,mapSpace="tangent",mapMaterials=output=="alpha",shadows=True,
            superSampling=1,filterType=0,filterSize=3,overscan=1,searchMethod=0,
            useGeometryNormals=True,ignoreMirroredFaces=False,flipU=False,flipV=False)

    def _original_wrinkle_mirror_image(self, source, destination, extension, *, append=False):
        # The source uses ImageMagick -flop and +append. MImage performs the same
        # RGBA pixel operations without an external executable or shell quoting.
        import maya.api.OpenMaya as om
        image=om.MImage()
        image.readFromFile(str(source))
        width,height=image.getSize()
        pixels=bytes(image.pixels())
        mirrored=bytearray(len(pixels))
        for y in range(height):
            for x in range(width):
                start=(y*width+x)*4
                other=(y*width+width-1-x)*4
                mirrored[start:start+4]=pixels[other:other+4]
        if append:
            joined=bytearray(width*height*8)
            for y in range(height):
                row=y*width*4
                output=y*width*8
                joined[output:output+width*4]=pixels[row:row+width*4]
                joined[output+width*4:output+width*8]=mirrored[row:row+width*4]
            image.setPixels(joined,width*2,height)
        else:
            image.setPixels(mirrored,width,height)
        image.writeToFile(str(destination),extension)

    def bake_original_face_wrinkle_maps(self):
        self._require_transaction()
        c=self._cmds
        raw=getattr(c,"raw",c)
        if not c.objExists("fileFaceWrinkles"):
            raise FitSkeletonValidationError("请先创建完整 WrinkleMap，再应用编辑")
        self._transaction_changed=True
        geometry,mesh=self._original_wrinkle_geometry()
        current=raw.polyUVSet(mesh,query=True,currentUVSet=True)[0]
        raw.polyUVSet(mesh,currentUVSet=True,uvSet="uvFaceWrinkles")
        before=self.capture_face_build_node_ids()
        if c.objExists("FaceWrinkleRenderingSet"):
            old=[node for node in c.sets("FaceWrinkleRenderingSet",query=True) or [] if c.objExists(node)]
            if old:
                c.delete(old)
            c.delete("FaceWrinkleRenderingSet")
        self._original_bs_delete_existing(("WrinkleRendering",))
        groups=c.listRelatives("WrinkleCurves",children=True) or []
        curves=[node for group in groups for node in c.listRelatives(group,children=True,type="transform") or []]
        eyebrow=self._original_wrinkle_fit_selection("EyeBrowInner_R")
        eyebrow_uv=raw.polyEditUV(self._original_wrinkle_selection_uvs(raw,eyebrow),query=True)
        for name,parent in (("WrinkleRendering",None),("WrinkleRenderingPlanes","WrinkleRendering"),
                            ("WrinkleRenderingCurves","WrinkleRendering"),("WrinkleRenderingMasks","WrinkleRendering"),
                            ("WrinkleRenderingMeshes","WrinkleRendering")):
            c.createNode("transform",name=name,**({"parent":parent} if parent else {}))
        image_path=Path(c.getAttr("WrinkleMap.imagePath"))
        image_path.mkdir(parents=True,exist_ok=True)
        extension=c.getAttr("WrinkleMap.format",asString=True)
        c.polyPlane(name="WrinkleFacePlane1",width=.5,height=1,subdivisionsX=1,subdivisionsY=1,
                    axis=(0,1,0),createUVs=2,constructionHistory=False)
        c.polyProjection("WrinkleFacePlane1.f[0:8]",constructionHistory=False,type="Planar",insertBeforeDeformers=True,mapDirection="y")
        c.parent("WrinkleFacePlane1","WrinkleRenderingPlanes")
        c.setAttr("WrinkleFacePlane1.t",.25,0,.5,type="float3")
        c.setAttr("WrinkleFacePlane1.v",0)
        c.duplicate("WrinkleFacePlane1",name="WrinkleFacePlane2")
        c.duplicate("WrinkleFacePlane2",name="WrinkleFacePlane3")
        c.setAttr("WrinkleFacePlane3.tx",.5)
        c.setAttr("WrinkleFacePlane3.sx",2)
        c.polyPlane(name="WrinkleFacePlane4",width=1,height=1,subdivisionsX=1,subdivisionsY=1,
                    axis=(0,1,0),createUVs=2,constructionHistory=False)
        c.setAttr("WrinkleFacePlane4.t",0,-.0125,.5,type="float3")
        c.setAttr("WrinkleFacePlane4.rz",90)
        c.setAttr("WrinkleFacePlane4.sx",.025)
        c.setAttr("WrinkleFacePlane4.v",0)
        c.parent("WrinkleFacePlane4","WrinkleRenderingPlanes")
        uvsets=raw.polyUVSet(geometry,query=True,allUVSets=True)
        default="map1" if "map1" in uvsets else uvsets[0]
        c.duplicate(geometry,name="tempMainGeometry")
        c.polyCopyUV("tempMainGeometry",uvSetNameInput="",uvSetName=default,constructionHistory=True)
        self._original_bs_delete_existing(("closestSampler",))
        c.createNode("closestPointOnMesh",name="closestSampler")
        c.connectAttr("tempMainGeometry.outMesh","closestSampler.inMesh",force=True)
        for curve in curves:
            count=int(c.getAttr(curve+".spans"))+int(c.getAttr(curve+".degree"))
            plane=curve+"OnPlane"
            c.duplicate(curve,name=plane)
            c.parent(plane,"WrinkleRenderingCurves")
            c.xform(plane,worldSpace=True,pivots=(0,0,0))
            for index in range(count):
                point=c.xform(curve+".cv["+str(index)+"]",query=True,worldSpace=True,translation=True)
                c.setAttr("closestSampler.inPosition",*point,type="float3")
                u,v=c.getAttr("closestSampler.parameterU"),c.getAttr("closestSampler.parameterV")
                c.xform(plane+".cv["+str(index)+"]",worldSpace=True,translation=(u,0,1-v))
        c.delete("tempMainGeometry")
        for curve in curves:
            leaf=self._original_restore_leaf(curve)
            depth=c.getAttr(curve+".depth") if c.objExists(curve+".depth") else 10
            width=c.getAttr(curve+".width") if c.objExists(curve+".width") else 10
            a,b,center=width*.001,width*-.001,.5
            if leaf=="SmileLineWrinkle1":
                b,center=width*-.025,.1
            plane=curve+"OnPlane"
            offset_a,offset_b=curve+"OnPlaneOffsetA",curve+"OnPlaneOffsetB"
            result=self._original_wrinkle_offset(plane,offset_a,a)
            c.rename(result[1],leaf+"OffsetCurveA")
            result=self._original_wrinkle_offset(plane,offset_b,b)
            history=c.rename(result[1],leaf+"OffsetCurveB")
            if leaf=="SmileLineWrinkle1" and c.getAttr(offset_b+".boundingBoxMin")[0][0]<.03:
                for index in range(1,20):
                    c.setAttr(history+".distance",b+.01*index)
                    if c.getAttr(offset_b+".boundingBoxMin")[0][0]>.03:
                        break
                b=c.getAttr(history+".distance")
            for attr,value in (("offsetA",a),("offsetB",b)):
                c.addAttr(plane,longName=attr,attributeType="double",defaultValue=value)
            loft_inputs=[offset_a,plane,offset_b]
            if c.getAttr(offset_a+".boundingBoxMin")[0][0]>.5:
                loft_inputs.remove(offset_a)
            surface=leaf+"Loft"
            c.loft(loft_inputs,name=surface,constructionHistory=False,uniform=True,close=False,
                   autoReverse=False,degree=1,sectionSpans=1,range=False,polygon=0,reverseSurfaceNormals=True)
            c.parent([offset_a,offset_b],"WrinkleRenderingCurves")
            polygon=leaf+"Mesh"
            self._original_wrinkle_polygon(surface,polygon)
            c.parent(polygon,"WrinkleRenderingMeshes")
            if c.polyNormalPerVertex(polygon+".vtx[0]",query=True,normalY=True)[0]<0:
                c.polyNormal(polygon,constructionHistory=False,normalMode=0,userNormalMode=0)
            c.delete([offset_a,offset_b,surface])
            raw.delete(self.scene_address(polygon),constructionHistory=True)
            shader=self._original_wrinkle_surface_shader(leaf+"WrinkleDepthShader",polygon)
            ramp1=self._original_wrinkle_ramp(leaf+"WrinkleDepthRamp1")
            ramp2=self._original_wrinkle_ramp(leaf+"WrinkleDepthRamp2")
            c.connectAttr(ramp1+".outColor",shader+".outColor")
            c.setAttr(ramp1+".type",0)
            c.setAttr(ramp1+".interpolation",4)
            self._original_wrinkle_color(ramp1,0,0)
            self._original_wrinkle_color(ramp1,1,1,center)
            self._original_wrinkle_color(ramp1,2,0,1)
            c.setAttr(ramp2+".type",1)
            c.setAttr(ramp2+".interpolation",4)
            self._original_wrinkle_color(ramp2,0,depth*.1 if leaf.startswith("ForeHeadWrinkle") else 0)
            self._original_wrinkle_color(ramp2,1,depth*.1,.25)
            self._original_wrinkle_color(ramp2,2,depth*(.05 if leaf.startswith("CrowsFeetWrinkle") else .1),.75)
            self._original_wrinkle_color(ramp2,3,0,1)
            c.connectAttr(ramp2+".outColor",ramp1+".colorEntryList[1].color")
        meshes=c.listRelatives("WrinkleRenderingMeshes",children=True) or []
        meshes=c.parent(meshes,world=True)
        c.polyUnite(meshes,constructionHistory=False,mergeUVSets=1,name="WrinklesMesh")
        c.parent("WrinklesMesh","WrinkleRenderingMeshes")
        # The source repeats this duplicate with an occupied name. Maya creates a
        # uniquely named extra plane; the existing Plane3 remains the sampler target.
        c.duplicate("WrinkleFacePlane2",name="WrinkleFacePlane3")
        c.setAttr("WrinkleFacePlane3.tx",.5)
        c.setAttr("WrinkleFacePlane3.sx",2)
        skip=c.objExists("SkipBaker")
        for group_node in groups:
            group=self._original_restore_leaf(group_node).removesuffix("Wrinkles")
            sections=[c.getAttr(group_node+".sections"+str(i)) for i in range(2) if c.objExists(group_node+".sections"+str(i))]
            planes=c.ls(group+"Wrinkle*OnPlane") or []
            if not planes:
                continue
            surface=group+"WrinkleMaskSurface"
            if len(planes)==1:
                a=c.getAttr(planes[0]+".offsetA") if c.objExists(planes[0]+".offsetA") else .01
                b=c.getAttr(planes[0]+".offsetB") if c.objExists(planes[0]+".offsetB") else -.01
                self._original_wrinkle_offset(planes[0],"WrinkleOffsetCurve1",a)
                self._original_wrinkle_offset(planes[0],"WrinkleOffsetCurve2",b)
                inputs=["WrinkleOffsetCurve1","WrinkleOffsetCurve2"]
            else:
                inputs=planes
            c.loft(inputs,name=surface,constructionHistory=False,uniform=True,close=False,autoReverse=False,
                   degree=1 if len(planes)==1 else 3,sectionSpans=1,range=False,polygon=0,reverseSurfaceNormals=True)
            if len(planes)==1:
                c.delete(inputs)
            c.extendSurface(surface,constructionHistory=False,extendMethod=0,extensionType=0,
                            distance=.02,join=True,replaceOriginal=True,extendSide=2,extendDirection=2)
            if group=="ForeHead":
                point=c.xform(surface+".cv[0][0]",query=True,worldSpace=True,translation=True)
                c.move((1-eyebrow_uv[0])-point[0],0,0,surface+".cv[0][0:99]",relative=True)
            mask=group+"WrinkleMask"
            self._original_wrinkle_polygon(surface,mask,mask=True)
            c.delete(surface)
            c.parent(mask,"WrinkleRenderingMasks")
            for index,section in enumerate(sections):
                name=group+section
                target=name+"WrinkleMask"
                if len(sections)>1:
                    c.duplicate(mask,name=target)
                random="".join(secrets.choice(string.ascii_uppercase) for _ in range(6))
                shader=self._original_wrinkle_surface_shader(random+name+"WrinkleMaskShader",target)
                ramp=self._original_wrinkle_ramp(random+name+"WrinkleMaskRamp")
                sections_ramp=self._original_wrinkle_ramp(name+"WrinkleSectionsMaskRamp")
                c.connectAttr(ramp+".outColor",shader+".outTransparency")
                c.setAttr(sections_ramp+".interpolation",4)
                self._original_wrinkle_color(sections_ramp,0,0)
                self._original_wrinkle_color(sections_ramp,1,0,1)
                c.connectAttr(sections_ramp+".outColor",ramp+".colorEntryList[0].color")
                c.setAttr(ramp+".type",5)
                c.setAttr(ramp+".colorEntryList[0].position",.9)
                self._original_wrinkle_color(ramp,1,1,1)
                c.setAttr(sections_ramp+".invert",group=="SmileLine")
                if len(sections)>1:
                    c.setAttr(sections_ramp+".type",1 if sections[0]=="U1" else 0)
                    self._original_wrinkle_color(sections_ramp,index,1)
                if group=="ForeHead" and section=="U2":
                    self._original_wrinkle_color(sections_ramp,0,1)
                    self._original_wrinkle_color(sections_ramp,1,1)
                    self._original_wrinkle_color(sections_ramp,2,0,.25)
                    self._original_bs_delete_existing(("closestSampler",))
                    c.createNode("closestPointOnMesh",name="closestSampler")
                    c.connectAttr("ForeHeadU1WrinkleMask.outMesh","closestSampler.inMesh",force=True)
                    c.setAttr("closestSampler.inPosition",eyebrow_uv[0],0,1-eyebrow_uv[1],type="float3")
                    c.setAttr(sections_ramp+".colorEntryList[2].position",c.getAttr("closestSampler.parameterU"))
                    c.setAttr(sections_ramp+".interpolation",1)
                    c.setAttr("closestSampler.inPositionX",.5)
                    self._original_wrinkle_color(sections_ramp,3,.5,c.getAttr("closestSampler.parameterU"))
                    c.delete("closestSampler")
                right=image_path/(name+"Mask_R."+extension)
                left=image_path/(name+"Mask_L."+extension)
                if not skip:
                    self._original_wrinkle_sample(target,"WrinkleFacePlane3",right.with_suffix(""),extension,
                        int(c.getAttr("WrinkleMap.maskWidth")),int(c.getAttr("WrinkleMap.maskHeight")),"alpha")
                    self._original_wrinkle_mirror_image(right,left,extension)
                for side,path in (("_R",right),("_L",left)):
                    c.setAttr("fileWrinkle"+name+side+".fileTextureName",str(path).replace(chr(92),"/"),type="string")
            if len(sections)>1:
                c.delete(mask)
        width,height=int(c.getAttr("WrinkleMap.mapWidth")),int(c.getAttr("WrinkleMap.mapHeight"))
        bump=image_path/("bump."+extension)
        if not skip:
            sampled=image_path/("sampleddiffuseRGB."+extension)
            self._original_wrinkle_sample("WrinklesMesh","WrinkleFacePlane2",sampled.with_suffix(""),extension,width//2,height,"diffuseRGB")
            self._original_wrinkle_mirror_image(sampled,bump,extension,append=True)
            sampled.unlink()
            snapshot=image_path/("uvSnapshot."+extension)
            if not snapshot.exists():
                raw.select(mesh,replace=True)
                raw.uvSnapshot(overwrite=True,fileFormat=extension,xResolution=width,yResolution=height,
                    antiAliased=True,redColor=255,greenColor=255,blueColor=255,name=str(snapshot),uMin=0,uMax=1,vMin=0,vMax=1)
        c.setAttr("fileFaceWrinkles.fileTextureName",str(bump).replace(chr(92),"/"),type="string")
        for node in ("WrinkleFacePlane2","WrinkleFacePlane3","WrinkleRenderingMasks"):
            c.setAttr(node+".v",0)
        modifier=int(c.getAttr("WrinkleMap.modifier"))
        c.setAttr("WrinkleMap.modifier",0)
        raw.polyUVSet(mesh,currentUVSet=True,uvSet=current)
        generated=[node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition")
                   and not before.intersection(c.ls(node,uuid=True) or [])]
        c.sets(generated,name="FaceWrinkleRenderingSet")
        if c.objExists("Sets"):
            c.sets("FaceWrinkleRenderingSet",add="Sets")
        scale=c.getAttr(self._fit(required=True)+".faceScale")
        point=c.xform("ctrlBox",query=True,worldSpace=True,translation=True)
        c.setAttr("WrinkleRendering.rx",90)
        c.setAttr("WrinkleRendering.s",scale*.75,scale*.75,scale*.75,type="float3")
        c.setAttr("WrinkleRendering.t",point[0]*-1.5,point[1]+scale*.35,point[2],type="float3")
        c.setAttr("WrinkleRenderingPlanes.ty",scale*-.005)
        if modifier!=4:
            c.delete("WrinkleRendering")
            alive=[node for node in c.sets("FaceWrinkleRenderingSet",query=True) or [] if c.objExists(node)]
            if alive:
                c.delete(alive)
        c.select(clear=True)
        return {"image_path":str(image_path),"bump":str(bump),"baked":not skip,"curves":len(curves)}
