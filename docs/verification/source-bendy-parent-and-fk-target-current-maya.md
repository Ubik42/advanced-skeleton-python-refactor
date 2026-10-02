# Bendy 父帧、末端跟随与传统 FK 来源：当前 Maya 记录

2026-10-02 UTC。本批以 ADV 6.925 原版 MEL 为只读依据，使用本地 Maya 2024；没有推送 GitHub。

本批补齐原版核心场景图，而非增加新产品行为：

- MEL 83641：编号 Bend Offset 实际挂在去扭转父帧下，保留完整缩放／shear；起点不再用额外 parentConstraint 代替真实父子关系。起点静态绑定矩阵有锁定记录，控制器地址及所有权登记随新层级更新。
- MEL 83670：子链起点影响先乘实际父逆矩阵，再用 pickMatrix 去掉局部旋转／shear。此前先过滤世界矩阵的顺序不等价。OPM 直接接矩阵；传统模式分解完整局部 TRS／shear。
- MEL 83952–83962：Bendy 最后一段 Micro Aim 指向下游 Bendy 的真实 BendMPX 起点；无下游 Bendy 才用末端代理。
- MEL 83762／83936：Micro Offset 跟随及 Body／Part 变形 parentConstraint 按原版不保持偏移。此前自动保留的约 9e-5 绑定偏移在非均匀缩放下放大。
- MEL 80413：来源 IKX 的每个关节继承 Fit 的旋转顺序，包括中间关节；新增声明、创建和登记检查。
- MEL 80313：传统模式中继承缩放的独立 FK 跟随分支也关闭上游 FKX 的 segmentScaleCompensate。
- MEL 80519：传统 Body FK／IK 混合直接读取真实 FKX；保留额外 FK 机制身份供现有动画及登记使用，但不让该机制链替代原版约束输入。
- 原版 joint 创建保留父 scale → inverseScale，即使 segmentScaleCompensate 为 false。Python 之前只在补偿开启时接线，漏掉了 orientConstraint 仍读取的逆缩放输入。本批补回继承缩放的 FK Body 接线并登记检查。

所有新增布局均有生成属性及重建策略。旧角色缺省保留旧布局；新增属性不会作为用户属性重复恢复。机制关节登记的 rotation_order 字段允许旧记录缺省为 None，其他未知／缺失字段仍严格拒绝，新记录保留实际旋转顺序。

严格对照使用原版生成的四组 Spline 参考场景，检查 108 个 Body／Part 关节的世界矩阵；本批从 48 组扩大到 71 组，新增 RP IK、局部缩放等分支。阈值保持 1e-4。

OPM v4：70／71，唯一未通过为 left_arm_ik，最大差异 0.0001422626298。此前四组 Main 非均匀缩放及其 Bendy Part 已通过。

传统 v7：70／71，唯一未通过为 left_arm_ik，最大差异 0.0001422600031。nonuniform_shoulder／nonuniform_wrist 最大差异分别从约 0.02072776／0.20754820 降至约 2.61e-6，均通过；其他已通过用例的最大差异为 global_scale 的 0.0000561557。此前四组 Main 非均匀缩放也全部通过。

OPM v4、传统 v7 的完整创建、Skin、姿态／动画往返、保存重开、FBX、保留原生 Skin／动画对象的同布局重建与撤销重做均通过。传统 v7 使用本批最终新增接线；OPM 不走新增传统模式分支，其验证运行于 Bendy 和 IK 旋转顺序修复后。

旧传统角色及本批 v7 新布局的 SplineTail_L 控制数量 3→5→3 均通过：原生 Skin／曲线身份、权重与成员、其他系统数量、撤销重做、保存重开及同布局后续重建均保留。新旧图分别运行，v7 数量变更后继续保留本批 Bendy 父帧、直接 FKX 混合及 inverseScale 接线。

证据均保存在忽略目录 validation/results/：

- OPM：biped-source-bendy-parent-v4-opm.log、original-source-bendy-parent-v4-opm-pose.json。
- 传统：biped-source-bendy-parent-v7-nonopm.log、original-source-bendy-parent-v7-nonopm-pose.json。
- 旧图迁移：spline-legacy-bendy-parent-v4-count-SplineTail_L/spline-count-rebuild.json。
- 新图迁移：spline-source-bendy-parent-v7-count-SplineTail_L/spline-count-rebuild.json。
- 登记兼容检查：source-bendy-parent-registry-tests.log，9 项通过；包含旧字段缺省、新旋转顺序往返和非法／未知字段拒绝。

原版 MEL SHA256 保持 828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02。

整体 ADV 复刻仍未完成。下一优先项是左臂 RP IK 的严格数值差异，之后继续覆盖矩阵中明确未完成的核心分支；本批组合通过不等于全部 ADV 源码已复刻。Goal 保持进行中。
