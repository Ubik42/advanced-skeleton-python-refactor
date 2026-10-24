"""Permanent asDecomposeOPM graph, ADV 6.925 source 23387–23416.

This is separate from temporary matrix reads used by the JSON exporters.
It changes the actual native DeformSet graph and is retained across rebuild.
"""
from .maya_original_control_identity import leaf, registration
from .maya_original_export_preparation import MayaOriginalExportPreparationHost
from .maya_game_registration import scene_ids, remember_generated_nodes


OUTPUTS = (('outputTranslate', 'translate'), ('outputRotate', 'rotate'),
           ('outputScale', 'scale'), ('outputShear', 'shear'))


class MayaOriginalOpmDecompositionHost(MayaOriginalExportPreparationHost):
    def decompose_original_offset_parent_matrices(self):
        self._require_transaction()
        c = self._cmds
        before = registration(self)
        ids = scene_ids(self)
        joints = tuple(c.sets('DeformSet', query=True) or [])
        self._transaction_changed = True
        temporary = c.createNode('transform', name='tempMatrixTransform')
        identity = c.xform(temporary, query=True, objectSpace=True, matrix=True)
        c.delete(temporary)
        created = []
        for joint in joints:
            dm = c.createNode('decomposeMatrix', name=leaf(joint) + 'DM')
            c.setAttr(dm + '.inputRotateOrder', c.getAttr(joint + '.rotateOrder'))
            for output, attribute in OUTPUTS:
                c.connectAttr(dm + '.' + output, joint + '.' + attribute)
            sources = c.listConnections(joint + '.offsetParentMatrix', source=True,
                                        destination=False, plugs=True) or []
            # Source requires its first incoming OPM plug; static OPM rigs are
            # not silently converted through a different graph or forced write.
            if not sources:
                raise RuntimeError('原版 OPM 分解缺少输入连接：' + joint)
            source = sources[0]
            c.disconnectAttr(source, joint + '.offsetParentMatrix')
            c.setAttr(joint + '.offsetParentMatrix', *identity, type='matrix')
            c.connectAttr(source, dm + '.inputMatrix')
            created.append(dm)
        self._remember_export_preparation(before, remember_generated_nodes(self, ids))
        return tuple(created)


def has_original_opm_decomposition(host):
    c = host._cmds
    if not c.objExists('DeformSet'):
        return False
    joints = c.sets('DeformSet', query=True) or []
    if not joints:
        return False
    for joint in joints:
        sources = c.listConnections(joint + '.translate', source=True,
                                    destination=False, plugs=True) or []
        if len(sources) != 1 or not sources[0].endswith('.outputTranslate'):
            return False
        dm = sources[0].split('.', 1)[0]
        scale_direct = c.isConnected(dm + '.outputScale', joint + '.scale')
        # GameScaling moves the authored scale inputs to its stored source
        # channels. The conversion remains active after that native rewrite.
        scale_stored = all(c.objExists(joint + '.GameEngineScalingS' + axis)
            and c.isConnected(dm + '.outputScale' + axis, joint + '.GameEngineScalingS' + axis)
            for axis in 'XYZ')
        if (c.nodeType(dm) != 'decomposeMatrix'
                or c.listConnections(joint + '.offsetParentMatrix', source=True, destination=False)
                or not c.listConnections(dm + '.inputMatrix', source=True, destination=False, plugs=True)
                or any(not c.isConnected(dm + '.' + output, joint + '.' + attribute)
                       for output, attribute in OUTPUTS if attribute != 'scale')
                or not (scale_direct or scale_stored)):
            return False
    return True
