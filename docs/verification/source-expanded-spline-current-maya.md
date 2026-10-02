# 原版 Spline 扩展链与 Main 缩放：Maya 2024 当前记录

2026-10-02 UTC。只读依据为 AdvancedSkeleton 6.925 MEL；没有修改原版源码或默认 biped Fit。此次替换的是来源 Spline 的主体图，不是对验证结果做补偿。

## 已完成的核心改动

- 按 `asGetIKJoints` 将 Fit Inbetween Part 放入原生 `ikSplineSolver` 父链，先规划整链，再创建关节和求解器。基础 FK／Body 索引与完整 IK 索引分别保存，不用求解后的相邻输出插值替代真实 Part。
- Spline 曲线使用完整 Fit IK 链的点。标准 biped 从错误的三个 CV／一次曲线恢复为原版七个 CV／三次曲线；增加的四个 CV 操作层进入角色和动画登记。
- 每个新增 IK 骨段都有自己的绑定长度、伸展驱动、缩放权重和 stretchEven 输出。Part Body 接收同一套 IKScaler 结果，移除重复的局部缩放计算，并将原生求解关节恢复为不携带 Body 缩放的状态。
- 按 MEL 81525–81695 使用 AimMatrix 求 IKAc 朝向，分别建立 IKSp／IKAc FollowOffset 后再混合世界矩阵；在 Main 空间处理 IKAc 旋转和 Scale／Shear 筛选。
- 中间 IK 的 FollowEnd 参考层保留 Main 的缩放继承，末端的 LocalStartOrient 使用实际起点 Body 朝向。
- 按原版 Main 输入计算 IKScaler 相对矩阵和曲线世界长度归一化；不再把方向不同的 Root FK 接收器当成 Main。
- 保存记录包含完整 IK 链、基础索引、Part 父链与绑定矩阵；读取和场景审计检查实际求解器 jointList、关节父级及矩阵接线。旧记录缺少扩展字段时仍走旧图解码，不能用新图字段解释旧场景。

## 原版依据

| MEL 位置 | 本批继承的行为 |
| --- | --- |
| 7442：asGetIKJoints | Fit 的起点到末端包含临时 Inbetween 条目 |
| 80433–80499、80802 | 完整 IK 机制父链和原生求解器 |
| 80970–81135 | 按完整 IK 条目创建曲线 CV、CV 控制器和主控 |
| 81308–81352 | stretchEven 权重、曲线长度及 MainScale 的归一化 |
| 81525–81695 | IKAc 采样、AimMatrix、两链独立 FollowOffset 和矩阵混合 |
| 82728–82876 | Main 相对缩放、完整链索引的平滑权重 |

## 最终集中运行结果

严格矩阵精度维持 `1e-4`，37 个用例全部保留。

| 骨架 | 关节范围 | 严格对照 | 仍失败 |
| --- | --- | --- | --- |
| 未改的原版 biped，加 Shoulder／Elbow Bendy | 72 Body＋18 Part，90 个关节 | 36／37 | left_arm_ik：0.00014226262986186122 |
| Root＝1、Spine1＝3、Neck＝1 的分段布局 | 72 Body＋17 Part，89 个关节 | 36／37 | left_arm_ik：0.00014226262983799143 |

标准布局的三个 Spline IK 用例：

| 用例 | 上一批最大矩阵差异 | 本批最终最大差异 |
| --- | --- | --- |
| Main 非均匀缩放＋Spline IK | 0.5113238735256984 | 0.000049029043744930334 |
| 中间 IK 位移 | 0.21621772790364618 | 0.00000260792147466736 |
| 中间 IK 缩放 | 0.05747226287063256 | 0.00000260792147466736 |

不均匀分段的这三项分别为 0.000049029043744042156、0.0000026078732552354406、0.0000026078732552354406，均通过。原有 30 组仍为 29 组通过；新增七组现在全部通过。37 组汇总依然是 **failed**，不能把剩余的左臂误差忽略或放宽精度。

两种 OPM／Bendy 布局的构建、Skin 变形、姿态文件往返、动画文件往返、保存重开、FBX、保留 Skin／原生动画曲线 UUID 的同布局重建、单次撤销重做和重建场景重开均通过。标准通道 2271，不均匀布局 2253。标准 FBX 902928 字节，不均匀布局 893024 字节。通道增加来自完整曲线的 CV 层，不代表增加了无关产品功能。

最终本地产物（均在忽略的验证目录）：

- `validation/results/biped-expanded-spline-final/original-biped-current.mb`、`original-biped-rebuilt.mb`、`original-biped-current.json`
- `validation/results/biped-expanded-spline-final-uneven/` 的同名文件
- `validation/results/original-expanded-spline-final-pose.json`
- `validation/results/original-expanded-spline-final-uneven-pose.json`

## 当前限制和后续核心工作

本批完成上述两种原版来源布局的完整 Spline 接入，并不表示 ADV 全量复刻完成。左臂近乎伸直／目标超出长度时的原生 RP 数值差异仍需按源码处理。多系统／多侧、控制数量变更及其它附件组合未在本批重新集中验收；传统非 OPM 标准 biped 的构建、Skin、姿态／动画文件往返、保存重开、FBX 和保留 Skin／动画 UUID 的重建、撤销重做也通过；报告位于 `validation/results/biped-expanded-spline-final-nonopm/original-biped-current.json`。没有对它运行本批 37 组严格对照，不套用 OPM 的精度结论。其余 Corrective Shapes 等缺口继续按现有源码覆盖计划推进。Goal 保持活跃，不推送 GitHub。
