"""ADV 6.925 shared cage creates Cheek/Nose/Chin/Brow projected controls."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_cage import FaceCageInput
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_jaw import MayaFaceJawHost
from .maya_face_cage_geometry import MayaFaceCageGeometryMixin
from .maya_face_cage_weights import MayaFaceCageWeightsMixin

class MayaFaceCageHost(MayaFaceCageGeometryMixin,MayaFaceCageWeightsMixin,MayaFaceJawHost):
    def capture_face_cage_input(self):
        c=self._cmds; fit=self._fit(required=True)
        above=c.objExists("EyeBrowInner"); below=c.objExists("upperLipMainCurve")
        if not above and not below: return None
        meshes=self.read_face_objects(FacePreRole.FACE)
        if len(meshes)!=1: raise FitSkeletonValidationError("Face Cage 需要唯一 Face 网格")
        head=c.getAttr(fit+".HeadJoint")
        heads=c.ls(head,long=True,type="joint") or []
        if len(heads)!=1: raise FitSkeletonValidationError("Face Cage 缺少唯一 Head 关节")
        required=("FaceJoint_M","FaceBuildInProgressHidden","FaceBuildingSets","FaceAreas",
                  "FaceControlOrient","OnFacecontrols","ctrlBox","templateLayer",
                  "upperEyeLidOuterCurve","lowerEyeLidOuterCurve","lowerLidOuterJoint_R","lowerLidOuterJoint_L")
        for node in required:
            if not c.objExists(node): raise FitSkeletonValidationError("Face Cage 缺少原版前置节点："+node)
        def option(name): return bool(c.objExists(fit+"."+name) and c.getAttr(fit+"."+name))
        return FaceCageInput(meshes[0],heads[0],self.original_face_production_skin(meshes[0],heads[0]),
            float(c.getAttr(fit+".faceScale")),option("MultiSkinClusters"),option("SimplerEyeLid"),
            bool(above),bool(below),self.face_use_offset_parent_matrix())

    def create_original_face_cage(self,source,options):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        raw.setToolTo("selectSuperContext")
        self.remove_original_face_fit_animations()
        self.hide_original_face_controllers(True)
        if source is None:
            return None
        skin=self.add_original_face_multi_skin("Cage",source.geometry) if source.multi_skin_clusters else source.skin
        suggestion=self._cage_suggest_smooth_passes(source)
        smooth=options.smooth_passes if options.smooth_passes is not None else suggestion
        controls,joints=self._cage_projected_controls(source)
        self._cage_make_triangles(source)
        self._cage_bind_geometry(source,joints,skin)
        if source.has_below_eye: self._cage_nose_region()
        for node in c.listRelatives("OnFacecontrols",allDescendents=True,type="transform") or []:
            leaf=node.rsplit("|",1)[-1]
            if leaf.startswith("EyeBrow") and "Offset_" in leaf: c.setAttr(node+".visibility",False)
        raw.setAttr(self.scene_address(source.geometry)+".visibility",False)
        c.select(clear=True)
        self._transaction_changed=True
        return {"controls":(*controls,*(("NoseRegion_M",) if source.has_below_eye else ())),
                "joints":joints,"skin":skin,"smooth_passes":smooth}
