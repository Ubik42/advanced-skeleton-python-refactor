# Game Engine、Face 输入与 Spline：源码接入范围

## 本批代码范围

- Game Root Motion 恢复原版现代／旧图、Main.height、MM／导出父级，登记路径按原节点身份更新。Game Scaling 恢复三个缩放处理阶段、UUID／直接祖先、PartScale1 和 IK 场景接线，保留原版断开后存在的 MPD 与缓存输入。
- Unreal Joints／Twist／Rename／Mannequin 恢复来源关节处理、CustomOrient、SDK、名称映射、原版资产及姿态分支；Root Motion 与 Scaling 的重建交接加入当前主流程。未以未运行的代码宣称这些全生命周期通过。
- Body Rig／Face Rig 数据、FBX preset／导出、Roblox 动态头、Export Preparation、Optimize／Publish、OPM 分解和原版模型修复均加入 Python 原版入口。Publish 的原生导出及撤销语义仍需要集中运行。
- Face Mask 保留原版单位／构建姿态确认、模型检查及四个 Shape 引导；读写原版 Mask 属性，兼容旧补充 JSON。原版场景不再被额外的 Python Mask JSON 前置要求拒绝。
- Face／All Head／Eye／Teeth／Tongue 选择恢复来源保留名、唯一名、Transform 子对象、Mesh／NURBS、组件分支和最后一个 Skin 历史选择。新 Skin 先确认、自动 Head 位置为引导高度三分之一、mi=1／dr=4／rui=false；取消时不继续录入。
- Head Joint 选择恢复首个选中关节规则；建立锁定 FaceGroup／FaceFitSkeleton，持久记录 HeadJoint。面板在打开和操作后读回 Mask、Face、All Head、HeadJoint 和 SkinCluster，避免默认 Head 覆盖原记录。All Head 可以先于 Face；已有 Face 时检查最初选择，而非展开后的子对象。
- Eye 的非球形 Lattice 按原版跨网格保留最后 FFD，逐件弹出原版 Yes／No 对话框、清理旧侧标签、重排 Skin 历史和 outsideLattice。没有把原版重复询问改为新的缓存策略。
- 完成绑定后记录 Extras 会立即执行原版新增影响、closestPoint／closestJoint 权重转移及移除未使用影响；复用 Finish 中同一实现，并把新模块节点记入 Face 选择集。
- EyeLid／Lip／Pupil／Iris／ForeHead 的管状预览统一使用来源 circle／extrude 参数、Shape 名、反向判定和材质分配，删除重复且参数不同的实现。Pupil／Iris 保留源码极值、选择覆盖判定及遍历上限。ForeHead 手动顺序使用选中 CV 和 pickWalk；Jaw 曲线端点恢复源码 CV[99]。
- Source Spline 新建场景创建持久 AlignIKTo：世界旋转保持零，仅平移到 Body；普通端点挂自身 FKX，Fit 末端挂父 Fit 对应 FKX。场景记录包含两个端点，锁定 Body UUID 证明共享节点归属；多个系统共用端点不重建已有参考，也不接管无归属的同名节点。
- 对齐恢复 MEL 的真实执行顺序：IK→FK 依据 ControlSet、逐个读取 IKX、连续写两次；FK→IK 每个 Hybrid 重新查询当前 Deform、随后才读取 AlignIKTo 朝向。距离使用三位小数、至少五位整数补零及带命名空间名称的文本排序。恢复 FK2IKCurve／tempPointOnCurveInfo 的原版临时节点名称及保留规则。
- 原版 detached NonSym 直接子关节的 previousParent 只对当前 Fit 身份生效；Spline AlignIKTo 和 IKfake1 共同使用来源末端判定，不把这种 Fit 叶子当作普通末端。
- 新 Spline 标志进入保存解码、源图路径变更、生成属性清单、场景成员登记和审计。同布局重建保留旧标志，明确的数量重建采用新图；不把旧保存图悄悄换成另一种布局。

## 当前证据

此文件只记录该批源码接入范围，当前事实以 [工程状态](../工程状态.md) 为准。旧的 649 检查无新增失败摘要已删除；[实际离线 JSON](offline-source-game-engine-2026-10-02.json)记录的是 2026-10-03 UTC 的 1137 文件、989 检查、13 失败、126 错误，不能报全绿。其后修改尚未生成新汇总。

退役 Body 登记和 Spline 显式 AlignIKTo 迁移后续已接入代码，不再列作未开发；包括这些修改在内的新 Game/SDK/Face/Custom/Squash 批次尚无完整 Maya 验收。本文件不能证明源码全部覆盖或运行结果等价。
