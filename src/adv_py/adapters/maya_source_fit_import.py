"""Import original Maya Fit assets and merge their joints/SDK connections."""
from contextlib import contextmanager
from pathlib import Path
import os

from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.source_fit_import import (
    SOURCE_FIT_REPLACE_ROLES, SourceFitMergePolicy, source_fit_import_rename,
    SourceFitPreparation,
)


def source_fit_asset_directory(*, limbs=False):
    folder = 'fitSkeletonsLimbs' if limbs else 'fitSkeletons'
    roots = []
    configured = os.environ.get('ADV_6925_DIRECTORY')
    if configured:
        roots.append(Path(configured))
    roots.append(Path(__file__).resolve().parents[3]/'local'/'adv_6_925')
    roots.extend(Path(item) for item in os.environ.get('MAYA_SCRIPT_PATH','').split(os.pathsep) if item)
    for root in roots:
        candidate = root/'AdvancedSkeletonFiles'/folder
        if candidate.is_dir():
            return candidate
    raise ValueError('缺少 ADV 6.925 '+folder+' 资产目录；设置 ADV_6925_DIRECTORY')


def source_fit_asset_catalog(*, limbs=False):
    return tuple(sorted(source_fit_asset_directory(limbs=limbs).glob('*.ma'), key=lambda item: item.name))


