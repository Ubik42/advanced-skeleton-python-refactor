# AutoPlace 源码阶段整理、脚部取样与 Fit 定位对照

2026-10-02 UTC。继续 ADV 6.925 MEL 的 Python 复刻。本批没有推送 GitHub，整个复刻未完成，Goal 保持活跃。

## 本批代码

肩肘扫描整理为原版依次执行的身体／头部分离、手臂取样、肩部 Skin 拉直、左右网格切分和肘部拉直阶段。四指扫描整理为截面检查、指甲壳处理、指尖取样、指根生长与曲线保存阶段。保留原版循环次数、阈值、蒙皮参数、跨阶段平均直径与失败状态，不通过重置失败标记来强行识别手指。

脚部六个临时坐标点改读原版明确使用的 `AnkleRotSamplerShape.boundingBoxMin/Max`。此前读取外层 transform，空子对象影响了包围盒，造成 Toes 偏移差异约 0.0242248；修正后实际 Maya 界面对照该偏移矩阵差异为 0。

展指、拇指、Loft、枢轴定位与 fat 写入明确加入现有整段事务，使直接调用这些阶段时的异常也进入撤销回滚。

## 更正上一批肩部判断

上一批“原版选择 9 个顶点、Python 选择 230 个顶点”来自图形 Maya 与 standalone 不同的选择状态，不能作为源码算法差异。实际图形 Maya 的相同输入对照中，最近顶点同为 12764，肩部选择同为 9 个顶点，两个 influence 的权重完全一致（9／15695），Skin 参数与 influence 顺序一致。没有为这一环境差异改动原版肩部算法。

`validation/results/fit-auto-place-gui-selection/shoulder-comparison.json`：CombinedSkin 与 Lower_M 顶点／面数相同、位置差异为 0；Upper_M、Upper_R 拓扑相同，最大顶点差异 9.5367431640625e-7；肩部权重差异为 0；脚趾偏移差异为 0。该报告是肩部检查点对照，不是整个 AutoPlace 成功报告。

## 集中 Maya 2024 验证

- `validation/results/fit-auto-place-positions-rollback-final/positions.json`：实际 43 关节 Fit 场景上，原版未经修改的 FromScanCurves／SetFat 与 Python 对照，无手指及有五指枢轴两类均通过。最大关节矩阵差异分别为 0、2.220446049250313e-16，fat 差异均为 0，生成约束分别为 15、21 个，撤销重做通过。
- 同报告的主动中断用例在 Root 与手指约束已写入后抛出异常，关节、中心锁、约束及节点 UUID 集合恢复，新增／丢失节点均为 0。取基线前先计算输入场景已有的投影历史，避免把 Maya 延迟生成的曲线输出误记为本次新增节点。
- `validation/results/fit-auto-place-phases-transactions/phases.json`：展指、zLoft、yLoft、拇指、外部求解器保留和独立命名空间展指，共 6／6 通过。四项几何／矩阵来源对照差异均为 0。
- 原版只读 MEL SHA256 仍为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

## 当前剩余工作

Sam 的 Python 整体自动识别仍返回 `not_detected`；原版同输入仍因重复 FingerCurveIndex 报错。它不能提供完整成功路径的原版对照。下一批继续从原版四指扫描逻辑与适用输入推进四指识别 → 展指 → 再扫描 → Loft → Fit 定位的完整成功路径；保留本批已证实的肩部、脚部和定位结果，避免重复误调选择阈值。完整 AutoPlace 命名空间流程仍未验收。

主体 Body／Part 沿用前批 70／71，左臂 IK 严格 1e-4 阈值下约 0.00014226 的差异仍在，本批未重跑主体对照。以上阶段通过不代表全部 ADV 完成。
