"""Capture original rig guide data from the scene already open in Maya."""
from __future__ import annotations

import re

NAME = re.compile(r"^(Root|Chest|Scapula|Shoulder|Elbow|Wrist|Hip|Knee|Ankle)[ABCD]Joint_[RL]$")
ANGLES = {"Hip": ("angleY", "angleZ"), "Shoulder": ("angleY",), "Wrist": ("angleY", "angleZ"), "Ankle": ("angleZ",)}
PARTS = ("RootPart1_M", "RootPart2_M", "Spine1Part1_M", "Spine1Part2_M", "NeckPart1_M", "NeckPart2_M")

def capture_volume(cmds, source_name: str) -> dict:
    def inputs(node):
        return {attr: cmds.listConnections(node + "." + attr,
            source=True, destination=False, plugs=True) or []
            for attr in ("translate", "rotate", "scale",
                         "translateX", "translateY", "translateZ",
                         "rotateX", "rotateY", "rotateZ",
                         "scaleX", "scaleY", "scaleZ",
                         "offsetParentMatrix")}

    def chain(node):
        result = []
        while node and node not in ("Group", "Main", "DeformationSystem"):
            result.append({
                "name": node,
                "type": cmds.nodeType(node),
                "parent": (cmds.listRelatives(node, parent=True,
                    fullPath=False) or [None])[0],
                "translate": cmds.getAttr(node + ".translate")[0],
                "rotate": cmds.getAttr(node + ".rotate")[0],
                "scale": cmds.getAttr(node + ".scale")[0],
                "world_matrix": cmds.xform(node, query=True,
                    worldSpace=True, matrix=True),
                "inputs": inputs(node),
            })
            node = result[-1]["parent"]
        return result

    def source_nodes(chain_rows):
        result = {}
        pending = [plug for row in chain_rows[:3]
                   for values in row["inputs"].values() for plug in values]
        while pending:
            plug = pending.pop()
            node = plug.split(".", 1)[0]
            if node in result:
                continue
            node_type = cmds.nodeType(node)
            if node_type not in ("blendWeighted", "animCurveUA", "animCurveUL",
                                 "animCurveUU", "animCurveUT", "unitConversion"):
                continue
            sources = cmds.listConnections(node, source=True,
                destination=False, plugs=True) or []
            pairs = cmds.listConnections(node, source=True,
                destination=False, plugs=True, connections=True) or []
            record = {"type": node_type,
                      "sources": sorted(set(sources)),
                      "connections": [pairs[index:index + 2]
                                      for index in range(0, len(pairs), 2)]}
            if node_type.startswith("animCurve"):
                record["keys"] = list(zip(
                    cmds.keyframe(node, query=True, floatChange=True) or [],
                    cmds.keyframe(node, query=True, valueChange=True) or []))
                record["pre_infinity"] = cmds.getAttr(node + ".preInfinity")
                record["post_infinity"] = cmds.getAttr(node + ".postInfinity")
                record["in_tangent_types"] = cmds.keyTangent(node,
                    query=True, inTangentType=True) or []
                record["out_tangent_types"] = cmds.keyTangent(node,
                    query=True, outTangentType=True) or []
                record["weighted_tangents"] = bool((cmds.keyTangent(node,
                    query=True, weightedTangents=True) or [False])[0])
            elif node_type == "unitConversion":
                record["conversion_factor"] = cmds.getAttr(
                    node + ".conversionFactor")
            elif node_type == "blendWeighted":
                indices = cmds.getAttr(node + ".input", multiIndices=True) or []
                record["weights"] = {str(index): cmds.getAttr(
                    f"{node}.weight[{index}]") for index in indices}
            result[node] = record
            pending.extend(sources)
        return result

    rows = []
    for name in sorted(cmds.ls(type="joint") or []):
        if not NAME.match(name):
            continue
        parent = (cmds.listRelatives(name, parent=True,
                                    fullPath=False) or [None])[0]
        constraints = cmds.listConnections(name, source=True,
            destination=False, type="parentConstraint") or []
        if len(set(constraints)) != 1:
            raise ValueError(name + " does not have one parent constraint")
        constraint = constraints[0]
        targets = cmds.parentConstraint(constraint, query=True,
                                        targetList=True) or []
        if len(targets) != 1:
            raise ValueError(name + " does not have one driver target")
        target = targets[0]
        target_parent = (cmds.listRelatives(target, parent=True,
            fullPath=False) or [None])[0]
        target_chain = chain(target)
        graph = source_nodes(target_chain)
        external = sorted({plug for node in graph.values()
            for plug in node["sources"]
            if plug.split(".", 1)[0] not in graph})
        rows.append({
            "name": name, "parent": parent, "target": target,
            "parent_world_matrix": cmds.xform(parent, query=True,
                worldSpace=True, matrix=True),
            "target_parent": target_parent,
            "joint_world_matrix": cmds.xform(name, query=True,
                worldSpace=True, matrix=True),
            "target_world_matrix": cmds.xform(target, query=True,
                worldSpace=True, matrix=True),
            "joint_local_translate": cmds.getAttr(name + ".translate")[0],
            "joint_local_rotate": cmds.getAttr(name + ".rotate")[0],
            "joint_orient": cmds.getAttr(name + ".jointOrient")[0],
            "joint_rotate_order": cmds.getAttr(name + ".rotateOrder"),
            "joint_local_scale": cmds.getAttr(name + ".scale")[0],
            "joint_inputs": inputs(name),
            "joint_scale_driver": [{"name": node,
                "type": cmds.nodeType(node),
                "input1": cmds.getAttr(node + ".input1")[0],
                "input2": cmds.getAttr(node + ".input2")[0],
                "connections": [pair[index:index + 2]
                    for index in range(0, len(pair), 2)]}
                for node in (cmds.listConnections(name + ".scale",
                    source=True, destination=False) or [])
                for pair in [cmds.listConnections(node, source=True,
                    destination=False, plugs=True, connections=True) or []]
                if cmds.nodeType(node) == "multiplyDivide"],
            "target_local_translate": cmds.getAttr(target + ".translate")[0],
            "target_local_rotate": cmds.getAttr(target + ".rotate")[0],
            "target_inputs": inputs(target),
            "target_chain": target_chain,
            "sdk_sources": graph,
            "external_drivers": {plug: {
                "value": cmds.getAttr(plug),
                "source": cmds.listConnections(plug, source=True,
                    destination=False, plugs=True) or []}
                for plug in external},
            "parent_node": {"type": cmds.nodeType(parent),
                "world_matrix": cmds.xform(parent, query=True,
                    worldSpace=True, matrix=True),
                "rotate_order": cmds.getAttr(parent + ".rotateOrder"),
                "parent_world_matrix": cmds.xform(
                    (cmds.listRelatives(parent, parent=True,
                        fullPath=False) or [None])[0], query=True,
                    worldSpace=True, matrix=True),
                "translate": cmds.getAttr(parent + ".translate")[0],
                "rotate": cmds.getAttr(parent + ".rotate")[0],
                "joint_orient": (cmds.getAttr(parent + ".jointOrient")[0]
                    if cmds.nodeType(parent) == "joint" else None),
                "scale": cmds.getAttr(parent + ".scale")[0],
                "inputs": inputs(parent),
                "constraints": [{"name": constraint,
                    "type": kind,
                    "targets": (cmds.pointConstraint(constraint,
                        query=True, targetList=True) if kind == "pointConstraint"
                        else cmds.orientConstraint(constraint,
                            query=True, targetList=True)) or [],
                    "weights": (cmds.pointConstraint(constraint,
                        query=True, weightAliasList=True) if kind == "pointConstraint"
                        else cmds.orientConstraint(constraint,
                            query=True, weightAliasList=True)) or [],
                    "weight_values": [cmds.getAttr(constraint + "." + alias)
                        for alias in ((cmds.pointConstraint(constraint,
                            query=True, weightAliasList=True)
                            if kind == "pointConstraint" else
                            cmds.orientConstraint(constraint, query=True,
                                weightAliasList=True)) or [])],
                    "offset": cmds.getAttr(constraint + ".offset")[0],
                    "interp_type": (cmds.getAttr(constraint + ".interpType")
                        if kind == "orientConstraint" else None)}
                    for kind in ("pointConstraint", "orientConstraint")
                    for constraint in sorted(set(cmds.listConnections(parent,
                        source=True, destination=False, type=kind) or []))]},
            "parent_zero": ({"name": parent.removesuffix("_50") + "_00",
                "parent": (cmds.listRelatives(
                    parent.removesuffix("_50") + "_00", parent=True,
                    fullPath=False) or [None])[0],
                "translate": cmds.getAttr(
                    parent.removesuffix("_50") + "_00.translate")[0],
                "rotate": cmds.getAttr(
                    parent.removesuffix("_50") + "_00.rotate")[0],
                "scale": cmds.getAttr(
                    parent.removesuffix("_50") + "_00.scale")[0]}
                if parent.endswith("_50") and cmds.objExists(
                    parent.removesuffix("_50") + "_00") else None),
            "parent_inputs": inputs(parent) if parent else None,
            "parent_parent": (cmds.listRelatives(parent, parent=True,
                fullPath=False) or [None])[0] if parent else None,
        })
    if len(rows) != 40:
        raise ValueError("expected 40 weighted volume joints, got " + str(len(rows)))
    return {"source": source_name,
        "root_world_matrix": cmds.xform("Root_M", query=True,
            worldSpace=True, matrix=True),
        "body_world_matrices": {name: cmds.xform(name, query=True,
            worldSpace=True, matrix=True) for name in
            ("Chest_M", "Scapula_R", "Scapula_L", "Knee_R", "Knee_L")},
        "count": len(rows), "joints": rows}

