# Face 可选驱动、瞳孔虹膜与转换来源对照

2026-10-11，继续 Maya 原版复刻阶段。未修改 ADV 6.925 MEL，SHA256 为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。来源过程直接在图形 Maya 2024 中运行，Python 从同一输入场景开始，对照门槛保持 `1e-4`。本批没有优化业务算法，没有开始 Blender，也没有推送 GitHub。

## 已确认范围

- Pupil/Iris：普通蒙皮的相邻环、分离环，以及多层蒙皮的分离环，三类输入各 17 组姿态。四个控制曲线、关节矩阵、全部眼球权重与眼球顶点均与原版一致，最大差异 0。真正撤销构建、重做、保存重开均通过。独立 `FaceActor` 角色在 `OtherEditor` 活动空间下也通过原版数值对照、撤销重做、保存重开、外部对象身份与编辑空间保持。
- ARKit 创建、SnapChat、外部 ARKit 连接和 Roblox：分别 156、147、156、150 组通道姿态，共 609 组。对照 FaceControlSet/SDK 数值和六个生产网格顶点，最大差异 0；四条链的构建节点撤销、重做数值、保存重开均通过。外部 ARKit 使用 `_R/_L` 别名。保留 SnapChat 原版不连接部分及 Roblox 重复 EyeClosed 调用。
- 独立角色：ARKit 创建、外部连接、Roblox 的撤销重做、保存重开、外部来源和其他角色 UUID、活动编辑空间保持通过。
- 纯 BlendShape 和保留目标的纯 BlendShape：97 个目标、8 个 BlendShape 节点、10 个模型、11 组姿态；全部目标点差、组件表和实际变形与原版一致，差异 0。实际撤销转换、重做和保存重开均通过。
- 完整 Face 回归：使用公开入口默认 Cage/Jaw 平滑次数，普通及多层蒙皮两类、OPM、Complete、眉毛睫毛附件，30 阶段完整构建、动作、真实撤销重做和保存重开通过。这是运行回归，不能代替所有 Face 阶段与原版的严格权重对照。

## 本批恢复的源码行为

Pupil/Iris Fit 曲线恢复与 Transform 匹配的 Shape 名称，避免 Prep 复制后匿名 Shape 歧义。Skin Smooth 初始化 Maya 原生绘制工具、影响列表回调和 Flood；此前直接创建 context 不等同于原版工具初始化，`whichTool="skin"` 在 Maya 2024 中无效。按原版仅在第二影响非空时锁定其余影响，Cage 保留刷新顺序，独立角色忽略命名空间后判断 EyeBrow 排除规则。

BlendShape 目标保留 Maya 已正确创建的别名，避免重复 aliasAttr 报错；Mixed 临时逆矩阵读取恢复 16 项扁平数据。ctrlBox2 投射矩阵按原版下划线分词恢复 `EyeBrowRegionMM_RTGXform` 等名称，保留现有矩阵接线。Skin Layer 复制后按完整 DAG 路径重命名，原版同样明确限定到复制组内，避免重命名原有 TemplateLayer 子模型。

## 当前补齐与范围限制

ARKit Quick 已修复 Maya 2024 多驱动 setDrivenKeyframe 隐式节点的撤销缺陷。保留来源的曲线类型、键值、线性切线、BlendWeighted 插入与 infinity 设置，显式登记同样的节点和接线。Transform 来源的 156 组及真实 BlendShape 别名来源的 260 组姿态，初次、重做、保存重开差异均 0；撤销无新建曲线或混合节点残留。真实 BlendShape 额外覆盖 0、0.5、1、2、-1，避免仅对照正常范围。

ARKit Disconnect 已修复删除曲线重做后 Maya 保留旧缓存的问题：仅对本次删图变成可写的数值通道，登记来源恢复姿态后已经算出的相同值，不新增默认值或改变未记录通道。连接及 Quick 两类，各 156 组初次、重做、保存重开对照均 0。

独立 FaceActor 的 Quick 已通过；五类可选链均保留其他对象身份和活动空间，Quick 外部驱动连接只读来源、写入本角色创建的曲线。

Face Mixed 已完成当前输入的来源与完整生命周期对照：97 个目标、10 个 BlendShape 节点、14 个姿态、53 个蒙皮对象及 324394 项权重，与原版差异均为 0（PID 43572，复用原版 PID 24464 的保存场景）。检查覆盖网格、曲线与曲面的实际蒙皮成员及绑定前矩阵。整次撤销恢复原节点身份、名称和父级；撤销、重做、保存重开的权重与姿态差异均为 0。控制器集合成员及通道锁定、显示状态匹配原版，生命周期恢复也通过。代码保留原版复合 TRS 连接和绘制结果，分别补齐锁定状态及权重的撤销记录。见 [Mixed 摘要](source-face-mixed-current.json)。

普通及多层蒙皮的完整 Face 构建均通过当前 Maya 检查（PID 19348）：公开入口默认平滑次数、OPM Complete、眉毛睫毛附件、全部 30 个阶段。两类输入分别有 33 和 53 个 Skin；整次撤销与重做的节点身份恢复通过，全部权重及绑定矩阵恢复差异为 0，重做与保存重开的姿态差异为 0。普通 SDK 改用已有显式曲线插入路径，消除了完整撤销留下的 428 条隐式曲线。asDsSdk 的 24 组原版对照、528 个姿态和曲线定义差异均为 0（PID 46412）。完整构建运行检查仍不能代替全部原版 Face 构建阶段的严格权重对照。见 [完整 Face 摘要](source-face-full-build-current.json) 和 [SDK 摘要](source-face-sdk-current.json)。

非 OPM 原版 ctrlBox2 的无条件重连错误继续作为来源输入限制。项目插件加载仅允许核对完整路径后的 native_node_cast.py 与 skin_bulk.py 本次加载；测试不修改持久安全设置。

普通/多层瞳孔结果不覆盖 Cyclops、面组件、多眼球子模型及所有非对称组合。程序化 Face 网格用于绑定逻辑对照，不能代表默认 ADV 模型外观或全界面布局一致。

普通 OPM Complete 完整重建已按原版全部 30 阶段核对：33 个 Skin 的 311408 项权重及绑定前矩阵差异约 6.74e-8，14 个 Face 姿态与 8 个 Head 旋转/缩放组合差异约 2.38e-7。共用 PP 的绝对挂接与缩放/镜像补偿、旧版朝向开关以及 Ribbon Shape 命名已恢复。普通完整生命周期通过。多层生命周期通过，但两处手改层权重保留及 blink 姿态仍失败；原版 Maya 2024 多层重建在 Prep 中止。当前证据见 [重建摘要](source-face-rebuild-current.json) 与 [PP 摘要](source-face-pp-current.json)。

## 可复现入口和下一工作

`validation/maya_face_pupil_parity.py`、`maya_face_channel_parity.py`、`maya_face_conversion_parity.py`、`maya_face_optional_namespace.py`、`maya_face_optional_full_build.py`、`maya_face_channel_disconnect_parity.py` 配套图形 Maya 启动文件。结果在本机忽略目录 `validation/results/face-*`；`face-conversion-parity/bs-modes-report.json` 保存两类纯 BS 的通过记录，Mixed 的独立重跑使用 `report.json`。

开发继续完整 Face 构建阶段的原版权重对照、保留数据重建与身体连接，随后处理 Body 70/71 及其余覆盖缺口。整体 Maya 复刻仍未完成；当前任务优先完成 Maya；独立性能优化与 Blender 迁移等待用户安排。Goal 保持活跃。
