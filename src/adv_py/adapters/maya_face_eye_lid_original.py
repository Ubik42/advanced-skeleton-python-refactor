"""Source-ordered asFaceEyeLid assembly, MEL 32933–34122.

The legacy Eyes Only builder remains separate. This entry builds the original
curve/joint/skin mechanism from the prepared Face hierarchy and Fit curves.
"""
from .maya_face_eye_lid_prep import MayaFaceEyeLidPrepMixin
from .maya_face_eye_lid_curves import MayaFaceEyeLidCurvesMixin
from .maya_face_eye_lid_drivers import MayaFaceEyeLidDriversMixin
from .maya_face_eye_lid_weights import MayaFaceEyeLidWeightsMixin
from .maya_face_eye_lashes import MayaFaceEyeLashesMixin


class MayaFaceEyeLidOriginalMixin(MayaFaceEyeLidPrepMixin, MayaFaceEyeLidCurvesMixin,
                                  MayaFaceEyeLidDriversMixin, MayaFaceEyeLidWeightsMixin,
                                  MayaFaceEyeLashesMixin):
    def create_original_face_eye_lid(self, source):
        self._require_transaction()
        c = self._cmds
        self.prepare_original_eye_lid(source)
        controls = list(self.create_original_eye_lid_curve_graph(source))
        if source["socket"]:
            controls.extend(("EyeSocket_R", "EyeSocket_L"))
        self.create_original_eye_lid_fleshy_graph()
        self.create_original_eye_lid_driver_graph(source)
        self.assign_original_eye_lid_weights(source)
        production_skins = [source["skin"]]
        if source["multi"]:
            production_skins.append(source["lid_skin"])
        if source["lashes"]:
            production_skins.extend(self.attach_original_face_eye_lashes(source))
        if source["simpler"]:
            controls.extend(self.create_original_lid_cheek_raiser(source))
        for node in ("closestSampler", "TempPos"):
            if c.objExists(node):
                c.delete(node)
        if not source["cyclops"]:
            c.setAttr("FaceControlOrient.v", False)
            c.rename("FaceControlOrient", "FaceControlOrientEye")
            c.rename("FaceControlSuspended", "FaceControlOrient")
        if source["cyclops"]:
            for node in c.listRelatives("SideReverse_R", children=True, type="transform") or []:
                leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if "Lid" in leaf and leaf.endswith("_R"):
                    c.setAttr(node + ".overrideEnabled", True)
                    c.setAttr(node + ".overrideVisibility", False)
        c.select(clear=True)
        self._transaction_changed = True
        return {"controls": tuple(controls), "production_skins": tuple(production_skins),
                "skin": source["lid_skin"], "original_stage": "asFaceEyeLid"}
