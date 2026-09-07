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

## 当前首版合同

`RigPlan` 只表达节点、父子关系和基础约束。`BuildRig` 在修改前统一校验，由 `RigHost` 负责事务、创建和复检。`InMemoryRigHost` 已经能够执行该合同；Maya 与 Blender 当前只有明确的适配器入口和能力说明，尚未声称完成真实宿主实现。

## 推荐开发顺序

1. 用公开或自生成的两节骨架，完成 Maya 与 Blender 的同一 RigPlan 构建。
2. 定义统一矩阵和坐标系转换，明确 Maya jointOrient 与 Blender bone roll 的差异。
3. 加入控制器形状、基础 parent/orient/point 约束和可重复构建。
4. 加入 IK/FK limb，分别做姿态与动画验收。
5. 迁移蒙皮数据模型和导出，而后再进入高级身体模块。
6. Face 保持独立子系统，等身体核心稳定后再设计 Blender shape key/driver 映射。

AdvancedSkeleton 只作为本机授权环境中的行为参考。若未来发布公开项目，公开核心应使用独立命名、公开/自生成测试资产和清洁实现记录，不能提交 ADV 源码或逐行派生代码。