def capture_angle(cmds, source_name: str) -> dict:
    def graph(plug):
        nodes = {}
        pending = cmds.listConnections(plug, source=True,
            destination=False, plugs=True) or []
        while pending:
            source = pending.pop()
            name = source.split(".", 1)[0]
            if name in nodes:
                continue
            kind = cmds.nodeType(name)
            if kind in ("joint", "transform"):
                continue
            pairs = cmds.listConnections(name, source=True,
                destination=False, plugs=True, connections=True) or []
            connections = [pairs[i:i + 2] for i in range(0, len(pairs), 2)]
            row = {"type": kind, "connections": connections}
            if kind == "locator":
                transform = (cmds.listRelatives(name, parent=True,
                    fullPath=False) or [None])[0]
                row["transform"] = transform
                row["parent"] = (cmds.listRelatives(transform, parent=True,
                    fullPath=False) or [None])[0]
                row["translate"] = cmds.getAttr(transform + ".translate")[0]
                row["rotate"] = cmds.getAttr(transform + ".rotate")[0]
                row["scale"] = cmds.getAttr(transform + ".scale")[0]
                row["local_position"] = cmds.getAttr(name + ".localPosition")[0]
                ancestors = []
                node = row["parent"]
                while node and cmds.nodeType(node) == "transform" and len(ancestors) < 8:
                    parent = (cmds.listRelatives(node, parent=True,
                        fullPath=False) or [None])[0]
                    pairs = cmds.listConnections(node, source=True,
                        destination=False, plugs=True, connections=True) or []
                    ancestors.append({"name": node, "parent": parent,
                        "translate": cmds.getAttr(node + ".translate")[0],
                        "rotate": cmds.getAttr(node + ".rotate")[0],
                        "scale": cmds.getAttr(node + ".scale")[0],
                        "world_matrix": cmds.xform(node, query=True,
                            worldSpace=True, matrix=True),
                        "constraints": [{"name": constraint,
                            "type": kind,
                            "targets": (cmds.pointConstraint(constraint,
                                query=True, targetList=True)
                                if kind == "pointConstraint" else
                                cmds.orientConstraint(constraint,
                                    query=True, targetList=True)) or [],
                            "offset": cmds.getAttr(constraint + ".offset")[0]}
                            for kind in ("pointConstraint", "orientConstraint")
                            for constraint in sorted(set(cmds.listConnections(
                                node, source=True, destination=False,
                                type=kind) or []))],
                        "connections": [pairs[i:i + 2]
                            for i in range(0, len(pairs), 2)]})
                    node = parent
                row["ancestor_chain"] = ancestors
            elif kind == "condition":
                row["operation"] = cmds.getAttr(name + ".operation")
                row["first_term"] = cmds.getAttr(name + ".firstTerm")
                row["second_term"] = cmds.getAttr(name + ".secondTerm")
                row["true_color"] = cmds.getAttr(name + ".colorIfTrue")[0]
                row["false_color"] = cmds.getAttr(name + ".colorIfFalse")[0]
            elif kind == "unitConversion":
                row["conversion_factor"] = cmds.getAttr(
                    name + ".conversionFactor")
            elif kind == "plusMinusAverage":
                row["operation"] = cmds.getAttr(name + ".operation")
                row["input3d"] = {str(index): cmds.getAttr(
                    f"{name}.input3D[{index}]")[0]
                    for index in (cmds.getAttr(name + ".input3D",
                        multiIndices=True) or [])}
            elif kind == "distanceBetween":
                row["point1"] = cmds.getAttr(name + ".point1")[0]
                row["point2"] = cmds.getAttr(name + ".point2")[0]
            nodes[name] = row
            pending.extend(pair[1] for pair in connections)
            if len(nodes) > 200:
                raise ValueError("angle graph unexpectedly large: " + plug)
        return nodes

    rows = {}
    for side in ("R", "L"):
        for stem, attrs in ANGLES.items():
            for attr in attrs:
                plug = f"{stem}_{side}.{attr}"
                rows[plug] = {"value": cmds.getAttr(plug),
                              "source_plug": (cmds.listConnections(plug,
                                  source=True, destination=False,
                                  plugs=True) or [None])[0],
                              "joint_world_matrix": cmds.xform(
                                  f"{stem}_{side}", query=True,
                                  worldSpace=True, matrix=True),
                              "graph": graph(plug)}
    return {"source": source_name, "angles": rows}

