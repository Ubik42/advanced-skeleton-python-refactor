"""Native imported Fit placement; never substitutes a synthetic body template."""
from adv_py.core.fbx_rig_import import detect_fbx_source_application
from adv_py.core.source_name_matcher import (
    read_source_name_matcher_template,source_name_matcher_name,
    SOURCE_NAME_MATCHER_RESERVED,
)
from .maya_source_fit_import import source_fit_asset_directory


def source_name_matcher_directory(*,mocap=False):
    if type(mocap) is not bool:raise ValueError('NameMatcher 模板类型无效')
    return source_fit_asset_directory().parent/('moCapMatchers' if mocap else 'nameMatchers')


def source_name_matcher_catalog(*,mocap=False):
    return tuple(sorted(source_name_matcher_directory(mocap=mocap).glob('*.txt'),key=lambda path:path.name))


def source_name_matcher_template_path(name, *,mocap=False):
    directory=source_name_matcher_directory(mocap=mocap)
    if not isinstance(name,str) or not name or any(char in name for char in '/\\:'):
        raise ValueError('原版 NameMatcher 模板名称无效')
    path=directory/(name+'.txt')
    if not path.is_file():raise ValueError('原版 NameMatcher 模板不存在：'+name)
    return path


class MayaSourceNameMatcherMixin:
    def read_source_name_matcher_template(self, name, *,mocap=False):
        path = source_name_matcher_template_path(name,mocap=mocap)
        return read_source_name_matcher_template(path.read_text(encoding='utf-8-sig'))

    def _source_matcher_dialog(self, message, *, buttons=('OK','Skip','Cancel'),title='Confirm'):
        raw = getattr(self._cmds,'raw',self._cmds)
        return raw.confirmDialog(title=title,message=message,button=buttons,
                                 defaultButton=buttons[0],dismissString=buttons[-1])

    def check_source_name_matcher(self, source_root):
        """asNameMatcherCheck checks after an explicit source-root selection."""
        self._require_transaction()
        raw = getattr(self._cmds,'raw',self._cmds)
        roots = raw.ls(source_root,long=True) or ()
        if len(roots)!=1 or raw.nodeType(roots[0]) not in ('joint','transform'):
            raise ValueError('NameMatcher 需要明确的来源骨架入口')
        root_uuid = raw.ls(roots[0],uuid=True)[0]
        source_root = roots[0]
        self._transaction_changed = True
        top_meshes = []
        for transform in raw.ls(assemblies=True,long=True) or ():
            shapes = raw.listRelatives(transform,noIntermediate=True,shapes=True,fullPath=True) or ()
            if shapes and raw.nodeType(shapes[0])=='mesh':
                top_meshes.append(transform)
        if top_meshes and not raw.objExists('geo') and not raw.objExists('Hi'):
            choice = self._source_matcher_dialog(
                'Found: '+str(len(top_meshes))+' TopLevel Geomtry objects,\nThese should be grouped as the model.\n')
            if choice=='Cancel':return None
            if choice=='OK':
                geo = raw.createNode('transform',name=':geo')
                raw.parent(top_meshes,geo)
                layer = raw.createDisplayLayer(name='Hi')
                raw.editDisplayLayerMembers(layer,geo,noRecurse=True)
                raw.select(clear=True)
        for shape in raw.ls(type='blendShape') or ():
            curves = raw.listConnections(shape,type='animCurve',source=True,destination=False) or ()
            if curves:raw.delete(curves)
        clashes = []
        for reserved in SOURCE_NAME_MATCHER_RESERVED:
            for path in raw.ls(reserved,long=True) or ():
                if 'FitSkeleton' not in path:clashes.append(reserved)
        if clashes:
            choice = self._source_matcher_dialog('Clashing Names Detected\n\n'
                'To proceed, a NameSpace will be added to the external skeleton.\n\n'+'\n'.join(clashes[:12]))
            if choice=='Cancel':return None
            if choice=='OK':
                if not raw.namespace(exists=':NameMatcher'):
                    raw.namespace(addNamespace=':NameMatcher')
                paths = tuple(raw.listRelatives(source_root,allDescendents=True,
                    type='transform',fullPath=True) or ())+(source_root,)
                # Original reverse descendant order avoids invalidating child
                # addresses. UUID resolution also handles duplicate leaf names.
                addresses = tuple((raw.ls(path,uuid=True)[0],path.rsplit('|',1)[-1]) for path in paths)
                for value,name in addresses:
                    path = raw.ls(value,long=True)[0]
                    temporary = raw.rename(path,':NameMatcher:TEMP_'+name)
                    raw.rename(temporary,':NameMatcher:'+name)
                source_root = raw.ls(root_uuid,long=True)[0]
        if raw.upAxis(query=True,axis=True)=='z':
            if self._source_matcher_dialog('Z-Up Axis Settings detected.\nIt is Highly recommended to use Y-Up\nSwitch to Y-Up ?',
                                           buttons=('OK','Skip'))=='OK':
                raw.upAxis(axis='y')
        if raw.objExists('top') and raw.getAttr('top.rotateX')>-89:
            if self._source_matcher_dialog('Z-Up Camera Values detected.\n\nSwitch to Y-Up Camera Values ?',
                                           buttons=('OK','Skip'))=='OK':
                for camera,rotation in (('top',(-90,0,0)),('front',(0,0,0)),
                                        ('side',(0,90,0)),('persp',(-27,45,0))):
                    raw.setAttr(camera+'.rotate',*rotation,type='float3')
                raw.xform('persp',pivots=(0,0,0))
        # MetaHuman intentionally skips the bindPose-reset pass.
        metahuman = bool(raw.objExists('CTRL_faceGUIfollowHead'))
        joints = list(raw.listRelatives(source_root,allDescendents=True,type='joint',fullPath=True) or ())
        if raw.nodeType(source_root)=='joint':joints.append(source_root)
        first = True
        if not metahuman:
            for joint in reversed(joints):
                if not raw.attributeQuery('bindPose',node=joint,exists=True):continue
                matrix = raw.getAttr(joint+'.bindPose')
                if len(matrix)==1 and isinstance(matrix[0],(tuple,list)):matrix=matrix[0]
                current = raw.getAttr(joint+'.matrix')
                if len(current)==1 and isinstance(current[0],(tuple,list)):current=current[0]
                if len(matrix)!=16 or tuple(matrix)==tuple(current):continue
                if first:
                    choice = self._source_matcher_dialog('detected joint that are Not in Bind Pose,\n\nReset joints to Bind-Pose ?')
                    if choice=='Cancel':return None
                    if choice=='Skip':break
                    first = False
                raw.xform(joint,worldSpace=True,matrix=matrix)
        raw.refresh()
        non_default = []
        for shape in raw.ls(noIntermediate=True,long=True,type='mesh') or ():
            transform = (raw.listRelatives(shape,parent=True,fullPath=True) or [None])[0]
            if not transform:continue
            history = raw.listHistory(shape) or ()
            if not any(raw.nodeType(item)=='skinCluster' for item in history):continue
            if any(raw.getAttr(transform+'.'+kind+axis)!=(1 if kind=='s' else 0)
                   for kind in 'trs' for axis in 'xyz'):
                non_default.append(transform)
        if non_default:
            choice = self._source_matcher_dialog(str(len(non_default))+
                ' Skinned Objects with Non Default Transform Values detected.\nReset Transforms ?',title='Reset Transforms ?')
            if choice=='Cancel':return None
            if choice=='OK':
                for transform in non_default:
                    curves = raw.listConnections(transform,source=True,destination=False,type='animCurve') or ()
                    if curves:raw.delete(curves)
                    if not raw.referenceQuery(transform,isNodeReferenced=True):
                        from .maya_original_transform_channels import lock_original_transform_channels
                        lock_original_transform_channels(raw,transform)
                    raw.makeIdentity(transform,apply=True,translate=True,rotate=True,scale=True)
                    for kind in 'trs':
                        for axis in 'xyz':raw.setAttr(transform+'.'+kind+axis,lock=True)
                    for item in raw.listHistory(transform,future=False,leaf=True,
                            interestLevel=1,pruneDagObjects=True) or ():
                        if raw.nodeType(item)=='transformGeometry':raw.rename(item,'asResetTransform')
        return raw.ls(root_uuid,long=True)[0]

    def create_source_name_matched_fit(self, source_root, rows, rules, *, template_name=None, preparation=None):
        self._require_transaction()
        raw = getattr(self._cmds,'raw',self._cmds)
        c = self._cmds
        source_root = self.check_source_name_matcher(source_root)
        if source_root is None:
            raise ValueError('已取消 NameMatcher 检查')
        if template_name is None:
            template_name = detect_fbx_source_application(tuple(raw.ls(long=True) or ())) or ''
        custom = source_name_matcher_directory()/(template_name+'.ma')
        source = custom if custom.is_file() else source_fit_asset_directory()/'biped.ma'
        # This is the original behavior: current world Fit is replaced before
        # importing the template chosen by NameMatcher, including finger0 and
        # multiple spine joints supplied by the custom .ma asset.
        if c.objExists('|FitSkeleton'):c.delete('|FitSkeleton')
        source_uuid = raw.ls(source_root,uuid=True)[0]
        self._merge_source_name_matcher_daz_hips(raw)
        source_root = raw.ls(source_uuid,long=True)[0]
        for joint in raw.ls(type='joint') or ():
            raw.setAttr(joint+'.segmentScaleCompensate',False)
        merge,policy = False,'existing'
        if c.objExists('FitSkeleton') and c.listRelatives('FitSkeleton',allDescendents=True,type='joint'):
            choice = raw.confirmDialog(title='Confirm',message='FitSkeleton already exists',
                button=('Replace','Merge','Cancel'),defaultButton='Replace',dismissString='Cancel')
            if choice=='Cancel':raise ValueError('已取消原版 Fit 导入')
            merge = choice=='Merge'
            if merge:
                choice = raw.confirmDialog(title='Confirm',message='Joints with same names ?',
                    button=('Keep existing','Keep imported','Keep both by renaming imported'),
                    defaultButton='Keep existing')
                policy = {'Keep existing':'existing','Keep imported':'imported'}.get(choice,'both')
        self.import_source_fit_scene(source,merge=merge,policy=policy,
            template_name=template_name if custom.is_file() else 'biped')
        if preparation is not None:self.save_source_fit_preparation(preparation)
        axis = 2 if raw.upAxis(query=True,axis=True)=='z' else 1
        highest = 0.
        for transform in raw.listRelatives(source_root,allDescendents=True,type='transform',fullPath=True) or ():
            highest = max(highest,float(raw.xform(transform,query=True,worldSpace=True,translation=True)[axis]))
        scale = highest/17.
        c.setAttr('FitSkeleton.scale',scale,scale,scale,type='float3')
        namespace = source_root.rsplit('|',1)[-1].rpartition(':')[0]
        placed,missing = [],[]
        for row in rows:
            matches = c.ls(row.fit_joint,long=True,type='joint') or ()
            fits = c.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True) or ()
            matches = [path for path in matches if path in fits]
            if len(matches)!=1:
                if 'Part' not in row.fit_joint:raw.warning('AdvancedSkeleton FitJoint "'+row.fit_joint+'" not found')
                continue
            position = c.xform(matches[0],query=True,worldSpace=True,translation=True)
            other = source_name_matcher_name(row.source_base,rules,
                middle=not(position[0]>.001 or position[0]<-.001),namespace=namespace)
            if not raw.objExists(other):
                missing.append(other)
                raw.warning('Other Joint "'+other+'" not found')
                continue
            position = raw.xform(other,query=True,worldSpace=True,translation=True)
            c.xform(matches[0],worldSpace=True,translation=position)
            placed.append(row.fit_joint)
        self.manual_update_fit()
        for finger in ('Thumb','Index','Middle','Ring','Pinky'):
            for index in range(1,5):
                name = finger+'Finger'+str(index)
                if name in placed:continue
                parents = c.listRelatives(name,parent=True) or ()
                if parents:c.setAttr(parents[0]+'.jointOrient',0.,0.,0.,type='float3')
        c.select('FitSkeleton',replace=True)
        from adv_py.application.name_matcher_fit import NameMatcherFitResult
        return NameMatcherFitResult(len(placed),tuple(missing),scale,source_root)

    @staticmethod
    def _merge_source_name_matcher_daz_hips(raw):
        """MEL 21103–21144: keep the hip with most descendants, drive others."""
        hips = tuple(raw.ls('hip',long=True) or ())
        if len(hips)<2:return
        keep = 'hip'
        maximum = 0
        if len(hips)>1:
            raw.warning('Found multiple objects called "hip", attempting to merge the DAZ skeletons..')
            for hip in hips:
                count = len(raw.listRelatives(hip,allDescendents=True,children=True) or ())
                if count>maximum:
                    maximum,keep = count,hip
        for hip in hips:
            if hip==keep:continue
            parents = raw.listRelatives(hip,parent=True) or ()
            if not parents:continue
            base = parents[0]
            full = tuple(raw.listRelatives(base,allDescendents=True,children=True,fullPath=True) or ())
            short = tuple(raw.listRelatives(base,allDescendents=True,children=True) or ())
            kept_full = tuple(raw.listRelatives(keep,allDescendents=True,children=True,fullPath=True) or ())
            kept_short = tuple(raw.listRelatives(keep,allDescendents=True,children=True) or ())
            # Parent renames cannot invalidate a later source identity.
            renamed = tuple((raw.ls(path,uuid=True)[0],name) for path,name in zip(full,short))
            references = tuple((raw.ls(path,uuid=True)[0],name) for path,name in zip(kept_full,kept_short))
            for value,name in renamed:
                target = raw.rename(raw.ls(value,long=True)[0],base+'_'+name)
                for reference,reference_name in references:
                    if reference_name==name:
                        source = raw.ls(reference,long=True)[0]
                        raw.parentConstraint(source,target)
                        raw.scaleConstraint(source,target)
