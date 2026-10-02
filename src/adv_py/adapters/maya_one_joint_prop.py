"""Original Preparation One Joint Prop through the shared source Body graph."""
from __future__ import annotations

from .maya_body import MayaBodyBuildHost


class MayaOneJointPropHost(MayaBodyBuildHost):
    def preflight_one_joint_prop(self, skin_objects, all_objects):
        """Original inputs are objects, including geometry hierarchies."""
        from adv_py.core.fit_settings import FitSkeletonValidationError
        c = self._cmds
        for role, objects in (("Skin", skin_objects), ("All", all_objects)):
            for node in objects:
                if not c.objExists(node):
                    raise FitSkeletonValidationError(
                        f'Choosen {role} object:"{node}" not found')
        for node in ("FitSkeleton", "|Group", "Root"):
            if c.objExists(node):
                raise FitSkeletonValidationError(node + " already exists")

    def create_one_joint_prop_rig(self, first_skin_mesh, *, skin_meshes,
                                  all_meshes, build_options=None):
        self._require_transaction()
        from adv_py.application.fit_container import CreateFitSkeleton
        from adv_py.application.registered_body_build import (
            BuildRegisteredBodyCharacter, _JoinedTransactionHost)
        from .maya_preparation_objects import MayaPreparationObjectsHost, _ATTRIBUTES
        from adv_py.core.preparation_objects import PreparationObjectRole
        from adv_py.core.one_joint_prop import plan_one_joint_prop_fit
        from .maya_original_fit_attributes import ensure_original_fit_joint_attributes

        c = self._cmds
        raw = getattr(c, 'raw', c)
        self._one_joint_prop_scene_before = self.capture_body_scene_nodes()
        bounds = raw.xform(self.scene_address(first_skin_mesh), query=True,
                           worldSpace=True, boundingBox=True)
        plan = plan_one_joint_prop_fit(bounds)
        fat = plan.fat
        self._transaction_changed = True
        c.select(clear=True)
        root = c.joint(name='Root', position=plan.position)
        c.setAttr(root + '.jointOrient', *plan.joint_orient, type='double3')
        # asOneJointProp initializes Root before the Fit container exists.
        # Moving this behind CreateFitSkeleton changes the initial scale/axis
        # lookup and the default fat attribute on this special preparation path.
        ensure_original_fit_joint_attributes(c, root, 'FitSkeleton', lambda node: '')
        c.setAttr(root + '.fat', fat)
        joined = _JoinedTransactionHost(self)
        gap = raw.optionVar(query='asFitSkeletonGap') if raw.optionVar(exists='asFitSkeletonGap') else .75
        fit = CreateFitSkeleton(joined).apply(vis_gap_default=gap).state.path
        # The source scales radius-3 Fit CVs by bboxMaxY/2, not half height.
        c.xform(fit + '.cv[0:7]', scale=(plan.fit_cv_scale,) * 3)
        root = c.parent(root, fit, absolute=True)[0]
        root = c.ls(root, long=True, type='joint')[0]

        records = MayaPreparationObjectsHost(self.namespace or ':')
        inputs = {
            PreparationObjectRole.SKIN: skin_meshes,
            PreparationObjectRole.ALL: all_meshes,
            PreparationObjectRole.RIGHT_EYE: records._stored_names(PreparationObjectRole.RIGHT_EYE),
            PreparationObjectRole.LEFT_EYE: records._stored_names(PreparationObjectRole.LEFT_EYE),
        }
        for role, meshes in inputs.items():
            c.setAttr(fit + '.' + _ATTRIBUTES[role],
                      ' '.join(mesh.rsplit('|', 1)[-1] for mesh in meshes), type='string')
        for attribute, field, preference in (
            ('gameEngine', 'game_engine', 'asBodyPreGameEngine'),
            ('useOffsetParentMatrix', 'use_offset_parent_matrix', 'asBodyPreOPM'),
            ('subControllers', 'sub_controllers', 'asBodyPreSub'),
            ('extraControllers', 'extra_controllers', 'asBodyPreExtra')):
            value = (getattr(build_options, field) if build_options is not None else
                     bool(raw.optionVar(query=preference))
                     if raw.optionVar(exists=preference) else False)
            c.setAttr(fit + '.' + attribute, value)
        result = BuildRegisteredBodyCharacter(joined).apply('FitSkeleton',
            _scene_before=self._one_joint_prop_scene_before)
        self._one_joint_prop_body = result
        return (c.ls('Root', long=True, type='joint')[0],
                result.skeleton.snapshot.root,
                result.rig.plan.global_control.control_path)

    def bind_one_joint_prop_meshes(self, meshes, joint, skin_names=()):
        """One native newSkinCluster batch, asOneJointProp 77154–77162.

        skin_names is accepted for older callers but does not override Maya's
        source naming. All selected descendant deformable shapes participate.
        """
        self._require_transaction()
        from .maya_original_skin_history import new_original_skin_clusters
        raw = getattr(self._cmds, 'raw', self._cmds)
        physical = tuple(self.scene_address(mesh) for mesh in meshes)
        self._transaction_changed = True
        raw.select(clear=True)
        if physical:
            raw.select(physical, add=True)
        if not self._cmds.objExists('Hi'):
            raw.createDisplayLayer(name=self.scene_address('Hi'), number=1, noRecurse=True)
        raw.select(self.scene_address(joint), add=True)
        skins = new_original_skin_clusters(commands=raw, namespace=self.namespace or "")
        raw.select(clear=True)
        return skins

    def finalize_one_joint_prop_geometry(self, meshes, first_skin_mesh):
        self._require_transaction()
        raw = getattr(self._cmds, 'raw', self._cmds)
        identifiers = tuple(raw.ls(self.scene_address(mesh), uuid=True)[0] for mesh in meshes)
        first = raw.ls(self.scene_address(first_skin_mesh), long=True)[0]
        top = '|' + first.split('|')[1]
        try:
            # Parent only the top node of the explicitly supplied first Skin.
            self._transaction_changed = True
            raw.parent(top, self.scene_address('|Group|Geometry'), absolute=True)
        except RuntimeError:
            # MEL wraps this particular parent command in catchQuiet. A
            # referenced or locked input may remain external after binding;
            # do not invent a stricter business failure for this step.
            pass
        return tuple(raw.ls(identifier, long=True)[0] for identifier in identifiers)
