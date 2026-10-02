# 来源 FK／Inbetween／Spline Part 矩阵补齐

2026-10-02 UTC，Maya 2024，原版 ADV 6.925 MEL 与原版 biped Fit。继续 Python 复刻，无 GitHub 推送。

本批将普通来源 FK Offset 改回原版独立世界矩阵接收：绑定旋转 → Main 缩放筛选 → NoShear，继承缩放使用原版 inheritScale 的反向输入。依据 MEL 80240–80387；不是另设计补偿算法。

Inbetween 的 Part FKPS 增加原版 NoShear 筛选，下游普通 FK 同样恢复绑定旋转、Main 和 NoShear 的顺序。绑定矩阵常量、节点、接线、输出和 inheritsTransform 进入锁定的闭合记录，角色登记和路径转换检查这些记录。

Spline Inbetween Part 的 Body 接收从朝向约束改为完整 FK／IK 矩阵混合与实际父逆矩阵；IKScaler 按扩展后的 Body＋Part 链索引计算原版平滑权重，保留局部体积因子和 Twist offset。相关图接入主构建、持久化读回和重建。

Bendy MicroOffset 按 MEL 83936 的 asParentConstraint 参数恢复矩阵连接：过滤 scale，保留 shear。旧 parentConstraint 无法传递该剪切，已替换；MicroOffset 的原版局部体积缩放仍保留，新闭合记录参与保存和重建检查。

## 本批实际运行结果

最终保留代码对应 `biped-inbetween-micro-current`：72 Body、18 Part、2233 通道，新建、Skin、姿态／动画文件往返、保存重开、FBX、保留 Skin／曲线 UUID 的原位重建和撤销重做通过。`biped-inbetween-fk-current` 与 `biped-inbetween-full-fixed` 是较早的本批成功生命周期结果。

最终严格对照 `original-inbetween-micro-pose.json` 为 90 Body／Part × 30 组，共 2700 次矩阵比较。阈值保持 1e-4，28 组通过，汇总仍 failed。Shoulder 非均匀缩放已通过；Main 非均匀缩放最大差约 0.06850146（上一批约 1.0155863），左臂 IK 位移最大差约 0.0001422626。

剩余 Main 差异集中于 Shoulder／Elbow 的 Bendy 链和 Neck Part；左臂 IK 的 rest frame／求解输入仍需逐项对齐原版。尝试新增 IK 根 Offset 的诊断版本影响原有 Follow 动作且未改善左臂误差，已撤回，不进入最终代码。不能将该诊断版本生命周期通过当作动作等价。

这只是上述标准 biped OPM／Bendy 样例的证据。传统非 OPM 的本批新增组合、非对称 Part 数量、历史场景升级、Spline 控制数量迁移、默认模型外观与其余 ADV 覆盖缺口仍需继续。较早生成的下游矩阵节点没有在本批自动删除，尚需按实际引用关系清理。Goal 保持活跃，不能宣布完整 ADV 完成。
