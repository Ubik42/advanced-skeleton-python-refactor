"""Restore the source SDK links retained on Fit at the end of Body build.

Source: ADV 6.925 MEL 85650–85795. Duplicate native curves so Maya retains
their complete tangent/weight state; text export has different source rules.
"""
import re

from adv_py.core.original_driving_fit import (
    OriginalDrivingFitCurve, OriginalDrivingFitSystem,
    original_fit_driven_destination, order_original_fit_driving_systems,
)
from .maya_original_control_identity import source_control_from_role, leaf


class MayaDrivingFitRestoreMixin:
    def capture_original_driving_fit_restore(self, fit='FitSkeleton'):
        c = self._cmds
        if not c.objExists(fit):
            raise ValueError('DrivingSystem 缺少 FitSkeleton')
        systems = []
        for attribute in c.listAttr(fit, userDefined=True, scalar=True) or []:
            if not attribute.startswith('drivingSystem_'):
                continue
            control = source_control_from_role(self, attribute[len('drivingSystem_'):])
            curves = c.listConnections(fit + '.' + attribute) or []
            plugs = c.listConnections(fit + '.' + attribute, plugs=True) or []
            links = c.listConnections(fit + '.' + attribute,
                                      connections=True, plugs=True) or []
            if len(links) % 2:
                raise ValueError('Fit DrivingSystem 属性连接对不完整：' + control)
            fit_indices = {}
            for own, peer in zip(links[::2], links[1::2]):
                index = re.fullmatch(re.escape(attribute) + r'\[([0-9]+)\]', own.split('.', 1)[1])
                if index:
                    node, target = peer.split('.', 1)
                    fit_indices[(leaf(node), target)] = int(index[1])
            if len(curves) != len(plugs):
                raise ValueError('Fit DrivingSystem 曲线和属性连接数量不同：' + control)
            rows = []
            depth = 0
            for curve, plug in zip(curves, plugs):
                if not c.nodeType(curve).startswith('animCurve'):
                    raise ValueError('Fit DrivingSystem 连接不是动画曲线：' + curve)
                name, driven, driven_attribute = original_fit_driven_destination(curve)
                depth = max(depth, len([token for token in leaf(curve).split('_') if token]))
                driver_attribute = plug.split('.', 1)[1]
                limits = []
                for present, value in (('hasMinValue', 'minValue'),
                                       ('hasMaxValue', 'maxValue'),
                                       ('hasSoftMinValue', 'softMinValue'),
                                       ('hasSoftMaxValue', 'softMaxValue')):
                    limits.append(float(c.addAttr(plug, query=True, **{value: True}))
                        if c.addAttr(plug, query=True, **{present: True}) else None)
                message_index = None
                if c.objExists(curve + '.drivingSystemOut'):
                    outputs = c.listConnections(curve + '.drivingSystemOut',
                        source=False, destination=True, plugs=True) or []
                    for output in outputs:
                        node, target = output.split('.', 1)
                        match = re.fullmatch(r'drivingSystem\[([0-9]+)\]', target)
                        if leaf(node) == leaf(fit) and match:
                            message_index = int(match[1])
                rows.append(OriginalDrivingFitCurve(curve, name, driver_attribute,
                    driven, driven_attribute, tuple(limits), c.ls(curve, uuid=True)[0],
                    fit_indices.get((leaf(curve), driver_attribute)), message_index))
            systems.append(OriginalDrivingFitSystem(control, tuple(rows), depth, attribute))
        return order_original_fit_driving_systems(systems)

    def restore_original_driving_from_fit(self, plan=None, *, fit='FitSkeleton'):
        self._require_transaction()
        c = self._cmds
        plan = self.capture_original_driving_fit_restore(fit) if plan is None else plan
        if not plan:
            return ()
        self._transaction_changed = True
        restored = []
        for system in plan:
            for row in system.curves:
                # Duplicate before missing-target handling, matching MEL.
                if row.source_uuid:
                    from contextlib import nullcontext
                    raw = getattr(c, 'raw', c)
                    sources = raw.ls(row.source_uuid, long=True) or []
                    if len(sources) != 1 or not raw.nodeType(sources[0]).startswith('animCurve'):
                        raise ValueError('Fit DrivingSystem 原曲线 UUID 已失效：' + row.source)
                    # The stage reads an old character's curve but writes only
                    # its own duplicate. UUID bypasses namespace name mapping.
                    with c._creation_namespace() if hasattr(c, '_creation_namespace') else nullcontext():
                        curve = raw.duplicate(sources[0], name=self.scene_address(row.name))[0]
                    if hasattr(c, 'identity'):
                        curve = c.identity.to_local(curve)
                else:
                    curve = c.duplicate(row.source, name=row.name)[0]
                driven = source_control_from_role(self, row.driven)
                if not c.objExists(driven):
                    c.warning('DrivingSystem attempting to drive: "' + driven
                              + '", but this object is not found.')
                    continue
                control = source_control_from_role(self, system.control)
                if not c.objExists(control):
                    self._original_create_driving_controller(control, (driven,))
                sdk = driven if driven.startswith('bw') else self.create_original_driving_sdk_layer(driven)
                destination = sdk + '.' + row.driven_attribute
                if c.objExists(destination) or row.driven_attribute.startswith('input['):
                    weighted = self.ensure_original_driving_weighted_input(destination)
                    outputs = c.listConnections(curve + '.output', source=False,
                        destination=True, skipConversionNodes=True) or []
                    if weighted not in outputs:
                        index = int(c.getAttr(weighted + '.input', size=True))
                        c.connectAttr(curve + '.output', weighted + '.input[' + str(index) + ']')
                        c.refresh()
                else:
                    c.warning('failed: connectAttr -f ' + curve + '.output ' + destination + ';')
                driver = control + '.' + row.attribute
                if not c.objExists(driver):
                    options = {}
                    for value, flag, enabled in zip(row.limits,
                            ('minValue', 'maxValue', 'softMinValue', 'softMaxValue'),
                            ('hasMinValue', 'hasMaxValue', 'hasSoftMinValue', 'hasSoftMaxValue')):
                        if value is not None:
                            options[enabled] = True
                            options[flag] = value
                    c.addAttr(control, longName=row.attribute, attributeType='float',
                              keyable=True, **options)
                    self._original_driving_pose_registration(control, row.attribute, face=False)
                output = self.original_face_output_bw(driver)
                if c.objExists(driver) and c.objExists(output) and not c.isConnected(output, curve + '.input'):
                    c.connectAttr(output, curve + '.input', force=True)
                restored.append(curve)
        # Only the saved source SDK list is eligible for source cleanup.
        if c.objExists(fit + '.drivingSystem'):
            for curve in c.listConnections(fit + '.drivingSystem', source=True, destination=False) or []:
                if not (c.listConnections(curve + '.output', source=False, destination=True) or []):
                    c.delete(curve)
        self.optimize_original_driving_controllers()
        from .maya_driving_registration import refresh_registered_sdks
        refresh_registered_sdks(self)
        return tuple(restored)
