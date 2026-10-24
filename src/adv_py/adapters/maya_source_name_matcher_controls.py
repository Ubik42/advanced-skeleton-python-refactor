"""Original NameMatcher BlendShapes Control and automatic FK curve scaling."""
from dataclasses import replace
from fnmatch import fnmatchcase

from adv_py.core.character_registry import CharacterChannel,REGISTRY_NAME,encode_registration
from .maya_original_control_identity import registration,control_roles,leaf
from .maya_original_transform_channels import lock_original_transform_channels
from .maya_game_registration import scene_ids,remember_generated_nodes,_write_members
from .maya_driving_registration import _write_string
from .maya_source_name_matcher_context import mapping_action


class MayaSourceNameMatcherControlsMixin:
    def capture_source_name_matcher_character_boundary(self,source_root):
        from .maya_source_mocap_boundary import capture_character
        return capture_character(self,source_root)

    def keep_source_name_matcher_animation(self,source_root):
        from .maya_source_name_matcher_animation import keep
        from adv_py.application.name_matcher_animation import NameMatcherKeptAnimationResult
        clone,count=keep(self,source_root,self.capture_name_matcher_source_animation(source_root))
        return NameMatcherKeptAnimationResult(clone,count)

    def bake_source_name_matcher_kept_animation(self,source_root,rows,rules):
        from .maya_source_name_matcher_animation import bake
        return bake(self,source_root,rows,rules)

    def capture_source_name_matcher_mocap_boundary(self,mapping):
        from .maya_source_mocap_boundary import capture
        return capture(self,mapping)

    def plan_source_name_matcher_mocap_mapping(self,source_root,rows,rules,*,source_namespace=None):
        """MEL's live target lookup, including its last non-Group full path.

        Only MoCapConnect performs this collision branch. Skin transfer and
        attachment retain their own original lookup and operation order.
        """
        from adv_py.core.source_name_matcher import source_name_matcher_targets
        from adv_py.core.name_matcher_fit import NameMatcherConstraintPair,NameMatcherConstraintPlan
        c=self._cmds;raw=getattr(c,'raw',c)
        namespace=(source_root.rsplit('|',1)[-1].rpartition(':')[0]
            if source_namespace is None else source_namespace)
        joints=c.listRelatives('DeformationSystem',allDescendents=True,type='joint',fullPath=True) or ()
        pairs,missing=[],[]
        for joint,target in source_name_matcher_targets(joints,rows,rules,namespace=namespace):
            paths=raw.ls(target,long=True) or ()
            if not paths:
                missing.append(target);continue
            resolved=paths[0]
            if len(paths)>1:
                for path in paths:
                    if '|Group|' not in path:resolved=path
            pairs.append(NameMatcherConstraintPair(joint,resolved))
        return NameMatcherConstraintPlan(tuple(pairs),tuple(dict.fromkeys(missing)))

    @mapping_action
    def zero_out_source_name_matcher_joints(self, source_root, rows, rules, *,template_name=None,source_namespace=None):
        """Native catchQuiet: a locked rotation skips that joint, not the pass."""
        from adv_py.core.source_name_matcher import source_name_matcher_targets
        from adv_py.application.name_matcher_mocap_operations import NameMatcherZeroOutResult
        self._require_transaction()
        c = self._cmds
        raw = getattr(c,'raw',c)
        namespace = (source_root.rsplit('|',1)[-1].rpartition(':')[0]
                     if source_namespace is None else source_namespace)
        joints = c.listRelatives('DeformationSystem',type='joint',
            allDescendents=True,fullPath=True) or ()
        resolved = source_name_matcher_targets(joints,rows,rules,namespace=namespace)
        count,missing = 0,[]
        for _,target in resolved:
            if not raw.objExists(target):
                missing.append(target)
                continue
            self._transaction_changed = True
            try:
                raw.setAttr(target+'.rotate',0,0,0,type='float3')
            except RuntimeError:
                # MEL catchQuiet covers the setAttr itself, including locked
                # axes or connected inputs. It never unlocks/disconnects them.
                pass
            count += 1
        if template_name is not None:
            from .maya_source_mocap_templates import apply_zero_out_hook
            apply_zero_out_hook(self,template_name,namespace)
        return NameMatcherZeroOutResult(count,tuple(missing))

    @mapping_action
    def transfer_source_name_matcher_skin(self, source_root, rows, rules):
        from .maya_source_name_matcher_skin import transfer_source_skin
        return transfer_source_skin(self, source_root, rows, rules)

    @mapping_action
    def attach_source_name_matcher_skeleton(self, source_root, rows, rules):
        """Native AutoRigConstraint replaces its four conventional constraints."""
        from adv_py.core.source_name_matcher import source_name_matcher_name
        from adv_py.application.name_matcher_constraints import NameMatcherConstraintResult
        self._require_transaction()
        c = self._cmds
        raw = getattr(c,'raw',c)
        namespace = source_root.rsplit('|',1)[-1].rpartition(':')[0]
        missing,count = [],0
        for joint in c.listRelatives('DeformationSystem',type='joint',allDescendents=True,fullPath=True) or ():
            name = leaf(joint)
            if not name.endswith(('_R','_L','_M')):continue
            base,side = name[:-2],name[-1]
            matching = tuple(row for row in rows if row.fit_joint==base)
            if not matching:continue
            row = matching[-1]
            target = source_name_matcher_name(row.source_base,
                replace(rules,right=rules.left) if side=='L' else rules,
                middle=side=='M',namespace=namespace)
            if not raw.objExists(target):
                missing.append(target)
                raw.warning('Expected targetJoint:"'+target+'" not found, skipping this.')
                continue
            self._transaction_changed = True
            raw.transformLimits(target,enableRotationX=(False,False),enableRotationY=(False,False),
                enableRotationZ=(False,False),enableTranslationX=(False,False),
                enableTranslationY=(False,False),enableTranslationZ=(False,False),
                enableScaleX=(False,False),enableScaleY=(False,False),enableScaleZ=(False,False))
            if not raw.referenceQuery(target,isNodeReferenced=True):
                lock_original_transform_channels(raw,target)
            raw.select(target,replace=True)
            for suffix in ('parentConstraint1','pointConstraint1','orientConstraint1','scaleConstraint1'):
                name = target+'_'+suffix
                if raw.objExists(name):raw.delete(name)
            source = self.scene_address(joint)
            raw.pointConstraint(source,target,maintainOffset=True)
            raw.orientConstraint(source,target,maintainOffset=True)
            raw.scaleConstraint(source,target,maintainOffset=True)
            count += 1
        return NameMatcherConstraintResult(count,tuple(missing))

    @mapping_action
    def create_source_name_matcher_blend_controls(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c,'raw',c)
        if raw.objExists('FRM_faceGUI'):
            return ()
        before = registration(self)
        ids = scene_ids(self)
        main=next((node for node in ('Main','AdvPy_Global') if c.objExists(node)),None)
        height = float(c.getAttr(main+'.height')) if main is not None else 10.
        shapes = tuple(raw.ls(type='blendShape') or ())
        aliases = {shape:tuple(name.lstrip('.') for name in raw.listAttr(
            shape+'.weight',multi=True) or ()) for shape in shapes}
        all_aliases,common = [],[]
        for shape in shapes:
            for name in aliases[shape]:
                if name in all_aliases:
                    if name not in common:common.append(name)
                else:all_aliases.append(name)
        self._transaction_changed = True
        created,channels = [],[]
        actual_controls = {}
        for index in range(-1,len(shapes)):
            if index==-1:
                if not common:continue
                shape = 'CommonBlendShapes'
            else:shape = shapes[index]
            # External blendShape nodes keep their physical addresses; control
            # creation belongs to the receiving character's namespace.
            requested = leaf(shape)+'Ctrl'
            control = c.circle(name=requested,center=(0,0,0),normal=(0,1,0),
                sweep=360,radius=1,degree=3,useTolerance=False,tolerance=.01,
                sections=8,constructionHistory=False)[0]
            constraint = c.parentConstraint('Head_M',control)[0]
            c.scaleConstraint('Head_M',control)
            c.setAttr(constraint+'.target[0].targetOffsetTranslateX',height/40.*index)
            c.setAttr(constraint+'.target[0].targetOffsetTranslateZ',height/-10.)
            curve = (c.listRelatives(control,shapes=True,type='nurbsCurve') or [None])[0]
            if curve is None:raise RuntimeError('NameMatcher BlendShape 控制器缺少曲线')
            c.setAttr(curve+'.overrideEnabled',True)
            c.setAttr(curve+'.overrideColor',17)
            lock_original_transform_channels(c,control,True,True,True,True)
            actual_controls[shape] = control
            created.append(control)
            if index==-1:continue
            for name in aliases[shape]:
                if name=='V_None':continue
                owner = actual_controls['CommonBlendShapes'] if name in common else control
                if not c.attributeQuery(name,node=owner,exists=True):
                    c.addAttr(owner,longName=name,attributeType='double',keyable=True,
                              softMinValue=0,hasSoftMinValue=True,softMaxValue=1,
                              hasSoftMaxValue=True,defaultValue=0)
                    channels.append((owner,name))
                raw.connectAttr(self.scene_address(owner)+'.'+name,shape+'.'+name,force=True)
            if not c.listAttr(control,keyable=True):
                c.delete(control)
                created.remove(control)
        common_control = actual_controls.get('CommonBlendShapes')
        if common_control and not c.listAttr(common_control,keyable=True):
            c.delete(common_control)
            created.remove(common_control)
        raw.refresh()
        added = remember_generated_nodes(self,ids)
        if before is not None:
            paths = tuple(dict.fromkeys((*[node.path for node in before.nodes],
                *(path for path in added if c.nodeType(path) in ('transform','joint')))))
            nodes = tuple(self.capture_character_registration_node(path) for path in paths)
            known = {channel.node+'.'+channel.attribute for channel in before.channels}
            extras = []
            for control,name in channels:
                path = c.ls(control,long=True)[0]
                if path+'.'+name not in known:
                    key = 'nameMatcher.blendShape.'+leaf(path)+'.'+name
                    # Native limits are soft; the registry stores hard limits.
                    extras.append(CharacterChannel(key,path,name))
            updated = replace(before,nodes=nodes,channels=before.channels+tuple(extras))
            _write_members(self,nodes)
            _write_string(c,REGISTRY_NAME+'.advPyRegistryDocument',encode_registration(updated))
        return tuple(created)

    def auto_scale_source_name_matcher_fk_curves(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c,'raw',c)
        choice = raw.confirmDialog(title='Auto Scale ?',message='Auto Scale Control Curves to geometry ?',
            button=('Yes','No'),defaultButton='Yes',dismissString='No')
        if choice!='Yes':return ()
        selected = tuple(raw.ls(selection=True,long=True) or ())
        members = tuple(c.sets('ControlSet',query=True) or ())
        skin = c.getAttr('FitSkeleton.objectsSkin') if c.objExists('FitSkeleton.objectsSkin') else ''
        if not skin:
            maximum = 0
            for shape in raw.ls(type='mesh') or ():
                count = int(raw.polyEvaluate(shape,vertex=True))
                if count<=maximum:continue
                maximum = count
                parents = raw.listRelatives(shape,parent=True,fullPath=True) or ()
                if parents:skin = parents[0]
            if skin and c.objExists('FitSkeleton.objectsSkin'):
                c.setAttr('FitSkeleton.objectsSkin',skin,type='string')
        roles = control_roles(registration(self))
        controls = tuple(control for control in members
            if fnmatchcase(roles.get(leaf(control),leaf(control)),'FK*_*')
            and not roles.get(leaf(control),leaf(control)).startswith('FKIK')
            and not roles.get(leaf(control),leaf(control)).endswith('_L')
            and c.listRelatives(control,children=True,type='nurbsCurve'))
        self._transaction_changed = True
        try:
            raw.select(clear=True)
            if controls:
                c.select(controls,replace=True)
                from adv_py.core.character_identity import CharacterIdentity
                # Skin may belong to a separate model namespace, including
                # root namespace. Preserve its physical read-only address.
                paths = raw.ls(skin,long=True) or ()
                if len(paths)!=1:raise ValueError('自动缩放需要唯一的 Skin 对象')
                mesh = CharacterIdentity(self.namespace or '').to_local(paths[0])
                self.project_control_curves(controls,mesh,strict=False)
                from .maya_source_control_curve_mirror import mirror_source_control_curves
                mirror_source_control_curves(self,False,'ControlSet')
        finally:
            raw.select(selected,replace=True) if selected else raw.select(clear=True)
        return controls
