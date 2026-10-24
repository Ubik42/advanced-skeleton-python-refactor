"""Native asCreateCustomControl Skin branch, MEL 57991–58149.

The metadata at the end describes the source graph; it does not replace its
shared ParentConstraintTo frame, X transform or native weight procedure.
"""
from types import SimpleNamespace

from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from .maya_body_parent_constraint import MayaBodyParentConstraintMixin
from .maya_face_softmod_weights import MayaFaceSoftModWeightsMixin
from .maya_original_skin_history import related_skin_cluster
from .maya_original_transform_channels import align_original_transform


def _parent_constraint(host, commands, driver, driven, maintain_offset=False):
    fit = host.scene_address("FitSkeleton.useOffsetParentMatrix")
    bridge = SimpleNamespace(_cmds=commands, namespace=None,
        _use_offset_parent_matrix=bool(commands.objExists(fit) and commands.getAttr(fit)),
        _transaction_changed=False, _require_transaction=host._require_transaction)
    driver = commands.ls(driver, long=True)[0]
    driven = commands.ls(driven, long=True)[0]
    inputs = MayaBodyParentConstraintMixin.capture_parent_constraint_input(bridge, driver, driven, maintain_offset)
    plan = plan_body_parent_constraint(inputs)
    MayaBodyParentConstraintMixin.preflight_parent_constraint(bridge, plan)
    MayaBodyParentConstraintMixin.create_parent_constraint(bridge, plan)
    host._transaction_changed |= bridge._transaction_changed
    return plan


