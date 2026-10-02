"""Fit-derived PolyBoxes in the original Body / Geometry hierarchy."""
from __future__ import annotations

from math import dist
from contextlib import contextmanager
from dataclasses import replace

from adv_py.core.geometry_poly_boxes import PolyBoxSource, PolyBoxSpec
from .maya_skin_cage import MayaSkinCageHost


class MayaPolyBoxesHost(MayaSkinCageHost):
    @staticmethod
    def _leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @staticmethod
    def _holder_name(box_name: str) -> str:
        return box_name[:-2] + "ParentConstraint" + box_name[-2:]

    @contextmanager
    def transaction(self, label):
        from .maya_fit_geometry import MayaFitGeometryHost
        with super().transaction(label):
            with MayaFitGeometryHost(self.namespace).namespace_scope():
                yield

    def _fit_size(self, joint: str) -> tuple[float, float]:
        c = self.cmds
        def value(names: tuple[str, ...]) -> float:
            for attribute in names:
                if c.attributeQuery(attribute, node=joint, exists=True):
                    return float(c.getAttr(joint + "." + attribute))
            return 1.0

        fat = value(("fat",))
        front = (value(("fatFrontAbs",))
                 if c.attributeQuery("fatFrontAbs", node=joint,
                                     exists=True) else
                 fat * value(("fatFront", "fatY")))
        width = (value(("fatWidthAbs",))
                 if c.attributeQuery("fatWidthAbs", node=joint,
                                     exists=True) else
                 fat * value(("fatWidth", "fatZ")))
        return front, width

    def _fit_heel(self, joint: str, side: str):
        c = self.cmds
        for child in c.listRelatives(joint, children=True,
                                     type="joint", fullPath=True) or ():
            label = (str(c.getAttr(child + ".otherType") or "")
                     if c.getAttr(child + ".drawLabel")
                     and int(c.getAttr(child + ".type")) == 18 else "")
            if "Heel" not in label and "Heel" not in self._leaf(child):
                continue
            position = c.xform(child, query=True,
                               worldSpace=True, translation=True)
            return ((-1 if side == "_L" else 1) * float(position[0]),
                    float(position[1]), float(position[2]))
        return None

    def capture_sources(self) -> tuple[PolyBoxSource, ...]:
        from .maya_fit_geometry import MayaFitGeometryHost
        c=self.cmds
        preview=MayaFitGeometryHost(self.namespace)
        segments=preview.capture_fit_geometry(poly_boxes=True)
        fit=self._name('FitSkeleton')
        template=c.getAttr(fit+'.fitSkeletonTemplate') if c.objExists(fit+'.fitSkeletonTemplate') else ''
        biped=str(template).startswith('biped')
        max_y=max((node.world_position[1] for node in preview._fit_geometry_snapshot.hierarchy.joints),default=0.)
        scale=max(.01,max_y/17.176163) if max_y>0 else 1.
        sources=[]
        for segment in segments:
            joint=preview._physical(segment.joint);child=preview._physical(segment.child)
            start=tuple(c.xform(joint,q=True,ws=True,t=True));end=tuple(c.xform(child,q=True,ws=True,t=True))
            front,width=self._fit_size(joint);end_front,end_width=self._fit_size(child)
            for suffix in ('_M','_R','_L'):
                existing=[]
                for index in range(segment.parts):
                    x=start[0]+(end[0]-start[0])*index/segment.parts
                    side='_R' if x<-.01*scale else '_M'
                    if suffix not in ((side,'_L') if side=='_R' else (side,)):continue
                    driver=segment.stem+('Part'+str(index) if index else '')+suffix
                    if c.objExists(self._name(driver)):existing.append(driver)
                if not existing:continue
                # Selection follows asCreateFromFitGeometry: Body existence,
                # including noSkin joints, rather than DeformSet membership.
                sources.append(PolyBoxSource(segment.stem,suffix,segment.stem+suffix,
                    self._leaf(child)+suffix,start,end,front,width,end_front,end_width,
                    segment.parts,biped and ('Ankle' in segment.stem or 'Toes' in segment.stem),
                    self._fit_heel(joint,suffix) if 'Ankle' in segment.stem else None,
                    tuple(existing)))
        self._fit_geometry_segments=segments
        return tuple(sources)

    def preflight_create(self, plan: tuple[PolyBoxSpec, ...]) -> None:
        c = self.cmds
        for leaf in ("Geometry", "MainScaleMultiplyDivide"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("PolyBoxes 缺少角色节点：" + leaf)
        if self.exists():
            raise ValueError("PolyBoxes 已存在；请先删除旧盒体")
        for spec in plan:
            for leaf in (spec.name, self._holder_name(spec.name)):
                if c.objExists(self._name(leaf)):
                    raise ValueError("PolyBoxes 名称已占用：" + leaf)
            if not c.objExists(self._name(spec.driver)):
                raise ValueError("PolyBoxes 缺少 Body 驱动关节：" + spec.driver)

    def _create_box(self, spec: PolyBoxSpec, parent: str) -> None:
        c=self.cmds
        source=self._name(spec.name[:-2])
        box=c.duplicate(source,name=self._name(spec.name),returnRootsOnly=True)[0]
        c.editDisplayLayerMembers(self._name('PolyBoxes'),box,noRecurse=True)
        c.setAttr(box+'.visibility',1)
        mirror=c.createNode('transform',name=self._name('AdvPy_BoxMirror'))
        c.parent(box,mirror)
        if spec.name.endswith('_L'):
            c.setAttr(mirror+'.scaleX',-1)
            c.polyNormal(box,normalMode=0,userNormalMode=0,constructionHistory=False)
        c.parent(box,world=True);c.delete(mirror)
        holder=c.createNode('transform',name=self._name(self._holder_name(spec.name)),parent=parent)
        c.delete(c.parentConstraint(box,holder))
        # Reuse the faithful asParentConstraint branches inside the outer
        # Geometry transaction, without creating an independent Undo chunk.
        helper=self._geometry_constraint_host
        driver=c.ls(self._name(spec.driver),long=True)[0]
        target=c.ls(holder,long=True)[0]
        if helper.namespace is not None:
            driver=helper._cmds.identity.to_local(driver)
            target=helper._cmds.identity.to_local(target)
        constraint=helper.capture_parent_constraint_input(driver,target,False)
        from adv_py.core.body_parent_constraint import plan_body_parent_constraint
        constraint=plan_body_parent_constraint(constraint)
        helper.preflight_parent_constraint(constraint)
        helper.create_parent_constraint(constraint)
        c.parent(box,holder)
        shape=c.listRelatives(box,shapes=True,noIntermediate=True)[0]
        c.setAttr(shape+'.overrideEnabled',False)
        for kind in ('translate','rotate'):
            for axis in 'XYZ':c.setAttr(box+'.'+kind+axis,lock=True,keyable=False)

    def _drop_foot(self, spec: PolyBoxSpec) -> None:
        if not spec.floor_foot:
            return
        c=self.cmds
        up=c.upAxis(query=True,axis=True)
        group=self._name('Group')
        locks=()
        if up=='z':
            locks=tuple(bool(c.getAttr(group+'.rotate'+axis,lock=True)) for axis in 'XYZ')
            for axis in 'XYZ':c.setAttr(group+'.rotate'+axis,lock=False)
            c.setAttr(group+'.rotate',0,0,0,type='double3');c.upAxis(axis='y',rotateView=False)
            # Source queries Heel after changing the scene axis.
            stem=spec.driver[:-2]
            segment=next((item for item in self._fit_geometry_segments if item.stem==stem),None)
            if segment is not None:
                from .maya_fit_geometry import MayaFitGeometryHost
                joint=MayaFitGeometryHost(self.namespace)._physical(segment.joint)
                spec=replace(spec,heel=self._fit_heel(joint,spec.driver[-2:]))
        try:self._drop_foot_y(spec)
        finally:
            if up=='z':
                c.setAttr(group+'.rotate',90,0,0,type='double3');c.upAxis(axis='z',rotateView=False)
                for axis,locked in zip('XYZ',locks):c.setAttr(group+'.rotate'+axis,lock=locked)

    def _drop_foot_y(self, spec: PolyBoxSpec) -> None:
        c = self.cmds
        def source_position(vertex):return tuple(float(value) for value in c.xform(
            vertex,query=True,worldSpace=True,translation=True))
        box = self._name(spec.name)
        vertices = c.ls(box + ".vtx[*]", flatten=True) or []
        if len(vertices) < 4:
            raise ValueError("足部 PolyBox 缺少四个底面顶点：" + spec.name)
        if spec.heel is not None:
            heel=spec.heel
            closest=list(vertices)
            # Source repeatedly removes the first greatest-distance point;
            # an ordinary stable minimum sort chooses different tied CVs.
            while len(closest)>2:
                farthest=max(closest,key=lambda vertex:dist(source_position(vertex),heel))
                closest.remove(farthest)
            positions = [source_position(vertex) for vertex in closest]
            offset = tuple(heel[axis] -
                           (positions[0][axis] + positions[1][axis]) / 2
                           for axis in range(3))
            c.select(closest,replace=True)
            c.move(*offset,relative=True)
        main=self._name('Main') if c.objExists(self._name('Main')) else self._name('AdvPy_Global')
        fit=self._name('FitSkeleton');driver=self._name(spec.driver)
        if (c.objExists(fit+'.worldmatch') and c.getAttr(fit+'.worldmatch')
                and c.objExists(driver+'.primaryAxis')):main=driver
        axis=(str(c.getAttr(main+'.secondaryAxis',asString=True)).lstrip('+-').upper()
              if c.objExists(main+'.secondaryAxis') else 'Y')
        if axis not in 'XYZ':axis='Y'
        height = float(c.getAttr(box + '.scale'+axis))
        try:
            c.setAttr(box + '.scale'+axis, 10.0)
            bottom=list(vertices)
            while len(bottom)>4:
                highest=max(bottom,key=lambda vertex:source_position(vertex)[1])
                bottom.remove(highest)
        finally:
            c.setAttr(box + '.scale'+axis, height)
        c.select(bottom,replace=True)
        for vertex in bottom:
            position = c.xform(vertex, query=True,
                               worldSpace=True, translation=True)
            c.xform(vertex, worldSpace=True,
                    translation=(position[0], 0.0, position[2]))

    def create(self, plan: tuple[PolyBoxSpec, ...]) -> None:
        from .maya_fit_geometry import MayaFitGeometryHost
        from .maya_body import MayaBodyBuildHost
        c=self.cmds
        fit=self._name('FitSkeleton')
        preview=MayaFitGeometryHost(self.namespace)
        segments=getattr(self,'_fit_geometry_segments',None)
        if segments is None:segments=preview.capture_fit_geometry(poly_boxes=True)
        helper=MayaBodyBuildHost(namespace=self.namespace,
            use_offset_parent_matrix=bool(c.getAttr(fit+'.useOffsetParentMatrix')))
        # These operations join the application's already-open transaction.
        helper._transaction_active=True
        self._geometry_constraint_host=helper
        preview.ensure_fit_geometry_profiles()
        preview.update_fit_geometry_orientation()
        segments=preview.capture_fit_geometry(poly_boxes=True)
        self._fit_geometry_segments=segments
        gap=c.getAttr(fit+'.visGap');vis=c.getAttr(fit+'.visGeo')
        try:
            joints=tuple(helper._cmds.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True) or ())
            helper.write_missing_fit_deform_profiles('FitSkeleton',joints)
            c.setAttr(fit+'.visGeo',1)
            preview.create_fit_geometry(segments,types=('Box',))
            c.setAttr(fit+'.visGeo',vis);c.setAttr(fit+'.visGap',1)
            c.dgdirty(allPlugs=True)
            c.setAttr(self._name('FitSkeletonVisualizers')+'.visibility',0)
            parent=c.createNode('transform',name=self._name('BoxesGeometry'),parent=self._name('Geometry'))
            c.connectAttr(self._name('MainScaleMultiplyDivide')+'.output',parent+'.scale')
            layer=c.createDisplayLayer(name=self._name('PolyBoxes'),empty=True);c.setAttr(layer+'.color',14)
            # Aims' native descendants order determines copied boxes and the
            # subsequent overlapping-vertex assignment order in BoxSkin.
            by_name={spec.name:spec for spec in plan}
            for source in c.listRelatives(self._name('Aims'),allDescendents=True,type='transform') or ():
                stem=self._leaf(source)
                if not stem.endswith('Box'):continue
                for side in ('_M','_R','_L'):
                    spec=by_name.get(stem+side)
                    if spec is not None:self._create_box(spec,parent)
            for spec in plan:self._drop_foot(spec)
            self.mirror(tuple((spec.name,spec.name[:-1]+'L') for spec in plan
                if spec.name.endswith('_R') and spec.name[:-1]+'L' in by_name))
            c.sets(parent,edit=True,forceElement='initialShadingGroup')
            c.select(clear=True)
        finally:
            c.setAttr(fit+'.visGap',gap)
            c.setAttr(fit+'.visGeo',vis)
            preview.delete_fit_geometry()
            helper._transaction_active=False

    def capture_created(self, plan: tuple[PolyBoxSpec, ...]) -> bool:
        c = self.cmds
        group = self._name("BoxesGeometry")
        layer = self._name("PolyBoxes")
        if not c.objExists(group) or not c.objExists(layer):
            return False
        source = c.connectionInfo(group + ".scaleX",
                                  sourceFromDestination=True)
        if source not in (self._name("MainScaleMultiplyDivide") + ".outputX",
                          self._name("MainScaleMultiplyDivide") + ".output"):
            return False
        for spec in plan:
            box = self._name(spec.name)
            holder = self._name(self._holder_name(spec.name))
            if (not c.objExists(box)
                    or not c.listRelatives(box, shapes=True,
                                           noIntermediate=True, type="mesh")
                    or not c.objExists(holder)
                    or holder not in (c.listRelatives(box, parent=True) or [])):
                return False
            if spec.floor_foot:
                # The source floors in its temporary Y scene, then restores
                # Group and its constraints. A transformed/Z scene need not
                # retain four zero world heights after that restoration.
                if int(c.polyEvaluate(box,vertex=True)) != 8:
                    return False
        return True

    def exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("BoxesGeometry"))
                or c.objExists(self._name("PolyBoxes")))

    def delete(self) -> None:
        c = self.cmds
        for leaf in ("BoxesGeometry", "PolyBoxes"):
            if c.objExists(self._name(leaf)):
                c.delete(self._name(leaf))

    def box_names(self) -> tuple[str, ...]:
        return tuple(name for name in self.all_box_names()
                     if name.endswith(("Box_L", "Box_R")))

    def all_box_names(self) -> tuple[str, ...]:
        c = self.cmds
        group = self._name("BoxesGeometry")
        if not c.objExists(group):
            raise ValueError("请先创建 PolyBoxes")
        return tuple(self._leaf(node)
            for holder in c.listRelatives(group,children=True,fullPath=True) or ()
            for node in c.listRelatives(holder,children=True,fullPath=True) or ()
            if c.listRelatives(node,shapes=True,noIntermediate=True,type='mesh'))

    def mirror(self, pairs: tuple[tuple[str, str], ...]) -> int:
        c = self.cmds
        for source_name, target_name in pairs:
            source = self._name(source_name)
            target = self._name(target_name)
            if not c.getAttr(target+'.scaleX',lock=True):
                c.setAttr(target+'.scale',*c.getAttr(source+'.scale')[0],type='double3')
            source_vertices = c.ls(source + ".vtx[*]", flatten=True) or []
            target_vertices = c.ls(target + ".vtx[*]", flatten=True) or []
            if len(source_vertices) != len(target_vertices):
                raise ValueError("PolyBoxes 镜像两侧顶点数量不同：" + source_name)
            expected = []
            for index, vertex in enumerate(source_vertices):
                position = c.xform(vertex, query=True,
                                   worldSpace=True, translation=True)
                mirrored = (-position[0], position[1], position[2])
                c.xform(target_vertices[index], worldSpace=True,
                        translation=mirrored)
                expected.append(mirrored)
            for index, position in enumerate(expected):
                actual = c.xform(target_vertices[index], query=True,
                                 worldSpace=True, translation=True)
                if dist(actual, position) > 1e-4:
                    raise RuntimeError("PolyBoxes 镜像写后读回不一致：" + target_name)
        return len(pairs)
