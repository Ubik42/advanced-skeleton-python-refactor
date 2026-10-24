# 验证入口

当前验证状态见 [工程状态](../docs/工程状态.md)。本目录保留可复用的原版对照、主链和生命周期脚本；脚本存在不代表当前版本已经通过。旧 Git 跟踪结果已删除，运行输出写入忽略的 `validation/results/`。

## 运行约束

用户已授权必要的真实 Maya 测试。只使用一个实例，先检查真实进程；窗口放在副屏工作区下半区，不抢主屏焦点。报告产生后核实本任务进程退出，再进行下一批。不批量并行启动图形 Maya。集中检查主链，避免频繁重复小测试。图形运行器 `run_maya_gui.ps1` 按实际屏幕布局定位并清理自己启动的进程。

离线检查不导入真实 DCC 时可以执行；模拟宿主失败需区分旧合同与业务错误。最近保存的离线结果仍有失败和错误，不能宣布全套通过。

## 主要脚本

| 范围 | 入口 |
| --- | --- |
| 标准来源骨架主链 | `maya_body_lifecycle_current.py` 通过 `run_maya_gui.ps1` 串行覆盖传统、OPM、Bendy；复用 `maya_original_biped_current_smoke.py`，直接检查重建前后全顶点和蒙皮数据 |
| Body SDK 重建输出 | `maya_body_sdk_lifecycle.py` 读取完整生命周期保存的重建前后场景，比较驱动属性上下限姿态中的 Body/SDK 矩阵、SDK TRS，以及原生曲线键值、切线和循环参数；不重复构建 |
| 旧角色与用户编辑 SDK | `maya_body_legacy_sdk_rebuild.py`：旧 RP 归属标记迁移、用户修改硬软范围和加权固定切线后的重建、蒙皮动画、保存重开及撤销重做；`ADV_LEGACY_SDK_CASES` 可选择 `pre-owner-marker`、`authored-sdk`，避免重复已通过案例 |
| 末端删除的归属对照 | `maya_retirement_delete_probe.py` 复用加权原场景和已保存暂存图，区分 Skin 与 AllSet 成员对原生节点删除的影响；读取成功只证明定位范围，不能替代完整重建验收。 |
| RP 输入定位 | `maya_rp_input_compare.py` 只读取保存的原版/Python 左臂关节、父级、求解器与拉伸图；读取成功不代表数值对照通过 |
| RP 输入差异隔离 | `maya_rp_source_input_isolation.py` 在不保存的临时场景逐组替换原版输入，定位误差来源；禁止将诊断替换当成生产修复 |
| 实际 Maya 面板入口 | `maya_current_inputs_and_panel.py` 复用保存角色，检查所有导航及真实 Qt 抓图；不执行绑定按钮、不代表业务或全部原版排布验收。`ADV_PANEL_ONLY=1` 跳过已完成的 RP 读取，`ADV_RP_PYTHON_SCENE` 指定已保存场景 |
| 当前多 Spline/Bendy 原版对照 | `maya_source_body_current_parity.py`：新建非 OPM 场景，验证完整重建及 71 组全 Body 姿态；不放宽原版对照误差 |
| Game 自定义导出骨架 | `maya_game_skeleton_parity.py`：六种轴组合和旧 root 包装，原版节点/变形及蒙皮交接对照；覆盖范围以实际报告为准 |
| Squash 原版节点与变形对照 | `maya_custom_squash_parity.py`，通过 `run_maya_gui.ps1` 运行 |
| 自定义控制器原版转换、镜像与新增模型 | `maya_custom_controller_parity.py`，通过 `run_maya_gui.ps1` 运行 |
| 原版末端清理及旧 Spline 迁移 | `maya_export_alignment_lifecycle.py` 在单个实例内串行运行；`ADV_EXPORT_ALIGNMENT_CASES=retirement` 或 `alignment` 选择未通过范围。前者调用 `maya_export_retirement_lifecycle.py`，已确认清理后设置 `ADV_RETIREMENT_REBUILD_ONLY=1` 可复用保存场景集中验证重建；后者调用 `maya_source_spline_alignment_lifecycle.py`，读取真实旧 Spline 场景。选择重建续跑时保留原清理证据及来源 PID，不重复宣称本实例执行过清理。 |
| Spline 控制数量重建 | `maya_spline_control_rebuild_smoke.py` |
| Spline 模式升级 | `maya_spline_mode_upgrade_smoke.py` |
| Face 转换原版对照 | `maya_face_conversion_parity.py` |
| Face 通道原版对照 | `maya_face_channel_parity.py` |
| Face 独立角色 | `maya_face_optional_namespace.py` |
| 控制器与面板 | `product_maya_adv_layout_offscreen.py`、`product_maya_panel_offscreen.py` |
| 模板几何 | `maya_template_geometry_parity.py` |
| 几何操作 | `maya_geometry_operations_parity.py` |
| 运行层边界 | `architecture_boundary_audit.py` |

脚本的参数和输入要求以文件内容为准，先核对适用版本和场景。其他细分脚本继续保留供定位问题使用，不作为必跑清单。运行时必须记录当前代码版本、原版输入、实际结果和剩余问题。

