# 来源 Body OPM 本批运行记录（2026-10-01）

依据 ADV 6.925 原版 asParentConstraint 的实际父 worldInverseMatrix 接线，本批修正接收节点 parentInverseMatrix → 自身 OPM 的反馈。未修改只读原版 MEL，未推送 GitHub。

## 本轮原版整图对照与修正（2026-10-02 UTC）

原版完整 GUI 构建已取得，之前 Spine 缺失 scaleConstraint 的失败是参考夹具仅改 UI、未执行其 onchange 写入 FitSkeleton.useOffsetParentMatrix，导致构建与辅助过程使用不同 OPM 值。夹具现同步原版 Fit 属性并断言 asGetOpm；只读 MEL 未修改，SHA256 仍为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。完整参考含 90 个 Body／Part 关节及右肘三个 FK 姿态，保存于 `validation/results/original-bendy-reference/`。

本轮按源码补回以下主体行为：

- Bendy 控制器、简单代理与末端代理先设置 rotateOrder，再对齐绑定矩阵，避免默认姿态出现接近 180° 的伪 Twist。
- 读取并保留旧 `worldOrient`，让新 `worldOrientUp` 优先覆盖；编辑沿用原有属性名，删除时清除两种属性，防止旧值重新生效。原始 biped 的 Ankle.worldOrient=3 按原版 xDown 定向。
- Fit 朝向跳过条件改为轴分量精度比较，避免旧点积条件把 Wrist 约 0.24° 的必要调整跳过。
- 按原版 asRlaChild 的顺序和中心 Spine 优先规则选取 Root 首子节点；该子节点的 Twist 参考直接使用 FKOffset，继承原版避免 legLock 影响的分支。
- OPM Bendy 的影响范围取重排前的完整绑定跨度，传统构建保留原版局部子段长度；multiplyDivide 权重检查按 Maya float32 存储值核验，不放宽姿态对照阈值。
- OPM FK 补齐父级空间内的第二个 pickMatrix，保留 Main 的整体比例；Main 缩放进入 FKSystem，覆盖同级 Inbetween 控制层，避免只缩放普通 FK 控制器组。保存与重建图记录同步使用这一接线。

### 已取得的实际证据

- 完整参考修正后，Python 90 个同名 Body／Part 默认姿态最大世界矩阵差 `9.2802157607e-5`；右肘 Z=0／30／-45 三姿态最大差分别约 `1.24e-7`、`1.05e-7`、`9.78e-8`，均通过 `1e-4` 阈值。报告 `validation/results/original-body-native-fit-fixed-compare.json`。
- 旧 worldOrient 的读、编辑、新字段优先、删除、撤销重做和保存重开通过。报告 `validation/results/legacy-world-orient-current/legacy-world-orient.json`。
- OPM Bendy=1 和传统 Bendy=3 均通过新建、Skin、姿态／动画往返、FBX、保存重开、保留 Skin／曲线 UUID 的重建与撤销重做。这两项在本轮后续整体缩放修正前取得，不能当作最新全分支验收。报告分别位于 `biped-opm-simple/`、`biped-traditional-bendy/`。
- Spine1 从原版 Inbetween 夹具改为 Twist=2／Bendy=3，验证 Root 首子参考路径；72 Body／18 Part／1696 通道，FBX 902912 字节，完整生命周期通过。报告 `validation/results/biped-spine-bendy-current/original-biped-current.json`。这是指定夹具分支，非原始 biped 的默认 Spine 设置。

### 最终集中运行结果

最新主体 `validation/results/biped-native-opm-span-fixed/original-biped-current.json`：72 Body／18 Part／2204 通道，FBX 902928 字节。公开新建、Skin、姿态与动画文件往返、真实 Main 动画形变、登记保存重开、FBX 导出、原位重建、Skin／动画曲线 UUID 保留、单次撤销重做及重建后重开全部通过。

未修改原版保存场景与最新 Python 主体的 90 个同名关节按七组实际控制编辑对照，全部通过 `1e-4` 阈值，没有删掉失败姿态或调整阈值。报告 `validation/results/original-body-pose-opm-span-fixed.json`，实际进程退出码 0。

