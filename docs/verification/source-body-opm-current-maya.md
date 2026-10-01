# 来源 Body OPM 本批运行记录（2026-10-01）

依据 ADV 6.925 原版 asParentConstraint 的实际父 worldInverseMatrix 接线，本批修正接收节点 parentInverseMatrix → 自身 OPM 的反馈。未修改只读原版 MEL，未推送 GitHub。

## 后续修正与当前结果（同日第二批）

下文 Bendy 导出／重建失败为上一批历史结果；本批已修复对应阻断，但不代表整套 ADV 完成。

原版 MEL 80109–80151 只在明确的 Fit childOfPart 或 firstAfterIK 情况下跟随 Body。旧 Python 将生成的 Twist Part 层级也算作 childOfPart，使普通 Elbow／Wrist FK 回读 Bendy 的受驱动 Body。来源构建现关闭该推断，保留 Fit 原始标记。另按 MEL 83313–83348 建立由独立 FK／父 FKIK blend 驱动的绑定姿态参考，避免父参考再读取受驱动 Body。Root 首子节点等全部特殊分支尚未逐项原版对照。

实际 Body 使用的归属标记与机制关节不同，原 FK／RP OPM 转换误检查机制标记而跳过 Body；现使用已有的 Body／机制归属判断。补齐原生下划线属性的图记录解析；Maya 最终单位转换命名同时改写四类闭合图记录，恢复原锁定状态；连接时不再改名先前已被其他图使用的共享转换节点。

- 普通 OPM：72 Body、18 Part、1582 通道，FBX 902896 字节。完整新建、Skin、姿态／动画往返、保存重开、导出、原位重建、Skin／动画曲线 UUID 保留、撤销重做及重建后重开通过。报告 `validation/results/biped-opm-body-records/original-biped-current.json`。
- 肩／肘左右各 3 Bendy 控件＋OPM：72 Body、18 Part、2204 通道，FBX 903712 字节。相同完整流程通过。报告 `validation/results/biped-opm-bendy-body-records/original-biped-current.json`。
- 修正后重建 Bendy：7 个指定关键节点，DG off／serial／parallel，帧 1／3／5／1，每帧重复求值 4 次，同姿态矩阵最大差 0，严格阈值 1e-5。仅证明所列节点的重复求值稳定性，不代表所有动画与所有 Bendy 数量。报告 `validation/results/bendy-evaluation-body-records/bendy-evaluation-summary.json`。
- 重开后的 10 个独立 Twist 父参考均通过闭合图审计；它们属于 TwistSystem 内部节点，登记检查现明确遍历该归属层级。人为断开一条参考输出后，读取角色登记拒绝该场景，撤销后恢复完整登记。报告 `validation/results/source-twist-reference-reopened.json`。
- 未修改原版完整 GUI 对照尝试：只读 MEL 与参考字节一致，SHA256 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。OPM biped＋Bendy 3 在原版第 81488 行缺失 `IKOffsetConstrainedSpine1_M_scaleConstraint1` 时终止，未取得完整原版参考数据，不能宣称整图等价。报告 `validation/results/original-bendy-reference/original-bendy-reference.json`；没有修改原版脚本掩盖失败。

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
