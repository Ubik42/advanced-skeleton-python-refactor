"""asWmUVUpdate: cylindrical projection and compression of unused regions."""
import shlex
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFaceWrinkleUVMixin:
    def _original_wrinkle_geometry(self):
        c = self._cmds
        raw = getattr(c, "raw", c)
        faces = self.read_face_objects(FacePreRole.FACE)
        if len(faces) != 1:
            raise FitSkeletonValidationError("WrinkleMap 需要唯一 Face 网格")
        geometry = self._original_bs_physical_address(raw.ls(self.scene_address(faces[0]), long=True)[0])
        shapes = raw.listRelatives(geometry, shapes=True, noIntermediate=True, fullPath=True) or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一可见 Shape")
        return geometry, shapes[0]

    def _original_wrinkle_fit_selection(self, section, geometry=None):
        c = self._cmds
        raw = getattr(c, "raw", c)
        holder = "FaceFit" + section.removesuffix("_R")
        if not c.objExists(holder + ".selection"):
            raise FitSkeletonValidationError("Wrinkle UV 缺少 Fit 选择记录：" + holder)
        items = shlex.split(c.getAttr(holder + ".selection") or "")
        if geometry:
            items = [geometry + "." + item.split(".", 1)[1] for item in items]
        items = raw.ls(items, flatten=True, long=True) or []
        if not items:
            raise FitSkeletonValidationError("Wrinkle UV 的 Fit 选择记录为空：" + holder)
        return items

    def _original_wrinkle_selection_uvs(self, raw, items):
        converted = raw.polyListComponentConversion(items, toUV=True)
        return raw.ls(converted, flatten=True) or []

    def update_original_face_wrinkle_uv(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        building = c.objExists("asWrinkleMapBuilding")
        if not building and not c.objExists("WrinkleCurves"):
            raise FitSkeletonValidationError("请先创建 Wrinkle 曲线")
        geometry, original_shape = self._original_wrinkle_geometry()
        intermediate = [shape for shape in raw.listRelatives(geometry, shapes=True, fullPath=True) or []
                        if raw.getAttr(shape + ".intermediateObject")
                        and not raw.listConnections(shape + ".inMesh", source=True, destination=False)]
        if not intermediate:
            raise FitSkeletonValidationError("Failed to find intermediateShape")
        self._transaction_changed = True
        visible = c.getAttr("ForeHeadAreaMesh.v")
        c.setAttr("ForeHeadAreaMesh.v", 1)
        forehead_max = c.getAttr("ForeHeadAreaMesh.boundingBoxMax")[0]
        c.setAttr("ForeHeadAreaMesh.v", visible)
        geo = geometry
        if not building:
            self._original_bs_delete_existing(("tempUVObject",))
            geo = self.scene_address(c.duplicate(geometry, name="tempUVObject")[0])
            for shape in raw.listRelatives(geo, shapes=True, fullPath=True) or []:
                if raw.getAttr(shape + ".intermediateObject"):
                    raw.delete(shape)
            raw.polyUVSet(geo, rename=True, uvSet="uvFaceWrinkles", newUVSet="uvFaceWrinklesOld")
        mesh = raw.listRelatives(geo, shapes=True, noIntermediate=True, fullPath=True)[0]
        current = raw.polyUVSet(mesh, query=True, currentUVSet=True)[0]
        context = c._creation_namespace if hasattr(c, "_creation_namespace") else nullcontext
        with context():
            projection = raw.polyProjection(geo + ".f[0:99999]", constructionHistory=True,
                type="Cylindrical", insertBeforeDeformers=building, createNewMap=True,
                uvSetName="uvFaceWrinkles", smartFit=True)[0]
        projection = raw.rename(projection, self.scene_address("polyProjFaceWrinkles"))
        raw.setAttr(projection + ".projectionHorizontalSweep", 360)
        raw.polyUVSet(mesh, currentUVSet=True, uvSet="uvFaceWrinkles")
        if raw.polyUVSet(mesh, query=True, currentUVSet=True)[0] != "uvFaceWrinkles":
            raw.delete(projection)
            raw.polyUVSet(geo, create=True, uvSet="uvFaceWrinkles")
            raw.polyUVSet(mesh, currentUVSet=True, uvSet="uvFaceWrinkles")
            with context():
                projection = raw.polyProjection(geo + ".f[0:99999]", constructionHistory=True,
                    type="Cylindrical", insertBeforeDeformers=building, createNewMap=False,
                    uvSetName="uvFaceWrinkles", smartFit=True)[0]
            raw.setAttr(projection + ".projectionHorizontalSweep", 360)
            raw.bakePartialHistory(geo, prePostDeformers=True)
            if raw.polyUVSet(mesh, query=True, currentUVSet=True)[0] != "uvFaceWrinkles":
                raise FitSkeletonValidationError("UV assignment failed via polyProjection and polyUVSet")
        jaw = self._original_wrinkle_fit_selection("Jaw_R", None if building else geo)
        jaw_y = raw.xform(jaw[0], query=True, worldSpace=True, translation=True)[1]
        def above(height):
            raw.select(geo, replace=True)
            raw.polySelectConstraint(mode=3, type=1, dist=3, distbound=(height,999),
                                     distaxis=(0,1,0), distpoint=(0,0,0))
            raw.polySelectConstraint(mode=0)
            return raw.ls(selection=True, flatten=True, long=True) or []
        jaw_above = above(jaw_y)
        all_vertices = raw.ls(geo + ".vtx[*]", flatten=True, long=True) or []
        above_set = set(jaw_above)
        lower_uvs = self._original_wrinkle_selection_uvs(raw, [v for v in all_vertices if v not in above_set])
        if lower_uvs:
            raw.polyEditUV(lower_uvs, pivotU=0, pivotV=0, scaleU=1, scaleV=.01)
        forehead_above = above(forehead_max[1])
        upper_uvs = self._original_wrinkle_selection_uvs(raw, forehead_above)
        if upper_uvs:
            raw.polyEditUV(upper_uvs, pivotU=0, pivotV=1, scaleU=1, scaleV=.01)
        excluded = set(forehead_above)
        middle = self._original_wrinkle_selection_uvs(raw, [v for v in jaw_above if v not in excluded])
        raw.select(middle, replace=True)
        previous_tool = raw.currentCtx()
        raw.texLatticeDeformContext("texLatticeDeformCtx", edit=True, latticeRows=2,
                                   latticeColumns=2, envelope=1, useBoundingRect=True)
        raw.setToolTo("texLatticeDeformSuperContext")
        try:
            low = raw.getAttr("texLattice1.boundingBoxSup")[0][0]
            high = raw.getAttr("texLattice1.boundingBoxInf")[0][0]
        finally:
            raw.setToolTo(previous_tool)
        raw.polyEditUV(middle, uValue=0, vValue=.5-(low+high)/2)
        raw.polyEditUV(middle, pivotU=.5, pivotV=.5, scaleU=1, scaleV=1/(high-low))
        forehead = self._original_wrinkle_fit_selection("ForeHead_R", None if building else geo)
        # MEL initializes min and nr to zero and retains the first selected component
        # if none crosses the negative X half-plane.
        nearest = forehead[0]
        minimum = 0.0
        for component in forehead:
            x = raw.xform(component, query=True, worldSpace=True, translation=True)[0]
            if x < minimum:
                minimum, nearest = x, component
        boundary = raw.polyEditUV(self._original_wrinkle_selection_uvs(raw, [nearest]), query=True)[0]
        count = int(raw.polyEvaluate(geo, uvcoord=True))
        left = [geo + ".map["+str(i)+"]" for i in range(count)
                if raw.polyEditUV(geo+".map["+str(i)+"]", query=True)[0] < boundary]
        if left:
            raw.polyEditUV(left, pivotU=0, pivotV=.5, scaleU=.01, scaleV=1)
        right = [geo + ".map["+str(i)+"]" for i in range(count)
                 if raw.polyEditUV(geo+".map["+str(i)+"]", query=True)[0] > 1-boundary]
        if right:
            raw.polyEditUV(right, pivotU=1, pivotV=.5, scaleU=.01, scaleV=1)
        middle = [geo + ".map["+str(i)+"]" for i in range(count)
                  if .1 < raw.polyEditUV(geo+".map["+str(i)+"]", query=True)[0] < .9]
        if middle:
            raw.polyEditUV(middle, pivotU=.5, pivotV=.5, scaleU=.5/(.5-boundary), scaleV=1)
        raw.polyUVSet(mesh, currentUVSet=True, uvSet=current)
        updated = 0
        if not building:
            raw.polyUVSet(geo, currentUVSet=True, uvSet="uvFaceWrinkles")
            raw.polyUVSet(geometry, currentUVSet=True, uvSet="uvFaceWrinkles")
            for index in range(count):
                uv = raw.polyEditUV(geo+".map["+str(index)+"]", query=True)
                if uv[0] < .1 or uv[0] > .9 or uv[1] < .1 or uv[1] > .9:
                    continue
                component = geometry+".map["+str(index)+"]"
                if uv != raw.polyEditUV(component, query=True):
                    raw.polyEditUV(component, relative=False, uValue=uv[0], vValue=uv[1])
                    updated += 1
            raw.delete(geo)
        raw.select(clear=True)
        return {"uv_count":count, "updated":updated, "building":building}