| 场景 | 最大世界矩阵分量差 |
| --- | ---: |
| 默认姿态 | 9.2802157606e-5 |
| 右肩 FK Z=30 | 9.2802157606e-5 |
| 右手腕 FK X=25 | 9.2802157606e-5 |
| 右肩 Bendy 主控 X=30 | 9.2802157606e-5 |
| 右肘 Bendy Y 平移=0.3 | 9.2802157606e-5 |
| Main 全局比例=1.25 | 6.1414447075e-5 |
| Root legLock=0、RootX Y=30 | 7.7935650866e-5 |

全局缩放的中间误差从约 1.6356，经遗漏的第二次矩阵筛选修正后降至 0.3552，再补齐使用非 FKX 来源的 Spline Base 分支后降至 6.14e-5；中间失败报告保留，没有宣称其通过。Maya 的 multiplyDivide 缩放权重是 float32，检查改为对照实际存储精度，姿态矩阵阈值保持不变。

1053 个源码／验证 Python 文件 AST 检查及差异空白检查通过；本轮未运行全量旧单元测试，旧夹具失败不能算作已修复。

### 下一核心批次

继续完整 IK 切换、控制器跟随、非均匀缩放与更多组合姿态的原版整图对照；补齐覆盖矩阵中的未完成源码分支。最新全局缩放图尚未集中重跑传统 Bendy=3、OPM Bendy=1 和 Spine 特殊夹具，旧场景图向新图的兼容性也未在本批证明。真实默认角色的外观与全部可选参数尚待验收。上述七组通过仅限所列 90 个关节和输入，不代表全量 ADV 完成。


## 历史第二批结果（下方失败已由本轮取得完整参考）

下文 Bendy 导出／重建失败为上一批历史结果；本批已修复对应阻断，但不代表整套 ADV 完成。

原版 MEL 80109–80151 只在明确的 Fit childOfPart 或 firstAfterIK 情况下跟随 Body。旧 Python 将生成的 Twist Part 层级也算作 childOfPart，使普通 Elbow／Wrist FK 回读 Bendy 的受驱动 Body。来源构建现关闭该推断，保留 Fit 原始标记。另按 MEL 83313–83348 建立由独立 FK／父 FKIK blend 驱动的绑定姿态参考，避免父参考再读取受驱动 Body。Root 首子节点等全部特殊分支尚未逐项原版对照。

实际 Body 使用的归属标记与机制关节不同，原 FK／RP OPM 转换误检查机制标记而跳过 Body；现使用已有的 Body／机制归属判断。补齐原生下划线属性的图记录解析；Maya 最终单位转换命名同时改写四类闭合图记录，恢复原锁定状态；连接时不再改名先前已被其他图使用的共享转换节点。

- 普通 OPM：72 Body、18 Part、1582 通道，FBX 902896 字节。完整新建、Skin、姿态／动画往返、保存重开、导出、原位重建、Skin／动画曲线 UUID 保留、撤销重做及重建后重开通过。报告 `validation/results/biped-opm-body-records/original-biped-current.json`。
- 肩／肘左右各 3 Bendy 控件＋OPM：72 Body、18 Part、2204 通道，FBX 903712 字节。相同完整流程通过。报告 `validation/results/biped-opm-bendy-body-records/original-biped-current.json`。
- 修正后重建 Bendy：7 个指定关键节点，DG off／serial／parallel，帧 1／3／5／1，每帧重复求值 4 次，同姿态矩阵最大差 0，严格阈值 1e-5。仅证明所列节点的重复求值稳定性，不代表所有动画与所有 Bendy 数量。报告 `validation/results/bendy-evaluation-body-records/bendy-evaluation-summary.json`。
- 重开后的 10 个独立 Twist 父参考均通过闭合图审计；它们属于 TwistSystem 内部节点，登记检查现明确遍历该归属层级。人为断开一条参考输出后，读取角色登记拒绝该场景，撤销后恢复完整登记。报告 `validation/results/source-twist-reference-reopened.json`。
- 未修改原版完整 GUI 对照尝试：只读 MEL 与参考字节一致，SHA256 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。OPM biped＋Bendy 3 在原版第 81488 行缺失 `IKOffsetConstrainedSpine1_M_scaleConstraint1` 时终止，未取得完整原版参考数据，不能宣称整图等价。该历史报告路径现由成功参考覆盖；失败日志保留于原批记录，没有修改原版脚本掩盖失败。

