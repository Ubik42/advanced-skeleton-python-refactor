"""Explicit native SDK insertion for Maya's multiple-driver undo defect.

The source still determines the driven plug, keys, curve type and blend. This
only journals the nodes that Maya 2024's implicit SDK insertion leaves behind.
"""
from contextlib import nullcontext


class MayaFaceSDKInsertMixin:
    def original_face_sdk_attribute(self, node, attribute):
        """Keep alias drivers while expanding real short attribute names."""
        c = self._cmds
        root, bracket, index = attribute.partition('[')
        aliases = c.aliasAttr(node, query=True) or []
        if attribute in aliases[::2]:
            return attribute
        if c.attributeQuery(root, node=node, exists=True):
            return c.attributeQuery(root, node=node, longName=True) + (bracket + index if bracket else '')
        # BlendShape target aliases are valid plugs, but attributeQuery only
        # recognizes the underlying weight array. asCtrlToBw keeps aliases.
        return c.attributeQuery(root, node=node, longName=True) + (bracket + index if bracket else '')

    def set_original_face_sdk_keys(self, driver, driven, keys):
        c = self._cmds
        incoming = c.listConnections(driven, source=True, destination=False,
                                     plugs=True, skipConversionNodes=True) or []
        source = incoming[0] if incoming else None
        source_node = source.split('.', 1)[0] if source else None
        kind = c.nodeType(source_node) if source_node else None
        curves = []
        if kind and kind.startswith('animCurve'):
            curves = [source_node]
        elif kind == 'blendWeighted':
            curves = c.listConnections(source_node + '.input', source=True,
                destination=False, type='animCurve', skipConversionNodes=True) or []
        curve = next((n for n in curves if c.isConnected(driver, n + '.input',
                                      ignoreUnitConversion=True)), None)
        if curve is None:
            attr_type = c.getAttr(driven, type=True)
            curve_type = {'doubleLinear': 'animCurveUL', 'doubleAngle': 'animCurveUA',
                          'time': 'animCurveUT'}.get(attr_type, 'animCurveUU')
            node, attr = driven.split('.', 1)
            if source is None:
                name = node.rsplit('|', 1)[-1].rsplit(':', 1)[-1] + '_' + self.original_face_sdk_attribute(node, attr).replace('[', '_').replace(']', '_')
                curve = c.createNode(curve_type, name=name)
                destination = driven
            else:
                curve = c.createNode(curve_type, name=curve_type + '#')
                if kind == 'blendWeighted':
                    destination = self.next_original_face_bw_input(source_node)
                else:
                    # Native SDK creates this exact two-input blend when a
                    # new driver is added to an already driven channel.
                    blend = c.createNode('blendWeighted', name='blendWeighted#')
                    actual = (c.listConnections(driven, source=True, destination=False, plugs=True) or [None])[0]
                    c.disconnectAttr(actual, driven)
                    c.connectAttr(actual, blend + '.input[0]')
                    c.connectAttr(blend + '.output', driven)
                    destination = blend + '.input[1]'
            # Read an external ARKit source into an owned curve. The generic
            # connectAttr boundary checks both plugs as mutations; SDK driver
            # sources are read-only just like native currentDriver arguments.
            raw = getattr(c, 'raw', c)
            with c._creation_namespace() if hasattr(c, '_creation_namespace') else nullcontext():
                raw.connectAttr(self.scene_address(driver), self.scene_address(curve) + '.input')
            c.connectAttr(curve + '.output', destination)
        for driver_value, value in keys:
            c.setKeyframe(curve, float=driver_value, value=value,
                inTangentType='linear', outTangentType='linear')
        self._transaction_changed = True
        return curve
