"""Source FitGeometry: live flare, distance, segment and aim graphs."""
from contextlib import contextmanager
from uuid import uuid4

from adv_py.core.fit_geometry import plan_fit_geometry
from .maya_skin_cage import MayaSkinCageHost


class MayaFitGeometryHost(MayaSkinCageHost):
    def fit_geometry_mode_scope(self, visible):
        from .maya_source_fit_mode import suspend_for_geometry
        return suspend_for_geometry(self, resume=visible)

    @contextmanager
    def transaction(self,label):
        with super().transaction(label):
            with self.namespace_scope():
                yield

    def set_fit_geometry_display(self,visible,geometry_type,gap=None):
        c=self.cmds;fit=self._name('FitSkeleton')
        c.setAttr(fit+'.visGeo',visible)
        if c.objExists(fit+'.visGeoType'):
            c.setAttr(fit+'.visGeoType',('cylinders','boxes','spheres','bones').index(geometry_type))
        for label,attribute in (('cylinders','visCylinders'),('boxes','visBoxes'),
                                ('spheres','visSpheres'),('bones','visBones')):
            c.setAttr(fit+'.'+attribute,label==geometry_type)
        if gap is not None:c.setAttr(fit+'.visGap',gap)

    def ensure_fit_geometry_profiles(self):
        from .maya_fit import MayaFitJointHost
        from adv_py.application.fit_settings import EnsureFitSkeletonSettings
        helper=MayaFitJointHost(namespace=self.namespace)
        helper._transaction_active=True
        try:
            plan=EnsureFitSkeletonSettings(helper).plan()
            for setting in plan.additions:helper.add_fit_skeleton_setting(plan.before.container,setting)
            joints=tuple(helper._cmds.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True) or ())
            helper.write_missing_fit_deform_profiles('FitSkeleton',joints)
        finally:helper._transaction_active=False

    def update_fit_geometry_orientation(self):
        from .maya_fit import MayaFitJointHost
        helper=MayaFitJointHost(namespace=self.namespace)
        helper._transaction_active=True
        try:
            helper.manual_update_fit('FitSkeleton')
        finally:helper._transaction_active=False

    @contextmanager
    def namespace_scope(self):
        c=self.cmds
        previous=c.namespaceInfo(currentNamespace=True,absoluteName=True)
        # Explicitly qualified _name addresses resolve from root. Keep the
        # caller's active namespace intact after this operation.
        changed=previous!=':'
        if changed:c.namespace(set=':')
        try: yield
        finally:
            if changed:c.namespace(set=previous)

    def capture_fit_geometry(self,*,poly_boxes=False):
        from .maya_fit import MayaFitJointHost
        host=MayaFitJointHost(namespace=self.namespace)
        snapshot=host.capture_fit_orientation('FitSkeleton')
        self._fit_geometry_snapshot=snapshot
        # Native asRlaChild uses Fit.sx, rather than asGetScale's body height.
        return plan_fit_geometry(snapshot,poly_boxes=poly_boxes)

    def _physical(self,path):
        if not path.startswith('|'): return self._name(path)
        return '|'.join((self._name(part) if part else '') for part in path.split('|'))

    def _ensure_shaders(self):
        from .maya_source_fit_pole_vectors import ensure_fit_shaders
        ensure_fit_shaders(self.cmds, self._name)

    def _template_bones(self):
        from .maya_geometry_skeleton import geometry_asset
        c=self.cmds
        namespace='AdvPyFitGeometryTemplate_'+uuid4().hex[:10]
        imported=c.file(str(geometry_asset()),i=True,namespace=namespace,
               mergeNamespacesOnClash=False,returnNewNodes=True)
        self._template_import_ids=tuple(c.ls(imported,uuid=True))
        group=namespace+':Skeleton_Geometry'
        templates={node.rsplit('|',1)[-1].split(':')[-1]:node
            for node in c.listRelatives(group,children=True,fullPath=True) or ()}
        return namespace,templates

    @contextmanager
    def fit_geometry_assets(self,enabled=True):
        if not enabled or getattr(self,'_prepared_templates',None) is not None:
            yield
            return
        namespace,templates=self._template_bones()
        self._prepared_templates=templates
        try:yield
        finally:
            c=self.cmds
            originals=c.ls(self._template_import_ids,long=True) or []
            if originals:c.delete(originals)
            if c.namespace(exists=namespace):
                c.namespace(removeNamespace=namespace,mergeNamespaceWithRoot=True)
            self._prepared_templates=None

    def delete_fit_geometry(self):
        c=self.cmds
        group=self._name('FitSkeletonVisualizers')
        if c.objExists(group):
            # Non-DAG distance/multiply nodes are not removed with parents.
            owned=c.getAttr(group+'.advPyFitGeometryNodes') if c.objExists(group+'.advPyFitGeometryNodes') else ''
            c.delete(group)
            for uuid in owned.split():
                matches=c.ls(uuid) or []
                if matches:c.delete(matches)

    def create_fit_geometry(self,plans,*,types=('Box','Cyl','Sphere','Bone')):
        with self.fit_geometry_assets('Bone' in types):
            return self._create_fit_geometry(plans,types=types)

    def _create_fit_geometry(self,plans,*,types):
        c=self.cmds
        fit=self._name('FitSkeleton')
        self.delete_fit_geometry()
        self._ensure_shaders()
        with self.namespace_scope():
            before=set(c.ls(uuid=True))
            templates=getattr(self,'_prepared_templates',None) or {}
            root=c.createNode('transform',name=self._name('FitSkeletonVisualizers'))
            aims=c.createNode('transform',name=self._name('Aims'),parent=root)
            c.connectAttr(fit+'.scale',root+'.scale')
            # Create all Aim transforms first: a middle joint may refer
            # to its IK start's Aim, despite descendants-first creation.
            for plan in plans:
                c.createNode('transform',name=self._name(plan.stem+'Aim'),parent=aims)
            for plan in plans:
                self._create_segment(plan,types,templates)
            for plan in plans:
                aim=self._name(plan.stem+'Aim')
                c.pointConstraint(self._physical(plan.joint),aim)
                c.aimConstraint(self._physical(plan.child),aim,
                    aimVector=(1,0,0),upVector=plan.up_vector,
                    worldUpType=plan.up_type,
                    worldUpObject=self._physical(plan.up_object),
                    worldUpVector=plan.world_up_vector)
            owned=set(c.ls(uuid=True))-before
            c.addAttr(root,longName='advPyFitGeometryNodes',dataType='string')
            c.setAttr(root+'.advPyFitGeometryNodes',' '.join(sorted(owned)),type='string')
        return tuple(self._name(plan.stem+('Part'+str(i) if i else '')+'Box')
                     for plan in plans for i in range(plan.parts) if 'Box' in types)

    def _create_segment(self,plan,types,templates):
        c=self.cmds
        fit=self._name('FitSkeleton');joint=self._physical(plan.joint);child=self._physical(plan.child)
        stem=plan.stem;aim=self._name(stem+'Aim')
        geometries=[]
        colors=('asGreen','asRed','asGreen2','asRed2','asBlue','asBlue2')
        for index in range(plan.parts):
            suffix='Part'+str(index) if index else ''
            geo=c.createNode('transform',name=self._name(stem+suffix+'Geo'),parent=aim)
            if 'Box' in types:
                box=c.polyCube(name=self._name(stem+suffix+'Box'),width=1.75,height=1.,depth=1.75,
                    subdivisionsX=1,subdivisionsY=1,subdivisionsZ=1,axis=(0,1,0),
                    createUVs=4,constructionHistory=False)[0]
                c.move(0,.5,0,box+'.vtx[0:7]',relative=True)
                for face,color in enumerate(colors):c.sets(box+f'.f[{face}]',edit=True,forceElement=self._name(color+'SG'))
                c.connectAttr(fit+'.visBoxes',box+'.visibility')
                c.setAttr(box+'Shape.overrideEnabled',True);c.setAttr(box+'Shape.overrideDisplayType',2)
                c.parent(box,geo);c.setAttr(box+'.scale',1,1,1,type='double3')
                c.rotate(0,-90,-90,box+'.vtx[0:7]',relative=True,pivot=(0,0,0),objectSpace=True)
                geometries.append(box)
            if 'Cyl' in types:
                cylinder=c.cylinder(name=self._name(stem+suffix+'Cyl'),pivot=(0,0,0),axis=(0,1,0),
                    startSweep=0,endSweep=360,radius=1,heightRatio=1,degree=3,
                    useTolerance=False,tolerance=.01,sections=8,spans=1,constructionHistory=False)[0]
                c.move(0,.5,0,cylinder+'.cv[0:3][0:7]',relative=True)
                for color,faces in (('asBlue',('[0][7]','[0][0]')),('asGreen',('[0][1:2]',)),
                                    ('asBlue2',('[0][3:4]',)),('asGreen2',('[0][5:6]',))):
                    c.sets(tuple(cylinder+'.sf'+face for face in faces),edit=True,forceElement=self._name(color+'SG'))
                c.connectAttr(fit+'.visCylinders',cylinder+'.visibility')
                c.setAttr(cylinder+'Shape.overrideEnabled',True);c.setAttr(cylinder+'Shape.overrideDisplayType',2)
                c.parent(cylinder,geo);c.setAttr(cylinder+'.scale',1,1,1,type='double3')
                c.rotate(0,-90,-90,cylinder+'.cv[0:3][0:7]',relative=True,pivot=(0,0,0),objectSpace=True)
                geometries.append(cylinder)
            for number,operation,value,source,target in (
                (4,1,index/plan.parts,'ScaleYMultiDiv1.outputY','.translateX'),
                (5,2,plan.parts,'ScaleYMultiDiv2.outputY','.scaleX')):
                node=c.createNode('multiplyDivide',name=self._name(stem+f'ScaleYMultiDiv{number}_{index}'))
                c.setAttr(node+'.operation',operation);c.setAttr(node+'.input2Y',value)
                # Source distance graph is created below, connect afterwards.
                c.connectAttr(node+'.outputY',geo+target)
        if 'Sphere' in types:
            sphere=c.polyCube(name=self._name(stem+'Sphere'),width=2.5,height=2.5,depth=2.5,
                subdivisionsX=1,subdivisionsY=1,subdivisionsZ=1,axis=(0,1,0),createUVs=4,constructionHistory=False)[0]
            for face,color in enumerate(colors):c.sets(sphere+f'.f[{face}]',edit=True,forceElement=self._name(color+'SG'))
            c.polySmooth(sphere,mth=0,dv=2,bnr=1,c=1,kb=1,ksb=1,khe=0,
                kt=1,kmb=1,suv=1,peh=0,sl=1,dpe=1,ps=.1,ro=1,ch=False)
            c.parent(sphere,aim);c.setAttr(sphere+'.scale',1,1,1,type='double3')
            c.rotate(0,-90,-90,sphere+'.vtx[*]',relative=True,pivot=(0,0,0),objectSpace=True)
            c.connectAttr(fit+'.visSpheres',sphere+'.visibility')
            c.setAttr(sphere+'Shape.overrideEnabled',True);c.setAttr(sphere+'Shape.overrideDisplayType',2)
            for axis in 'XYZ':c.connectAttr(joint+'.fat',sphere+'.scale'+axis)
        if 'Bone' in types and stem!='Scapula':
            template=stem+'Bone'
            if template not in templates:
                template=('SpineBone' if stem in ('Root','Chest') or stem.startswith(('Neck','Spine'))
                          else 'DigitBone' if 'Finger' in stem else 'GenericBone')
            bone=c.duplicate(templates[template],name=self._name(stem+'Bone'),returnRootsOnly=True)[0]
            for shape in c.listRelatives(bone,shapes=True,fullPath=True) or []:
                c.rename(shape,self._name(stem+'BoneShape'))
            c.parent(bone,aim);c.sets(bone,edit=True,forceElement=self._name('asBonesSG'))
            c.connectAttr(fit+'.visBones',bone+'.visibility')
            for axis in 'YZ':c.connectAttr(joint+'.fat',bone+'.scale'+axis)
        if geometries:
            flare,handle=c.nonLinear(geometries,type='flare',lowBound=0,highBound=1,
                startFlareX=1,startFlareZ=1,endFlareX=1,endFlareZ=1,curve=0)
            flare=c.rename(flare,self._name(stem+'Flare'))
            handle=c.rename(handle,self._name(stem+'FlareHandle'))
            c.parent(handle,aim)
            c.setAttr(handle+'.scale',1,1,1,type='double3');c.setAttr(handle+'.translate',0,0,0,type='double3')
            c.setAttr(handle+'.rotate',0,0,-90,type='double3');c.setAttr(handle+'.visibility',0,lock=True)
            destination=handle if c.isConnected(handle+'.startFlareX',flare+'.startFlareX') else flare
            for source,target in ((joint+'.fatFrontAbs','startFlareX'),(joint+'.fatWidthAbs','startFlareZ'),
                                  (child+'.fatFrontAbs','endFlareX'),(child+'.fatWidthAbs','endFlareZ')):
                c.connectAttr(source,destination+'.'+target)
        distance=c.createNode('distanceBetween',name=self._name(stem+'Distance'))
        c.connectAttr(joint+'.worldMatrix[0]',distance+'.inMatrix1')
        c.connectAttr(child+'.worldMatrix[0]',distance+'.inMatrix2')
        divide=c.createNode('multiplyDivide',name=self._name(stem+'ScaleYMultiDiv1'))
        c.setAttr(divide+'.operation',2);c.connectAttr(distance+'.distance',divide+'.input1Y')
        c.connectAttr(fit+'.scaleY',divide+'.input2Y')
        gap=c.createNode('multiplyDivide',name=self._name(stem+'ScaleYMultiDiv2'))
        c.connectAttr(divide+'.outputY',gap+'.input1Y');c.connectAttr(fit+'.visGap',gap+'.input2Y')
        if geometries:c.connectAttr(divide+'.outputY',handle+'.scaleY')
        for index in range(plan.parts):
            for number,source in ((4,divide),(5,gap)):
                c.connectAttr(source+'.outputY',self._name(stem+f'ScaleYMultiDiv{number}_{index}')+'.input1Y')
        if 'Bone' in types and stem!='Scapula':c.setAttr(bone+'.scaleX',c.getAttr(divide+'.outputY'))
