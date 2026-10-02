"""Native asFaceAttachEyeLashes transfer cages, MEL 42254–42393."""
from contextlib import nullcontext
from .maya_original_skin_history import bind_original_skin


class MayaFaceEyeLashesMixin:
    def attach_original_face_eye_lashes(self, source, selection=None, retain_cages=False):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        selection = tuple(selection if selection is not None else source["lashes"])
        if not selection:
            raise ValueError("EyeLashes 需要所选网格")
        cages = []
        count = 0  # MEL numLid lives across both the cage and influence loops.
        for side, factor in (("_R", 1), ("_L", -1)):
            if source["cyclops"] and side == "_R":
                continue
            for arc in ("upper", "lower"):
                for index in range(1, 99):
                    if not c.objExists(arc + "LidMain" + str(index) + side):
                        break
                    count = index
                cage = arc + "EyeLidCage" + side
                c.polyPlane(name=cage, width=1, height=1, subdivisionsX=count - 1,
                            subdivisionsY=1, axis=(0, 1, 0), createUVs=2, constructionHistory=True)
                cages.append(cage)
                joints = []
                for index in range(1, count + 1):
                    joint = arc + "LidMain" + str(index) + side
                    joints.append(joint)
                    position = self._lip_pos(joint)
                    for row in (index - 1, index - 1 + count):
                        c.xform(cage + f".vtx[{row}]", worldSpace=True, translation=position)
                    eye = self._lip_pos("FitEyeBall")
                    c.scale(4, 4, 4, cage + f".vtx[{index - 1 + count}]", relative=True,
                            pivot=(eye[0] * factor, eye[1], eye[2]))
                skin = arc + "EyeLidCageSC" + side
                bind_original_skin(c, (cage, *joints), skin, namespace=self.namespace)
                self._cage_copy_selected((source["geometry"],), (cage,))
                for index in range(count):
                    near = self.scene_address(cage) + f".vtx[{index}]"
                    far = self.scene_address(cage) + f".vtx[{index + count}]"
                    influences = raw.skinPercent(self.scene_address(skin), near, ignoreBelow=.001,
                                                 query=True, transform=None) or []
                    weights = raw.skinPercent(self.scene_address(skin), near, ignoreBelow=.001,
                                              query=True, value=True) or []
                    for influence, weight in zip(influences, weights):
                        raw.skinPercent(self.scene_address(skin), far, transformValue=((influence, weight),))
        production_skins = []
        primary = self.scene_address(source["skin"])
        last_skin = ""
        for geometry in selection:
            mesh = self.scene_address(geometry)
            for node in raw.listHistory(mesh) or []:
                if raw.nodeType(node) == "skinCluster":
                    last_skin = node
            # Original compares to the primary Face Skin, including when an
            # eyelash face selection lies on the main head mesh.
            if last_skin == primary:
                continue
            influences = []
            for side in ("_R", "_L"):
                for arc in ("upper", "lower"):
                    for index in range(1, 99):
                        if not c.objExists(arc + "LidMain" + str(index) + side):
                            break
                        count = index
                    influences.extend(self.scene_address(arc + "LidMain" + str(i) + side)
                                      for i in range(1, count + 1))
            if source["multi"]:
                with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
                    added = raw.skinCluster([mesh, *influences], multi=True, frontOfChain=True,
                                            toSelectedBones=True, name=self.scene_address("EyeLidSC"))[0]
                production_skins.append(added)
            else:
                raw.skinCluster(last_skin, edit=True, dropoffRate=4, addInfluence=influences)
            if not source["game"]:
                raw.setAttr(last_skin + ".skinningMethod", 1)
        for geometry in selection:
            self._cage_copy_selected(tuple(cages), (geometry,))
        if not retain_cages:
            c.delete(cages)
        raw.select(tuple(self.scene_address(item) for item in selection), replace=True)
        return tuple(production_skins)
