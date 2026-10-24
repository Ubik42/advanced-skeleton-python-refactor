"""Original ADV BodyRig schema 2 discovery, MEL 23889–24234."""
from math import floor
import re

from adv_py.core.fit_ik import fit_joint_ik_info
from adv_py.core.source_fit_identity import source_fit_build_name
from adv_py.core.original_body_rig import dominant_axis
from adv_py.core.original_control_orientation import original_control_identity
from .maya_driving_systems import MayaDrivingSystemsHost
from .maya_original_body_rig_data import MayaOriginalBodyRigDataMixin
from .maya_unreal_face_display import leaf, parent


class MayaOriginalBodyRigHost(MayaOriginalBodyRigDataMixin, MayaDrivingSystemsHost):
    def preflight_original_body_rig(self):
        c = self._cmds
        if c.objExists('|root') or c.objExists('UnrealRoot'):
            raise ValueError('已找到 Unreal 关节；请先导出未重命名的原版 ADV 绑定')
        self._unique('ControlSet', 'objectSet')
        self._unique('DeformSet', 'objectSet')

    def _body_rig_deform_chain(self, start, end):
        c = self._cmds
        reverse = []
        current = end
        for _ in range(512):
            if not current:
                break
            reverse.append(current)
            if leaf(current) == leaf(start):
                return list(reversed(reverse))
            ancestors = c.listRelatives(current, parent=True, type='joint') or []
            if not ancestors:
                return []
            current = ancestors[0]
        return []

    def _body_rig_reverse_feet(self, systems, append):
        c = self._cmds
        result = []
        for system in systems:
            control = system['control']
            append(control, 'Main', system['end'], '', 'IK', 'Box_Thick', True, system['ik'])
            if c.objExists(system['pole']):
                append(system['pole'], 'Main', system['middle'], '', 'IKPole', 'Sphere_Solid', True)
            reverse, rolls = [], []
            for candidate in reversed(c.listRelatives(control, allDescendents=True, type='transform') or []):
                name = leaf(candidate)
                if (not c.sets(candidate, isMember='ControlSet') or not c.listRelatives(candidate, shapes=True)
                        or not name.startswith(('Roll', 'IK'))):
                    continue
                reverse.append(candidate)
                if name.startswith('Roll'):
                    rolls.append(candidate)
            if not rolls:
                continue
            reverse_names = {leaf(candidate) for candidate in reverse}
            for candidate in reverse:
                parent_control = control
                walk = parent(c, candidate)
                while walk:
                    if leaf(walk) == leaf(control):
                        break
                    if leaf(walk) in reverse_names:
                        parent_control = walk
                        break
                    walk = parent(c, walk)
                kind, joint = 'ReverseFoot', ''
                if leaf(candidate).startswith('IK'):
                    kind = 'ReverseFootToe'
                    joint = re.sub(r'^IKhybrid', '', leaf(candidate), count=1)
                    if joint == leaf(candidate):
                        joint = re.sub(r'^IK', '', joint, count=1)
                    if not c.objExists(joint) or c.nodeType(joint) != 'joint':
                        joint = ''
                append(candidate, parent_control, joint, '', kind, 'Circle_Thick', True)
            result.append(dict(ikControl=leaf(control), endJoint=leaf(system['end']),
                targetParent=leaf(rolls[-1]), controls=[leaf(candidate) for candidate in reverse],
                rock=self._body_rig_rock(control)))
        return result

    def _body_rig_splines(self, append):
        c = self._cmds
        if not c.objExists('FitSkeleton'):
            return []
        hierarchy = self.capture_fit_hierarchy('FitSkeleton')
        labels = {joint.path: self.read_joint_label(joint.path) for joint in hierarchy.joints}
        nodes = {joint.path: joint for joint in hierarchy.joints}
        paths = {leaf(joint.path): joint.path for joint in hierarchy.joints}
        result, names = [], set()
        for fit in c.listRelatives('FitSkeleton', type='joint', allDescendents=True) or []:
            info = fit_joint_ik_info(hierarchy, labels, paths[leaf(fit)])
            if info is None or info.solver != 'ikSplineSolver':
                continue
            system_name = source_fit_build_name(info.name)
            for side in ('_M', '_L', '_R'):
                name = system_name + side
                if name in names or not c.objExists('IK' + system_name + '1' + side):
                    continue
                # The source remembers the system before checking its chain.
                names.add(name)
                chain = [source_fit_build_name(nodes[path].short_name) + side for path in info.joints
                         if c.objExists(source_fit_build_name(nodes[path].short_name) + side)]
                if len(chain) >= 2:
                    full = self._body_rig_deform_chain(chain[0], chain[-1])
                    if len(full) >= len(chain):
                        chain = full
                if len(chain) < 2:
                    continue
                count = 3 if info.control_count == 2 else info.control_count
                controls = []
                for index in range(1, count + 1):
                    control = 'IK' + system_name + str(index) + side
                    if not c.objExists(control):
                        continue
                    controls.append(control)
                    joint_index = floor((index - 1) / (count - 1) * (len(chain) - 1) + .5) if count > 1 else 0
                    append(control, 'RootX_M', chain[joint_index], '', 'SplineIK', 'Square_Thick', True)
                if len(controls) < 2:
                    continue
                switch = 'FKIK' + system_name + side
                default_ik = 1
                if c.objExists(switch) and c.objExists(switch + '.FKIKBlend'):
                    default_ik = int(c.getAttr(switch + '.FKIKBlend') >= 5)
                if c.objExists(switch):
                    append(switch, 'Main', chain[0], '', 'FKIK', 'Star4_Thick', True)
                world = c.xform(chain[1], query=True, worldSpace=True, translation=True)
                offset = self._body_rig_position_local(world, chain[0], 'asBodyRigSplineAxisProbe')
                primary, _ = dominant_axis(offset)
                result.append(dict(name=name, fitJoint=leaf(fit), fitStartJoint=leaf(info.start),
                    fitMiddleJoint=leaf(info.middle), fitEndJoint=leaf(info.end), numControls=count,
                    sourceNumControls=info.control_count, solver='ikSplineSolver', startJoint=leaf(chain[0]),
                    middleJoint=source_fit_build_name(nodes[info.middle].short_name) + side,
                    endJoint=leaf(chain[-1]), joints=[leaf(joint) for joint in chain],
                    controls=[leaf(control) for control in controls], primaryAxis=primary,
                    switchControl=switch, defaultIK=default_ik))
        return result

    def capture_original_body_rig(self):
        from .maya_original_body_rig_roles import body_rig_role_scope
        with body_rig_role_scope(self):
            return self._capture_original_body_rig()

    def _capture_original_body_rig(self):
        self._require_transaction()
        # Curve readers and native OPM-safe axis probes create scratch nodes.
        self._transaction_changed = True
        c = self._cmds
        members = c.sets('ControlSet', query=True) or []
        controls, names, rp_systems = [], set(), []
        def append(control, ancestor, joint, fit, kind, gizmo, world_space, ik=None):
            name = leaf(control)
            if name in names:
                return
            controls.append(self._body_rig_control(control, ancestor, joint, fit, kind, gizmo, world_space, ik))
            names.add(name)
        append('Main', 'MainSystem', 'DeformationSystem', '', 'Main', 'Circle_Thick', True)
        if c.objExists('RootX_M'):
            append('RootX_M', 'Main', 'Root_M', '', 'Root', 'Arrow4_Thin', True)
        for member in members:
            name = leaf(member)
            if not name.startswith('FKIK') or not c.objExists(member + '.FKIKBlend'):
                continue
            control = name.replace('FKIK', 'IK', 1)
            if not c.objExists(control):
                continue
            side = '_' + name.split('_')[-1]
            start, middle, end = (c.getAttr(member + '.' + attr) + side
                                  for attr in ('startJoint', 'middleJoint', 'endJoint'))
            pole = name.replace('FKIK', 'Pole', 1)
            ik = self._body_rig_ik(start, middle, end, pole, c.getAttr(member + '.FKIKBlend') >= 5)
            rp_systems.append(dict(control=control, start=start, middle=middle, end=end, pole=pole, ik=ik))
            append(member, 'Main', start, '', 'FKIK', 'Star4_Thick', True, ik)
        reverse_feet = self._body_rig_reverse_feet(rp_systems, append)
        splines = self._body_rig_splines(append)
        ik_ends = {leaf(system['end']) for system in rp_systems}
        for joint in reversed(c.listRelatives('DeformationSystem', type='joint', allDescendents=True) or []):
            if not c.sets(joint, isMember='DeformSet'):
                continue
            role = leaf(joint)
            control = 'FK' + role
            if not c.objExists(control) or control in names:
                continue
            parts = [part for part in role.split('_') if part]
            if len(parts) < 2:
                continue
            is_part = re.search(r'Part[0-9]', parts[0]) is not None
            if not is_part and not c.sets(control, isMember='ControlSet') and not c.sets(control, isMember='AllSet'):
                continue
            fit = parts[0]
            if not c.objExists(fit) and is_part:
                fit = re.sub(r'Part[0-9]*$', '', fit, count=1)
            if not c.objExists(fit):
                continue
            parent_joint = ''
            ancestors = c.listRelatives(joint, fullPath=True, parent=True) or []
            if ancestors:
                for candidate in reversed([part for part in ancestors[0].split('|') if part]):
                    candidate = leaf(candidate)
                    candidate_control = 'FK' + candidate
                    if candidate in ik_ends:
                        parent_joint = candidate
                        break
                    if candidate_control not in names:
                        continue
                    shape = candidate_control + 'Shape.visibility'
                    if c.objExists(shape) and c.getAttr(shape) == 0:
                        continue
                    parent_joint = candidate
                    break
            if is_part:
                parent_joint = leaf(parent(c, joint))
            parent_control = parent_joint if parent_joint in ik_ends else 'RootX_M'
            if parent_control == 'RootX_M' and c.objExists('FK' + parent_joint):
                parent_control = 'FK' + parent_joint
            if control == 'FKRoot_M' and c.objExists('RootX_M'):
                parent_control = 'RootX_M'
            append(control, parent_control, joint, '' if is_part else fit, 'FK', 'Circle_Thick', False)
        if c.objExists('RootMotion_M') and c.objExists('FKRootMotion_M'):
            append('FKRootMotion_M', 'Main', 'RootMotion_M', '', 'FK', 'Circle_Thick', False)
        if c.objExists('HipSwinger_M'):
            append('HipSwinger_M', 'FKRoot_M', 'Root_M', '', 'HipSwinger', 'Circle_Thick', True)
        for control in members:
            if not leaf(control).startswith('Bend') or leaf(control) in names:
                continue
            info = original_control_identity(leaf(control))
            joint = info.name + info.side
            if not c.objExists(joint) or c.nodeType(joint) != 'joint':
                joint = ''
            append(control, 'Main', joint, '', 'BendMid' if leaf(control).startswith('BendMid') else 'Bend', 'Circle_Thick', False)
        local_members = c.sets('AllSet', query=True) or [] if c.objExists('AllSet') else members
        for control in local_members:
            if (not c.objExists(control) or c.nodeType(control) != 'transform'
                    or not leaf(control).startswith('IKLocal') or leaf(control) in names):
                continue
            parent_control, walk = 'Main', control
            for _ in range(99):
                walk = parent(c, walk)
                if not walk:
                    break
                if leaf(walk) in names:
                    parent_control = walk
                    break
            joint = ''
            switch = self.find_original_fkik_control(control)
            if switch and c.objExists(switch + '.endJoint'):
                joint = c.getAttr(switch + '.endJoint') + original_control_identity(leaf(control)).side
            append(control, parent_control, joint, '', 'IKLocal', 'Circle_Thick', False)
        for control in members:
            paths = c.ls(control, long=True) or []
            if not paths or not any(leaf(part) == 'DrivingSystem' for part in paths[0].split('|')):
                continue
            joint = self._body_rig_driving_joint(control)
            if joint:
                append(control, 'Main', joint, '', 'DrivingSystem', 'Circle_Thick', False)
        for control in members:
            if not leaf(control).startswith('FKIK') or leaf(control) in names:
                continue
            joint = ''
            if c.objExists(control + '.startJoint'):
                joint = c.getAttr(control + '.startJoint') + '_' + leaf(control).split('_')[-1]
            append(control, 'Main', joint, '', 'FKIK', 'Star4_Thick', True)
        deform = list(c.listRelatives('DeformationSystem', type='joint', allDescendents=True) or [])
        if c.objExists('DeformationSystem'):
            deform.append('DeformationSystem')
        document = dict(schemaVersion=2, exporter='AdvancedSkeleton', exportType='AdvancedSkeletonBodyRig',
            rig=dict(controlSet='ControlSet', reverseFootSystems=reverse_feet, ikSystems=splines,
                controls=controls, joints=[self._body_rig_joint(joint) for joint in deform
                    if leaf(joint) == 'DeformationSystem' or c.sets(joint, isMember='DeformSet')]))
        if c.objExists('Main.version'):
            document['advancedSkeletonVersion'] = str(float(c.getAttr('Main.version')))
        return document
