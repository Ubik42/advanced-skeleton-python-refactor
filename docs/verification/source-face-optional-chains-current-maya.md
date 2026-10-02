# Face 可选驱动、瞳孔虹膜与转换来源对照

2026-10-02，继续 Maya 原版复刻阶段。未修改 ADV 6.925 MEL，SHA256 为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。来源过程直接在图形 Maya 2024 中运行，Python 从同一输入场景开始，对照门槛保持 `1e-4`。本批没有优化业务算法，没有开始 Blender，也没有推送 GitHub。

## 已确认范围

- Pupil/Iris：普通蒙皮的相邻环、分离环，以及多层蒙皮的分离环，三类输入各 17 组姿态。四个控制曲线、关节矩阵、全部眼球权重与眼球顶点均与原版一致，最大差异 0。真正撤销构建、重做、保存重开均通过。独立 `FaceActor` 角色在 `OtherEditor` 活动空间下也通过原版数值对照、撤销重做、保存重开、外部对象身份与编辑空间保持。
- ARKit 创建、SnapChat、外部 ARKit 连接和 Roblox：分别 156、147、156、150 组通道姿态，共 609 组。对照 FaceControlSet/SDK 数值和六个生产网格顶点，最大差异 0；四条链的构建节点撤销、重做数值、保存重开均通过。外部 ARKit 使用 `_R/_L` 别名。保留 SnapChat 原版不连接部分及 Roblox 重复 EyeClosed 调用。
- 独立角色：ARKit 创建、外部连接、Roblox 的撤销重做、保存重开、外部来源和其他角色 UUID、活动编辑空间保持通过。
- 纯 BlendShape 和保留目标的纯 BlendShape：97 个目标、8 个 BlendShape 节点、10 个模型、11 组姿态；全部目标点差、组件表和实际变形与原版一致，差异 0。实际撤销转换、重做和保存重开均通过。
- 完整 Face 回归：使用公开入口默认 Cage/Jaw 平滑次数，普通及多层蒙皮两类、OPM、Complete、眉毛睫毛附件，30 阶段完整构建、动作、真实撤销重做和保存重开通过。这是运行回归，不能代替所有 Face 阶段与原版的严格权重对照。

## 本批恢复的源码行为

Pupil/Iris Fit 曲线恢复与 Transform 匹配的 Shape 名称，避免 Prep 复制后匿名 Shape 歧义。Skin Smooth 初始化 Maya 原生绘制工具、影响列表回调和 Flood；此前直接创建 context 不等同于原版工具初始化，`whichTool="skin"` 在 Maya 2024 中无效。按原版仅在第二影响非空时锁定其余影响，Cage 保留刷新顺序，独立角色忽略命名空间后判断 EyeBrow 排除规则。

BlendShape 目标保留 Maya 已正确创建的别名，避免重复 aliasAttr 报错；Mixed 临时逆矩阵读取恢复 16 项扁平数据。ctrlBox2 投射矩阵按原版下划线分词恢复 `EyeBrowRegionMM_RTGXform` 等名称，保留现有矩阵接线。Skin Layer 复制后按完整 DAG 路径重命名，原版同样明确限定到复制组内，避免重命名原有 TemplateLayer 子模型。

## 明确未通过

ARKit Quick 已修复 Maya 2024 多驱动 setDrivenKeyframe 隐式节点的撤销缺陷。保留来源的曲线类型、键值、线性切线、BlendWeighted 插入与 infinity 设置，显式登记同样的节点和接线。Transform 来源的 156 组及真实 BlendShape 别名来源的 260 组姿态，初次、重做、保存重开差异均 0；撤销无新建曲线或混合节点残留。真实 BlendShape 额外覆盖 0、0.5、1、2、-1，避免仅对照正常范围。

ARKit Disconnect 已修复删除曲线重做后 Maya 保留旧缓存的问题：仅对本次删图变成可写的数值通道，登记来源恢复姿态后已经算出的相同值，不新增默认值或改变未记录通道。连接及 Quick 两类，各 156 组初次、重做、保存重开对照均 0。

独立 FaceActor 的 Quick 已通过；五类可选链均保留其他对象身份和活动空间，Quick 外部驱动连接只读来源、写入本角色创建的曲线。

Mixed 现已修复 Skin 历史查询：严格采用 asGetSkinCluster 的 pruneDagObjects=True、interestLevel=2 并取最后一个 Skin，避免误取 BlendShape 目标层的蒙皮。97 个目标、10 个 BS 节点、11 组姿态来源差异均 0。完整撤销仍未验收：Maya 原生 nodeCast 会切断外层撤销记录，最小复现已确认；使用相同原生交换的显式撤销命令最小场景通过，完整转换仍在验证。非 OPM 的原版 ctrlBox2 无条件重连错误仍是来源限制。

普通/多层瞳孔结果不覆盖 Cyclops、面组件、多眼球子模型及所有非对称组合。程序化 Face 网格用于绑定逻辑对照，不能代表默认 ADV 模型外观或全界面布局一致。

## 可复现入口和下一工作

`validation/maya_face_pupil_parity.py`、`maya_face_channel_parity.py`、`maya_face_conversion_parity.py`、`maya_face_optional_namespace.py`、`maya_face_optional_full_build.py`、`maya_face_channel_disconnect_parity.py` 配套图形 Maya 启动文件。结果在本机忽略目录 `validation/results/face-*`；`face-conversion-parity/bs-modes-report.json` 保存两类纯 BS 的通过记录，Mixed 的独立重跑使用 `report.json`。

继续完成 Mixed 的完整撤销图，之后处理已有完整 AutoPlace、Body 70/71 及其余覆盖缺口。整体 Maya 复刻仍未完成；确认后才进入绑定结果不变的性能/架构优化，再迁移 Blender Body+Face。Goal 保持活跃。
