"""SkinCage curve and cylinder construction from ADV 6.925, 69973–71003."""
from __future__ import annotations

from fnmatch import fnmatchcase

from adv_py.core.adv_icon_axis import icon_axis_offset


from .maya_original_transform_channels import align_original_transform

class MayaSkinCageSourceMixin:
    @staticmethod
    def _cage_leaf(node):
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _cage_main(self):
        """Resolve the existing Main role without renaming generated controls."""
        for leaf in ('Main','AdvPy_Global'):
            nodes=self.cmds.ls(self._name(leaf),long=True,type='transform') or []
            if len(nodes)==1:return nodes[0]
            if nodes:raise ValueError('SkinCage 的 Main 控制器不唯一')
        raise ValueError('SkinCage 缺少 Main 控制器')

    def _cage_fk(self,joint):
        leaf=self._cage_leaf(joint)
        original=self._name('FK'+leaf)
        if self.cmds.objExists(original):return original
        from adv_py.core.character_registry import REGISTRY_NAME,decode_registration
        from adv_py.core.character_identity import CharacterIdentity
        plug=self._name(REGISTRY_NAME)+'.advPyRegistryDocument'
        if not self.cmds.objExists(plug):return ''
        registry=decode_registration(self.cmds.getAttr(plug))
        identity=CharacterIdentity(self.namespace)
        candidates=set()
        for channel in registry.channels:
            if (channel.key.startswith('generic.fk.') and '.extra.' not in channel.key
                    and '.sub.' not in channel.key):
                role=channel.key[len('generic.fk.'):].split('.',1)[0]
                if role==leaf+'FK':candidates.add(channel.node)
        for limb in registry.source_limbs:
            candidates.update(row.control for row in limb.joints
                if self._cage_leaf(row.body)==leaf and row.control!=row.fk_driver)
        for spline in (registry.spine,*registry.additional_spines):
            if spline is not None:
                candidates.update(control for body,control in zip(spline.body_joints,spline.fk_controls)
                                  if self._cage_leaf(body)==leaf)
        if len(candidates)>1:raise ValueError('SkinCage 的 FK 控制器不唯一：'+leaf)
        return identity.to_scene(next(iter(candidates))) if candidates else ''

    def _cage_label(self, joint):
        """asLabel/asLabelCodeLookup; disabled labels are empty."""
        c = self.cmds
        if not c.objExists(joint):
            return "AA"
        if not c.objExists(joint + ".type"):
            return "BB"
        if not c.getAttr(joint + ".drawLabel"):
            return ""
        kind = int(c.getAttr(joint + ".type"))
        if kind == 18:
            return c.getAttr(joint + ".otherType") or ""
        return {0: "None", 1: "Root", 2: "Hip", 4: "Foot", 10: "Shoulder",
                12: "Hand", 15: "PropA", 16: "PropB", 17: "PropC"}.get(kind, "")

    def _cage_parent(self, joint):
        return (self.cmds.listRelatives(joint, parent=True, type="joint") or [""])[0]

    def _cage_rla_child(self, joint):
        c = self.cmds
        tolerance = .01 * (c.getAttr(self._name("FitSkeleton") + ".sx")
                           if c.objExists(self._name("FitSkeleton")) else 1)
        children = c.listRelatives(joint, children=True, type="joint") or []
        center = abs(c.xform(joint, query=True, worldSpace=True,
                             translation=True)[0]) < tolerance
        chosen = next((child for child in children if center == (abs(c.xform(
            child, query=True, worldSpace=True, translation=True)[0]) < tolerance)), "")
        for marker, preferred in (("Head", "Head"), ("Ankle", "Toes"),
                                  ("Toes", "Toes"), ("Root", "Spine")):
            if marker in self._cage_leaf(joint):
                for child in children:
                    if preferred in self._cage_leaf(child):
                        chosen = child
        return chosen

    def _cage_children(self, joint):
        c = self.cmds
        skips = ("FaceJoint_M", "Slider[0-9]", "Slide50", "Cup_", "Scapula_",
                 "ThumbFinger1_", "FootSideOuter_", "FootSideInner_", "Heel_",
                 "Jaw_", "JawEnd_", "Eye_", "Eye[0-9]_", "Partial_", "Float",
                 "VS[0-9]JStart")
        subtrees = ("FaceJoint_M", "PinkyToe_", "BigToe_", "Jaw_", "JawEnd_",
                    "Eye_", "Eye[0-9]_", "Partial_", "Float", "VS[0-9]JStart")
        preferred = self._cage_rla_child(joint)
        result = [preferred] if preferred and preferred not in skips else []
        for child in c.listRelatives(joint, children=True, type="joint") or []:
            if child == preferred:
                continue
            leaf = self._cage_leaf(child)
            skip = any(fnmatchcase(leaf, "*" + token + "*") for token in skips)
            skip_children = any(fnmatchcase(leaf, "*" + token + "*") for token in subtrees)
            fit = self._name(leaf.split("_")[0])
            if ((c.objExists(fit + ".noSkin") and c.getAttr(fit + ".noSkin"))
                    or (c.objExists(child + ".skinControlJoint")
                        and c.getAttr(child + ".skinControlJoint"))):
                skip = skip_children = True
            if skip:
                if not skip_children:
                    for grandchild in c.listRelatives(child, children=True, type="joint") or []:
                        if not any(fnmatchcase(self._cage_leaf(grandchild), "*" + token + "*")
                                   for token in skips):
                            result.append(grandchild)
            elif child:
                result.append(child)
        return result

    def _cage_descendants(self, joint):
        c = self.cmds
        skips = ("Slider[0-9]", "Slide50", "Cup_", "Scapula_", "ThumbFinger1_",
                 "FootSideOuter_", "FootSideInner_", "Heel_", "Jaw_", "Eye_",
                 "Partial_", "Float", "Part[0-9]_", "Part[0-9][0-9]_", "VS[0-9]JStart")
        subtrees = ("PinkyToe_", "BigToe_", "Jaw_", "JawEnd_", "Eye_", "Eye[0-9]_",
                    "Partial_", "Float", "VS[0-9]JStart")
        result = []
        for path in c.listRelatives(joint, allDescendents=True, type="joint", fullPath=True) or []:
            leaf = self._cage_leaf(path)
            if (any(fnmatchcase(leaf, "*" + token + "*") for token in skips)
                    or any(fnmatchcase(path, "*" + token + "*") for token in subtrees)):
                continue
            fit = self._name(leaf.split("_")[0])
            fit_paths = c.ls(fit, long=True) or []
            ancestors = fit_paths[0].split("|")[1:] if fit_paths else []
            if any(c.objExists(node + "." + attr) and c.getAttr(node + "." + attr)
                   for node in ancestors for attr in ("noSkin", "skinControlJoint")):
                continue
            if ((c.objExists(fit + ".noSkin") and c.getAttr(fit + ".noSkin"))
                    or (c.objExists(path + ".skinControlJoint") and c.getAttr(path + ".skinControlJoint"))):
                continue
            result.append((c.ls(path) or [path])[0])
        return result

    def _cage_axis(self, joint, which):
        from .maya_original_axes import original_axis
        return original_axis(self.cmds,which,joint,self._name('FitSkeleton'),
                             fit_skeleton=self._name('FitSkeleton'))

    def _cage_align(self, target, source, *, translate=True, rotate=True):
        return align_original_transform(self.cmds,target,source,translate,rotate)

    def _cage_mesh_curve(self, name):
        c = self.cmds
        joint = name.rsplit("_", 1)[0]
        curve = c.curve(name=name, degree=1,
                        point=[(0, -1, 1), (0, 1, 1), (0, 1, -1),
                               (0, -1, -1), (0, -1, 1)])
        c.reverseCurve(curve, constructionHistory=False, replaceOriginal=True)
        temporary = self._name("tempXform")
        if c.objExists(temporary):
            c.delete(temporary)
        temporary = c.createNode("transform", name=temporary)
        constraint = c.orientConstraint(temporary, curve)[0]
        c.setAttr(constraint + ".offset", *icon_axis_offset(
            self._cage_axis(joint, "primary"), self._cage_axis(joint, "secondary")), type="float3")
        c.delete(constraint, temporary)
        c.refresh()
        c.makeIdentity(curve, apply=True, translate=False, rotate=True, scale=False, normal=0)
        profile = c.duplicate(curve, name=name.replace("Curve", "Profile"))[0]
        c.sets(profile, add=self._name("SkinCageCurvesSet"))
        c.scale(1.2, 1.2, 1.2, profile, relative=True)
        c.parent(curve, profile)
        c.connectAttr(profile + ".worldSpace[0]", curve + ".create")
        c.setAttr(curve + ".v", 0)
        return profile

    def _cage_two_targets(self, offset, first, second, first_weight, second_weight):
        c = self.cmds
        for command in (c.pointConstraint, c.scaleConstraint):
            command(first, offset, weight=first_weight)
            if second:
                command(second, offset, weight=second_weight)

    def _cage_end_curve(self, joint, previous, suffix, negative, terminal):
        c = self.cmds
        curve = joint + "_" + suffix + "Curve"
        profile = self._cage_mesh_curve(curve)
        offset = c.createNode("transform", name=curve + "Offset")
        c.parent(profile, offset)
        c.parent(offset, self._name("MeshCurves"))
        c.editDisplayLayerMembers(self._name("SkinCurves2"), profile, noRecurse=True)
        c.parent(offset, joint + "_middleCurve")
        for attribute, values in (("t", (0, 0, 0)), ("r", (0, 0, 0)), ("s", (1, 1, 1))):
            c.setAttr(offset + "." + attribute, *values, type="float3")
        c.parent(offset, self._name("MeshCurves"))
        if terminal:
            sign = 1 if negative else -1
            if suffix == "end":
                sign *= -1
            c.setAttr(profile + ".tx", .482 * sign)
        self._cage_two_targets(offset, joint + "_middleCurve",
                               previous + "_middleCurve" if previous else "", .75, .25)
        return curve

    def _cage_main_box(self, first):
        joints = []
        child = self._cage_rla_child(first)
        while child:
            if not fnmatchcase(child, "*Part[0-9]*"):
                if not joints:
                    joints.append(first)
                joints.append(child)
            child = self._cage_rla_child(child)
        if joints:
            return self._cage_build_chain(joints)
        return None

    def _cage_build_chain(self, joints):
        c = self.cmds
        height = float(c.getAttr(self._cage_main() + ".height"))
        count = len(joints)
        spine, terminator, top, negative = [], [], [], []
        down = [0] * count
        up = [0] * count
        scales = []
        children = []
        for joint in joints:
            leaf = self._cage_leaf(joint)
            spine.append(any(fnmatchcase(leaf, token) for token in (
                "Head_M", "Hair_M", "Root_M", "Spine*_M", "Chest_M", "Tail*_M")))
            children = self._cage_children(joint)
            terminator.append(not children)
            top.append(not self._cage_parent(joint))
            value = 0
            if children:
                plug = children[0] + ".tx"
                # asGetAttrOPM reads local translation including an OPM graph.
                value = c.getAttr(plug)
                opm = children[0] + ".offsetParentMatrix"
                if c.objExists(opm):
                    matrix = c.getAttr(opm)
                    if len(matrix) == 1: matrix = matrix[0]
                    if abs(matrix[12]) > abs(value): value = matrix[12]
            negative.append(value < 0)
        for i, joint in enumerate(joints):
            leaf = self._cage_leaf(joint)
            divisor = 40
            if fnmatchcase(leaf, "Wrist_*"): divisor = 80
            if fnmatchcase(leaf, "Elbow_*"): divisor = 60
            if "Finger" in leaf: divisor = 140
            if spine[i]: divisor = 15
            scale = height / divisor
            scales.append(scale)
            profile = self._cage_mesh_curve(joint + "_middleCurve")
            c.xform(profile, objectSpace=True, scale=(scale, scale, scale))
            self._cage_align(profile, joint)
            parent = self._cage_parent(joint)
            if (leaf.startswith("Elbow") or leaf.startswith("Knee")) and parent:
                constraint = c.orientConstraint(joint, parent, profile)[0]
                c.setAttr(constraint + ".interpType", 2)
                c.delete(constraint)
            if terminator[i]:
                self._cage_align(profile, parent, translate=False)
            c.parent(profile, self._name("MeshCurves"))
            c.editDisplayLayerMembers(self._name("SkinCurves1"), profile, noRecurse=True)
            c.refresh()
        for i, chain_joint in enumerate(joints):
            fit = self._name(self._cage_leaf(chain_joint).split("_")[0])
            parts = 2
            for attribute in ("inbetweenJoints", "twistJoints"):
                if c.objExists(fit + "." + attribute):
                    parts = int(c.getAttr(fit + "." + attribute))
            joint = chain_joint
            part_number = 1
            while True:
                children = self._cage_children(joint)
                twist = children[0] if children else ""
                for child in children:
                    if fnmatchcase(child, "*Part[0-9]*"):
                        twist = child
                joint = twist
                if not fnmatchcase(joint, "*Part[0-9]*"):
                    break
                down[i] += 1
                curve = chain_joint + "_twistCurve" + str(down[i])
                profile = self._cage_mesh_curve(curve)
                offset = c.createNode("transform", name=curve + "Offset")
                c.parent(profile, offset)
                c.parent(offset, self._name("MeshCurves"))
                c.editDisplayLayerMembers(self._name("SkinCurves2"), profile, noRecurse=True)
                self._cage_align(offset, twist)
                amount = part_number / (parts + 1.0)
                self._cage_two_targets(offset, chain_joint + "_middleCurve",
                                       joints[i + 1] + "_middleCurve", 1 - amount, amount)
                part_number += 1
            if i > 0 and down[i - 1]:
                up[i] = down[i - 1]
        starts = [not terminator[i] and not spine[i] and not up[i] and count > 1
                  and not c.objExists(joints[0] + ".noStartCurve") for i in range(count)]
        ends = [not terminator[i] and not spine[i] and not down[i] and count > 1
                and not c.objExists(joints[0] + ".noEndCurve") for i in range(count)]
        for i, joint in enumerate(joints):
            if starts[i]:
                self._cage_end_curve(joint, joints[i - 1] if i else "", "start", negative[i], i == 0)
        for i, joint in enumerate(joints):
            if ends[i]:
                self._cage_end_curve(joint, joints[i + 1] if i + 1 < count else "", "end", negative[i], i == count - 1)
        curves = []
        for i, joint in enumerate(joints):
            if starts[i]: curves.append(joint + "_startCurve")
            curves.append(joint + "_middleCurve")
            if ends[i]: curves.append(joint + "_endCurve")
            curves.extend(joint + "_twistCurve" + str(n) for n in range(1, down[i] + 1))
            children = self._cage_children(joint)
        copies = []
        flip = False
        previous = ""
        for i, curve in enumerate(curves):
            duplicate = c.duplicate(curve, name=curve + "_copy")[0]
            c.connectAttr(curve + ".worldSpace[0]", duplicate + ".create")
            copies.append(duplicate)
            joint = curve.rsplit("_", 1)[0]
            twist_rotation = c.getAttr(joint + ".jointOrientX")
            if i > 0 and abs(twist_rotation) > 90 and joint != previous:
                flip = not flip
            previous = joint
            if flip: c.setAttr(duplicate + ".rx", 180)
        surface_name = joints[0] + "_surface"
        if count == 1:
            surface = c.extrude(copies, name=surface_name, ch=1, rn=False,
                                po=0, et=0, upn=1, length=height / -250,
                                rotation=0, scale=1, dl=3)[0]
        else:
            surface = c.loft(copies, name=surface_name, ch=1, u=1, c=0,
                             ar=1, d=1, ss=1, rn=0, po=0, rsn=True)[0]
        c.parent(surface, self._name("NurbsGeometry"))
        poly = c.nurbsToPoly(surface, name=joints[0] + "_poly", mnd=1, ch=1,
                             f=3, pt=0, pc=200, chr=.9, ft=.01, mel=.001, d=.1,
                             ut=1, un=3, vt=1, vn=3, uch=0, ucr=0, cht=0,
                             es=0, ntr=0, mrt=0, uss=1)[0]
        c.polySoftEdge(poly, angle=0, constructionHistory=True)
        if self._cage_leaf(joints[0]).endswith("_L"):
            c.polyNormal(poly, normalMode=0, userNormalMode=0, constructionHistory=True)
        c.polyMergeVertex(poly, distance=.0001, alwaysMergeTwoVertices=True, constructionHistory=True)
        c.duplicate(poly, name=poly + "_copy")
        c.parent(poly, self._name("MeshGeometry"))
        c.select(joints, replace=True)
        parent = self._cage_parent(joints[0])
        if parent: c.select(parent, add=True)
        last_children = []
        for joint in joints:
            last_children = c.listRelatives(joint, children=True, type="joint") or []
            if not last_children: c.select(joint, deselect=True)
        for child in last_children:
            if c.listRelatives(child, children=True, type="joint"):
                c.select(child, add=True)
        for i, joint in enumerate(joints):
            name, side = self._cage_leaf(joint).split("_")[:2]
            for n in range(1, down[i] + 1):
                c.select(self._name(name + "Part" + str(n) + "_" + side), add=True)
            partial = self._name(name + "Partial_" + side)
            if c.objExists(partial): c.select(partial, add=True)
        c.select(poly, add=True)
        from .maya_original_skin_history import new_original_skin_clusters
        skin = new_original_skin_clusters(commands=c, namespace=self.namespace)[0]
        sampler = self._name("closestSampler")
        if c.objExists(sampler): c.delete(sampler)
        sampler = c.createNode("closestPointOnMesh", name=sampler)
        shape = c.listRelatives(poly, shapes=True, noIntermediate=True, type="mesh")[0]
        c.connectAttr(shape + ".outMesh", sampler + ".inMesh", force=True)
        def weight_curve(curve, weights):
            for cv in range(4):
                point = c.xform(f"{curve}.cv[{cv}]", query=True, worldSpace=True, translation=True)
                c.setAttr(sampler + ".inPosition", *point, type="float3")
                vertex = int(c.getAttr(sampler + ".closestVertexIndex"))
                for joint, weight in weights:
                    c.skinPercent(skin, f"{poly}.vtx[{vertex}]", transformValue=(joint, weight))
        for i, joint in enumerate(joints):
            name, side = self._cage_leaf(joint).split("_")[:2]
            parent = self._cage_parent(joint)
            skin_joint = joint
            if not (c.listRelatives(joint, children=True, type="joint") or []) and parent:
                skin_joint = parent
            weights = [(skin_joint, 1)]
            if not spine[i] and parent and skin_joint == joint:
                weights.append((parent, .5))
            partial = self._name(name + "Partial_" + side)
            if c.objExists(partial): weights.append((partial, 1))
            weight_curve(joint + "_middleCurve", weights)
            for n in range(1, down[i] + 1):
                weight_curve(joint + "_twistCurve" + str(n),
                             [(self._name(name + "Part" + str(n) + "_" + side), 1)])
            if starts[i] and not top[i]:
                weight_curve(joint + "_startCurve", [(joints[i - 1] if i else self._cage_parent(joints[0]), 1)])
            if ends[i]: weight_curve(joint + "_endCurve", [(joint, 1)])
        if not children:
            end = joints[-1]
            cap = c.polyPlane(name=end + "_cap_copy", width=1, height=1,
                              subdivisionsX=1, subdivisionsY=1, axis=(1, 0, 0),
                              createUVs=2, constructionHistory=False)[0]
            if self._cage_leaf(end).endswith("_L"):
                c.polyNormal(cap, normalMode=0, userNormalMode=0, constructionHistory=True)
            size = scales[-1] * 2 / 1.2
            c.setAttr(cap + ".s", size, size, size, type="float3")
            self._cage_align(cap, end)
            self._cage_align(cap, self._cage_parent(end), translate=False)
        return poly

    def _cage_native(self, command):
        from maya import mel
        mel.eval(command + ";")

    def _cage_face_normal(self, face):
        from math import sqrt
        values = self.cmds.polyInfo(face, faceNormals=True)[0].split()[-3:]
        normal = tuple(float(value) for value in values)
        length = sqrt(sum(value * value for value in normal))
        return tuple(value / length for value in normal) if length else (0, 0, 0)

    def _cage_remove_fourth_edge(self, mesh):
        c = self.cmds
        count = int(c.polyEvaluate(mesh, vertex=True))
        for i in range(count):
            vertex = f"{mesh}.vtx[{i}]"
            c.select(vertex, replace=True)
            self._cage_native("ConvertSelectionToEdges")
            if len(c.ls(selection=True, flatten=True) or []) < 4:
                continue
            self._cage_native("ConvertSelectionToVertices")
            c.select(vertex, deselect=True)
            neighbors = c.ls(selection=True, flatten=True) or []
            for neighbor in neighbors:
                c.select(neighbor, replace=True)
                self._cage_native("ConvertSelectionToEdges")
                if len(c.ls(selection=True, flatten=True) or []) < 4:
                    continue
                self._cage_native("ConvertSelectionToVertices")
                c.select(neighbor, deselect=True)
                if vertex in (c.ls(selection=True, flatten=True) or []):
                    c.select([vertex, neighbor], replace=True)
                    self._cage_native("ConvertSelectionToContainedEdges")
                    if c.ls(selection=True):
                        try: c.delete()
                        except RuntimeError: pass
        c.select(clear=True)

    def _cage_generic_branch(self, joint, children):
        """asCreateBranchBoxes generic branch: normal selection + 20-span bridge.

        The source trims fixed bridge topology after construction. It does not
        connect corresponding profile corners with four independent facets.
        """
        c = self.cmds
        height = float(c.getAttr(self._cage_main() + ".height"))
        if self._cage_leaf(joint) == "Root_M":
            preferred = self._cage_rla_child(joint)
            children = [child for child in children if child != preferred]
        children = [child for child in children if c.objExists(child + "_startCurve")
                    or c.objExists(child + "_middleCurve")]
        if len(children) < 2:
            return None
        parent_curve = joint + "_middleCurve"
        if c.objExists(joint + "_endCurve"):
            parent_curve = joint + "_endCurve"
        if not c.objExists(parent_curve):
            return None
        center = c.createNode("transform", name=self._name("branchBoxCenter"))
        c.pointConstraint(joint, center)
        if self._cage_leaf(joint) != "Root_M":
            for child in children: c.pointConstraint(child, center)
        bridge = self._name("bridgeMesh")
        closest_face = 0
        bridge_curve = ""
        edges = [edge for base in range(14, 167, 8)
                 for edge in (base, base + 2, base + 4, base + 5)]
        for y, child in enumerate(children):
            child_curve = child + ("_startCurve" if c.objExists(child + "_startCurve") else "_middleCurve")
            plane = c.polyPlane(name=self._name("tempPolyPlane" + self._cage_leaf(child)),
                                w=1, h=1, sx=1, sy=1, ax=(0, 1, 0), cuv=2, ch=0)[0]
            self._cage_align(plane, child_curve, rotate=False)
            c.delete(c.aimConstraint(joint, plane, offset=(0, 0, 0), weight=1,
                                     aimVector=(0, 1, 0), upVector=(1, 0, 0),
                                     worldUpType="vector", worldUpVector=(1, 0, 0)))
            c.makeIdentity(plane, apply=True, translate=False, rotate=True, scale=False)
            direction = self._cage_face_normal(plane + ".f[0]")
            c.delete(plane)
            if y > 0:
                side = self._cage_leaf(joint).split("_")[-1]
                bridge_curve = self._name("bridgeCurve_" + self._cage_leaf(joint) + "_" + side + "_middleProfile")
                c.select(child_curve, replace=True)
                c.cluster(name=self._name("tempCluster"), envelope=1)
                # Source reads the handle origin before deleting the cluster;
                # retain evaluation even though the returned position is unused.
                c.getAttr(self._name("tempClusterHandleShape") + ".origin")
                c.delete(self._name("tempCluster"))
                minimum_dot = 999
                for face in range(int(c.polyEvaluate(bridge, face=True))):
                    normal = self._cage_face_normal(f"{bridge}.f[{face}]")
                    dot = sum(a * b for a, b in zip(direction, normal))
                    if dot >= minimum_dot:
                        continue
                    sampler = self._name("closestSampler")
                    if c.objExists(sampler): c.delete(sampler)
                    sampler = c.createNode("closestPointOnMesh", name=sampler)
                    shape = c.listRelatives(bridge, shapes=True, noIntermediate=True, type="mesh")[0]
                    c.connectAttr(shape + ".outMesh", sampler + ".inMesh", force=True)
                    c.select(f"{bridge}.f[{face}]", replace=True)
                    self._cage_native("ConvertSelectionToVertices")
                    vertices = set(c.ls(selection=True, flatten=True) or [])
                    connects = False
                    for a in range(4):
                        position = c.xform(f"{child_curve}.cv[{a}]", query=True,
                                           worldSpace=True, translation=True)
                        c.setAttr(sampler + ".inPosition", *position, type="float3")
                        vertex = int(c.getAttr(sampler + ".result.closestVertexIndex"))
                        if f"{bridge}.vtx[{vertex}]" in vertices: connects = True
                    if connects:
                        minimum_dot = dot
                        closest_face = face
                    c.delete(sampler)
                c.select(f"{bridge}.f[{closest_face}]", replace=True)
                self._cage_native("ConvertSelectionToEdges")
                self._cage_native("DuplicateCurve -ch 0")
                old_curves = c.ls(selection=True) or []
                c.attachCurve(ch=0, rpo=0, kmk=1, m=1, bb=.5, bki=0, p=.1)
                c.delete(old_curves)
                c.rename((c.ls(selection=True) or [""])[0], bridge_curve)
            meshes = []
            for parent_side in (True, False):
                curve = parent_curve if parent_side else child_curve
                mesh_name = self._name("parentMesh" if parent_side else "childMesh")
                sign = -1 if parent_side else 1
                if y > 0 and parent_side: curve = bridge_curve
                if fnmatchcase(curve, "*_L_*"): sign *= -1
                if fnmatchcase(curve, "*Root_M_*"): sign *= -1
                surface = c.extrude(curve, name=self._name("parentSurface"), ch=1,
                                    rn=False, po=0, et=0, upn=1,
                                    length=height / 100 * sign, rotation=0, scale=1, dl=3)[0]
                if bridge_curve and c.objExists(bridge_curve): c.delete(bridge_curve)
                mesh = c.nurbsToPoly(surface, name=mesh_name, mnd=1, ch=0, f=2,
                                     pt=1, pc=200, chr=.9, ft=.01, mel=.001, d=.1,
                                     ut=3, un=1, vt=3, vn=1, uch=0, ucr=0, cht=.2,
                                     es=0, ntr=0, mrt=0, uss=1)[0]
                c.delete(surface)
                c.select([f"{mesh}.e[{edge}]" for edge in (2, 6, 9, 11)], replace=True)
                self._cage_native("FillHole")
                if sign == -1:
                    c.polyNormal(mesh, normalMode=0, userNormalMode=0, constructionHistory=True)
                meshes.append(mesh)
            c.delete(meshes, constructionHistory=True)
            part = c.polyUnite(meshes, mergeUVSets=1, name=self._name("bridgeMesh" + str(y)))[0]
            c.delete(part, constructionHistory=True)
            c.select(part, replace=True)
            operation = c.polyBridgeEdge(ch=1, divisions=20, twist=0, taper=1,
                                         curveType=0, smoothingAngle=30)[0]
            c.rename(operation, self._name("SkinCurvesBranchingPolyBridgeEdge"))
            c.select(part + ".f[0:9]", replace=True)
            c.delete()
            c.select([f"{part}.e[{edge}]" for edge in edges], replace=True)
            selected_edges = c.ls(selection=True) or []
            self._cage_native("ConvertSelectionToVertices")
            selected_vertices = c.ls(selection=True) or []
            c.select(selected_edges, replace=True)
            c.delete()
            c.select(selected_vertices, replace=True)
            c.delete()
            c.delete(part, constructionHistory=True)
            if y == 0:
                c.duplicate(part, name=bridge)
            else:
                old = c.rename(bridge, self._name("bridgeMeshOld"))
                c.delete(f"{old}.f[{closest_face}]")
                copy = c.duplicate(part, name=self._name("bridgeMeshToMerge" + str(y)))[0]
                c.polyUnite(old, copy, ch=0, mergeUVSets=1, name=bridge)
                c.polyMergeVertex(bridge, d=.001, am=1, ch=0)
                c.select(clear=True)
                if self._cage_leaf(joint).endswith("_M") and len(children) % 2 == 0:
                    self._cage_remove_fourth_edge(bridge)
        c.delete(center)
        result = c.rename(bridge, joint + "_branch")
        leftovers = c.ls(self._name("bridgeMesh*") ) or []
        if leftovers: c.delete(leftovers)
        return result

    def _cage_parent_constraint(self, source, target, *, maintain_offset=True):
        # Reuse the already translated asParentConstraint graph. The outer
        # SkinCage transaction owns it; this helper does not open another chunk.
        from types import SimpleNamespace
        from .maya_body_parent_constraint import MayaBodyParentConstraintMixin
        from adv_py.core.body_parent_constraint import plan_body_parent_constraint
        c = self.cmds
        opm = self._name("FitSkeleton") + ".useOffsetParentMatrix"
        bridge = SimpleNamespace(_cmds=c, namespace=None,
                                 _use_offset_parent_matrix=bool(c.objExists(opm) and c.getAttr(opm)),
                                 _transaction_changed=False, _require_transaction=lambda: None)
        source = c.ls(source, long=True)[0]
        target = c.ls(target, long=True)[0]
        inputs = MayaBodyParentConstraintMixin.capture_parent_constraint_input(bridge, source, target, maintain_offset)
        plan = plan_body_parent_constraint(inputs)
        MayaBodyParentConstraintMixin.preflight_parent_constraint(bridge, plan)
        MayaBodyParentConstraintMixin.create_parent_constraint(bridge, plan)
