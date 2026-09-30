"""Original procedural wrinkle curves and their editing controls."""
from contextlib import nullcontext
from pathlib import Path
import json
import shlex
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFaceWrinkleCurvesMixin:
    def ensure_original_face_wrinkle_map(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        if c.objExists("WrinkleMap"):
            return "WrinkleMap"
        selection = raw.ls(selection=True, long=True) or []
        self._transaction_changed = True
        c.createNode("transform", name="WrinkleMap", parent="FaceGroup")
        for kind in ("t", "r", "s"):
            for axis in "xyz":
                c.setAttr("WrinkleMap." + kind + axis, lock=True, keyable=False)
        scene = raw.file(query=True, sceneName=True)
        image_path = Path(raw.workspace(query=True, active=True)) / raw.workspace(query=True, fileRuleEntry="images") / "WrinkleMaps" / (Path(scene).stem or "Untitled")
        for attr in ("imagePath", "shader", "shaderRestoreCmd", "duplicatedSG"):
            c.addAttr("WrinkleMap", longName=attr, dataType="string")
        c.setAttr("WrinkleMap.imagePath", str(image_path).replace(chr(92), "/"), type="string")
        for attr, value in (("mapWidth",1024),("mapHeight",1024),("maskWidth",512),("maskHeight",512)):
            c.addAttr("WrinkleMap", longName=attr, attributeType="long", defaultValue=value, keyable=True)
        c.addAttr("WrinkleMap", longName="format", attributeType="enum", enumName="png:tga", keyable=True)
        c.addAttr("WrinkleMap", longName="modifier", attributeType="long", defaultValue=0)
        head = c.getAttr(self._fit(required=True) + ".HeadJoint")
        position = c.xform(head, query=True, worldSpace=True, translation=True)
        for axis in "xyz":
            c.setAttr("WrinkleMap.t" + axis, lock=False)
        c.xform("WrinkleMap", worldSpace=True, translation=position)
        for axis in "xyz":
            c.setAttr("WrinkleMap.t" + axis, lock=True)
        raw.select(selection, replace=True) if selection else raw.select(clear=True)
        return "WrinkleMap"

    def capture_original_face_wrinkle_curves(self, shader=None):
        c = self._cmds
        raw = getattr(c, "raw", c)
        if not c.objExists("FaceGroup.version") or c.getAttr("FaceGroup.version") < 5.750:
            raise FitSkeletonValidationError("WrinkleMap 需要 Face 版本不低于 5.750")
        faces = self.read_face_objects(FacePreRole.FACE)
        if len(faces) != 1:
            raise FitSkeletonValidationError("WrinkleMap 需要唯一 Face 网格")
        geometry = self._original_bs_physical_address(raw.ls(self.scene_address(faces[0]),long=True)[0])
        if c.objExists("WrinkleCurves") and c.listRelatives("WrinkleCurves", children=True):
            return {"remove": True, "geometry": geometry}
        for node in ("ForeHeadAreaMesh", "EyeBrowInner_R", "EyeBrowOuter_R", "EyeBrowCenter_M",
                     "FitEyeBall", "upperEyeLidMainCurve", "lowerEyeLidMainCurve", "innerLid_R",
                     "innerLid_L", "Nose_M", "NoseCorner_R", "Lip_R", "Cheek_R"):
            if not c.objExists(node):
                raise FitSkeletonValidationError("WrinkleCurves 缺少前置节点：" + node)
        shape = raw.listRelatives(geometry, shapes=True, noIntermediate=True, fullPath=True)[0]
        groups = raw.listConnections(shape + ".instObjGroups[0]", source=False, destination=True, type="shadingEngine") or []
        if not groups:
            groups = raw.listConnections(shape + ".instObjGroups[0].objectGroups", source=True, destination=False, type="shadingEngine") or []
        groups = tuple(dict.fromkeys(groups))
        if shader:
            groups = tuple(group for group in groups if shader in (raw.listConnections(group + ".surfaceShader", source=True, destination=False) or []))
        if len(groups) != 1:
            raise FitSkeletonValidationError("Face 有多个材质，请指定要添加 WrinkleMap 的 Shader")
        group = groups[0]
        shaders = raw.listConnections(group + ".surfaceShader", source=True, destination=False) or []
        if len(shaders) != 1 or not raw.objExists(shaders[0] + ".normalCamera"):
            raise FitSkeletonValidationError("Face 材质缺少 normalCamera，无法连接凹凸贴图")
        if group.lstrip(":") == "initialShadingGroup":
            raise FitSkeletonValidationError("请先为 Face 指定独立材质")
        return {"remove": False, "geometry": geometry, "shape": shape, "shader": shaders[0],
                "group": group, "scale": float(c.getAttr(self._fit(required=True) + ".faceScale"))}

    def _original_wrinkle_project(self, geometry, position):
        c = self._cmds
        c.xform("tempLoc", worldSpace=True, translation=position)
        c.delete(c.geometryConstraint(geometry, "tempLoc"))
        return tuple(c.xform("tempLoc", query=True, worldSpace=True, translation=True))

    def _original_wrinkle_curve(self, name, group, points, depth, width):
        c = self._cmds
        c.curve(name=name, degree=1, point=points)
        c.parent(name, group)
        for attr, value in (("depth", depth), ("width", width)):
            c.addAttr(name, longName=attr, attributeType="double", defaultValue=value, keyable=True)
        return name

    def remove_original_face_wrinkles(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        self._transaction_changed = True
        restore = c.getAttr("WrinkleMap.advPyShaderRestore") if c.objExists("WrinkleMap.advPyShaderRestore") else None
        if restore is not None:
            restore_rows = json.loads(restore or "[]")
        else:
            restore_rows = []
            source_commands = c.getAttr("WrinkleMap.shaderRestoreCmd") if c.objExists("WrinkleMap.shaderRestoreCmd") else ""
            for statement in (source_commands or "").split(";"):
                tokens = shlex.split(statement)
                if not tokens:
                    continue
                if len(tokens) != 5 or tokens[:3] != ["sets","-e","-forceElement"]:
                    raise FitSkeletonValidationError("旧 Wrinkle Shader 恢复记录不是原版 sets 指令")
                restore_rows.append((tokens[4],tokens[3]))
        for name in ("FaceWrinkleSet", "FaceWrinkleRenderingSet", "FaceWrinkleCurvesSet"):
            if c.objExists(name):
                members = [node for node in c.sets(name, query=True) or [] if c.objExists(node)]
                if members:
                    c.delete(members)
                if c.objExists(name):
                    c.delete(name)
        for attr in c.listAttr("ctrlBox", userDefined=True) or []:
            if attr.startswith("wrinkle"):
                c.deleteAttr("ctrlBox." + attr)
        for member, shader_group in restore_rows:
            if raw.objExists(member) and raw.objExists(shader_group):
                raw.sets(member, edit=True, forceElement=shader_group)
        if c.objExists("WrinkleMap"):
            c.delete("WrinkleMap")
        self.apply_face_build_pose(self.read_face_build_pose())
        return {"removed": True}

    def create_original_face_wrinkle_curves(self, source):
        self._require_transaction()
        if source["remove"]:
            return self.remove_original_face_wrinkles()
        c = self._cmds
        raw = getattr(c, "raw", c)
        self._transaction_changed = True
        before = self.capture_face_build_node_ids()
        self.ensure_original_face_wrinkle_map()
        self.apply_face_build_pose(self.read_face_build_pose())
        raw.refresh()
        c.setAttr("WrinkleMap.shader", source["shader"], type="string")
        members = tuple(dict.fromkeys(raw.listConnections(source["group"] + ".dagSetMembers", source=True, destination=False) or []))
        if len(members) > 1:
            old_sets = set(raw.ls(type="shadingEngine") or [])
            raw.select(source["group"], noExpand=True, replace=True)
            with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                raw.hyperShade(duplicate=True)
            duplicated = [node for node in raw.ls(type="shadingEngine") or [] if node not in old_sets]
            if len(duplicated) != 1:
                raise FitSkeletonValidationError("Face Shader 复制未得到唯一 ShadingGroup")
            duplicate = duplicated[0]
            c.setAttr("WrinkleMap.duplicatedSG", duplicate, type="string")
            restore = []
            geometry_id = set(raw.ls(source["geometry"], uuid=True) or [])
            for member in members:
                if raw.nodeType(member) == "mesh":
                    member = raw.listRelatives(member, parent=True, fullPath=True)[0]
                if geometry_id.intersection(raw.ls(member, uuid=True) or []):
                    continue
                raw.sets(member, edit=True, forceElement=duplicate)
                restore.append((member, source["group"]))
            c.addAttr("WrinkleMap", longName="advPyShaderRestore", dataType="string")
            c.setAttr("WrinkleMap.advPyShaderRestore", json.dumps(restore), type="string")
            c.setAttr("WrinkleMap.shaderRestoreCmd", "".join("sets -e -forceElement " + group + " " + node + ";" for node, group in restore), type="string")
        self._original_bs_delete_existing(("bump2dWrinkle",))
        if not c.objExists("WrinkleCurves"):
            c.createNode("transform", name="WrinkleCurves", parent="WrinkleMap")
        c.spaceLocator(name="tempLoc")
        visible = bool(c.getAttr("ForeHeadAreaMesh.v"))
        if not visible:
            c.setAttr("ForeHeadAreaMesh.v", 1)
        lower = c.getAttr("ForeHeadAreaMesh.boundingBoxMin")[0]
        upper = c.getAttr("ForeHeadAreaMesh.boundingBoxMax")[0]
        if not visible:
            c.setAttr("ForeHeadAreaMesh.v", 0)
        scale = source["scale"]
        pos = lambda node: tuple(c.xform(node, query=True, worldSpace=True, translation=True))
        curves = []
        c.createNode("transform", name="ForeHeadWrinkles", parent="WrinkleCurves")
        a, b, center = pos("EyeBrowInner_R"), pos("EyeBrowOuter_R"), pos("EyeBrowCenter_M")
        projected = self._original_wrinkle_project("ForeHeadAreaMesh", (center[0], (center[1]+upper[1])/2, center[2]))
        first = tuple((projected[i]+center[i])/2 for i in range(3))
        offset = first[1]-center[1]
        points = [first, (a[0],a[1]+offset,a[2])]
        for index in (1,2):
            if c.objExists("EyeBrowMid" + str(index) + "_R"):
                point = self._original_wrinkle_project("ForeHeadAreaMesh", pos("EyeBrowMid" + str(index) + "_R"))
                points.append(self._original_wrinkle_project("ForeHeadAreaMesh", (point[0],point[1]+offset,point[2])))
        points.append(self._original_wrinkle_project("ForeHeadAreaMesh", (b[0]-offset,b[1]+offset*.5,b[2]-offset)))
        curves.append(self._original_wrinkle_curve("ForeHeadWrinkle1", "ForeHeadWrinkles", points,10,20))
        for index, width, depth in ((2,15,5),(3,10,7),(4,5,1)):
            name = "ForeHeadWrinkle" + str(index)
            c.duplicate("ForeHeadWrinkle1", name=name)
            c.move(0,offset*.7*(index-1),0,name+".cv[0:99]",relative=True)
            c.setAttr(name+".depth",depth)
            c.setAttr(name+".width",width)
            curves.append(name)
        c.createNode("transform", name="FrownWrinkles", parent="WrinkleCurves")
        a,b = pos("EyeBrowInner_R"),pos("ForeHeadWrinkle1.cv[0]")
        points = [(a[0]/divisor,b[1]-offset*factor,a[2]) for divisor,factor in ((2.8,.7),(2.5,1.7),(1,2.2))]
        curves.append(self._original_wrinkle_curve("FrownWrinkle1","FrownWrinkles",points,7,12))
        c.createNode("transform",name="CrowsFeetWrinkles",parent="WrinkleCurves")
        count=int(c.getAttr("upperEyeLidMainCurve.spans"))+int(c.getAttr("upperEyeLidMainCurve.degree"))
        a=pos("upperEyeLidMainCurve.cv["+str(count-1)+"]")
        b=self._original_wrinkle_project(source["shape"],((a[0]+lower[0])/2,a[1],(a[2]+lower[2])/2))
        curves.append(self._original_wrinkle_curve("CrowsFeetWrinkle2","CrowsFeetWrinkles",(a,b),6,6))
        a=pos("upperEyeLidMainCurve.cv["+str(count-2)+"]")
        curves.append(self._original_wrinkle_curve("CrowsFeetWrinkle1","CrowsFeetWrinkles",(a,(b[0],b[1]+scale/20,b[2])),4,4))
        count=int(c.getAttr("lowerEyeLidMainCurve.spans"))+int(c.getAttr("lowerEyeLidMainCurve.degree"))
        a=pos("lowerEyeLidMainCurve.cv["+str(count-2)+"]")
        curves.append(self._original_wrinkle_curve("CrowsFeetWrinkle3","CrowsFeetWrinkles",(a,(b[0],b[1]-scale/20,b[2])),4,4))
        c.createNode("transform",name="BunnyLinesWrinkles",parent="WrinkleCurves")
        a=pos("innerLid_R")
        constraints=c.pointConstraint("innerLid_R","innerLid_L","Nose_M","NoseCorner_R","tempLoc")
        aliases=c.pointConstraint(constraints[0],query=True,weightAliasList=True)
        for alias,value in zip(aliases,(1,.5,.5,0)):
            c.setAttr(constraints[0]+"."+alias,value)
        b=pos("tempLoc")
        self._original_wrinkle_curve("BunnyLinesWrinkle1","BunnyLinesWrinkles",(a,b),1,1)
        for alias,value in zip(aliases,(1,0,1,1)):
            c.setAttr(constraints[0]+"."+alias,value)
        b=pos("tempLoc")
        self._original_wrinkle_curve("BunnyLinesWrinkle3","BunnyLinesWrinkles",((a[0],a[1]-scale/80,a[2]),b),3,3)
        c.delete(constraints)
        c.duplicate("BunnyLinesWrinkle3",name="BunnyLinesWrinkle2")
        c.blendShape("BunnyLinesWrinkle1","BunnyLinesWrinkle2",name="tempBs",frontOfChain=True,weight=(0,.5))
        raw.delete(self.scene_address("BunnyLinesWrinkle2"),constructionHistory=True)
        c.reorder("BunnyLinesWrinkle2",relative=-1)
        for index in (1,2,3):
            name="BunnyLinesWrinkle"+str(index)
            c.reverseCurve(name,constructionHistory=False,replaceOriginal=True)
            curves.append(name)
        c.createNode("transform",name="SmileLineWrinkles",parent="WrinkleCurves")
        c.pointConstraint("NoseCorner_R","tempLoc",weight=.5)
        c.pointConstraint("innerLid_R","tempLoc",weight=.25)
        c.pointConstraint("Nose_M","tempLoc",weight=.25)
        c.delete("tempLoc_pointConstraint1")
        a=self._original_wrinkle_project(source["shape"],pos("tempLoc"))
        c.pointConstraint("Lip_R","tempLoc",weight=.7)
        c.pointConstraint("Cheek_R","tempLoc",weight=.3)
        b=self._original_wrinkle_project(source["shape"],pos("tempLoc"))
        lip=pos("Lip_R")
        curves.append(self._original_wrinkle_curve("SmileLineWrinkle1","SmileLineWrinkles",(a,(b[0],b[1]+scale/20,b[2]),(b[0],b[1]-scale/20,b[2]),(lip[0],lip[1]-scale/10,lip[2])),10,10))
        for group in c.listRelatives("WrinkleCurves",children=True) or []:
            c.setAttr(group+".v",0)
        for curve in curves:
            c.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,rebuildType=0,endKnots=1,
                keepRange=0,keepControlPoints=False,keepEndPoints=False,keepTangents=False,spans=3,degree=3,tolerance=.00155)
            crossing=False
            for index in range(6):
                point=self._original_wrinkle_project(source["shape"],pos(curve+".cv["+str(index)+"]"))
                if point[0]>0:
                    crossing=True
                    point=self._original_wrinkle_project(source["shape"],(0,point[1],point[2]))
                if index==1 and crossing:
                    first=pos(curve+".cv[0]")
                    point=self._original_wrinkle_project(source["shape"],(point[0],first[1],point[2]))
                c.xform(curve+".cv["+str(index)+"]",worldSpace=True,translation=point)
        c.delete("tempLoc")
        generated=[node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition")
                   and not before.intersection(c.ls(node,uuid=True) or [])]
        c.sets(generated,name="FaceWrinkleCurvesSet")
        c.sets("FaceWrinkleCurvesSet",add="FaceAllSet")
        self.edit_original_face_wrinkle("All","Curves")
        return {"curves":tuple(curves),"removed":False}

    def edit_original_face_wrinkle(self, wrinkle, element):
        self._require_transaction()
        c=self._cmds
        if not c.objExists("WrinkleCurves"):
            raise FitSkeletonValidationError("请先创建 Wrinkle 曲线")
        if element not in ("Curves","Mask","Test"):
            raise ValueError("Wrinkle 编辑类型无效")
        self._transaction_changed=True
        groups=c.listRelatives("WrinkleCurves",children=True) or []
        if element!="Mask":
            self.apply_face_build_pose(self.read_face_build_pose())
        selected=groups if wrinkle=="All" else [wrinkle+"Wrinkles"]
        if any(group not in groups for group in selected):
            raise FitSkeletonValidationError("Wrinkle 曲线组不存在："+wrinkle)
        if element=="Curves":
            if not c.objExists("asWrinkleMapBuilding"):
                raw=getattr(c,"raw",c)
                if raw.headsUpDisplay("HUDEDSMode",query=True,exists=True):
                    raw.headsUpDisplay("HUDEDSMode",edit=True,remove=True)
                raw.headsUpDisplay("HUDEDSMode",section=2,block=0,blockSize="medium",
                    label="编辑 WrinkleMap："+wrinkle+"（"+element+"）",labelFontSize="large")
                raw.displayColor("headsUpDisplayLabels",16)
            c.setAttr("WrinkleCurves.s",1.015,1,1.015,type="float3")
            for group in groups:
                c.setAttr(group+".v",group in selected)
            controls=[node for group in selected for node in c.listRelatives(group,children=True,type="transform") or []]
            c.select(controls,replace=True)
        elif element=="Mask":
            c.select(selected,replace=True)
        else:
            for group in selected:
                if not c.objExists(group+".driver"):
                    raise FitSkeletonValidationError("请先创建 WrinkleMap 驱动")
                driver=c.getAttr(group+".driver")
                if driver=="ctrlMouthCorner_R.txPos_tyPos":
                    c.setAttr("ctrlMouthCorner_R.tx",1)
                    c.setAttr("ctrlMouthCorner_R.ty",1)
                else:
                    c.setAttr(driver,1 if ".tx" in driver or ".ty" in driver else 10)
        return tuple(selected)

    def view_original_face_wrinkle_material(self, node):
        raw=getattr(self._cmds,"raw",self._cmds)
        physical=self.scene_address(node)
        try:
            raw.soloMaterial(node=physical)
        except RuntimeError:
            # The original initializes the node-editor surface if soloMaterial
            # has not yet initialized its viewport connection in this session.
            from maya import mel
            previous=set(raw.lsUI(type="window") or [])
            mel.eval("nodeEditorWindow;")
            opened=[window for window in raw.lsUI(type="window") or []
                    if window not in previous and window.startswith("nodeEditor") and window.endswith("Window")]
            for window in opened:
                raw.evalDeferred(lambda window=window: raw.deleteUI(window))
            raw.evalDeferred(lambda: raw.soloMaterial(node=physical),lowestPriority=True)

    def original_face_wrinkle_modifiers(self):
        return int(getattr(self._cmds,"raw",self._cmds).getModifiers())

    def cancel_original_face_wrinkle_edit(self):
        self._require_transaction()
        c=self._cmds
        raw=getattr(c,"raw",c)
        if raw.headsUpDisplay("HUDEDSMode",query=True,exists=True):
            raw.headsUpDisplay("HUDEDSMode",edit=True,remove=True)
        self._transaction_changed=True
        self.apply_face_build_pose(self.read_face_build_pose())
        if c.objExists("WrinkleCurves"):
            for group in c.listRelatives("WrinkleCurves",children=True) or []:
                c.setAttr(group+".v",0)
            c.setAttr("WrinkleCurves.s",1,1,1,type="float3")
        c.select(clear=True)
