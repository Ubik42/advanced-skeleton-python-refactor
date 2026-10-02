"""ADV 6.925 Teeth controls and asSkinTeeth, 38004–38051 / 42481–42625."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_original_skin_history import bind_original_skin

class MayaFaceTeethMixin:
    def read_original_face_parts(self,attribute):
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        text=c.getAttr(fit+"."+attribute) if c.objExists(fit+"."+attribute) else ""
        if not text: return ()
        result=tuple(raw.ls(tuple(self.scene_address(token) for token in text.split()),
            long=True,flatten=True) or [])
        if not result: raise FitSkeletonValidationError(attribute+" 记录的对象或组件已经不存在")
        return result

    def record_original_face_parts(self,attribute):
        if attribute not in ("UpperTeeth","LowerTeeth","Tongue","Eyebrow","EyeLash","Extras"): raise ValueError("Face 部件类型无效")
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        selected=tuple(raw.ls(selection=True,long=True,flatten=True) or [])
        if not selected: raise FitSkeletonValidationError("请先选择 "+attribute+" 网格或组件")
        for object_name in dict.fromkeys(node.split(".",1)[0] for node in selected):
            shapes=raw.listRelatives(object_name,shapes=True,noIntermediate=True,type="mesh") or []
            if not shapes: raise FitSkeletonValidationError(attribute+" 输入必须来自多边形网格")
        fit=self._fit(required=True)
        if not c.objExists(fit+"."+attribute): c.addAttr(fit,longName=attribute,dataType="string")
        c.setAttr(fit+"."+attribute," ".join(selected),type="string")
        self._transaction_changed=True
        return selected

    def _face_part_vertices(self,parts):
        raw=getattr(self._cmds,"raw",self._cmds)
        return tuple(raw.ls(raw.polyListComponentConversion(parts,toVertex=True),long=True,flatten=True) or []) if parts else ()

    def create_original_teeth_controls(self,source):
        c=self._cmds; raw=getattr(c,"raw",c); controls=[]
        for arc,parts in (("upper",source.upper_teeth),("lower",source.lower_teeth)):
            if not parts: continue
            objects=tuple(dict.fromkeys(vertex.split(".",1)[0] for vertex in parts))
            for mesh in objects: raw.showHidden(mesh,above=True)
            # Original multiple-object path duplicates whole objects for its bound.
            bounds=raw.exactWorldBoundingBox(*(objects if len(objects)>1 else parts))
            stem=arc+"Teeth"; control=self.create_original_face_controller(stem,"_M",4)
            c.parent(stem+"Joint_M","FaceJoint_M",absolute=True)
            c.parent(stem+"Offset_M","SideReverse_M",absolute=True)
            c.setAttr(stem+"Offset_M.scale",1,1,1)
            c.rotate(-90,0,0,control+".cv[0:7]",relative=True,objectSpace=True,pivot=(0,0,0))
            c.scale((bounds[3]-bounds[0])/(source.face_scale*.03),1,
                (bounds[5]-bounds[2])/(source.face_scale*.03),control+".cv[0:7]")
            c.xform(stem+"Offset_M",worldSpace=True,translation=(0,(bounds[1]+bounds[4])/2,(bounds[2]+bounds[5])/2))
            c.move(0,0,-source.face_scale/10,control+".cv[*]",relative=True)
            shape=(c.listRelatives(control,shapes=True,fullPath=True) or [None])[0]
            c.connectAttr("ctrlBox.TeethCtrlVis",shape+".overrideVisibility",force=True)
            if arc=="lower": self.add_original_face_follow(control,"JawFollow_M","JawStatic_M",10)
            if source.use_offset_parent_matrix:
                self.constrain_original_face(control,stem+"Joint_M")
                self.reset_original_face_joint_matrix_scale(stem+"Joint_M")
            else:
                c.parentConstraint(control,stem+"Joint_M")
                c.scaleConstraint(control,stem+"Joint_M",maintainOffset=True)
            c.setAttr(stem+"Joint_M.segmentScaleCompensate",False)
            c.setAttr(stem+"Offset_M.visibility",False)
            controls.append(control)
        return controls

    def _original_face_skin_history(self,mesh):
        raw=getattr(self._cmds,"raw",self._cmds)
        skins=[node for node in raw.listHistory(mesh,pruneDagObjects=True,interestLevel=2) or []
               if raw.nodeType(node)=="skinCluster"]
        return skins[-1] if skins else None

    def skin_original_face_teeth(self,source):
        """asSkinTeeth includes temporary Jaw Skin on an object-level tongue."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); result=[]
        production=self.scene_address(source.skin)
        geometry=self.scene_address(source.geometry)
        # asSkinTeeth matches the complete LowerTeeth text by its prefix and
        # presence of any component token, even while weighting upper teeth.
        lower_text=" ".join(source.lower_teeth)
        lower_components=bool(lower_text.startswith(geometry) and "." in lower_text)
        for arc,parts in (("upper",source.upper_teeth),("lower",source.lower_teeth)):
            vertices=self._face_part_vertices(parts)
            if not vertices: continue
            joint=self.scene_address(arc+"TeethJoint_M")
            objects=tuple(dict.fromkeys(vertex.split(".",1)[0] for vertex in vertices))
            for mesh in objects:
                skin=self._original_face_skin_history(mesh)
                if skin is None:
                    skin=bind_original_skin(raw,(joint,mesh),
                        self.scene_address(arc+"TeethSC"),namespace=self.namespace)
                else:
                    # Preserve the MEL condition: both branches consult the
                    # original LowerTeeth text, even while weighting upper teeth.
                    target=production if lower_components else skin
                    influences=raw.skinCluster(target,query=True,influence=True) or []
                    joint_ids=set(raw.ls(joint,uuid=True) or [])
                    if lower_components or not any(joint_ids & set(raw.ls(inf,uuid=True) or []) for inf in influences):
                        raw.skinCluster(target,edit=True,addInfluence=joint,lockWeights=False,weight=0)
                    if lower_components:
                        raw.skinPercent(target,vertices,transformValue=[(joint,1)])
                    else:
                        try:raw.skinPercent(target,vertices,transformValue=[(joint,1)])
                        except RuntimeError:pass  # Source catchQuiet on this branch only.
                result.append(skin)
        if source.tongue and not any("." in value for value in source.tongue):
            vertices=self._face_part_vertices(source.tongue)
            if vertices:
                mesh=vertices[0].split(".",1)[0]; jaw=self.scene_address("JawJoint_M")
                skin=self._original_face_skin_history(mesh)
                if skin is None:
                    skin=bind_original_skin(raw,(jaw,mesh),
                        self.scene_address("TongueSC"),namespace=self.namespace)
                else:
                    influences=raw.skinCluster(skin,query=True,influence=True) or []
                    joint_ids=set(raw.ls(jaw,uuid=True) or [])
                    if not any(joint_ids & set(raw.ls(inf,uuid=True) or []) for inf in influences):
                        raw.skinCluster(skin,edit=True,addInfluence=jaw,lockWeights=False,weight=0)
                    raw.skinPercent(skin,vertices,transformValue=[(jaw,1)])
                result.append(skin)
        from maya import mel
        raw.setToolTo(mel.eval('$advPySelectTool = $gSelect;'))
        self._transaction_changed=True
        return tuple(dict.fromkeys(result))
