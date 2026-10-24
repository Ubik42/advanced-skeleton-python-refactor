"""Maya scene storage for the original Face / Pre mask and geometry rows."""
from __future__ import annotations

import json
from contextlib import nullcontext
import re

from adv_py.application.face_pre import EyeLidLayer, OptionalEyeLidLayer, FacePreRole, FaceSide
from adv_py.core.face_eyelid_fit import (
    EyeLidLoop, eye_lid_area_faces, order_eye_lid_loop)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face import MayaFaceHost
from .maya_original_eye_ball_fit import MayaOriginalEyeBallFitMixin
from .maya_original_face_fit_display import MayaOriginalFaceFitDisplayMixin
from .maya_original_face_fit_area import MayaOriginalFaceFitAreaMixin
from .maya_original_face_fit_assist import MayaOriginalFaceFitAssistMixin
from .maya_original_face_inputs import MayaOriginalFaceInputsMixin
from .maya_original_face_fit_tube import create_original_face_fit_tube
from .maya_original_face_options import MayaOriginalFaceOptionsMixin


_FACE_PATTERN = re.compile(r"^(?P<mesh>.+)\.f\[(?P<index>\d+)\]$")
_EDGE_PATTERN = re.compile(r"^(?P<mesh>.+)\.e\[(?P<index>\d+)\]$")
_VERTEX_PATTERN = re.compile(r"^(?P<mesh>.+)\.vtx\[(?P<index>\d+)\]$")