下一主项：取得原版完整 Body／Bendy 对照并核对姿态图，补齐可选数量、命名空间、特殊父参考分支和真实默认角色外观，继续覆盖矩阵缺口。

## 前一批已通过真实 Maya

- 原版默认 biped Fit：72 Body、18 Part、1582 通道；公开新建、Skin、原生总控动画、姿态和动画文件、保存重开、FBX（906032 字节）、原位重建、Skin／动画 UUID 保留、单次撤销重做和重开。报告 `validation/results/biped-opm-parent-fixed/original-biped-current.json`。
- OPM Partial：完整公开生命周期；真实原版 GUI／未修改 MEL 5 组 66 姿态对照，最大世界矩阵差 4.6629367034256575e-15。详见 Partial 记录。
- 历史自反馈修复：在真实有动画和 Skin 的 Cup FK 跟随图中故意注入旧错误，定点修复后世界矩阵和模型顶点最大差 2.220446049250313e-16，曲线身份、撤销重做、保存重开通过。正确图修复为空操作。报告 `validation/results/opm-parent-repair/opm-parent-repair.json`。
- Spline：OPM 主体控制数量 2→4→2、同布局再次重建；Skin UUID、权重、成员集合、动画曲线身份、撤销重做和重开通过。报告 `validation/results/spline-opm-parent-fixed/spline-count-rebuild.json`。
- Root Motion：原有 OPM 动画主体公开创建／删除，精确恢复登记、Skin 顶点、单次撤销重做和重开通过。另修复保存后的 multi 成员元素锁定、不要把用户动画输入写为固定登记、保留既有成员顺序。报告 `validation/results/opm-root-motion-current/opm-root-motion.json`。

## Bendy 本批接入

实际父逆矩阵贯通主／次曲线影响关节、末端、Micro 和主控制跟随；角度接线用 Maya 原生 logical connection 回读，允许自动 unitConversion，仍保留节点类型、参数和完整接线检查。曲线 Skin 产生 Orig 形状，审计只读取非中间形状；API 2.0 MMatrix 按平铺数据读取；先设置 rotateOrder 再写绑定矩阵。第二曲线完成后审计最终矩阵跟随，Body 与机制关节采用已有明确归属规则。

左右 Shoulder／Elbow 各 3 Bendy 控件：72 Body、18 Part、2204 通道，新建、Skin、原生动画、姿态／动画文件、保存重开通过。Bendy FBX 尚失败，具体在 Elbow Part 及其后代导出骨架世界姿态。未放宽容差；不将该组合算作发布通过。

Bendy 原位重建发现 Skin 驱动曲线通过 create 接收求值几何，旧保留检查仅识别 controlPoints 驱动。本批补识别 create 驱动，保留完整拓扑及连接审计，不把求值 CV 当用户编辑。该曲线形状检查已继续通过，但重接后的主体／控制空间／Skin 一致性仍失败（最大差约 10.1056）；事务回滚，未将该重建算为成功。报告日志 `validation/results/biped-opm-bendy-retained.log`。

## 检查范围

1040 个源码／验证 Python 文件语法检查通过；历史父矩阵的 4 项定点单元测试通过。旧 Hand 模拟测试 20 项仍有 2 失败、10 错误；用 HEAD 原 core 模块重跑得到相同数量，旧夹具还未更新，不报告全部单元测试通过。

这些证据不证明整个 ADV 原版图、全部角色和真实默认模型外观完成。后续主项为 Bendy 重建与导出组合、整图对照及覆盖矩阵的未完成分支。
