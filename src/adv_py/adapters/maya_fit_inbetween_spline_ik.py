"""Maya graph for Inbetween markers on a variable-length spline spine."""
from __future__ import annotations

import json

from adv_py.core.fit_inbetween_spline_ik import InbetweenSplineIkPlan


class MayaInbetweenSplineIkMixin:
    def preflight_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> None:
        c = self._cmds
        if (c.ls(plan.root_path, long=True, type="transform") or []) != [plan.root_path]:
            raise ValueError("Spline Inbetween 根层不存在")
        for path in (plan.start_output_path, plan.end_output_path):
            if ((c.ls(path, long=True) or []) != [path]
                    or c.nodeType(path) not in ("transform", "joint")):
                raise ValueError("Spline Inbetween 输出层不存在：" + path)
        if any((c.ls(frame.body_part_path, long=True, type="joint") or [])
               != [frame.body_part_path] for frame in plan.frames):
            raise ValueError("Spline Inbetween Body Part 不存在")
        for frame in plan.frames:
            if frame.native_output_path is not None and ((c.ls(frame.native_output_path,long=True,type='transform') or [])!=[frame.native_output_path]):
                raise ValueError('Spline Part 原生双链输出不存在')
        if any(c.objExists(name) for name in plan.node_names):
            raise ValueError("Spline Inbetween 节点名称冲突")

    def create_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> None:
        self._require_transaction()
        c = self._cmds
        for frame in plan.frames:
            bind_matrix = c.xform(frame.body_part_path, query=True,
                                  worldSpace=True, matrix=True)
            output=frame.native_output_path
            if output is not None:
                parent=c.createNode('transform',name=frame.frame_name,parent=output)
                c.xform(parent,worldSpace=True,matrix=bind_matrix)
                c.addAttr(parent,longName='advPySplineRestLocal',dataType='string')
                c.setAttr(parent+'.advPySplineRestLocal',json.dumps(tuple(c.getAttr(parent+'.matrix'))),type='string',lock=True)
                marker=c.createNode('joint',name=frame.ikx_name,parent=parent,skipSelect=True)
                c.setAttr(marker+'.drawStyle',2)
                c.setAttr(marker+'.segmentScaleCompensate',0)
                c.setAttr(marker+'.rotateOrder',frame.rotate_order)
                self._transaction_changed=True
                continue
            blend = c.createNode("blendMatrix", name=frame.blend_name)
            local = c.createNode("multMatrix", name=frame.local_matrix_name)
            parent = c.createNode("transform", name=frame.frame_name,
                                  parent=plan.root_path)
            marker = c.createNode("joint", name=frame.ikx_name,
                                  parent=parent, skipSelect=True)
            self._transaction_changed = True
            c.setAttr(marker + ".drawStyle", 2)
            c.setAttr(marker + ".segmentScaleCompensate", 0)
            c.setAttr(marker + ".rotateOrder", frame.rotate_order)
            c.connectAttr(plan.start_output_path + ".worldMatrix[0]",
                          blend + ".inputMatrix")
            c.connectAttr(plan.end_output_path + ".worldMatrix[0]",
                          blend + ".target[0].targetMatrix")
            c.setAttr(blend + ".target[0].weight", frame.fraction)
            c.connectAttr(blend + ".outputMatrix", local + ".matrixIn[0]")
            c.connectAttr(plan.root_path + ".worldInverseMatrix[0]",
                          local + ".matrixIn[1]")
            c.connectAttr(local + ".matrixSum", parent + ".offsetParentMatrix")
            c.xform(marker, worldSpace=True, matrix=bind_matrix)

    def capture_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> bool:
        c = self._cmds
        for frame in plan.frames:
            parent = c.ls(frame.frame_name, long=True, type="transform") or []
            marker = c.ls(frame.ikx_name, long=True, type="joint") or []
            output=frame.native_output_path
            if output is not None:
                if (len(parent)!=1 or len(marker)!=1
                        or (c.listRelatives(parent[0],parent=True,fullPath=True) or [])!=[output]
                        or (c.listRelatives(marker[0],parent=True,fullPath=True) or [])!=parent
                        or any(abs(a-b)>1e-5 for a,b in zip(
                            c.xform(marker[0],query=True,worldSpace=True,matrix=True),
                            c.xform(frame.body_part_path,query=True,worldSpace=True,matrix=True)))):
                    return False
                continue
            if (len(parent) != 1 or len(marker) != 1
                    or (c.listRelatives(parent[0], parent=True, fullPath=True)
                        or []) != [plan.root_path]
                    or (c.listRelatives(marker[0], parent=True, fullPath=True)
                        or []) != parent):
                return False
            edges = (
                (frame.blend_name + ".inputMatrix",
                 plan.start_output_path + ".worldMatrix[0]"),
                (frame.blend_name + ".target[0].targetMatrix",
                 plan.end_output_path + ".worldMatrix[0]"),
                (frame.local_matrix_name + ".matrixIn[0]",
                 frame.blend_name + ".outputMatrix"),
                (frame.local_matrix_name + ".matrixIn[1]",
                 plan.root_path + ".worldInverseMatrix[0]"),
                (parent[0] + ".offsetParentMatrix",
                 frame.local_matrix_name + ".matrixSum"),
            )
            if (any(not c.isConnected(source, destination)
                    for destination, source in edges)
                    or abs(c.getAttr(frame.blend_name + ".target[0].weight")
                           - frame.fraction) > 1e-8
                    or any(abs(a - b) > 1e-5 for a, b in zip(
                        c.xform(marker[0], query=True, worldSpace=True,
                                matrix=True),
                        c.xform(frame.body_part_path, query=True,
                                worldSpace=True, matrix=True)))):
                return False
        return True
