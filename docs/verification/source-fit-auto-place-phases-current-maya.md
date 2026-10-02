# AutoPlace 扫描状态、展指、拇指与 Loft 的本批记录

后续更正：本记录末尾 9／230 的选择差来自图形 Maya 与 standalone 环境，实际图形 Maya 同输入两边均为 9，权重完全一致。脚趾包围盒来源、Fit 定位／fat 和异常回滚也已完成后续对照，详见[最新记录](source-fit-auto-place-placement-current-maya.md)。下面保留当批记录，不再把该肩部环境差异列为算法缺口。

2026-10-02 UTC。本批继续 ADV 6.925 的 Python 复刻，没有推送 GitHub。整个复刻尚未完成，Goal 保持活跃。

## 实际代码改动

- 将单个 MEL 过程的扫描变量集中到 `FitAutoPlaceScanState`。四指生长失败、平均直径、上一圈包围盒等变量跨扫描轴和重试保留；没有修改原版四指判定阈值，也没有清除原版持久失败标记来制造成功。
- 主扫描按原版顺序先刷新 Maya，再读取投影子对象与命中数。四指自动重投影不再覆盖原版没有重新赋值的命中数和投影数组。
- 胯部的 Root／Hip 偏移重新读取选中的中心曲线宽度。前面的重叠曲线合并宽度继续用于身体／腋下扫描，不混用这两个来源值。
- 面转换补回 Maya 原生命令的来源组件类型、选择掩码和选择替换顺序；无转换结果时保留原选择。跨网格壳生长保持原版 Wrap 参数、距离增减和选择处理。
- 展指的 stock nCloth 使用当前操作单独创建的临时 Nucleus，恢复原来的活动求解器，避免原版单角色的全场景重命名／删除影响其他角色。只有 stock 过程尚未加载时才 source 它，避免重新初始化 Maya 的活动求解器全局变量。
- 拇指最终局部 X 搜索保留原版 `posB` 的分支包围盒取样作为未找到正 X 顶点时的值。
- 已有 AutoPlacing 时，“自动放置”和“缩放”直接走原版退出引导流程，不读取失效眼球字段，也不调用模型检查。已经删除的可选 All 模型只跳过可见性恢复；开始新操作时准备记录仍严格校验。

## 集中 Maya 验收

`validation/maya_fit_auto_place_phases.py` 在 Maya 2024 中使用相同的受控输入场景。Loft 调用未经修改的原版 helper；nCloth 和拇指是从只读原版提取未改写的 inline 块，仅在验证程序中声明其过程局部变量。它们是阶段对照，不能称作 Sam 完整 AutoPlace 对照。

最终报告：`validation/results/fit-auto-place-phases-final/phases.json`，6／6 passed。

| 阶段／行为 | 结果 |
| --- | --- |
| 四指 nCloth 展指、Wrap、复制权重、straightenBS、临时节点清理 | 网格顶点最大差异 0 |
| 躯干 zLoft | 左右网格、枢轴矩阵、编辑偏移差异均为 0 |
| 手臂 yLoft | 左右网格、枢轴矩阵、编辑偏移差异均为 0 |
| 拇指反向扫描、枢轴定位及扫描位置恢复 | 最大矩阵差异 0 |
| 已有用户 Nucleus | UUID、参数、活动求解器保留，没有挂入本次 nCloth |
| 独立 AutoPlaceRig 命名空间展指 | 实际 Maya 运算通过；生成的 BlendShape 属于当前角色；临时 Cloth／Nucleus 清除；外部求解器保留 |

面板两个公开按钮的退出路径也经过实际 Maya 验证：删除可选眼球和 All 模型后仍能结束引导，恢复 Skin／Root 可见性，撤销重做通过。报告为 `validation/results/fit-auto-place-panel-finish/panel.json`，2／2 passed。

## Sam 整体流程仍有缺口

最终受控跟踪 `validation/results/fit-auto-place-diagnostic-final/diagnostic.json` 仍为 `not_detected`。完成 z、x、yArmStraight、yElbowStraight、y 五段后，四指生长失败，按原版条件结束引导；没有把这一返回误报成自动放置成功。

同一个 Sam 实际网格、原版 biped Fit 输入，未经修改的原版仍因 `FingerCurveIndex` 重名在 52699 行中断。其完整对照报告 `validation/results/fit-auto-place-sam-source/parity.json` 为 failed。错误中间状态与 Python 清理后的矩阵差异不能作为完整算法对照的有效误差。

另外保存了肩部拉直前后的几何检查点，将差异缩到上游选择／Skin 写入：

- 原始 CombinedSkin 和切出的 Lower_M 顶点、面数及位置一致。
- Upper_M 和 Upper_R 的顶点／面数一致，但变形后位置不同。
- 肩部关节矩阵接近一致；首次 Skin 写入后原版 Shoulder 权重为 1 的顶点数是 9，Python 为 230。
- 在同一个恢复到静止状态的网格、同一个起始选择上，原版 `asPolyGrowPastShell` 与 Python helper 的结果选择一致（230 → 231）。所以不能把整个上游差异简单归因于 helper 公式或随意更改它的阈值。

后续实际界面对照已排除上述肩部算法差异，继续连通真实角色四指识别 → 展指 → 二次识别 → Loft → Fit 定位。当前已验收的单独阶段不能扩大成完整主链成功；完整 AutoPlace 命名空间链、复杂角色输入仍未验收。

主体 Body／Part 对照沿用前批 70／71。左臂 IK 的严格误差缺口没有在本批重新微调；没有将其报为通过。
