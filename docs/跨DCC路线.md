# 跨 DCC 路线

2026-10-02 用户已明确授权完整 Blender 绑定框架迁移。当前按三个阶段顺序推进：完成并确认 Maya Python 原版复刻 → 保持具体绑定业务行为不变的性能／架构优化 → Blender 原生迁移。Blender 尚未进入当前产品包，不能把历史实验计入当前功能完成度。

## 优化阶段约束

Maya 复刻达到完整验收门槛后，冻结输入、输出和绑定行为，再记录整链构建／重建、控制求解、权重处理与保存重开的时间和内存基线。优化只处理重复计算、查询与写入成本、模块依赖、资源寿命和宿主边界；保留原版参数、识别判定、权重、控制关系与动画语义。每批改动用相同输入比较最终骨骼矩阵、顶点变形、层级、权重、动画和持久化结果，并实测性能收益；没有等价结果或没有实测收益的优化不算完成。Maya 当前尚有未通过项目，不能提前开始这一阶段。

## 可以迁移的部分

可跨 Maya 与 Blender 复用的是绑定意图和数据，而不是具体命令：骨骼层级、控制器语义、IK/FK 关系、命名规则、构建阶段、驱动关系、校验规则与导出契约都应进入纯 Python 核心。

Maya 第一阶段已经产出两类可迁移合同。FitSkeleton schema v1 用 Up Axis、轴配置、安全设置、短名拓扑、局部位置、行为世界轴、标签与元数据表达可编辑源骨架，不包含 Maya DAG 路径、场景对象列表或 ReBuild 脚本文本；当前 Maya 支持向调用方明确给出的空容器完整导入，也支持在轴配置、设置和共享关节语义一致时只新增缺失分支。Blender 第二阶段可以复用文档、校验与增量联合计划，但必须另行实现 EditBone 层级、矩阵和 roll 的适配。面向完整角色动画的 Hand Pose schema v1 则以左右侧、手指、节段和数值表达 14 个聚合属性与 30 个 FK 旋转，同样不包含 Maya DAG 路径。Maya namespace 只存在于应用层的显式角色根解析和 adapter 完整路径中，不进入文档摘要。核心已经区分只读、静态写入和当前帧写键三种访问意图，并用语义文档合并表达双手、显式单侧及左右镜像目标；镜像聚合值保持同号，行为坐标系中的 FK 旋转使用 `(-X, -Y, Z)`。命名预设库同样位于 DCC 无关的应用/文件边界：`.handpose.json`、安全中文名称、原子保存、完整清单校验与按名解析都不依赖 Maya，未来 Blender 可直接复用。当前仍只有 Maya adapter 负责两类文档的场景解析、可写性预检、事务和 Undo，并把预设应用与写键落实为原生 animCurve。第二阶段进入 Blender 时，应保持 schema、预设目录合同、访问、目标侧与镜像结果语义不变，只新增 Armature/EditBone/PoseBone/ID Property、FCurve 的显式目标解析与写入，不反向改变已验证的 Maya 行为。

FitSkeleton 的增量联合也已进入纯 Python 核心：共享关节必须保持父级、位置、行为轴、标签和元数据一致，宿主只能物化缺失分支。该规则未来可由 Blender EditBone adapter 复用，但第一阶段不据此扩展 Blender；Maya 中尚未验证的冲突覆盖、重父级或删除式同步不会提前成为跨 DCC 合同。

空场景新建导入进一步明确了宿主边界：文件解析、完整设置合成、名称预检和关节物化顺序位于应用层，Maya 圆环容器、通道属性与 Undo Chunk 位于 adapter。未来 Blender 可以把同一计划落到 Armature/EditBone，但不能照搬 Maya 容器形状或属性实现；当前仍不新增 Blender 代码。

非默认 Primary/Secondary/World Match 也遵循这一边界。核心文档保存六方向语义，Maya adapter 用 enum/bool 属性表达；未来 Blender 必须将同一语义转换为 EditBone 矩阵与 roll 规则，不能复制 Maya 的属性布局。第一阶段仍只验证 Maya 写入与读取闭环。

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

