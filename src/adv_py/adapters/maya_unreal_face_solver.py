"""Python scene evaluation of native FaceRig export; no MEL rig procedures."""
from contextlib import contextmanager
from fnmatch import fnmatchcase

from adv_py.core.unreal_face_solver import (
    SAMPLED_ON_FACE, JointSolverSample, TOLERANCE, sample_values,
    middle_lid_index, positive_quaternion, driven_channels, channel_name,
)
from .maya_driving_systems import MayaDrivingSystemsHost
from .maya_unreal_face_display import leaf, parent, vector, display_document


class _Cancelled(Exception):
    pass


class MayaUnrealFaceSolverHost(MayaDrivingSystemsHost):
    def preflight_unreal_face_solver(self):
        self._unique('FaceJoint_M', 'joint')
        pose = self.read_face_build_pose()
        self.preflight_face_build_pose(pose)

    def _face_solver_range(self, control, attribute):
        c = self._cmds
        for short, long in (('t', 'translate'), ('r', 'rotate'), ('s', 'scale')):
            for axis in 'XYZ':
                if attribute in (short + axis.lower(), long + axis):
                    return tuple(c.transformLimits(control, query=True, **{short + axis.lower(): True}))
        values = []
        for exists, query, hard_exists, hard_query in (
                ('softMinExists', 'softMin', 'minExists', 'minimum'),
                ('softMaxExists', 'softMax', 'maxExists', 'maximum')):
            if c.attributeQuery(attribute, node=control, **{exists: True}):
                number = c.attributeQuery(attribute, node=control, **{query: True})[0]
            elif c.attributeQuery(attribute, node=control, **{hard_exists: True}):
                number = c.attributeQuery(attribute, node=control, **{hard_query: True})[0]
            else:
                # MEL's dynamic float array pads index zero when only a
                # maximum is supplied, but has size one for minimum alone.
                if not values:
                    values.append(0.)
                continue
            if query == 'softMax' and len(values) == 0:
                values.append(0.)
            values.append(number)
        return tuple(values) if len(values) > 1 else ()

    def _face_solver_drivers(self):
        c = self._cmds
        controls = list(self.original_driving_systems())
        controls.extend(control for control in SAMPLED_ON_FACE if c.objExists(control))
        rows = []
        for control in controls:
            name = leaf(control)
            if name == 'EyeBrowInner_L':
                continue
            paths = c.ls(control, long=True) or []
            if not paths:
                continue
            sampled = name in SAMPLED_ON_FACE
            normalized = paths[0].replace(self.namespace + ':' if self.namespace else '', '')
            if not sampled and not fnmatchcase(normalized, '*|FaceGroup*'):
                continue
            attrs = SAMPLED_ON_FACE[name] if sampled else self.original_driving_attributes(control)
            rows.extend((control, attr, sampled) for attr in attrs
                        if attr != 'visibility' and not c.getAttr(control + '.' + attr, lock=True))
        return tuple(rows)

    @contextmanager
    def _face_solver_progress(self, maximum):
        c = self._cmds
        raw = getattr(c, 'raw', c)
        bar = None
        if not raw.about(batch=True):
            from maya import mel
            # Read Maya's existing main progress bar, never open another window.
            bar = mel.eval('$advPyProgress = $gMainProgressBar')
            raw.progressBar(bar, edit=True, beginProgress=True, isInterruptable=True,
                status='Computing Unreal Face Solver Data', minValue=0, maxValue=max(1, maximum))
        def step(index, plug):
            if bar:
                if raw.progressBar(bar, query=True, isCancelled=True):
                    raise _Cancelled()
                raw.progressBar(bar, edit=True, progress=index, status='Computing Delta ' + plug)
        try:
            yield step
        finally:
            if bar:
                raw.progressBar(bar, edit=True, endProgress=True)

    def _face_solver_transform(self, joint, kind):
        from .maya_original_transform_channels import original_transform_values
        return original_transform_values(self._cmds, joint, kind)

    def _face_solver_sample(self, joint, dm=None):
        c = self._cmds
        return JointSolverSample(self._face_solver_transform(joint, 'translate'),
            self._face_solver_transform(joint, 'scale'),
            tuple(c.xform(joint, query=True, worldSpace=True, translation=True)),
            positive_quaternion(vector(c, dm + '.outputQuat')) if dm else (0., 0., 0., 1.))

    def _face_solver_affects(self, plug, values, joint, neutral):
        c = self._cmds
        if not c.objExists(joint):
            return True
        c.setAttr(plug, neutral)
        matrix = c.xform(joint, query=True, worldSpace=True, matrix=True)
        try:
            for value in values:
                c.setAttr(plug, value)
                actual = c.xform(joint, query=True, worldSpace=True, matrix=True)
                if any(abs(a - b) > TOLERANCE for a, b in zip(actual, matrix)):
                    return True
            return False
        finally:
            c.setAttr(plug, neutral)

    def _face_solver_enabled_joints(self, joints, control, plug, values, neutral):
        c = self._cmds
        skips = []
        if (leaf(control) not in ('upperLip_M', 'lowerLip_M') and c.objExists('upperLipJoint0_M')
                and not self._face_solver_affects(plug, values, 'upperLipJoint0_M', neutral)):
            skips.append('*LipJoint*_*')
        for prefix, pattern in (('upperLidMain', '*upperLid*'), ('lowerLidMain', '*lowerLid*')):
            for side in ('_R', '_L'):
                index = middle_lid_index(i for i in range(100) if c.objExists(prefix + str(i) + side))
                if index is not None and not self._face_solver_affects(
                        plug, values, prefix + str(index) + side, neutral):
                    skips.append(pattern + side)
        return tuple(joint for joint in joints if not any(fnmatchcase(leaf(joint), pattern) for pattern in skips))

    def capture_unreal_face_solver(self):
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        drivers = self._face_solver_drivers()
        joints = tuple(c.listRelatives('FaceJoint_M', allDescendents=True, type='joint') or []) + ('FaceJoint_M',)
        self.apply_face_build_pose(self.read_face_build_pose())
        stale = c.ls('asUnrealFaceSolverRotExport_*') or []
        if stale:
            c.delete(stale)
        nodes, matrices = [], {}
        result, rest_joints = [], []
        parents = {}
        for joint in joints:
            current = joint
            while current and current not in parents:
                ancestor = parent(c, current)
                parents[leaf(current)] = leaf(ancestor)
                if not ancestor:
                    break
                current = ancestor
        try:
            for index, joint in enumerate(joints):
                local = c.createNode('multMatrix', name='asUnrealFaceSolverRotExportLocalMM_' + str(index), skipSelect=True)
                nodes.append(local)
                c.connectAttr(joint + '.worldMatrix[0]', local + '.matrixIn[0]')
                ancestor = parent(c, joint)
                if ancestor:
                    c.connectAttr(ancestor + '.worldInverseMatrix[0]', local + '.matrixIn[1]')
                delta = c.createNode('multMatrix', name='asUnrealFaceSolverRotExportMM_' + str(index), skipSelect=True)
                nodes.append(delta)
                dm = c.createNode('decomposeMatrix', name='asUnrealFaceSolverRotExportDM_' + str(index), skipSelect=True)
                nodes.append(dm)
                c.connectAttr(local + '.matrixSum', delta + '.matrixIn[1]')
                c.connectAttr(delta + '.matrixSum', dm + '.inputMatrix')
                matrices[joint] = (local, delta, dm)
            with self._face_solver_progress(len(drivers)) as step:
                for index, (control, attr, sampled) in enumerate(drivers, 1):
                    plug = control + '.' + attr
                    if not c.getAttr(plug, settable=True):
                        continue
                    step(index, plug)
                    limits = (-1., 1.) if sampled else self._face_solver_range(control, attr)
                    if len(limits) < 2:
                        continue
                    original = c.getAttr(plug)
                    values = sample_values(*limits, original)
                    try:
                        c.setAttr(plug, original)
                        enabled = self._face_solver_enabled_joints(joints, control, plug, values, original)
                        base = {}
                        from maya.api import OpenMaya as om
                        for joint in enabled:
                            base[leaf(joint)] = self._face_solver_sample(joint)
                            local, delta, _ = matrices[joint]
                            inverse = om.MMatrix(vector(c, local + '.matrixSum')).inverse()
                            c.setAttr(delta + '.matrixIn[0]', *tuple(inverse), type='matrix')
                        samples = []
                        for value in values:
                            c.setAttr(plug, value)
                            samples.append({leaf(joint): self._face_solver_sample(joint, matrices[joint][2]) for joint in enabled})
                        driven = driven_channels(tuple(leaf(joint) for joint in joints), parents, base, samples, values)
                    finally:
                        c.setAttr(plug, original)
                    if driven:
                        ancestor = parent(c, control)
                        result.append(dict(control=leaf(control), channel=channel_name(attr, driver=not sampled),
                            mayaAttribute=leaf(control) + '.' + attr, mayaDriverMin=limits[0], mayaDriverMax=limits[1],
                            controlParent=leaf(ancestor),
                            controlOffsetLocation=list(vector(c, ancestor + '.translate')) if ancestor else [0., 0., 0.],
                            controlOffsetScale=list(vector(c, ancestor + '.scale')) if ancestor else [1., 1., 1.],
                            driven=driven))
                        rest_joints.extend(row['bone'] for row in driven if row['bone'] not in rest_joints)
        except _Cancelled:
            c.warning('WriteUnrealFaceSolverDataFile 已取消')
            return None
        finally:
            existing = [node for node in nodes if c.objExists(node)]
            if existing:
                c.delete(existing)
            # Native asWriteUnrealFaceSolverDataFile dirties evaluation globally;
            # this command has no node-address arguments to namespace-map.
            getattr(c, 'raw', c).dgdirty(allPlugs=True)
        document = display_document(c, rest_joints)
        document['drivers'] = result
        return document
