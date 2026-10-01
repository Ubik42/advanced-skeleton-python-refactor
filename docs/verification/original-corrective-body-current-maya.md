# Body 高级修形与原版控制器接入

更新：2026-10-01。本批继续以 ADV 6.925 的 asCreateQRotateAttrs、asCreateCorrectiveShapes、asCorrectiveDuplicate、asConnectCorrective、asEditCorrectiveShape、asMatchSoftModSettings、asBakeIntoCorrectiveShapes 为依据。

## 已修正的主体问题

原版 iconsGroup 的曲线进入 ControlSet；noControl 时同时移除 FK 与 FKExtra（MEL 78786、79968）。旧 Python 选择集将主控制器替换为 Extra，导致主 FK 不在集合中且其绑定姿态通道缺失。本批保留两层控制器；旧场景缺失的已登记普通 FK 本地 TRS 按原生默认值兼容读取，不覆盖已有绑定姿态记录。

Python Body 的内部控制器名允许重组，但原版操作需要识别其 FK、关节和 Extra 角色。新增宿主身份层从既有角色登记读取映射，修形驱动使用实际 Body 关节，重新摆姿态使用对应主 FK。普通、Part/Spline 的驱动不另建第二套绑定图。采集恢复姿态包括已登记通道；有效主 FK 烘焙不再因内部名称被跳过，Root 与 Extra 保留原版排除规则，noControl 也继续排除。

后台刷新没有视口求值。SoftMod 链保存前读取实际雕刻输出，再按原版断开末端并删除历史；修复批量重编辑时烘焙未变形缓存的问题。雕刻复制与烘焙来源连接也明确求值。零驱动及旧零范围 SDK 显式报错并回滚，不生成退化目标或继续除零。

## Maya 2024 已通过

输入为原版 biped 的 Python Body 绑定场景，并创建真实绑定在 Shoulder_R 的局部代理网格；不是默认人物外观对照。输入场景的 Global 演示动画在验证准备阶段移除，保证世界空间雕刻比较处于同一静态姿态，不宣称本批验证了带动画雕刻。

- Shoulder_R.qRotateZ 驱动：创建、雕刻、原生 invertShape、应用单次撤销重做、保存重开、再次编辑、批量重新应用、删除后恢复原 Skin 变形。
- 两层原生 SoftMod：同一完整流程；两条变形器 UUID、Handle、链连接及雕刻效果在应用／重新编辑／保存重开后保留，更新第一层后批量应用仍保持实际顶点位置。
- 最新原版 biped 主链：72 个 Body、18 个 Part、1582 个通道；构建、Skin、姿态与动画文件往返、FBX、原位重建、原生 Skin／曲线身份保留、单次撤销重做和保存重开通过。

| 范围 | validation/results 中的报告 | 状态 |
| --- | --- | --- |
| Body QRotation 单轴完整编辑 | corrective-body-qrotation-final/body-corrective.json | passed |
| Body 两层 SoftMod 完整编辑 | corrective-body-softmods-final/body-corrective.json | passed |
| biped 构建／重建／动画／FBX | biped-primary-controls-final/original-biped-current.json | passed |
| 原有 Complete Face 修形回归 | corrective-face-body-integration-final/corrective.json | passed |

验证入口为 validation/maya_original_corrective_body_smoke.py 和已有 biped／Face 主链入口。场景及报告在忽略目录中，本仓库不提交二进制输出。

## 六方向烘焙仍未完成

validation/maya_original_corrective_bake_smoke.py 检验原版六方向实际来源／目标网格一致性，不只数目标。原版切全 FK 已映射到登记的真实 RP 模式通道；当前 Wrist 样例能创建六个 QRotation 目标，整体撤销重做也通过，但实际顶点比较失败，不能标为烘焙通过。

最后失败证据：corrective-bake-all-fk/bake.json。X=90 时实际 qRotateX 为 30.086361770953427，来源与目标的采样 Y 分别为 15.706863403320312、15.712176322937012；采样驱动与最终实际驱动不一致仍需追踪。Shoulder 纯 X 旋转还观察到主 Body 的 QRotation 驱动为零，须核对 Twist／Part 的来源图，不能改用控制器角度掩盖这个问题。

下一最高优先级是完成这些 QRotation／Twist／六方向采样问题，再检验混合旋转、镜像 SoftMods、取消及 Curve-Based Deformations。单轴 Shoulder 修形通过不代表所有 QRotation 参数通过。Maya 原生 Curve Info／权重及顺序提示仍存在，不宣称零警告。全量 Goal 活跃，不推送 GitHub。