因此 Blender 不是替换 import 就能运行。未来的宿主适配器需将 Maya 主线稳定后的语义合同转成 Blender 原生结构，并分别验证最终矩阵、层级、权重和动画行为。

## 早期可行性验证

2026-09-07 曾使用独立的 `RigPlan`/`BuildRig` 样板验证 Maya 与 Blender 的最小骨架和 IK/FK 链。该样板不参与 ADV 的 Fit → Body → Rig 主流程，已从当前产品包和验证入口移除。以下结果仅记录当时的技术实验，不能代表当前 Blender 功能覆盖。

2026-09-07 的本机后台验证结果：

| 宿主 | 版本 | 创建 | 约束 | 重复构建预检 | 回滚清理 |
| --- | --- | ---: | ---: | --- | --- |
| Maya standalone | 2024 | 4 个逻辑节点 | parent + orient | 通过 | 无残留 |
| Blender background | 5.2.0 LTS | 4 个逻辑节点 | Copy Transforms + Copy Rotation | 通过 | 无残留 |

同日完成的 IK/FK limb 验证使用 15 个逻辑节点。Maya 通过 RP IK Handle、Pole Vector、反向权重节点和 Bind 双源 orientConstraint 落地；Blender 使用 IK、Copy Transforms 和属性驱动。Maya 的三关节链表示两个被求解骨段，Blender 因骨骼本身代表骨段，将 IK 放在第二根机制骨并以 `chain_count=2` 求解。

当时的 Blender 实验把 Bind 骨链放入独立 Armature，FK/IK 机制骨链保留在主 Armature，并在完整约束图建立后统一注册驱动，以避免 Bind 混合约束形成依赖环。

实验的矩阵合同使用“行主序存储、列向量计算”。Maya 端在 `xform` 边界转置，Blender 端直接构造 `mathutils.Matrix`。当时实测矩阵同时包含平移、绕 Z 的骨骼 aim 和绕本地 Y 的 roll。

两边不比较底层 Euler 数值，而比较最终静态世界矩阵：Maya 将旋转冻结进 `jointOrient` 并保持 `rotate` 为零；子关节因父空间分解，其 `jointOrient` 数值不需要等于世界矩阵输入角。Blender 将相同静态方向写入 EditBone matrix，实测 roll 为 `20°` 与 `-10°`。两边构建后复检均通过。

## 阶段顺序

1. 历史可行性验证：同一份自生成 RigPlan 在 Maya 与 Blender 建立两节骨架，并确认坐标与静态朝向边界；实验代码已移出当前产品包。
2. 历史可行性验证：同一份最小 LimbSpec 在两边建立三关节 IK/FK limb 并通过姿态验收；实验代码已移出当前产品包。
3. 当前第一阶段：依原版只读 MEL 完成 Maya Python 复刻，清除来源清单缺口并确认完整绑定工作流。历史 `迁移架构.md` 的早期切片和 Legacy Bridge 不再作为当前要求。
4. 第二阶段：在冻结绑定业务行为的前提下完成有实测收益的性能和架构优化；不擅改原版识别、权重与控制规则。
5. 第三阶段：迁移同一绑定框架至 Blender，连续完成 Fit、Body／Part、FK／IK、Spline、Twist、Bendy／Inbetween、控制器、蒙皮、重建、动画与导出，再贯通 Face 及其他已复刻绑定模块。Face 按原版行为映射到 Blender shape keys、约束与驱动，不另改业务方向。每项必须落实创建、修改、保存重开、保留动画重建和多角色隔离，不能只交付适配器样板。

AdvancedSkeleton 只作为本机授权环境中的行为参考。若未来发布公开项目，公开核心应使用独立命名、公开/自生成测试资产和清洁实现记录，不能提交 ADV 源码或逐行派生代码。
