# 来源 Body OPM 本批运行记录（2026-10-01）

依据 ADV 6.925 原版 asParentConstraint 的实际父 worldInverseMatrix 接线，本批修正接收节点 parentInverseMatrix → 自身 OPM 的反馈。未修改只读原版 MEL，未推送 GitHub。

## 已通过真实 Maya

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