class MayaSourceFitImportMixin:
    def save_source_fit_preparation(self, preparation):
        self._require_transaction()
        if not isinstance(preparation,SourceFitPreparation):
            raise ValueError('Fit 导入需要原版 Preparation 参数')
        c = self._cmds
        raw = getattr(c,'raw',c)
        for name,value in preparation.preferences:
            raw.optionVar(intValue=(name,int(value)))
        if c.objExists('FitSkeleton'):
            self._transaction_changed = True
            for name,value in preparation.fit_values:
                if isinstance(value,str):
                    c.setAttr('FitSkeleton.'+name,value,type='string')
                else:
                    c.setAttr('FitSkeleton.'+name,value)

    @contextmanager
    def _source_fit_import_namespace(self):
        c = getattr(self._cmds, 'raw', self._cmds)
        prior = c.namespaceInfo(currentNamespace=True, absoluteName=True)
        try:
            c.namespace(setNamespace=':'+(self.namespace or ''))
            yield c
        finally:
            c.namespace(setNamespace=prior)

    def import_source_fit_scene(self, source, *, merge=False,
                                policy=SourceFitMergePolicy.EXISTING, template_name=None):
        self._require_transaction()
        c = self._cmds
        override = 'FitSkeletonOverride.fitSkeletonFile'
        if c.objExists(override):
            source = c.getAttr(override)
        source = Path(source).resolve()
        if not source.is_file() or source.suffix.lower() != '.ma':
            raise ValueError('原版 Fit 导入需要已有 Maya ASCII 资产文件')
        if type(merge) is not bool:
            raise ValueError('Fit 导入 merge 必须是布尔值')
        policy = SourceFitMergePolicy(policy)
        scale = tuple(c.getAttr('FitSkeleton.scale')[0]) if c.objExists('FitSkeleton') else (0.,0.,0.)
        axis = c.upAxis(query=True, axis=True)
        self._transaction_changed = True
        if not merge:
            for role in SOURCE_FIT_REPLACE_ROLES:
                if c.objExists(role):
                    c.delete(role)
        with self._source_fit_import_namespace() as raw:
            if merge:
                namespace = (self.namespace+':' if self.namespace else '')+'Merge'
                if raw.namespace(exists=':'+namespace):
                    raw.namespace(removeNamespace=':'+namespace)
                raw.file(str(source), i=True, renameAll=True, namespace=namespace, options='v=0')
                self._merge_source_fit_scene(raw, namespace, policy)
            else:
                self._import_source_fit_file(raw, source)
        if scale[0] != 0.:
            c.setAttr('FitSkeleton.scale', *scale, type='float3')
        if c.objExists('Group|Main') and not c.objExists('Group|Main|FitSkeleton') and c.objExists('FitSkeleton'):
            c.parent('FitSkeleton','Group|Main')
        if c.objExists('FitSkeleton'):
            if not c.attributeQuery('fitSkeletonTemplate', node='FitSkeleton', exists=True):
                c.addAttr('FitSkeleton', longName='fitSkeletonTemplate', dataType='string')
            c.setAttr('FitSkeleton.fitSkeletonTemplate', template_name or source.stem, type='string')
            if axis == 'z':
                self.flip_character_scene_up_axis('FitSkeleton','z')
            self._ensure_source_fit_display_settings()
        return tuple(c.listRelatives('FitSkeleton', allDescendents=True, type='joint', fullPath=True) or ())

    def _import_source_fit_file(self, raw, source):
        if not self.namespace:
            return raw.file(str(source), i=True, renamingPrefix='AdvancedSkeleton', options='v=0')
        # Maya's renamingPrefix and namespace import flags are alternatives.
        # Import into an owned child namespace, then reproduce prefix-on-clash
        # while moving only those newly imported identities into the character.
        namespace = self.namespace+':AdvancedSkeletonImport'
        if raw.namespace(exists=':'+namespace):
            raw.namespace(removeNamespace=':'+namespace)
        raw.file(str(source), i=True, namespace=namespace, options='v=0')
        own = CharacterIdentity(self.namespace)
        while True:
            nodes = raw.ls(namespace+':*') or ()
            if not nodes:
                break
            node = nodes[0]
            name = self._source_import_leaf(node, namespace)
            if raw.objExists(own.to_scene(name)):
                name = 'AdvancedSkeleton_'+name
            raw.rename(node, ':'+own.to_scene(name))
        raw.namespace(removeNamespace=':'+namespace)

    @staticmethod
    def _source_import_leaf(node, namespace):
        leaf = node.rsplit('|',1)[-1].lstrip(':')
        prefix = namespace+':'
        if not leaf.startswith(prefix):
            raise ValueError('导入节点不属于当前 Fit 暂存命名空间：'+node)
        return leaf[len(prefix):].split(':',1)[0]

    def _merge_source_fit_scene(self, raw, namespace, policy):
        """Two explicit character namespaces form the import transfer boundary."""
        own = CharacterIdentity(self.namespace or '')
        imported = CharacterIdentity(namespace)
        fit = own.to_scene('FitSkeleton')
        merge_fit = imported.to_scene('FitSkeleton')
        locked = raw.getAttr(fit+'.lockCenterJoints')
        raw.setAttr(fit+'.lockCenterJoints',False)
        if policy != SourceFitMergePolicy.BOTH:
            origin, target = ((imported, own) if policy == SourceFitMergePolicy.EXISTING else (own, imported))
            root = merge_fit if policy == SourceFitMergePolicy.EXISTING else fit
            for joint in raw.listRelatives(root, allDescendents=True, type='joint') or ():
                if not raw.objExists(joint):
                    continue
                counterpart = target.to_scene(origin.to_local(joint))
                if raw.objExists(counterpart):
                    raw.delete(joint)
                    continue
                parents = raw.listRelatives(joint, parent=True) or ()
                if parents:
                    counterpart_parent = target.to_scene(origin.to_local(parents[0]))
                    if raw.objExists(counterpart_parent):
                        raw.parent(joint,counterpart_parent)
        roots = raw.listRelatives(merge_fit, children=True, type='joint') or ()
        if roots:
            raw.parent(roots,fit)
        if raw.objExists(merge_fit):
            for joint in raw.listRelatives(fit, allDescendents=True, type='joint') or ():
                for kind in 'tr':
                    for axis in 'xyz':
                        raw.setAttr(joint+'.'+kind+axis, lock=False)
            if not raw.attributeQuery('drivingSystem',node=fit,exists=True):
                raw.addAttr(fit,longName='drivingSystem',attributeType='message',
                            multi=True,indexMatters=False,keyable=False)
            for attribute in raw.listAttr(merge_fit,userDefined=True,multi=True) or ():
                if not attribute.startswith('drivingSystem'):
                    continue
                plug = merge_fit+'.'+attribute
                sources = raw.listConnections(plug,source=True,destination=False,plugs=True) or ()
                if sources:
                    raw.connectAttr(sources[0],fit+'.drivingSystem',nextAvailable=True)
                    raw.disconnectAttr(sources[0],merge_fit+'.drivingSystem',nextAvailable=True)
                destinations = raw.listConnections(plug,source=False,destination=True,plugs=True) or ()
                if destinations:
                    name = attribute.split('[',1)[0]
                    if not raw.attributeQuery(name,node=fit,exists=True):
                        raw.addAttr(fit,longName=name,attributeType='bool',defaultValue=True,
                                    multi=True,keyable=False)
                    raw.connectAttr(fit+'.'+attribute,destinations[0],force=True)
            raw.delete(merge_fit)
        while True:
            nodes = raw.ls(namespace+':*') or ()
            if not nodes:
                break
            node = nodes[0]
            name = self._source_import_leaf(node, namespace)
            candidate = source_fit_import_rename(name,lambda item:raw.objExists(own.to_scene(item)))
            raw.rename(node, ':'+own.to_scene(candidate))
        if locked:
            raw.setAttr(fit+'.lockCenterJoints',True)
        raw.namespace(removeNamespace=':'+namespace)

    def import_source_fit_limb(self, source, *, choose=None):
        """asFitSkeletonLimbsImport's prefix, branch and SDK transfer rules."""
        self._require_transaction()
        source = Path(source).resolve()
        if not source.is_file() or source.suffix.lower() != '.ma':
            raise ValueError('原版 Fit limb 导入需要已有 Maya ASCII 资产文件')
        c = self._cmds
        scale = tuple(c.getAttr('FitSkeleton.scale')[0]) if c.objExists('FitSkeleton') else (1.,1.,1.)
        self._transaction_changed = True
        with self._source_fit_import_namespace() as raw:
            self._import_source_fit_file(raw, source)
        if c.objExists('Group|FitSkeleton') and c.objExists('|FitSkeleton'):
            c.rename('|FitSkeleton','AdvancedSkeleton_FitSkeleton')
        imported = 'AdvancedSkeleton_FitSkeleton'
        moved = []
        if c.objExists(imported) and c.objExists('FitSkeleton'):
            c.setAttr(imported+'.scale',*scale,type='float3')
            dialog = ''
            roots = tuple(c.listRelatives(imported,children=True,type='transform',fullPath=True) or ())
            for root in roots:
                name = root.rsplit('|',1)[-1]
                counterparts = tuple(c.ls(name,long=True) or ())
                if len(counterparts) > 1:
                    if choose is None:
                        raw = getattr(c,'raw',c)
                        dialog = raw.confirmDialog(title='Confirm',message=name+' already exist',
                            button=('Replace','Merge'),defaultButton='Replace',dismissString='Merge')
                    else:
                        dialog = choose(name)
                if dialog == 'Replace':
                    for counterpart in counterparts:
                        if counterpart == root:
                            continue
                        parents = c.listRelatives(counterpart,parent=True,fullPath=True) or ()
                        c.delete(counterpart)
                        moved.append(c.parent(root,parents[0] if parents else 'FitSkeleton')[0])
                else:
                    moved.append(c.parent(root,'Root' if c.objExists('Root') else 'FitSkeleton')[0])
            for curve in c.ls('AdvancedSkeleton_*',type='animCurveUA') or ():
                name = curve.replace('AdvancedSkeleton_','',1)
                if c.objExists(name):
                    c.delete(curve)
            if c.attributeQuery('drivingSystem',node=imported,exists=True):
                curves = c.listConnections(imported+'.drivingSystem') or ()
                if not c.attributeQuery('drivingSystem',node='FitSkeleton',exists=True):
                    c.addAttr('FitSkeleton',longName='drivingSystem',attributeType='message',
                              multi=True,indexMatters=False,keyable=False)
                for curve in curves:
                    c.connectAttr(curve+'.drivingSystemOut','FitSkeleton.drivingSystem',nextAvailable=True)
                for attribute in c.listAttr(imported,userDefined=True) or ():
                    if not attribute.startswith('drivingSystem_'):
                        continue
                    if not c.attributeQuery(attribute,node='FitSkeleton',exists=True):
                        c.addAttr('FitSkeleton',longName=attribute,attributeType='bool',
                                  defaultValue=True,multi=True,keyable=False)
                    targets = c.listConnections(imported+'.'+attribute,plugs=True) or ()
                    for index,target in enumerate(targets):
                        c.connectAttr('FitSkeleton.'+attribute+'['+str(index)+']',target,force=True)
            c.delete(imported)
        if c.objExists('FitSkeleton'):
            self._ensure_source_fit_display_settings()
        return tuple(moved)
