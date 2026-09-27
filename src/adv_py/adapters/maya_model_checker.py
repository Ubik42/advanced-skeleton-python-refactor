"""Maya sampling for the original Preparation / Model Check rules."""
from __future__ import annotations

from adv_py.core.model_checker import (
    ModelCheckGate, ModelHistoryNode, ModelSymmetryIssue,
    ModelTransformIssue, ModelTransformState,
)


class MayaModelCheckHost:
    def __init__(self):
        from maya import cmds
        from maya.api import OpenMaya

        self.cmds = cmds
        self.om = OpenMaya

    def selected_mesh(self) -> str:
        cmds = self.cmds
        selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        if not selection:
            raise ValueError("请先选择一个多边形模型")
        node = selection[0]
        if cmds.nodeType(node) == "mesh":
            shapes = [node]
            transform = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
        else:
            transform = node
            shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                        fullPath=True) or []
        if not transform or cmds.nodeType(transform) != "transform":
            raise ValueError("所选对象不是多边形模型")
        meshes = [shape for shape in shapes if cmds.nodeType(shape) == "mesh"]
        if len(meshes) != 1:
            raise ValueError("请选择恰有一个非中间多边形 Shape 的模型")
        return meshes[0]

    def vertex_count(self, mesh: str) -> int:
        return int(self.cmds.polyEvaluate(mesh, vertex=True))

    def transform_chain(self, mesh: str) -> tuple[ModelTransformState, ...]:
        cmds = self.cmds
        transform = (cmds.listRelatives(mesh, parent=True, fullPath=True) or [None])[0]
        chain = []
        while transform:
            def value(attribute):
                return tuple(float(v) for v in cmds.getAttr(
                    transform + "." + attribute)[0])

            chain.append(ModelTransformState(transform, value("translate"),
                value("rotate"), value("scale"), value("rotatePivot"),
                value("scalePivot")))
            transform = (cmds.listRelatives(transform, parent=True,
                                            fullPath=True) or [None])[0]
        return tuple(reversed(chain))

    def history(self, mesh: str) -> tuple[ModelHistoryNode, ...]:
        cmds = self.cmds
        nodes = cmds.listHistory(mesh, pruneDagObjects=True,
                                 interestLevel=2) or []
        return tuple(ModelHistoryNode(node, cmds.nodeType(node)) for node in nodes
                     if node != mesh and cmds.nodeType(node) != "mesh")

    def symmetry_samples(self, mesh: str, tolerance: float) -> tuple[
        tuple[tuple[float, float, float], ...], tuple[int, ...]]:
        cmds, om = self.cmds, self.om
        dag = om.MSelectionList().add(mesh).getDagPath(0)
        positions = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
        points = tuple((float(p.x), float(p.y), float(p.z)) for p in positions)
        nearest = list(range(len(points)))
        if not any(point[0] <= tolerance for point in points):
            return points, tuple(nearest)
        was_modified = cmds.file(query=True, modified=True)
        undo_enabled = cmds.undoInfo(query=True, state=True)
        node = None
        try:
            cmds.undoInfo(stateWithoutFlush=False)
            node = cmds.createNode("closestPointOnMesh", name="advPyModelCheck#")
            cmds.connectAttr(mesh + ".outMesh", node + ".inMesh",
                             force=True)
            world_to_object = dag.inclusiveMatrixInverse()
            for index, (x, y, z) in enumerate(points):
                if x <= tolerance:
                    local = om.MPoint(-x, y, z) * world_to_object
                    cmds.setAttr(node + ".inPosition", local.x, local.y,
                                 local.z, type="double3")
                    nearest[index] = int(cmds.getAttr(node + ".closestVertexIndex"))
        finally:
            try:
                if node and cmds.objExists(node):
                    cmds.delete(node)
            finally:
                try:
                    cmds.file(modified=was_modified)
                finally:
                    cmds.undoInfo(stateWithoutFlush=undo_enabled)
        return points, tuple(nearest)

    def select_asymmetric_vertices(
        self, mesh: str, issues: tuple[ModelSymmetryIssue, ...]
    ) -> None:
        cmds = self.cmds
        vertices = sorted({index for issue in issues
                           for index in (issue.vertex, issue.closest_vertex)})
        cmds.select([f"{mesh}.vtx[{index}]" for index in vertices], replace=True)

    def confirm_model_check_gate(self, gate: ModelCheckGate) -> bool:
        if gate.category == "transform":
            title = "模型检查 · 变换"
            details = [
                f"{issue.attribute}: {issue.value:g}（默认 {issue.expected:g}）"
                for issue in gate.issues
                if isinstance(issue, ModelTransformIssue)
            ]
        elif gate.category == "history":
            title = "模型检查 · 构建历史"
            details = [
                f"{issue.name} [{issue.node_type}]"
                for issue in gate.issues
                if isinstance(issue, ModelHistoryNode)
            ]
        elif gate.category == "symmetry":
            title = "模型检查 · 左右对称"
            details = [
                f"顶点 {issue.vertex} → {issue.closest_vertex}: "
                f"偏差 {issue.distance:.6g} cm"
                for issue in gate.issues
                if isinstance(issue, ModelSymmetryIssue)
            ]
        else:
            raise ValueError("未知模型检查阶段：" + gate.category)
        summary = "\n".join(details[:12])
        if len(details) > 12:
            summary += f"\n另有 {len(details) - 12} 项"
        choice = self.cmds.confirmDialog(
            title=title,
            message=f"{gate.subject}\n\n{summary}\n\n继续检查？",
            button=["继续", "取消"],
            defaultButton="取消",
            cancelButton="取消",
            dismissString="取消",
        )
        return choice == "继续"
