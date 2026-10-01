# 原版 Partial Joints 主体接入（2026-10-01）

本批以 ADV 6.925 `asCreatePartialJoints`、`asCreateMultiPartialJoints`、`asDeletePartialJoints` 为依据，修正当前 Python Body 的公开入口和图。未修改参考 MEL，不推送 GitHub。

## 普通模式已通过

从原版 biped Fit 通过公开 Body Build 新建当前主体，再经公开 Partial 入口验证：内部 FK 选择仅处理对应 Elbow；单段带控制器／左侧不带控制器；follow 0／5／10；控制器局部位移；六段 Spline 链加入原有 Skin；总控缩放；单次撤销重做；原生保存重开；选定删除和全部清理。创建 Partial 后，主体登记仍识别原来的主体拓扑。单段控制器删除后，其 buildPose 附加命令也移除；附加构建姿态恢复验证 tx 归零及 follow 回到 5。来源主体传入高度后，标准 biped 的 72 Body／18 Part／1582 通道新建、姿态与动画文件、FBX、原位重建、Skin 与原生曲线身份保留、撤销重做和重开也再次通过。

在 Maya 图形程序中加载未修改的完整原版 MEL 和原版 UI，对同一个 Python Body 分别运行原版和 Python Partial：右侧无控制器、左右带控制器、左右六段链，共 66 个旋转／follow／缩放组合，所有关节世界矩阵的最大差为 **1.5543122344752192e-15**。报告为 `validation/results/partial-joints-source-parity/partial-parity.json`，状态 `passed_source_parity`。该比较证明这五组 Partial 行为，未比较整套原版 Body 构建图或真实模型外观。

## 具体修正

- 使用角色登记把内部主 FK 名称对应到原版 Body 关节，避免未识别选择退回全部关节。
- 原版偏移量读取 Main.height；来源 Body 总控补传已有 Fit height，避免遗漏高度属性。
- 旋转顺序必须在写入世界矩阵前设置；原零框架的设置顺序会改变中性姿态。
- 多段采用原版临时兄弟关节、复制和绝对重新挂父级，保留 Maya 自动调整的 jointOrient。
- 带控制器的单段复用原版 parent-constraint 复刻器；OPM 的关节 MM 与控制层 MM2 分别规划和清理。Extra 的缩放和可见性按原版锁定。
- 修复写 buildPose 时属性变量被中性通道循环覆盖；Partial 加入现有辅助影响关节身份体系。
- 多段与已有单段遵循原版创建入口的先行跳过规则。

## OPM 尚未通过

真实 OPM Body 新建未完成，不能报告 Partial 的 OPM 已验收。集中运行已发现并修正父矩阵读回把短 DAG 名称误判为接线变化的问题；补入按绑定世界矩阵与实际父驱动反算 FK 缩放补偿偏移，以及祖先先于后代的创建顺序。这些 OPM 改动处于代码接入，尚未通过完整主体验收。

原始 biped OPM 继续卡在 Neck Inbetween 改接 Head FK Offset 的绑定姿态变化；关闭 Fit 的 inbetweenJoints 后，卡在 Cup_L → PinkyFinger1_L 的缩放补偿绑定姿态。没有删除检查或放宽容差。失败报告保存在 `validation/results/partial-joints-opm/partial-joints.json`；下一主项是按原版完成这两个主体接线，随后重跑完整 OPM Body 与 Partial 对照。

Partial 的完整 Body 重建保留、带已有权重的所有删除组合、全部角色侧别和独立角色命名空间仍未在本批验证。代码存在和本批通过范围都不能代表全量 ADV 完成。

## 复现入口

`validation/maya_partial_joints_lifecycle_smoke.py`：Maya standalone 的公开生命周期；`--opm` 必须从原版 Fit 新建 OPM 主体，不能仅修改已经构建的普通 Body 开关。`--no-parts` 明确关闭 Fit 的分段参数，仅用于定位主体阻断。

`validation/maya_partial_joints_source_parity.py`：Maya GUI 延迟入口，加载真实原版 UI；只翻译输入夹具的 Main／FK 名称。以相同主体分别测量原版和 Python 输出。
