# Driving Systems 原版源码接入记录

依据：只读 AdvancedSkeleton 6.925 `AdvancedSkeleton.mel`。本批仅完成 Python 代码接入，未启动 Maya、未执行测试套件、未推送 GitHub。

| 原版过程 | Python 实现 |
| --- | --- |
| asCopyAnimCurve、asDSversionCheck | maya_driving_curves.py、maya_driving_edit.py；单位补偿、T／U 输入转换、键与切线、连接和无效转换清理 |
| asDsCreate 63319–64105 | maya_driving_create.py；buildPose／faceBuildPose 与 run 差异、动画发现、驱动选项、左右和中间、SDK 与 BW、编辑曲线交接、Fit 同步 |
| asShiftDSScaleAnimCurve、asDSNormalizeScales | maya_driving_curves.py；非首个缩放驱动的基值归一化 |
| asDsAutoFindAndEdit、asDsEdit、asDsEditApply／Cancel | maya_driving_edit.py；非零驱动、嘴角组合规则、时间轴编辑、对称预览和恢复 |
| asDsRemoveTestAnimation、asMuteSDKs／UnMuteSDKs | maya_original_driver_attributes.py；角色范围、时间轴、HUD、显示和 SDK 静音恢复 |
| asEnsureSDKcurvesNamed、asDsOptimizeControllers、asDsCreateController | maya_driving_curves.py、maya_driving_optimize.py、maya_driving_create.py；SDK 图遍历、半圆控制器、共同祖先与约束 |
| asPoseAdd／Store、CustomOrient 启停、asUpdatePoseAttributes | maya_original_pose_functions.py、maya_driving_optimize.py；Fit.run 与命名姿态、朝向保存恢复、过时通道清理 |

应用编排为 `application/driving_systems.py`。操作接入 `maya_panel_controller.py`、`maya_panel.py` 与原版栏目 `maya_adv_layout.py`。

仍须集中 Maya 验收：普通 Body 自动驱动、已有动画转 SDK、缩放多驱动、Face 混合属性、对称编辑、新增通道 Apply、Cancel、保存重开及 Body／Face 重建。不能把静态检查写成这些场景已经运行通过，也不能把这批过程的代码接入当作整个 ADV 全量复刻完成。
