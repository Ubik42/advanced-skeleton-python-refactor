# 全身控制与显式蒙皮示例

`maya_complete_character.py` 的 `build_character(with_hand=True)` 从空场景生成 Fit、Body、完整角色控制与代理网格，并写入每个顶点的显式权重。`with_hand=False` 使用 30 关节身体，默认使用 70 关节五指身体。返回值包含 `host`、`container`、`rig`、`mesh`、`skin` 和 `weights`。

环境要求：Maya 2024、Z Up、degree 角度单位、Undo 开启。场景不得已有 joint、mesh、FitSkeleton 或 AdvPy 命名对象；不清空已有场景。普通标记对象和选择会保留。

在仓库目录运行的 mayapy 脚本中：

```python
import sys
from pathlib import Path
import maya.standalone

root = Path.cwd()
sys.path[:0] = [str(root / "src"), str(root / "examples")]
maya.standalone.initialize(name="python")
try:
    from maya import cmds
    from maya_complete_character import build_character
    from adv_py.application import SwitchBodyControlSpace

    cmds.upAxis(axis="z", rotateView=False)
    cmds.undoInfo(state=True)
    character = build_character(with_hand=True)
    spine = character.rig.plan.torso.torso.spine
    cmds.setAttr(spine.fk_controls[1] + ".rotateZ", -20)
    SwitchBodyControlSpace(character.host).execute(
        character.rig.plan.control_spaces, "head", "global",
    )
finally:
    maya.standalone.uninitialize()
```

代理网格由每条非零身体骨段的低分段圆柱合并而成：30 关节对应 348 顶点，70 关节对应 828 顶点。每个顶点分配相邻两关节的正权重，总和为 1。权重由示例骨段几何确定，然后交给 `BindSkin` 与 `EditSkinWeights` 的既有校验及读回接口。代理包含分离的表面，目的是复现控制到线性蒙皮的完整链路，不代表生产网格拓扑或自动高质量权重。

示例宿主把内部用例加入同一外层事务，任何异常向外传播并整体回滚；标准宿主仍拒绝嵌套事务。一次 Undo 移除本次 Fit、Body、控制、网格与 skinCluster，Redo 恢复相同位置。适配器以 UUID 区分本次新建对象，在事务结束记录其无输入局部变换，避免重做世界空间构建命令时依赖部分恢复的父级。

综合后台验收入口为 `validation/maya_complete_character_smoke.py`。它核对显式权重、全身代表动作、脊柱双向匹配、全部空间切换、Global 移动 / 旋转 / 1.5 倍缩放、整个流程 Undo / Redo，以及蒙皮写入阶段注入失败后的整体回滚。具体命令见 [后台验证](../validation/README.md)。