class MayaFacePreHost(MayaOriginalFaceOptionsMixin, MayaOriginalFaceInputsMixin, MayaOriginalFaceFitAssistMixin, MayaOriginalFaceFitAreaMixin, MayaOriginalFaceFitDisplayMixin, MayaOriginalEyeBallFitMixin, MayaFaceHost):
    def set_original_face_skin_input(self, value: str) -> None:
        """Persist native editable asFaceSkinClusterTextField (MEL 1709)."""
        if not isinstance(value, str):
            raise TypeError("Face SkinCluster 输入必须为文字")
        c = self._cmds
        fit = self._fit(required=True)
        with self.transaction("记录 Face SkinCluster 输入"):
            self._transaction_changed = True
            if not c.objExists(fit + ".SkinCluster"):
                c.addAttr(fit, longName="SkinCluster", dataType="string")
            c.setAttr(fit + ".SkinCluster", value, type="string")

    def check_original_face_fit_upgrade(self):
        # Pre hosts deliberately do not inherit all Face build mixins. Join
        # the existing port lazily, sharing namespace and transaction state.
        from .maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_original_build import UpgradeOriginalFaceFit
        joined = MayaOriginalFaceBuildHost.__new__(MayaOriginalFaceBuildHost)
        joined.__dict__ = self.__dict__
        return UpgradeOriginalFaceFit(joined).apply()

    def _fit(self, *, required=False):
        matches = self._cmds.ls("FaceFitSkeleton", long=True,
                                type="transform") or []
        if len(matches) > 1 or (required and len(matches) != 1):
            raise FitSkeletonValidationError("FaceFitSkeleton 缺失或不唯一；先记录 Mask")
        return matches[0] if matches else None

    def face_skin_cluster(self, mesh):
        """Find the Skin deforming this mesh, excluding upstream lattice Skin."""
        c = self._cmds
        shapes = c.listRelatives(mesh,shapes=True,noIntermediate=True,
                                 fullPath=True,type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一可见 Shape")
        mesh_ids = set(c.ls((mesh,shapes[0]),uuid=True) or [])
        skins = []
        for node in dict.fromkeys(c.listHistory(shapes[0],pruneDagObjects=True) or []):
            if c.nodeType(node) != "skinCluster": continue
            geometry = c.skinCluster(node,query=True,geometry=True) or []
            geometry_ids = set(c.ls(geometry,uuid=True) or []) if geometry else set()
            if mesh_ids & geometry_ids:
                skins.append(node)
        if len(skins) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一直接蒙皮 Skin")
        return skins[0]

    def active_face_side(self) -> FaceSide:
        fit = self._fit(required=True)
        c = self._cmds
        if (c.attributeQuery("NonSym", node=fit, exists=True)
                and c.attributeQuery("NonSymSide", node=fit, exists=True)
                and c.getAttr(fit + ".NonSymSide") == "Left"):
            return FaceSide.LEFT
        return FaceSide.RIGHT

    def set_face_fit_side(self, side: FaceSide) -> FaceSide:
        if not isinstance(side, FaceSide):
            raise ValueError("Face Fit 编辑侧别无效")
        c = self._cmds
        fit = self._fit(required=True)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能切换引用中的 FaceFitSkeleton")
        with self.transaction("切换 Face Fit 编辑侧"):
            self._transaction_changed = True
            if not c.attributeQuery("NonSym", node=fit, exists=True):
                c.addAttr(fit, longName="NonSym", attributeType="bool")
            if not c.attributeQuery("NonSymSide", node=fit, exists=True):
                c.addAttr(fit, longName="NonSymSide", dataType="string")
            self.switch_original_face_fit_side(1 if side is FaceSide.RIGHT else 0)
        return self.active_face_side()

    def selected_mask(self):
        c = self._cmds
        selected = c.ls(selection=True, flatten=True, long=True) or []
        parsed = [_FACE_PATTERN.fullmatch(item) for item in selected]
        if not parsed or any(item is None for item in parsed):
            raise FitSkeletonValidationError("Mask 只接受所选面部多边形面")
        meshes = {item.group("mesh") for item in parsed}
        if len(meshes) != 1:
            raise FitSkeletonValidationError("Mask 的所有面必须来自同一件网格")
        mesh = next(iter(meshes))
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Mask 网格需要唯一可见多边形 Shape")
        indices = tuple(sorted({int(item.group("index")) for item in parsed}))
        count = int(c.polyEvaluate(mesh, face=True))
        if not indices or indices[-1] >= count:
            raise FitSkeletonValidationError("Mask 面索引已超出网格拓扑")
        bounds = tuple(float(value) for value in c.exactWorldBoundingBox(*selected))
        if len(bounds) != 6:
            raise FitSkeletonValidationError("Mask 包围盒无效")
        return mesh, indices, bounds

    def prepare_original_face_mask(self):
        """Native up-axis, units and build-pose gates, MEL 29045–29080."""
        self._require_transaction()
        c=self._cmds
        raw=getattr(c,'raw',c)
        if str(raw.upAxis(query=True,axis=True)).lower()=='z':
            raw.confirmDialog(title='Z up',
                message='Z-up axis detected.\nTo add FaceSetup,\nFirst go to the Preparation>Rig section, and turn OFF "Z up Axis".\nOnce the FaceSetup is complete you can turn back ON "Z up Axis".',
                button=['OK'],defaultButton='OK')
            return False
        selected=raw.ls(selection=True) or []
        if not selected or '.f' not in selected[0]:
            raise FitSkeletonValidationError('No poly-faces selected, The polygons of the characters`s face must be selected.')
        unit=raw.currentUnit(query=True,linear=True,fullName=True)
        if unit!='centimeter':
            message='Units currently set to: "'+unit+'"\nAdvancedSkeleton FaceSetup requires "cm".\nClick OK to switch'
            if raw.confirmDialog(title='Confirm',message=message,
                    button=['Ok','Cancel'],defaultButton='Ok')!='Ok':
                raise FitSkeletonValidationError('Unable to continue, AdvancedSkeleton FaceSetup requires "cm" as the WorkingUnit')
            raw.currentUnit(linear='cm')
            self._transaction_changed=True
        return bool(self.confirm_original_control_build_pose())

    def _read_mask_payload(self):
        fit = self._fit(required=True)
        c=self._cmds
        if c.objExists(fit+'.Mask'):
            # Native saved scenes carry Mask, not the supplemental Python JSON.
            tokens=(c.getAttr(fit+'.Mask') or '').split()
            components=c.ls(tokens,long=True,flatten=True) or [] if tokens else []
            parsed=[_FACE_PATTERN.fullmatch(item) for item in components]
            if not parsed or any(item is None for item in parsed):
                raise FitSkeletonValidationError('原版 Mask 组件记录为空或已失效')
            meshes={item.group('mesh') for item in parsed}
            if len(meshes)!=1:
                raise FitSkeletonValidationError('Mask 组件必须来自同一件网格')
            mesh=next(iter(meshes))
            value={'mesh':mesh,'faces':[int(item.group('index')) for item in parsed],
                   'faceCount':int(c.polyEvaluate(mesh,face=True))}
        elif c.attributeQuery("advPyMaskFaces", node=fit, exists=True):
            value = json.loads(c.getAttr(fit + ".advPyMaskFaces"))
        else:
            raise FitSkeletonValidationError("FaceFitSkeleton 尚未记录 Mask")
        if (not isinstance(value, dict) or not isinstance(value.get("mesh"), str)
                or not isinstance(value.get("faces"), list)):
            raise FitSkeletonValidationError("Mask 记录无效")
        return fit, value

    def read_face_mask(self):
        fit, data = self._read_mask_payload()
        mesh = data["mesh"]
        matches = self._cmds.ls(mesh, long=True, type="transform") or []
        if matches != [mesh]:
            raise FitSkeletonValidationError("Mask 网格已缺失或路径改变")
        count = int(self._cmds.polyEvaluate(mesh, face=True))
        indices = tuple(data["faces"])
        if (count != data.get("faceCount") or not indices
                or any(type(index) is not int or index < 0 or index >= count
                       for index in indices)):
            raise FitSkeletonValidationError("Mask 网格拓扑已改变")
        scale = float(self._cmds.getAttr(fit + ".faceScale"))
        return mesh, indices, scale

    def store_face_mask(self, mesh, faces, bounds):
        c = self._cmds
        if str(c.upAxis(query=True, axis=True)).lower() != "y":
            raise FitSkeletonValidationError("原版 Face Mask 要求 Y-up 场景")
        if str(c.currentUnit(query=True, linear=True)).lower() != "cm":
            raise FitSkeletonValidationError("Face Mask 要求厘米场景单位")
        fit = self._fit()
        if fit and c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能改写引用中的 FaceFitSkeleton")
        upgrading = bool(fit and c.objExists(fit + ".advPyFitUpgradePending") and c.getAttr(fit + ".advPyFitUpgradePending"))
        for name in ("FaceGroup", "FaceFitSkeleton"):
            matches = c.ls(name, long=True) or []
            if len(matches) > 1 or any(c.nodeType(path) != "transform"
                                      for path in matches):
                raise FitSkeletonValidationError("Face 引导节点名称已冲突：" + name)
        height = bounds[4] - bounds[1]
        payload = json.dumps({"mesh": mesh, "faces": list(faces),
                              "faceCount": int(c.polyEvaluate(mesh, face=True))},
                             separators=(",", ":"))
        with (nullcontext() if self._transaction_active else
              self.transaction("记录 Face Mask 并建立 Fit 范围")):
            self._transaction_changed = True
            if not fit:
                fit = self.ensure_original_face_fit_container()
            from adv_py.application.model_check import ReviewModelCheck
            from .maya_model_checker import MayaModelCheckHost
            raw=getattr(c,'raw',c)
            raw.select(self.scene_address(mesh),replace=True)
            options = getattr(self, '_face_input_options', None)
            if options is None:
                options = getattr(self, '_auto_face_options', None)
            if options is None:
                options = self.read_original_face_options() or {}
            ReviewModelCheck(MayaModelCheckHost()).execute(skip_symmetry=True,
                game_engine=options.get('GameEngine', False))
            raw.select(clear=True)
            for shape in c.listRelatives(fit, shapes=True, fullPath=True) or []:
                c.delete(shape)
            self._create_original_face_mask_guides(fit,bounds)
            if not c.attributeQuery("faceScale", node=fit, exists=True):
                c.addAttr(fit, longName="faceScale", attributeType="double")
            c.setAttr(fit + ".faceScale", height)
            if not c.attributeQuery("advPyMaskFaces", node=fit, exists=True):
                c.addAttr(fit, longName="advPyMaskFaces", dataType="string")
            c.setAttr(fit + ".advPyMaskFaces", payload, type="string")
            if not c.objExists(fit+'.Mask'):
                c.addAttr(fit,longName='Mask',dataType='string')
            c.setAttr(fit+'.Mask',' '.join(self.scene_address(mesh)+f'.f[{index}]'
                for index in faces),type='string')
            if upgrading:
                c.setAttr(fit + ".advPyFitUpgradePending", False)
            # Native leaves the authored polygon mask selected after shaping
            # the four guides; it does not clear Face/AllHead input strings.
            c.select([mesh+f'.f[{index}]' for index in faces],replace=True)

    def _create_original_face_mask_guides(self,fit,bounds):
        """Source circle/three hierarchy duplicates, MEL 29096–29131."""
        self._require_transaction()
        c=self._cmds
        c.select(clear=True)
        circle=c.circle(name='TempCircle',center=(0,0,0),normal=(0,1,0),
            sweep=360,radius=.5,degree=3,useTolerance=False,
            tolerance=.000393701,sections=8,constructionHistory=False)[0]
        shape=c.listRelatives(circle,shapes=True)[0]
        c.parent(shape,fit,add=True,shape=True)
        c.delete(circle)
        shape=c.rename(shape,'FaceFitSkeletonShape')
        c.setAttr(shape+'.overrideEnabled',1)
        c.setAttr(shape+'.overrideColor',13)
        c.rotate(0,-90,0,fit+'.cv[0:99]',relative=True,
                 objectSpace=True,pivot=(0,0,0))
        # Native duplicates the Fit hierarchy and instances each new root
        # shape back onto FaceFitSkeleton before removing the duplicate roots.
        duplicates=[c.duplicate(fit,name=name)[0] for name in (
            'FaceFitSkeletonHeight','FaceFitSkeletonCircle','FaceFitSkeletonHeightCircle')]
        for duplicate in duplicates:
            duplicate_shape=c.listRelatives(duplicate,shapes=True)[0]
            c.parent(duplicate_shape,fit,add=True,shape=True)
        c.delete(duplicates)
        c.move(0,1,0,'FaceFitSkeletonHeightShape.cv[0:99]',
            'FaceFitSkeletonHeightCircleShape.cv[0:99]',relative=True,objectSpace=True)
        width,height,depth=(bounds[index+3]-bounds[index] for index in range(3))
        for shape in c.listRelatives(fit,shapes=True) or []:
            cvs=shape+'.cv[0:99]'
            c.scale(width,height,depth,cvs,relative=True,pivot=(0,0,0))
            c.move(0,bounds[1],(bounds[2]+bounds[5])/2,cvs,
                relative=True,objectSpace=True,worldSpaceDistance=True)

    def selected_face_meshes(self):
        return self.selected_original_face_geometry()

    def validate_original_all_head_selection(self):
        # Native checks the original selection before adding descendants.
        # An empty Face field permits recording All Head first.
        faces=self.read_face_objects(FacePreRole.FACE)
        if faces and (len(faces)!=1 or faces[0] not in
                      (self._cmds.ls(selection=True,long=True) or [])):
            raise FitSkeletonValidationError('All Head 必须直接选中已记录的 Face 对象')

    def read_face_objects(self, role: FacePreRole):
        fit = self._fit(required=True)
        if not self._cmds.attributeQuery(role.value, node=fit, exists=True):
            return ()
        names = tuple((self._cmds.getAttr(fit + "." + role.value) or "").split())
        resolved = []
        for name in names:
            matches = self._cmds.ls(name, long=True, type="transform") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("Face Pre 网格已缺失或不唯一：" + name)
            resolved.append(matches[0])
        return tuple(resolved)

    def select_face_mask(self):
        mesh, faces, _ = self.read_face_mask()
        self._cmds.select([f"{mesh}.f[{index}]" for index in faces],
                          replace=True)
        return len(faces)

    def select_face_objects(self, role: FacePreRole):
        meshes = self.read_face_objects(role)
        if not meshes:
            raise FitSkeletonValidationError("Face Pre 尚未记录 " + role.value)
        self._cmds.select(meshes, replace=True)
        return meshes

    def store_face_objects(self, role: FacePreRole, meshes, head_joint):
        c = self._cmds
        fit = self._fit(required=True)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能改写引用中的 FaceFitSkeleton")
        names = tuple(mesh.rsplit("|", 1)[-1] for mesh in meshes)
        if any((c.ls(name, long=True, type="transform") or []) != [mesh]
               for name, mesh in zip(names, meshes)):
            raise FitSkeletonValidationError("Face 网格短名在场景内不唯一")
        with (nullcontext() if self._transaction_active else
              self.transaction("记录 Face Pre " + role.value)):
            skins=self.ensure_original_face_input_skins(meshes,head_joint or 'Head_M')
            if skins is None:
                return False
            self._transaction_changed = True
            if not c.attributeQuery(role.value, node=fit, exists=True):
                c.addAttr(fit, longName=role.value, dataType="string")
            c.setAttr(fit + "." + role.value, " ".join(names), type="string")
            if role is FacePreRole.FACE:
                missing_head = not c.attributeQuery("HeadJoint", node=fit, exists=True)
                if missing_head:
                    c.addAttr(fit, longName="HeadJoint", dataType="string")
                # asChooseInput resets the Face row's Head field to its local
                # default even when this mesh already has Skin. AutoFit then
                # selects the profile's actual Head joint as a separate step.
                c.setAttr(fit + ".HeadJoint",head_joint or 'Head_M',type="string")
                if not c.objExists(fit+'.SkinCluster'):
                    c.addAttr(fit,longName='SkinCluster',dataType='string')
                c.setAttr(fit+'.SkinCluster',skins[-1] if skins else '',type='string')
        return meshes

    def create_eye_ball_fit(self, eye_mesh: str, head_joint: str,
                            side: FaceSide = FaceSide.RIGHT) -> str | None:
        # Keep the public Python entry while dispatching native ADV behavior.
        c = self._cmds
        fit = self._fit(required=True)
        attribute = 'LeftEye' if side is FaceSide.LEFT else 'RightEye'
        with (nullcontext() if self._transaction_active else
              self.transaction('Build FitEyeBall')):
            tokens=tuple(c.ls(eye_mesh.split(),long=True,flatten=True) or [])
            tokens=self.original_face_geometry(tokens,allow_components=True)
            if not tokens:
                raise FitSkeletonValidationError('Eye 输入的对象或组件不存在')
            eye_mesh=' '.join(self.scene_address(token) for token in tokens)
            saved=(c.getAttr(fit+'.'+attribute) or '').split() if c.objExists(fit+'.'+attribute) else []
            saved_tokens=tuple(c.ls(saved,long=True,flatten=True) or []) if saved else ()
            if saved_tokens!=tokens:
                # An explicit API input can perform the preceding Choose
                # Input step. A saved Pre input must not run it a second time
                # when the user presses the native EyeBall Fit button.
                if self.ensure_original_face_input_skins(tokens,head_joint or 'Head_M') is None:
                    return None
                self.mark_original_non_spherical_eye_lattice(tokens,
                    'L' if side is FaceSide.LEFT else 'R')
            self._transaction_changed=True
            if not c.objExists(fit + '.' + attribute):
                c.addAttr(fit, longName=attribute, dataType='string')
            c.setAttr(fit + '.' + attribute, eye_mesh, type='string')
            if not c.objExists(fit + '.HeadJoint'):
                c.addAttr(fit,longName='HeadJoint',dataType='string')
            c.setAttr(fit+'.HeadJoint',head_joint,type='string')
            return self.create_original_eye_ball_fit(eye_mesh, head_joint, side)

    def read_eye_ball_fit(self, side: FaceSide | None = None) -> str:
        c = self._cmds
        fit = self._fit(required=True)
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        matches = c.ls("FitEyeBall" + suffix, long=True,
                       type="transform") or []
        if len(matches) != 1 or not matches[0].startswith(fit + "|"):
            raise FitSkeletonValidationError("EyeBall Fit 缺失或父级无效")
        locator = matches[0]
        if not c.ls(locator + "|FitEyeSphere" + suffix, long=True,
                    type="transform"):
            raise FitSkeletonValidationError("EyeBall Fit 的球体预览缺失")
        return locator

    def eye_ball_fit_center_y(self) -> float:
        return float(self._cmds.xform(self.read_eye_ball_fit(), query=True,
                                      worldSpace=True, translation=True)[1])

    def selected_eye_lid_edges(self):
        from maya.api import OpenMaya as om

        c = self._cmds
        selected = c.ls(selection=True, flatten=True, long=True) or []
        edge_matches = [_EDGE_PATTERN.fullmatch(item) for item in selected]
        corner_matches = [_VERTEX_PATTERN.fullmatch(item) for item in selected]
        if (not selected or not any(edge_matches)
                or any(edge is None and corner is None
                       for edge, corner in zip(edge_matches, corner_matches))):
            raise FitSkeletonValidationError("EyeLid Fit 需要闭合边环，可加选一至两个眼角顶点")
        meshes = {match.group("mesh") for match in edge_matches + corner_matches
                  if match is not None}
        if len(meshes) != 1:
            raise FitSkeletonValidationError("EyeLid Fit 只接受同一网格的边和顶点")
        mesh = next(iter(meshes))
        if self.read_face_objects(FacePreRole.FACE) != (mesh,):
            raise FitSkeletonValidationError("眼睑边必须属于 Face 网格")
        indices = tuple(sorted({int(match.group("index")) for match in edge_matches
                                if match is not None}))
        corners = tuple(int(match.group("index")) for match in corner_matches
                        if match is not None)
        if len(set(corners)) != len(corners):
            raise FitSkeletonValidationError("EyeLid Fit 眼角顶点重复")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        if not indices or indices[-1] >= mesh_fn.numEdges:
            raise FitSkeletonValidationError("眼睑边索引已超出网格拓扑")
        edges = tuple((index, *mesh_fn.getEdgeVertices(index))
                      for index in indices)
        vertices = {vertex for _, first, second in edges
                    for vertex in (first, second)}
        positions = {vertex: (float(point.x), float(point.y), float(point.z))
                     for vertex in vertices
                     for point in (mesh_fn.getPoint(vertex, om.MSpace.kWorld),)}
        return mesh, edges, positions, corners

    def original_eye_lid_fit_cyclops(self):
        c = self._cmds
        fit = self._fit(required=True)
        return bool(c.objExists(fit + '.Cyclops') and c.getAttr(fit + '.Cyclops'))

    def create_eye_lid_fit(self, layer: EyeLidLayer, mesh: str,
                           loop: EyeLidLoop, positions,
                           edges, selected_corners, *,native_main2_part=False) -> tuple[str, str]:
        c = self._cmds
        fit = self._fit(required=True)
        side = self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        if self.read_face_objects(FacePreRole.FACE) != (mesh,):
            raise FitSkeletonValidationError("眼睑边与 Face 网格不一致")
        if layer is EyeLidLayer.INNER:
            self.read_eye_lid_fit(EyeLidLayer.OUTER)
            self.read_eye_lid_fit(EyeLidLayer.MAIN)
        part = layer.value
        holder_name = "FaceFitEyeLid" + part + suffix
        geo_name = "FaceFitEyeLid" + part + "Geo" + suffix
        curve_parent_name = "FaceFitEyeLid" + part + "Curve" + suffix
        loc_name = "FaceFitEyeLid" + part + "Loc" + suffix
        curve_names = ("upperEyeLid" + part + "Curve" + suffix,
                       "lowerEyeLid" + part + "Curve" + suffix)
        names = (holder_name, geo_name, curve_parent_name,
                 loc_name, *curve_names)
        if layer is EyeLidLayer.INNER:
            names += ("EyeLidInnerAreaMesh" + suffix,
                      "EyeLidInnerAreaMeshExtrude" + suffix)
        if any(c.ls(name, long=True) for name in names):
            raise FitSkeletonValidationError("眼睑 Fit 节点名称已占用：" + part)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用的 FaceFitSkeleton 下建立眼睑")
        selected = c.ls(selection=True, long=True) or []
        with (nullcontext() if self._transaction_active else
              self.transaction("建立 EyeLid " + part + " Fit")):
            self._transaction_changed = True
            holder = c.createNode("transform", name=holder_name, parent=fit)
            geo_holder = c.createNode("transform", name=geo_name,
                                      parent=holder)
            curve_holder = c.createNode("transform", name=curve_parent_name,
                                        parent=holder)
            c.createNode("transform", name=loc_name, parent=holder)
            paths = []
            for name, vertices in zip(curve_names,
                                      (loop.upper_vertices, loop.lower_vertices)):
                points = [positions[index] for index in vertices]
                curve = c.curve(name=name, degree=1, point=points)
                curve = c.parent(curve, curve_holder, absolute=True)[0]
                c.makeIdentity(holder,apply=True,translate=True,rotate=True,scale=True)
                shape = (c.listRelatives(curve, shapes=True,
                                         fullPath=True) or [None])[0]
                c.rename(shape, name + 'Shape')
                shape = c.listRelatives(curve, shapes=True, fullPath=True)[0]
                c.setAttr(shape + ".overrideEnabled", True)
                c.setAttr(shape + ".overrideColor", {
                    EyeLidLayer.OUTER: 14, EyeLidLayer.MAIN: 13,
                    EyeLidLayer.INNER: 15, OptionalEyeLidLayer.MAIN2: 17}[layer])
                paths.append((c.ls(curve, long=True,
                                    type="transform") or [curve])[0])
            scale = float(c.getAttr(fit + ".faceScale"))
            from .maya_face_base import MayaFaceBaseMixin
            MayaFaceBaseMixin.ensure_face_fit_shaders(self)
            for name, curve in zip(("upper", "lower"), paths):
                create_original_face_fit_tube(self,
                    'EyeLidMain2' if layer is OptionalEyeLidLayer.MAIN2 and not native_main2_part else 'EyeLid',
                    '' if layer is OptionalEyeLidLayer.MAIN2 and not native_main2_part else part,suffix,name,scale,
                    None if native_main2_part else ('asGreenSG' if name=='upper' else 'asGreen2SG'))
            if layer is EyeLidLayer.INNER:
                self.create_original_face_fit_inner_area('EyeLid', suffix, mesh,
                    geo_holder, float(c.getAttr(fit + '.faceScale')), selected)
            c.addAttr(holder, longName="selection", dataType="string")
            c.setAttr(holder + ".selection", " ".join(
                [f"{mesh}.e[{index}]" for index in loop.edge_ids]
                + [f"{mesh}.vtx[{index}]" for index in selected_corners]),
                type="string")
            c.addAttr(holder, longName="advPyFaceCount", attributeType="long")
            c.setAttr(holder + ".advPyFaceCount",
                      int(c.polyEvaluate(mesh, face=True)))
            c.addAttr(holder, longName="advPyEdgeVertices", dataType="string")
            c.setAttr(holder + ".advPyEdgeVertices", json.dumps(
                [(index, *sorted((first, second)))
                 for index, first, second in sorted(edges)],
                separators=(",", ":")), type="string")
            c.select(holder, replace=True)
        return tuple(paths)

    def mirror_right_eye_fit_to_left(self, left_eye_mesh: str) -> dict:
        """Build left EyeBall and eyelid Fit on a symmetric Face mesh."""
        from maya.api import OpenMaya as om

        c = self._cmds
        fit = self._fit(required=True)
        if (c.attributeQuery("NonSym", node=fit, exists=True)
                and c.getAttr(fit + ".NonSym")):
            raise FitSkeletonValidationError("非对称 Face Fit 应单独编辑左侧")
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能镜像引用中的 Face Fit")
        mesh = self.read_face_objects(FacePreRole.FACE)[0]
        self.read_eye_ball_fit(FaceSide.RIGHT)
        if c.ls("FaceFitEyeBallLeft", long=True):
            raise FitSkeletonValidationError("左侧 Face Fit 已存在")
        eye_meshes = c.ls(left_eye_mesh, long=True, type="transform") or []
        heads = c.ls(c.getAttr(fit + ".HeadJoint"), long=True,
                     type="joint") or []
        if len(eye_meshes) != 1 or len(heads) != 1:
            raise FitSkeletonValidationError("镜像眼睑需要唯一左眼网格和 Head 关节")
        shape = (c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [None])[0]
        selection = om.MSelectionList()
        selection.add(shape)
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        points = [tuple(float(mesh_fn.getPoint(index, om.MSpace.kWorld)[axis])
                        for axis in range(3))
                  for index in range(mesh_fn.numVertices)]
        edge_lookup = {tuple(sorted(mesh_fn.getEdgeVertices(index))): index
                       for index in range(mesh_fn.numEdges)}
        right_rows = {}
        vertices = set()
        for layer in EyeLidLayer:
            self.read_eye_lid_fit(layer, FaceSide.RIGHT)
            holder = (c.ls("FaceFitEyeLid" + layer.value,
                           long=True, type="transform") or [None])[0]
            if int(c.getAttr(holder + ".advPyFaceCount")) != mesh_fn.numPolygons:
                raise FitSkeletonValidationError("右侧眼睑 Fit 与 Face 面数不一致")
            record = (c.getAttr(holder + ".selection") or "").split()
            edges, corners = [], []
            for item in record:
                edge = _EDGE_PATTERN.fullmatch(item)
                corner = _VERTEX_PATTERN.fullmatch(item)
                if edge and edge.group("mesh") == mesh:
                    index = int(edge.group("index"))
                    if index >= mesh_fn.numEdges:
                        raise FitSkeletonValidationError("右侧眼睑边索引无效")
                    first, second = mesh_fn.getEdgeVertices(index)
                    edges.append((index, first, second))
                    vertices.update((first, second))
                elif corner and corner.group("mesh") == mesh:
                    index = int(corner.group("index"))
                    if index >= mesh_fn.numVertices:
                        raise FitSkeletonValidationError("右侧眼角顶点索引无效")
                    corners.append(index)
                    vertices.add(index)
                else:
                    raise FitSkeletonValidationError("右侧眼睑选择记录无效")
            expected = [tuple(row) for row in json.loads(
                c.getAttr(holder + ".advPyEdgeVertices"))]
            observed = [(index, *sorted((first, second)))
                        for index, first, second in sorted(edges)]
            if not edges or observed != expected:
                raise FitSkeletonValidationError("右侧眼睑边连接已改变")
            right_rows[layer] = (tuple(edges), tuple(corners))
        bounds = c.exactWorldBoundingBox(eye_meshes[0])
        if (bounds[0] + bounds[3]) / 2. <= 1e-6:
            raise FitSkeletonValidationError("所选左眼网格必须位于正 X 侧")
        diameter = max(bounds[index + 3] - bounds[index]
                       for index in range(3))
        tolerance = max(diameter * .05, 1e-4)
        candidates = [index for index, point in enumerate(points)
                      if point[0] > 1e-6]
        if not candidates:
            raise FitSkeletonValidationError("Face 网格缺少左侧顶点")
        mirrored = {}
        maximum_distance = 0.
        for vertex in sorted(vertices):
            source = points[vertex]
            if source[0] >= -1e-6:
                raise FitSkeletonValidationError("右侧眼睑 Fit 跨越对称中线")
            target = (-source[0], source[1], source[2])
            counterpart = min(candidates, key=lambda index:
                sum((points[index][axis] - target[axis]) ** 2
                    for axis in range(3)))
            distance_sq = sum((points[counterpart][axis] - target[axis]) ** 2
                              for axis in range(3))
            if distance_sq > tolerance * tolerance:
                raise FitSkeletonValidationError(
                    f"Face 网格左右眼睑顶点不对称：右顶点 {vertex} "
                    f"镜像距离 {distance_sq ** .5:.6f} cm，"
                    f"容差 {tolerance:.6f} cm")
            maximum_distance = max(maximum_distance, distance_sq ** .5)
            mirrored[vertex] = counterpart
        if len(set(mirrored.values())) != len(mirrored):
            raise FitSkeletonValidationError("镜像眼睑顶点映射不唯一")
        eye_y = (bounds[1] + bounds[4]) / 2.
        left_rows = {}
        for layer, (edges, corners) in right_rows.items():
            reflected = []
            for _, first, second in edges:
                left_first, left_second = mirrored[first], mirrored[second]
                edge_id = edge_lookup.get(tuple(sorted((left_first,
                                                        left_second))))
                if edge_id is None:
                    raise FitSkeletonValidationError("镜像侧缺少对应眼睑边")
                reflected.append((edge_id, left_first, left_second))
            left_corners = tuple(mirrored[index] for index in corners)
            left_positions = {index: points[index] for _, first, second in
                              reflected for index in (first, second)}
            loop = order_eye_lid_loop(tuple(reflected), left_positions,
                eye_center_y=eye_y, corner_vertices=left_corners,
                side=FaceSide.LEFT.value)
            left_rows[layer] = (loop, left_positions,
                                tuple(reflected), left_corners)
        selected = c.ls(selection=True, long=True) or []
        with (nullcontext() if self._transaction_active else
              self.transaction("从右侧镜像生成左侧眼睑 Fit")):
            self._transaction_changed = True
            if not c.attributeQuery("NonSymSide", node=fit, exists=True):
                c.addAttr(fit, longName="NonSymSide", dataType="string")
            c.setAttr(fit + ".NonSymSide", "Left", type="string")
            self.create_eye_ball_fit(eye_meshes[0], heads[0], FaceSide.LEFT)
            for layer in EyeLidLayer:
                self.create_eye_lid_fit(layer, mesh, *left_rows[layer])
            c.setAttr(fit + ".NonSymSide", "Right", type="string")
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return {"mapped_vertices": len(mirrored),
                "layers": tuple(layer.value for layer in EyeLidLayer),
                "maximum_distance_cm": maximum_distance,
                "tolerance_cm": tolerance}

    def _eye_lid_area_faces(self, mesh: str, inner_edges: tuple[int, ...],
                            side: FaceSide) -> tuple[int, ...]:
        from maya.api import OpenMaya as om

        c = self._cmds
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))

        def stored_edges(layer: EyeLidLayer) -> tuple[int, ...]:
            self.read_eye_lid_fit(layer, side)
            suffix = "Left" if side is FaceSide.LEFT else ""
            holder = (c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                           type="transform") or [None])[0]
            record = c.getAttr(holder + ".selection") or ""
            components = [_EDGE_PATTERN.fullmatch(item) for item in record.split()
                          if ".e[" in item]
            if (not components or any(match is None or
                    match.group("mesh") != mesh for match in components)
                    or int(c.getAttr(holder + ".advPyFaceCount"))
                       != mesh_fn.numPolygons):
                raise FitSkeletonValidationError("眼睑 " + layer.value
                                                + " 与当前 Face 拓扑不一致")
            expected = json.loads(c.getAttr(holder + ".advPyEdgeVertices"))
            indices = tuple(sorted(int(match.group("index"))
                                   for match in components))
            if (indices[-1] >= mesh_fn.numEdges or
                    [(index, *sorted(mesh_fn.getEdgeVertices(index)))
                     for index in indices] != [tuple(row) for row in expected]):
                raise FitSkeletonValidationError("眼睑 " + layer.value
                                                + " 边连接已改变")
            return indices

        outer = stored_edges(EyeLidLayer.OUTER)
        main = stored_edges(EyeLidLayer.MAIN)
        poly_it = om.MItMeshPolygon(selection.getDagPath(0))
        face_edges = []
        while not poly_it.isDone():
            face_edges.append(tuple(poly_it.getEdges()))
            poly_it.next()
        edge_it = om.MItMeshEdge(selection.getDagPath(0))
        edge_faces = []
        while not edge_it.isDone():
            edge_faces.append(tuple(edge_it.getConnectedFaces()))
            edge_it.next()
        return eye_lid_area_faces(face_edges, edge_faces,
                                  outer_edges=outer, main_edges=main,
                                  inner_edges=inner_edges)

    def read_eye_lid_area(self, side: FaceSide | None = None) -> tuple[str, str]:
        c = self._cmds
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        self.read_eye_lid_fit(EyeLidLayer.INNER, side)
        holder = (c.ls("FaceFitEyeLidInner" + suffix, long=True,
                       type="transform") or [None])[0]
        geo_holder = holder + "|FaceFitEyeLidInnerGeo" + suffix
        paths = tuple(geo_holder + "|" + name for name in
                      ("EyeLidInnerAreaMesh" + suffix,
                       "EyeLidInnerAreaMeshExtrude" + suffix))
        if any((c.ls(path, long=True, type="transform") or []) != [path]
               or not c.listRelatives(path, shapes=True, type="mesh")
               for path in paths):
            raise FitSkeletonValidationError("EyeLid Inner 区域网格缺失")
        return paths

    def read_eye_lid_fit(self, layer: EyeLidLayer,
                         side: FaceSide | None = None) -> tuple[str, str]:
        c = self._cmds
        fit = self._fit(required=True)
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        holder = c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                      type="transform") or []
        if len(holder) != 1 or not holder[0].startswith(fit + "|"):
            raise FitSkeletonValidationError("眼睑 Fit 缺失或父级无效：" + layer.value)
        curve_parent = holder[0] + "|FaceFitEyeLid" + layer.value \
                       + "Curve" + suffix
        paths = tuple(curve_parent + "|" + prefix + "EyeLid" + layer.value
                      + "Curve" + suffix for prefix in ("upper", "lower"))
        if any((c.ls(path, long=True, type="transform") or []) != [path]
               for path in paths):
            raise FitSkeletonValidationError("眼睑 Fit 曲线缺失：" + layer.value)
        return paths

    def select_eye_lid_fit(self, layer: EyeLidLayer) -> int:
        from maya.api import OpenMaya as om

        side = self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        self.read_eye_lid_fit(layer, side)
        c = self._cmds
        holder = (c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                       type="transform") or [None])[0]
        selected = tuple((c.getAttr(holder + ".selection") or "").split())
        edge_matches = [_EDGE_PATTERN.fullmatch(item) for item in selected]
        corner_matches = [_VERTEX_PATTERN.fullmatch(item) for item in selected]
        if (not any(edge_matches)
                or any(edge is None and corner is None
                       for edge, corner in zip(edge_matches, corner_matches))):
            raise FitSkeletonValidationError("眼睑边选择记录无效")
        mesh = next(match.group("mesh") for match in edge_matches
                    if match is not None)
        if (not c.objExists(mesh)
                or any(match.group("mesh") != mesh
                       for match in edge_matches + corner_matches
                       if match is not None)
                or int(c.polyEvaluate(mesh, face=True))
                    != int(c.getAttr(holder + ".advPyFaceCount"))):
            raise FitSkeletonValidationError("眼睑网格拓扑已改变")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("眼睑 Face 网格已缺失")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        expected = json.loads(c.getAttr(holder + ".advPyEdgeVertices"))
        indices = sorted(int(match.group("index")) for match in edge_matches
                         if match is not None)
        corners = tuple(int(match.group("index")) for match in corner_matches
                        if match is not None)
        if indices[-1] >= mesh_fn.numEdges or any(
                index >= mesh_fn.numVertices for index in corners):
            raise FitSkeletonValidationError("眼睑边索引已超出网格拓扑")
        observed = [(index, *sorted(mesh_fn.getEdgeVertices(index)))
                    for index in indices]
        if observed != [tuple(row) for row in expected]:
            raise FitSkeletonValidationError("眼睑边连接已改变，不能使用旧 Fit 选择")
        if any(vertex not in {item for _, first, second in observed
                              for item in (first, second)} for vertex in corners):
            raise FitSkeletonValidationError("眼角顶点已不在旧 Fit 边环上")
        c.select(selected, replace=True)
        return len(indices)
