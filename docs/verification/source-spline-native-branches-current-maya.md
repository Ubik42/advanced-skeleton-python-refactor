# 来源 Spline 原生伸展、扭转与 Root 参考：Maya 当前记录

2026-10-02 UTC，Maya 2024。继续以未经修改的 AdvancedSkeleton 6.925 MEL 为依据；本批补现有主体图，不改原版资产、不推送 GitHub。

本批已接入以下原版逻辑：

- MEL 80747–80810：Spline 求解末端使用独立 IKfake1；有子关节时放在末端下，无子关节时放在前一关节下，实际 solver jointList 按这个父链登记和审计。
- MEL 81331–81348：逐骨骼用 multiplyDivide＋blendTwoAttr 混合原始长度与伸展长度，IKSpEnd 保持原始长度，辅助末端也纳入相应的长度计算。
- MEL 81400–81415：中间扭转使用曲线切线 LocalOrient0，单独保存绑定逆矩阵；缩放和 solver up 使用另一套 LocalOrient2，不能复用两者。
- MEL 81660–81695：非伸展末端位置取 IKSp，旋转取末端 LocalOrient2，并清除旧的旋转补偿。
- MEL 83313–83348、84453–84466：Root 下的 Twist 参考读取 Root FK／IK 混合输出，前置 Inbetween 旋转逆矩阵。关闭 firstJointFixed 时仍继承原版的参考关系。
- 没有 Spline Part 的来源链也接入完整 native 描述与辅助末端；旧场景没有这些字段时继续按旧图解码。
- 无 Root Inbetween 的 HipSwing 新图使用实际 FKX 父级的 worldInverseMatrix，避免自身 parentInverseMatrix／OPM 回路及新旧重建边界不一致。

严格矩阵阈值仍为 `1e-4`。原有 37 组用例全部保留，增加十组 Spline 分支：原生链中性、弯曲、扭转，曲线链扭转，半伸展、非伸展、半 FK／IK，关闭首关节固定，末端旋转，原生链＋Main 非均匀缩放。

| 输入布局 | 关节范围 | 结果 | 唯一失败 |
| --- | --- | --- | --- |
| 原版 biped＋Shoulder／Elbow Bendy | 72 Body＋18 Part | 46／47 | left_arm_ik，0.00014226262986186122 |
| Root＝1、Spine1＝3、Neck＝1 | 72 Body＋17 Part | 46／47 | left_arm_ik，0.00014226262983799143 |

新增十组在两种布局中全部通过。标准布局 九个单位缩放分支的最大矩阵差异为约 0.00000305；Main 非均匀缩放组合约 0.00004903。汇总仍为 **failed**，不能把 46／47 写成全 ADV 完成比例。

两种布局均通过实际构建、Skin 变形、姿态／动画文件往返、保存重开、FBX、保留 Skin／原生动画曲线 UUID 的重建、撤销重做和重建场景重开。标准 2271 通道，不均匀布局 2253 通道。

另外，Root／Spine1 的 Inbetween 数量设为 0 的副本已通过同一套实际构建、文件往返、FBX、保存重开、保留 Skin／曲线 UUID 重建与撤销重做。范围为 72 Body＋14 Part、2157 通道；该布局仅证明生命周期接通，未与对应原版场景做严格矩阵等价对照。默认 Fit 文件未改。

本地产物在忽略的验证目录：

- `validation/results/biped-source-spline-branches/`：标准构建和重建场景、JSON、FBX。
- `validation/results/biped-source-spline-branches-uneven/`：不均匀布局的同类产物。
- `validation/results/original-source-spline-branches-pose.json` 与 `original-source-spline-branches-uneven-pose.json`：全部 47 组矩阵与逐关节误差。
- `validation/results/biped-source-spline-no-parts-final/`：无 Spline Part 布局的构建、重建场景和实际运行报告。

整体复刻仍未完成。左臂近伸直原生 RP 数值差异、多系统／多侧／数量变更的完整组合，以及覆盖矩阵中的其余原版分支继续保留在开发计划中；本批结果限定上述实际运行范围。
