# 来源 Spline 旧模式升级与父矩阵修复

2026-10-01，Maya 2024。此记录验证原版 biped 的单组中线 Spline，根命名空间和独立 `ModeActor` 命名空间各跑一遍。

## 实现依据与操作

原版 MEL 81830–81945 建立独立 FKIK 图标、父接收器、FKIKBlend 0–10 用户范围、0.1 权重转换、自动／手动显示和 Hybrid 显示。Python 的旧 `spineIkFk` 0–1 图使用显式“升级旧 Spline FKIK”入口迁移，普通重建仍保留旧模式范围，不隐式改写动画。

升级根据实际 Fit 标签、完整 Body 链及其物理父级解析原版控制器身份，包含 Part 父级、Root 的 LegLock 分支和 NonSymmetry 的原版符号。原生 mode 曲线整体乘 10，通过 Maya scaleKey 同时变换带权切线；保留曲线 UUID、键时间、切线类型、循环外推以及原来的显示曲线。生成图的权重使用 0.1 转换，显示使用原版用户范围与 setRange。通道登记改为新建角色相同的 FKIKBlend 语义，闭合的 Body 矩阵记录只替换明确的模式输入。

共享给其他通道的模式曲线、未知范围、非原生动画输入、引用或锁定曲线以及名称冲突会明确拒绝。单次 Undo 包含控制器、图接线、曲线换算、登记和选择集扩展；晚期失败完整回滚。

## 同批修正的原版矩阵接线

集中运行定位出旧 Python Source Root／Spline 的 OPM 自反馈：驱动接收器的矩阵使用了该接收器自己的 parentInverseMatrix。该矩阵包含 OPM，因此 Root 在查询顺序变化时会在正常位置与零点间跳变。

原版 `asParentConstraint`（MEL 25730 后）明确从 `listRelatives -p` 得到父节点，再接父节点的 worldInverseMatrix。现按此逻辑修正 Source Root Follow、LegLock 输出、Root 分支偏移和 Spline FirstFixed 输出。显式模式升级和普通重建在同一个原生事务中修复这些明确的历史自反馈边；仅识别登记内的已知接收器，不覆盖外部输入，锁定或引用的矩阵会阻断。

动作等价验证以修正自反馈后的图为基准。修复前由求值顺序产生的零点跳变不是需要保留的动画效果；本项不宣称逐帧保留错误图的跳变。

重建的登记成员比较也已改为相同 message 身份关系，允许扩展在表尾增加控制器。登记读回仍逐个核对实际序号与节点身份，其他图连接检查保持不变。Inbetween 权重检查使用原生连接身份，避免完整 DAG 路径与 Maya 返回的短名被误判为不同输入。

## 集中运行结果

`validation/maya_spline_mode_upgrade_smoke.py` 从只读原版 biped.ma 构建真实旧 0–1 图，再复现历史自反馈接线。两种命名空间均通过：

- 72 个 Body 的旧模式升级与原生蒙皮保留。
- 带权固定切线、15 个键内／键外采样以及循环外推的 10 倍换算；保留原生曲线 UUID。
- 自动／手动显示属性和显示曲线迁移，既有控制器 UUID 保留。
- 共享曲线提交前拒绝、提交末期失败回滚、单次 Undo／Redo。
- 保存 Maya Binary、重开登记、重复升级无额外修改。
- 升级后的普通原位重建，身体／蒙皮严格采样比较和原生曲线保留。

结果：

- `validation/results/spline-mode-upgrade-final-20261001/spline-mode-upgrade.json`
- `validation/results/spline-mode-upgrade-ns-final-20261001/spline-mode-upgrade.json`
- 两目录的 `spline-mode-upgraded.mb` 可在 Maya 打开；图内已有 FKIKSpine_M 控制器和带权动画。

纯 Python 的模式身份、通道迁移、错误侧标记和父矩阵修复边界也通过针对性检查。

## 实际范围

尚未覆盖多组 Spline、左右独立链、复杂附件、任意动画层或非均匀缩放的完整组合。旧 0–1 姿态／动画 JSON 的兼容摘要与新 0–10 范围不同，此入口迁移场景中的原生曲线，不转换外部旧 JSON 文件。此结果不代表完整 Face 或全量 ADV 源码已验收。
