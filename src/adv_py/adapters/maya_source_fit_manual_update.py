"""Native shared Fit manual update and Center Joints lock transitions."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.source_fit_center_locks import source_fit_center_locks


class MayaSourceFitManualUpdateMixin:
    def source_fit_orientation_context(self):
        from .maya_source_fit_aim import native_update_context
        return native_update_context(self)

    def aim_source_fit_joint(self,parent,child,snapshot,info,state):
        from .maya_source_fit_aim import aim_joint
        return aim_joint(self,parent,child,snapshot,info,state)

    def update_source_fit_orientations(self, children, *, container='FitSkeleton', recursive=False):
        from .maya_source_fit_orientation import update_orientations
        return update_orientations(self, children, container=container, recursive=recursive)

    def toggle_source_fit_mode(self):
        from .maya_source_fit_mode import toggle
        return toggle(self)

    def stop_source_fit_mode(self):
        from .maya_source_fit_mode import stop
        return stop(self)

    def set_fit_center_joint_lock_state(self, container_name, enabled):
        self._require_transaction()
        if type(enabled) is not bool:
            raise FitSkeletonValidationError('Fit 中心关节锁定状态必须是布尔值')
        container = self._resolve_transform(container_name, FitSkeletonValidationError)
        c = self._cmds
        if not c.attributeQuery('lockCenterJoints', node=container, exists=True):
            raise FitSkeletonValidationError('FitSkeleton 缺少 lockCenterJoints 原版设置')
        hierarchy = self.capture_fit_hierarchy(container)
        primary = (c.getAttr(container+'.primaryAxis', asString=True)
                   if c.attributeQuery('primaryAxis', node=container, exists=True) else 'X')
        secondary = (c.getAttr(container+'.secondaryAxis', asString=True)
                     if c.attributeQuery('secondaryAxis', node=container, exists=True) else 'Y')
        parents = {}
        if enabled:
            for joint in hierarchy.joints:
                if joint.dag_parent not in parents:
                    parents[joint.dag_parent] = tuple(c.xform(joint.dag_parent,
                        query=True, worldSpace=True, matrix=True))
            locks = dict(source_fit_center_locks(hierarchy, parents, primary, secondary))
        else:
            locks = {}
        self._transaction_changed = True
        c.setAttr(container+'.lockCenterJoints', enabled)
        for joint in hierarchy.joints:
            for kind in 'trs':
                for axis in 'xyz':
                    c.setAttr(joint.path+'.'+kind+axis, lock=False)
            for channel in locks.get(joint.path, ()):
                c.setAttr(joint.path+'.'+channel, lock=True)

    def toggle_fit_center_joint_locks(self, container_name='FitSkeleton'):
        self._require_transaction()
        container = self._resolve_transform(container_name, FitSkeletonValidationError)
        enabled = not bool(self._cmds.getAttr(container+'.lockCenterJoints'))
        self.set_fit_center_joint_lock_state(container, enabled)
        return enabled

    def manual_update_fit(self, container_name='FitSkeleton', *, from_body_build=False):
        """asFitModeManualUpdate's name, label, lock, scale and aim sequence."""
        self._require_transaction()
        c = self._cmds
        if not c.objExists(container_name):
            return
        container = self._resolve_transform(container_name, FitSkeletonValidationError)
        selected = tuple(c.ls(selection=True, long=True) or ())
        self.normalize_fit_joint_names(container)
        self.normalize_fit_ik_labels(container)
        had_locked_centers = (c.attributeQuery('lockCenterJoints', node=container, exists=True)
                              and bool(c.getAttr(container+'.lockCenterJoints')))
        if had_locked_centers:
            self.set_fit_center_joint_lock_state(container, False)
        with self.fit_manual_update_channels(container):
            if from_body_build:
                self.bake_fit_container_scale_for_build(container)
            else:
                self.bake_fit_container_scale(container)
            from adv_py.application.registered_body_build import _refresh_fit_orientations_before_body
            _refresh_fit_orientations_before_body(self, container)
        if had_locked_centers:
            self.set_fit_center_joint_lock_state(container, True)
        # MEL catchQuiet(select(oldSelection)) tolerates names that changed in
        # asUniqueNameAll. Do not invent a replacement selection from UUIDs.
        try:
            c.select(selected, replace=True) if selected else c.select(clear=True)
        except RuntimeError:
            pass