class _WeightHost(MayaFaceSoftModWeightsMixin):
    def __init__(self, host):
        self._cmds = host._cmds
        self.scene_address = host.scene_address
        self._require_transaction = host._require_transaction
        self._transaction_changed = False

    def _original_face_softmod_sets(self):
        from .maya_face_deformer_sets import original_face_deformer_sets
        return original_face_deformer_sets(self._cmds)

    @staticmethod
    def _original_restore_leaf(node):
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def create(host, plan):
    host._require_transaction()
    from maya import cmds as c
    address = host.scene_address
    host._transaction_changed = True
    mesh = host._mesh(plan.region.mesh)
    chosen = host._skin_for_mesh(mesh, plan.skin_cluster)
    parent = host._unique_custom_parent(plan.parent_joint)
    source_parent = parent
    if plan.partial_parent:
        parent = host._ensure_custom_partial_parent(parent)
    c.select(clear=True)
    joint = c.joint(name=address(plan.joint_name))
    joint = c.parent(joint, parent)[0]
    c.setAttr(joint + ".segmentScaleCompensate", 0)
    c.addAttr(joint, longName="skinControlJoint", attributeType="bool", defaultValue=1)
    c.xform(joint, worldSpace=True, translation=plan.region.center)
    if plan.local:
        c.delete(c.orientConstraint(parent, joint))
        c.makeIdentity(joint, apply=True, translate=False, rotate=True, scale=False)
        c.setAttr(joint + ".segmentScaleCompensate", 0)
    system = host._custom_system()
    parent_leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    attach = address("ParentConstraintTo" + parent_leaf)
    if not c.objExists(attach):
        attach = c.createNode("transform", name=attach, parent=system)
        _parent_constraint(host, c, parent, attach)
    attach = host._unique(attach, "transform")
    offset = c.createNode("transform", name=address(plan.offset_name))
    points = ((-.5,.5,.5),(-.5,.5,-.5),(.5,.5,-.5),(.5,.5,.5),
              (-.5,.5,.5),(-.5,-.5,.5),(.5,-.5,.5),(.5,-.5,-.5),
              (-.5,-.5,-.5),(-.5,-.5,.5),(-.5,-.5,-.5),(-.5,.5,-.5),
              (-.5,-.5,-.5),(.5,-.5,-.5),(.5,.5,-.5),(.5,-.5,-.5),
              (.5,-.5,.5),(.5,.5,.5))
    control = c.curve(name=address(plan.control_name), degree=1, point=points)
    c.addAttr(control, longName="skinControl", attributeType="bool", defaultValue=1)
    c.addAttr(control, longName="localOrient", attributeType="bool", defaultValue=plan.local)
    size = plan.region.falloff_radius / 4.
    c.xform(control + ".cv[0:17]", worldSpace=True, scale=(size, size, size))
    shape = c.listRelatives(control, shapes=True, fullPath=True)[0]
    c.setAttr(shape + ".isHistoricallyInteresting", 0)
    control = c.parent(control, offset)[0]
    x = c.createNode("transform", name=address("X" + plan.name + plan.side), parent=control)
    offset = c.parent(offset, attach)[0]
    if plan.local and not plan.middle and parent_leaf.endswith("_M") and plan.side == "_R":
        temporary = c.createNode("transform", name=address("tempXForm"))
        c.setAttr(temporary + ".sx", -1)
        temporary = c.parent(temporary, attach)[0]
        scale = c.getAttr(temporary + ".s")[0]
        c.delete(temporary)
        if host.face:
            c.setAttr(offset + ".s", *scale, type="float3")
        else:
            c.rotate(180, 180, 0, offset, relative=True, euler=True)
    offset = align_original_transform(c, offset, joint, True, False)
    if plan.local:
        offset = align_original_transform(c, offset, joint, False, True)
    # Resolve paths again after native parenting; the X driver is the child
    # frame used by the source, rather than the controller transform itself.
    control = host._unique(plan.control_name, "transform")
    x = host._unique("X" + plan.name + plan.side, "transform")
    joint = host._unique(plan.joint_name, "joint")
    c.setAttr(shape.rsplit("|", 1)[-1] + ".overrideEnabled", 1)
    c.setAttr(shape.rsplit("|", 1)[-1] + ".overrideColor", 17)
    _parent_constraint(host, c, x, joint)
    if not host.face:
        c.sets(joint, add=address("DeformSet"))
    c.sets(control, add=address("FaceControlSet" if host.face else "ControlSet"))
    original_skin = related_skin_cluster(mesh)
    layered = chosen != original_skin
    skin = chosen
    base = address("ExtraSkinClustersBaseJoint_M")
    if chosen == "*new":
        if not c.objExists(base):
            base = c.createNode("joint", name=base, parent=address("DeformationSystem"))
            c.setAttr(base + ".drawStyle", 2)
            c.setAttr(base + ".inheritsTransform", 0, lock=True)
            if c.objExists(address("Main.jointVis")):
                c.connectAttr(address("Main.jointVis"), base + ".v")
        skin = c.skinCluster(base, mesh, multi=True)[0]
        if c.objExists(original_skin):
            c.reorderDeformers(original_skin, skin, mesh)
    joint_offset = None
    if layered:
        for kind in ("parentConstraint", "scaleConstraint"):
            constraint = address(plan.joint_name + "_" + kind + "1")
            if c.objExists(constraint):c.delete(constraint)
        joint_offset = c.createNode("transform", name=address("JointOffset" + plan.name + plan.side), parent=joint)
        joint_offset = c.parent(joint_offset, base)[0]
        joint = c.parent(joint, joint_offset)[0]
        matrix = c.createNode("multMatrix", name=address(plan.name + "JointMM" + plan.side))
        c.connectAttr(control + ".worldMatrix[0]", matrix + ".matrixIn[0]")
        c.connectAttr(offset + ".worldInverseMatrix[0]", matrix + ".matrixIn[1]")
        c.connectAttr(matrix + ".matrixSum", joint + ".offsetParentMatrix")
    c.skinCluster(skin, edit=True, lockWeights=False, weight=0, addInfluence=joint)
    converting = c.createNode("transform", name=address("convertingSoftMod"))
    c.addAttr(converting, longName="softMod", dataType="string")
    c.setAttr(converting + ".softMod", plan.region.deformer, type="string")
    weights = _WeightHost(host)
    try:
        count = weights.weight_original_face_by_softmod(joint, mesh, skin,
            plan.region.falloff_radius, plan.region.falloff_mode)
    finally:
        host._transaction_changed |= weights._transaction_changed
    c.delete(converting)
    c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind", dataType="string")
    c.setAttr(joint + ".advPyAuxiliaryInfluenceKind", "custom-skin-v1", type="string", lock=True)
    if layered and c.objExists(base) and not c.objExists(base + ".advPyAuxiliaryInfluenceKind"):
        c.addAttr(base, longName="advPyAuxiliaryInfluenceKind", dataType="string")
        c.setAttr(base + ".advPyAuxiliaryInfluenceKind", "custom-skin-v1", type="string", lock=True)
    c.addAttr(control, longName="advPyLayeredSkin", attributeType="bool", defaultValue=layered)
    c.setAttr(control + ".advPyLayeredSkin", lock=True)
    c.addAttr(control, longName="parent", dataType="string")
    c.setAttr(control + ".parent", parent.rsplit("|", 1)[-1], type="string")
    c.addAttr(control, longName="advPyCustomControlKind", dataType="string")
    c.setAttr(control + ".advPyCustomControlKind", plan.kind.value, type="string", lock=True)
    c.addAttr(control, longName="advPyCustomControlWeightCount", attributeType="long")
    c.setAttr(control + ".advPyCustomControlWeightCount", count, lock=True)
    for attribute, target in (("Deformer",skin),("Joint",joint),("Parent",source_parent)):
        c.addAttr(control, longName="advPyCustomControl" + attribute, attributeType="message")
        c.connectAttr(target + ".message", control + ".advPyCustomControl" + attribute)
    c.delete(host._unique(plan.region.source_handle, "transform"))
    if c.objExists(plan.region.deformer):c.delete(plan.region.deformer)
    paths = (attach, offset, control, x,
             *((base, joint_offset) if joint_offset else ()), joint)
    host._register_custom_nodes(paths, control)
