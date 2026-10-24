"""Geometry and Skin branches of asChooseInput, MEL 45240–45420.

Input strings remain on FaceFitSkeleton; this module performs the scene
operations which precede the original text-field assignment.
"""
from adv_py.core.fit_settings import FitSkeletonValidationError


RESERVED_FACE_INPUT_NAMES = ('Eye_R','Eye_L','upperTeeth_M','lowerTeeth_M',
                            'Tongue0_M','Nose_M')


class MayaOriginalFaceInputsMixin:
    def validate_original_face_input_names(self, selected):
        c=self._cmds
        for node in selected:
            owner=node.split('.',1)[0]
            name=owner.rsplit('|',1)[-1]
            if name in RESERVED_FACE_INPUT_NAMES:
                c.select(node,replace=True)
                raise FitSkeletonValidationError('Selected object: "'+name+'" uses a name that AdvancedSkeleton needs to use, rename this object to another name.')
            if (c.ls(name,long=True) or [])!=[owner]:
                c.select(node,replace=True)
                raise FitSkeletonValidationError('Selected object: "'+owner+'" does not have a unique name, rename to a unique name.')

    def selected_original_face_geometry(self, *, allow_components=False):
        selected=tuple(self._cmds.ls(selection=True,long=True) or [])
        return self.original_face_geometry(selected,allow_components=allow_components)

    def original_face_geometry(self, selected, *, allow_components=False):
        """Run source selection rules for both UI selection and explicit input."""
        c=self._cmds
        selected=tuple(selected)
        if not allow_components and any('.' in node for node in selected):
            raise FitSkeletonValidationError('Only select Object, not vertices, edges or faces')
        self.validate_original_face_input_names(selected)
        descendants=[]
        for node in selected:
            if '.' not in node:
                descendants.extend(c.listRelatives(node,allDescendents=True,
                    fullPath=True,type='transform') or [])
        geometry=[]
        for node in dict.fromkeys((*selected,*descendants)):
            if '.' in node:
                # Source assigns the entire selection when a component occurs.
                geometry=list(dict.fromkeys((*selected,*descendants)))
                continue
            shapes=c.listRelatives(node,shapes=True,noIntermediate=True,fullPath=True) or []
            if shapes and c.nodeType(shapes[0]) in ('mesh','nurbsSurface'):
                geometry.append(node)
        return tuple(geometry)

    def ensure_original_face_fit_container(self):
        """Create the locked FaceGroup/FaceFitSkeleton before input recording."""
        self._require_transaction()
        c=self._cmds
        fit=self._fit()
        if fit is not None:return fit
        if c.objExists('FaceFitSkeleton'):
            raise FitSkeletonValidationError('FaceFitSkeleton 名称被其他类型节点占用')
        group=c.ls('FaceGroup',long=True) or []
        if len(group)>1 or group and c.nodeType(group[0])!='transform':
            raise FitSkeletonValidationError('FaceGroup 名称已冲突')
        selected=c.ls(selection=True,long=True) or []
        self._transaction_changed=True
        try:
            if not group:
                parent=(c.ls('|Group',long=True,type='transform') or [None])[0]
                node=c.createNode('transform',name='FaceGroup',**({'parent':parent} if parent else {}))
                group=c.ls(node,long=True,type='transform') or []
                for kind in ('translate','rotate','scale'):
                    for axis in 'XYZ':c.setAttr(group[0]+'.'+kind+axis,lock=True,keyable=False)
            node=c.createNode('transform',name='FaceFitSkeleton',parent=group[0])
            fit=(c.ls(node,long=True,type='transform') or [None])[0]
            if fit is None:raise FitSkeletonValidationError('FaceFitSkeleton 创建失败')
            for owner in (group[0],fit):
                for kind in ('translate','rotate','scale'):
                    for axis in 'XYZ':c.setAttr(owner+'.'+kind+axis,lock=True,keyable=False)
            return fit
        finally:
            c.select(selected,replace=True) if selected else c.select(clear=True)

    def record_original_face_head_joint(self):
        """asChooseInput's Joint branch uses the first selected joint."""
        self._require_transaction()
        c=self._cmds
        selected=c.ls(selection=True,long=True) or []
        if not selected:raise FitSkeletonValidationError('请先选择 Head 关节')
        self.validate_original_face_input_names(selected)
        head=selected[0]
        if '.' in head or c.objectType(head)!='joint':
            raise FitSkeletonValidationError('A joint must be selected')
        fit=self.ensure_original_face_fit_container()
        if c.referenceQuery(fit,isNodeReferenced=True):
            raise FitSkeletonValidationError('不能改写引用中的 FaceFitSkeleton')
        self._transaction_changed=True
        if not c.objExists(fit+'.HeadJoint'):c.addAttr(fit,longName='HeadJoint',dataType='string')
        c.setAttr(fit+'.HeadJoint',head.rsplit('|',1)[-1],type='string')
        return head

    def record_original_face_eye_input(self,side):
        """Choose Right/Left Eye records input; it does not build EyeBall Fit."""
        self._require_transaction()
        if side not in ('Right','Left'):raise ValueError('原版 Eye 输入侧别无效')
        geometry=self.selected_original_face_geometry(allow_components=True)
        if not geometry:raise FitSkeletonValidationError('请先选择眼球对象或组件')
        fit=self.ensure_original_face_fit_container()
        c=self._cmds
        if c.referenceQuery(fit,isNodeReferenced=True):
            raise FitSkeletonValidationError('不能改写引用中的 FaceFitSkeleton')
        if self.ensure_original_face_input_skins(geometry) is None:return None
        self.mark_original_non_spherical_eye_lattice(geometry,'R' if side=='Right' else 'L')
        attribute='RightEye' if side=='Right' else 'LeftEye'
        if not c.objExists(fit+'.'+attribute):c.addAttr(fit,longName=attribute,dataType='string')
        self._transaction_changed=True
        c.setAttr(fit+'.'+attribute,' '.join(self.scene_address(node) for node in geometry),type='string')
        return geometry

    def ensure_original_face_input_skins(self, geometry, head_joint='Head_M'):
        """Return source history choices, or None after the user's Cancel."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,'raw',c)
        if not c.objExists('FaceFitSkeletonShape'):
            raise FitSkeletonValidationError('Start with choosing Mask')
        approved=False
        result=[]
        for mesh in geometry:
            history=c.listHistory(mesh,pruneDagObjects=True,interestLevel=2) or []
            skins=[node for node in history if c.objectType(node)=='skinCluster']
            skin=skins[-1] if skins else None
            if skin is None:
                if not approved:
                    approved=raw.confirmDialog(title='Confirm',
                        message='No SkinCluster found on this geometry:\n'+self.scene_address(mesh),
                        button=['Create New SkinCluster','Cancel'],
                        defaultButton='Create New SkinCluster',dismissString='Cancel')=='Create New SkinCluster'
                    if not approved:
                        return None
                self._transaction_changed=True
                c.select(clear=True)
                if not c.objExists(head_joint):
                    c.joint(name=head_joint)
                    if c.objExists('FaceFitSkeleton'):
                        bottom=c.xform('FaceFitSkeletonShape.cv[0]',query=True,worldSpace=True,translation=True)
                        top=c.xform('FaceFitSkeletonHeightShape.cv[0]',query=True,worldSpace=True,translation=True)
                        c.xform(head_joint,worldSpace=True,translation=(0,bottom[1]+(top[1]-bottom[1])/3.,0))
                if not c.objExists('FaceFitSkeleton.HeadJoint'):
                    c.addAttr('FaceFitSkeleton',longName='HeadJoint',dataType='string')
                c.setAttr('FaceFitSkeleton.HeadJoint',head_joint,type='string')
                c.select((mesh,head_joint),replace=True)
                # Native newSkinCluster passes these exact four flags.
                skin=c.skinCluster(mesh,head_joint,toSelectedBones=True,
                    maximumInfluences=1,dropoffRate=4,removeUnusedInfluence=False)[0]
                c.select(mesh,replace=True)
            result.append(skin)
        return tuple(result)

    def mark_original_non_spherical_eye_lattice(self, geometry, side):
        """Native lattice discovery, tagging and history order after Eye input."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,'raw',c)
        lattice=None
        tagged=[]
        for mesh in geometry:
            skin=None
            for node in c.listHistory(mesh) or []:
                kind=c.objectType(node)
                if kind=='ffd': lattice=node
                if kind=='skinCluster': skin=node
            # MEL retains ffd across the outer loop; do not reset it per mesh.
            if lattice is None:
                continue
            # The native sentinel is "Detected Lattice", while the dialog
            # returns Yes/No. It therefore asks again for each geometry.
            answer=raw.confirmDialog(title='Confirm',
                message='Lattice detected.\nUse this Lattice for non-spherical eyes ?',
                button=['Yes','No'],defaultButton='Yes',dismissString='No')
            if answer!='Yes':
                continue
            self._transaction_changed=True
            for attribute in c.listAttr(lattice,userDefined=True) or []:
                if attribute.startswith('asNonSphereLattice_'):
                    c.deleteAttr(lattice+'.'+attribute)
            c.addAttr(lattice,longName='asNonSphereLattice_'+side,
                      attributeType='bool',defaultValue=True,keyable=False)
            c.reorderDeformers(lattice,skin,mesh)
            if c.getAttr(lattice+'.outsideLattice')!=1:
                c.setAttr(lattice+'.outsideLattice',1)
            tagged.append(lattice)
        return tuple(tagged)
