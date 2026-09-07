# 跨 DCC 路线

## 可以迁移的部分

可跨 Maya 与 Blender 复用的是绑定意图和数据，而不是具体命令：骨骼层级、控制器语义、IK/FK 关系、命名规则、构建阶段、驱动关系、校验规则与导出契约都应进入纯 Python 核心。

## 必须分别实现的部分

| 语义 | Maya | Blender |
| --- | --- | --- |
| 骨骼对象 | DAG joint | Armature 的 EditBone / PoseBone |
| 变换 | transform + jointOrient / OPM | bone matrix、roll、pose matrix |
| 约束 | constraint nodes | PoseBone constraints |
| 自定义属性 | addAttr / setAttr | ID Properties / RNA |
| 形变 | skinCluster、blendShape | Armature modifier、vertex groups、shape keys |
| 撤销 | undo chunk | operator/undo stack，部分数据 API 需显式回滚 |
| UI | PySide / Maya workspaceControl | Blender Panel / Operator / PropertyGroup |

因此 Blender 不是替换 import 就能运行。宿主适配器要把同一条 RigPlan 翻译成各自原生结构，并分别验证最终矩阵、层级、权重和动画行为。

## 当前首版合同与验证

`RigPlan` 现在表达节点、世界矩阵、骨骼 extent、父子关系和基础约束。`BuildRig` 在修改前统一校验，由 `RigHost` 负责事务、创建、复检与显式回滚。内存、Maya 与 Blender 三个适配器已经执行同一份 `two_joint_plan()`。

2026-09-07 的本机后台验证结果：

| 宿主 | 版本 | 创建 | 约束 | 重复构建预检 | 回滚清理 |
| --- | --- | ---: | ---: | --- | --- |
| Maya standalone | 2024 | 4 个逻辑节点 | parent + orient | 通过 | 无残留 |
| Blender background | 5.2.0 LTS | 4 个逻辑节点 | Copy Transforms + Copy Rotation | 通过 | 无残留 |

矩阵合同使用“行主序存储、列向量计算”。Maya 适配器在 `xform` 边界转置，Blender 适配器直接构造 `mathutils.Matrix`。当前实测姿态是平移矩阵；旋转矩阵、Maya jointOrient 和 Blender bone roll 的等价性仍是下一阶段内容。

## 推荐开发顺序

1. 已完成：用自生成的两节骨架，在 Maya 与 Blender 构建同一 RigPlan。
2. 当前：验证旋转矩阵和坐标系转换，明确 Maya jointOrient 与 Blender bone roll 的差异。
3. 随后：加入控制器形状、point 约束和可重复更新。
4. 加入 IK/FK limb，分别做姿态与动画验收。
5. 迁移蒙皮数据模型和导出，而后再进入高级身体模块。
6. Face 保持独立子系统，等身体核心稳定后再设计 Blender shape key/driver 映射。

AdvancedSkeleton 只作为本机授权环境中的行为参考。若未来发布公开项目，公开核心应使用独立命名、公开/自生成测试资产和清洁实现记录，不能提交 ADV 源码或逐行派生代码。