## RP 随动完整流程

`maya_source_rp_follow_lifecycle.py` 复用保存的原版多 Spline/Part 输入，检查传统与 OPM 新建、蒙皮和动画保留、重建、整次撤销重做、保存重开及原版姿态。`ADV_RP_FOLLOW_CASES` 选择 `traditional,opm,legacy`；`ADV_RP_FOLLOW_OUTPUT` 指定独立结果目录。`ADV_RP_FOLLOW_REUSE=1` 仅在代码和输入保持相同、已有生命周期通过时复用该项证据。脚本按实际 Spine 系统名解析姿态入口，失败数值和门槛继续保留。

`maya_source_rp_follow_scale_compare.py` 对照同一原版输入、修改前保存角色和当前角色，读取 IK、PoleAim、父级框架及最终关节。脚本的 `passed` 仅表示诊断读取完成；姿态数值另列在 `comparisons`。当前验收范围以工程状态和紧凑摘要为准。

`maya_source_rp_part_snapshot.py` 只读打开保存的原版与 Python 角色，读取中性、手臂拉伸、长度及传统模式颈部非均匀缩放下的实际关节、矩阵与输入连接。`ADV_RP_PART_CURRENT` 指定 Python 场景的结果目录名，默认使用 `source-rp-part-position-final-current`。报告的 `passed` 表示读取完成，数值通过以完整姿态对照为准。

`maya_source_fit_aim_follow.py` 直接调用生产通用 Aim 构造函数，对照原版中央随动的传统/OPM、Main 初始变换、0/5/10 权重及 Head/Main 缩放，共 36 组矩阵。脚本同时检查旧 TR 图读取、新图输出约束及四组保存重开。设置 `ADV_AIM_FOLLOW_LIFECYCLE=1` 后，脚本在同一个 Maya 实例继续完整角色构建与重建；`ADV_RP_FOLLOW_OUTPUT` 指定整角色报告目录，`ADV_RP_FOLLOW_CASES` 选择配置。组件通过与整角色结果分别记录。

`maya_source_fit_aim_controls.py` 在同一个 Maya 实例执行新角色完整生命周期、原版侧边通道状态，以及旧 TRS 通道布局和额外旋转/缩放动画的保留重建。启动前设置 `ADV_RP_FOLLOW_CASES=traditional`、`ADV_RP_FOLLOW_AIM_CASES=1` 与 `ADV_RP_FOLLOW_OUTPUT=source-fit-aim-native-controls-lifecycle-current`。新旧角色各保存重建前后 34 个原版姿态；旧输入复用上批已修正 AimFollow 的保存角色。结果写入 `source-fit-aim-controls-current/report.json`，不覆盖早期脚趾失败输入。

## Face 当前整段流程

`maya_face_rebuild_lifecycle.py` 检查保存角色的完整重建、手改数据及撤销重做。脚本保留多层权重失败，并继续记录其他生命周期结果。`ADV_FACE_REBUILD_CASES` 可选择 ordinary 或 multi。

`maya_face_rebuild_source_parity.py` 从相同输入执行全部原版阶段，核对全部 Skin 和 Head 旋转、缩放响应。`ADV_FACE_REBUILD_REUSE=1` 读取已保存的原版构建，避免重复创建。原版多层重建在 Maya 2024 的 Prep 失败单独记录。

`maya_face_pp_source_parity.py` 核对 PP 的传统/OPM、三侧与旧版朝向共 12 组矩阵和撤销重做。当前结果见 `docs/verification/source-face-pp-current.json`。

## 已有证据的限制

Body 的历史严格对照为 70/71，汇总仍失败；不能写成整体通过。Face 的两类纯 BS 转换当前对照及生命周期通过；Mixed 的当前 OPM 输入已通过来源与完整生命周期对照，53 个蒙皮对象的权重与绑定矩阵差异为 0。完整 Face 构建阶段及重建的来源范围另见当前工程状态。Custom Controller 的 Body 10 组、Face 9 组以及 Squash 5 组当前原版对照通过，仅证明脚本实际覆盖的输入和分支。自定义控制器脚本默认验证 Body，设置 ADV_CUSTOM_SCOPE=face 验证 Face，分别保存 report.json 和 face-report.json。Game/SDK 和重建改动未经过整版验收。完整默认模型、AutoPlace 和 UI 仍不能认定完成。

`maya_face_skin_input`：原版 Face Pre 可编辑 SkinCluster 输入，根角色实际面板槽函数、命名空间、撤销重做、保存重开与普通/多层完整保存场景输入检查。结果在 `validation/results/face-skin-input-current/`；该项不代替完整 Face 构建来源与多层权重保留验证。

`maya_body_face_lifecycle`：复用完整 Body 保存角色，通过原版 EyeBall/Jaw Fit 替换身体眼睛与下颌，再执行完整 Face 构建、撤销重做、保存重开及 Face 重建。检查 Body 登记、已有动画、蒙皮与合并姿态。程序网格只用作功能输入。不同任务并行 Maya 已获 2026-10-12 用户授权，运行器使用 `-AllowOtherMaya`，本工程自身仍限制一个实例。