def capture_axial(cmds, source_name: str) -> dict:
    rows = {}
    names = set(PARTS)
    for part in PARTS:
        names.add("FKX" + part)
        names.add("IKX" + part)
        names.add("FK" + part)
        names.add("FKExtra" + part)
        names.add("FKPS2" + part)
        names.add("FKPS1" + part)
    names.update(("FKRoot_M", "FKSpine1_M", "FKNeck_M"))
    for stem in ("Root", "Spine1", "Neck"):
        names.update((f"InbetweenBase{stem}_M",
                      f"InbetweenTarget{stem}_M"))
    for part in PARTS:
        paths = cmds.ls("FKX" + part, long=True) or []
        if len(paths) == 1:
            for ancestor in paths[0].split("|")[1:-1]:
                if ancestor.startswith("FK"):
                    names.add(ancestor)
    for name in sorted(names):
        paths = cmds.ls(name, long=True) or []
        if len(paths) != 1:
            continue
        path = paths[0]
        inputs = {}
        for attr in ("translate", "rotate", "scale", "jointOrient"):
            if not cmds.attributeQuery(attr, node=path, exists=True):
                continue
            plugs = []
            for plug in (path + "." + attr,
                         *(path + "." + child for child in
                           (cmds.attributeQuery(attr, node=path,
                                                listChildren=True) or []))):
                plugs.extend(cmds.listConnections(
                    plug, source=True, destination=False, plugs=True,
                    skipConversionNodes=False) or [])
            if plugs:
                inputs[attr] = sorted(set(plugs))
        constraints = []
        for node in sorted({plug.split(".", 1)[0]
                            for plugs in inputs.values() for plug in plugs}):
            kind = cmds.nodeType(node)
            query = {"pointConstraint": cmds.pointConstraint,
                     "orientConstraint": cmds.orientConstraint,
                     "parentConstraint": cmds.parentConstraint}.get(kind)
            if query:
                aliases = query(node, query=True, weightAliasList=True) or []
                constraints.append({"name": node, "type": kind,
                    "targets": query(node, query=True, targetList=True) or [],
                    "weights": [cmds.getAttr(node + "." + alias)
                                for alias in aliases]})
        rows[name] = {
            "type": cmds.nodeType(path), "path": path,
            "parent": (cmds.listRelatives(path, parent=True,
                                           fullPath=True) or [None])[0],
            "world_matrix": cmds.xform(path, query=True,
                                        worldSpace=True, matrix=True),
            "translate": cmds.getAttr(path + ".translate")[0],
            "rotate": cmds.getAttr(path + ".rotate")[0],
            "scale": cmds.getAttr(path + ".scale")[0],
            "joint_orient": (cmds.getAttr(path + ".jointOrient")[0]
                             if cmds.nodeType(path) == "joint" else None),
            "rotate_order": cmds.getAttr(path + ".rotateOrder"),
            "inputs": inputs, "constraints": constraints,
        }
    drivers = {}
    for part in PARTS:
        for suffix in ("InbetweenDM_M", "InbetweenMM_M",
                       "InbetweenBM_M", "HSMM_M"):
            name = part.replace("_M", suffix)
            if not cmds.objExists(name):
                continue
            plugs = cmds.listConnections(name, source=True,
                destination=False, connections=True, plugs=True) or []
            drivers[name] = {"type": cmds.nodeType(name),
                "connections": list(zip(plugs[::2], plugs[1::2])),
            }
            if cmds.nodeType(name) == "multMatrix":
                drivers[name]["matrix_sum"] = cmds.getAttr(
                    name + ".matrixSum")
    for stem in ("Root", "Spine1", "Neck"):
        for position in ("Mid", "End"):
            name = f"FK{stem}{position}BiasRV_M"
            plugs = cmds.listConnections(name, source=True,
                destination=False, connections=True, plugs=True) or []
            drivers[name] = {"type": cmds.nodeType(name),
                "connections": list(zip(plugs[::2], plugs[1::2])),
                "out_value": cmds.getAttr(name + ".outValue")}
    poses = {}
    for stem in ("Root", "Spine1", "Neck"):
        control = "FK" + stem + "_M"
        cmds.setAttr(control + ".rotateY", 20.0)
        poses[stem] = {name: {
            "world_matrix": cmds.xform(name, query=True,
                                        worldSpace=True, matrix=True),
            "rotate": cmds.getAttr(name + ".rotate")[0],
        } for name in (control, "FKX" + stem + "_M",
            *(f"FKOffset{stem}Part{i}_M" for i in (1, 2)),
            *(f"FKPS2{stem}Part{i}_M" for i in (1, 2)),
            *(f"FKPS1{stem}Part{i}_M" for i in (1, 2)),
            *(f"FKX{stem}Part{i}_M" for i in (1, 2)),
            *(f"{stem}Part{i}_M" for i in (1, 2)))}
        cmds.setAttr(control + ".rotateY", 0.0)
    return {"source": source_name, "nodes": rows,
            "drivers": drivers, "poses": poses}

def capture_original_guides(cmds, source_name: str) -> tuple[dict, dict, dict]:
    """Capture all guide data after switching the source legs to FK."""
    return (capture_volume(cmds, source_name),
            capture_angle(cmds, source_name),
            capture_axial(cmds, source_name))
