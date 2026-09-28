"""Maya host for Model Cleaner / Create geo."""
from __future__ import annotations

from adv_py.core.model_geo_group import (
    ModelAssembly, ModelGeoGroupPlan, plan_model_geo_group,
)


class MayaModelGeoGroupHost:
    def __init__(self) -> None:
        from maya import cmds
        self.cmds = cmds

    def capture_model_assemblies(self) -> tuple[ModelAssembly, ...]:
        c = self.cmds
        rows = []
        for path in c.ls(assemblies=True, long=True) or []:
            shapes = c.listRelatives(path, shapes=True,
                                     fullPath=True) or []
            rows.append(ModelAssembly(
                path, c.nodeType(path),
                tuple(c.nodeType(shape) for shape in shapes),
                bool((c.lockNode(path, query=True,
                                 lock=True) or [False])[0])))
        return tuple(rows)

    def apply_model_geo_group(
        self, plan: ModelGeoGroupPlan,
    ) -> tuple[str, ...]:
        c = self.cmds
        if plan_model_geo_group(self.capture_model_assemblies()) != plan:
            raise RuntimeError("Create geo 执行前场景顶层模型已变化")
        if not c.undoInfo(query=True, state=True):
            raise ValueError("Create geo 需要开启 Maya Undo")
        before = tuple((path, c.ls(path, uuid=True)[0],
                        tuple(c.xform(path, query=True,
                                      worldSpace=True, matrix=True)))
                       for path in plan.move_paths)
        c.undoInfo(openChunk=True, chunkName="Model Cleaner Create geo")
        changed = False
        try:
            if plan.create_geo:
                changed = True
                created = c.createNode("transform", name="geo",
                                       skipSelect=True)
                if (c.ls(created, long=True) or []) != ["|geo"]:
                    raise RuntimeError("Create geo 顶层路径漂移")
            for path, _, _ in before:
                changed = True
                c.parent(path, "|geo", absolute=True)
            result = []
            for _, uuid, matrix in before:
                matches = c.ls(uuid, long=True) or []
                if len(matches) != 1 or (
                    c.listRelatives(matches[0], parent=True,
                                    fullPath=True) or []) != ["|geo"]:
                    raise RuntimeError("Create geo 模型父级回读失败")
                current = c.xform(matches[0], query=True,
                                  worldSpace=True, matrix=True)
                if (len(matrix) != 16 or len(current) != 16 or
                    max(abs(float(a) - float(b))
                        for a, b in zip(matrix, current)) > 1e-5):
                    raise RuntimeError("Create geo 改变了模型世界矩阵")
                result.append(matches[0])
            if (c.ls("|geo", long=True,
                     type="transform") or []) != ["|geo"]:
                raise RuntimeError("Create geo 结果组缺失")
            changed = True
            c.select("|geo", replace=True)
        except Exception:
            c.undoInfo(closeChunk=True)
            if changed:
                c.undo()
            raise
        c.undoInfo(closeChunk=True)
        return tuple(result)
