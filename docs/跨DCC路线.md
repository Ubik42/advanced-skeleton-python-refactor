# 跨 DCC 路线

本文描述第二阶段的迁移目标，不是当前并行开发计划。当前主线是先完成 Maya Python 重构；Blender 仅保留最小可行性适配器，等 Maya 侧语义稳定后再逐项迁移。

## 可以迁移的部分

可跨 Maya 与 Blender 复用的是绑定意图和数据，而不是具体命令：骨骼层级、控制器语义、IK/FK 关系、命名规则、构建阶段、驱动关系、校验规则与导出契约都应进入纯 Python 核心。

Maya 第一阶段已经产出首个面向完整角色动画的可迁移合同：Hand Pose schema v1 以左右侧、手指、节段和数值表达 14 个聚合属性与 30 个 FK 旋转，不包含 Maya DAG 路径。Maya namespace 也只存在于应用层的显式角色根解析和 adapter 完整路径中，不进入文档摘要。核心已经区分只读、静态写入和当前帧写键三种访问意图；当前仍只有 Maya adapter 把写键落实为原生 animCurve，并负责场景解析、可写性预检、事务和 Undo。第二阶段进入 Blender 时，应保持 schema 与访问语义不变，只新增 Armature/PoseBone/ID Property、FCurve 的显式目标解析与写入，不反向改变已验证的 Maya 行为。

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

`RigPlan` 现在表达节点、世界矩阵、骨骼 extent、父子关系、基础约束与 `LimbSpec`。`LimbSpec` 只描述 Bind/FK/IK 三链、FK 控制、IK 目标、Pole Vector、设置节点和 blend 属性，不包含任何 Maya 或 Blender 类型。`BuildRig` 在修改前统一校验，由 `RigHost` 负责事务、创建、复检与显式回滚。

2026-09-07 的本机后台验证结果：

| 宿主 | 版本 | 创建 | 约束 | 重复构建预检 | 回滚清理 |
| --- | --- | ---: | ---: | --- | --- |
| Maya standalone | 2024 | 4 个逻辑节点 | parent + orient | 通过 | 无残留 |
| Blender background | 5.2.0 LTS | 4 个逻辑节点 | Copy Transforms + Copy Rotation | 通过 | 无残留 |

同日完成的 IK/FK limb 验证使用 15 个逻辑节点。Maya 通过 RP IK Handle、Pole Vector、反向权重节点和 Bind 双源 orientConstraint 落地；Blender 使用 IK、Copy Transforms 和属性驱动。Maya 的三关节链表示两个被求解骨段，Blender 因骨骼本身代表骨段，将 IK 放在第二根机制骨并以 `chain_count=2` 求解。

Blender 适配器把 Bind 骨链放入独立 Armature，FK/IK 机制骨链保留在主 Armature，并在完整约束图建立后统一注册驱动。这既避免 Bind 混合约束形成依赖环，也避免驱动在半构建图上首次求值后永久失效。该宿主差异没有泄漏进核心模型。

矩阵合同使用“行主序存储、列向量计算”。Maya 适配器在 `xform` 边界转置，Blender 适配器直接构造 `mathutils.Matrix`。当前实测矩阵同时包含平移、绕 Z 的骨骼 aim 和绕本地 Y 的 roll。

两边不比较底层 Euler 数值，而比较最终静态世界矩阵：Maya 将旋转冻结进 `jointOrient` 并保持 `rotate` 为零；子关节因父空间分解，其 `jointOrient` 数值不需要等于世界矩阵输入角。Blender 将相同静态方向写入 EditBone matrix，实测 roll 为 `20°` 与 `-10°`。两边构建后复检均通过。

## 阶段顺序

1. 已完成可行性验证：同一份自生成 RigPlan 在 Maya 与 Blender 建立两节骨架，并确认坐标与静态朝向边界。
2. 已完成可行性验证：同一份最小 LimbSpec 在两边建立三关节 IK/FK limb 并通过姿态验收。
3. 当前回到第一阶段主线：按 `迁移架构.md` 在 Maya 内逐模块重构 ADV 行为；Blender 功能冻结。
4. Maya 身体核心达到阶段门槛后，第二阶段再迁移控制器、可重复更新、蒙皮、导出和高级身体模块。
5. Face 保持独立子系统，等 Maya 身体核心稳定后再决定其 Blender shape key/driver 映射。

AdvancedSkeleton 只作为本机授权环境中的行为参考。若未来发布公开项目，公开核心应使用独立命名、公开/自生成测试资产和清洁实现记录，不能提交 ADV 源码或逐行派生代码。
