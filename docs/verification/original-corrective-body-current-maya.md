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

## 曲线修形主链已通过

按原版 asCBDCreate、asCreateSliders、asCBDCreateDeformMesh、asCBCleanup 衔接当前 Body。修正内部 FK 身份识别、SkinCage 复制后约束重名、Partial 与 Part 分支混淆，以及末端 Twist 截面解析为 Wrist 后仍按 Elbow 截面限轴的问题。来源模型及 FK 增加 message 连接，已有字符串保留兼容读取。测试动画按原版只切选中肢体到 FK，不能改变其余肢体模式；实际验证将无关肢体置于 0.7，运行后保持 0.7。

原版创建 CorrectiveSC / CorrectiveWrap 使用 asDeformer（MEL 68328、68343），临时关闭 deformationUseComponentTags 以生成原生变形器成员集合。Python 现复用对应偏好范围，成功及异常均恢复原偏好，不用普通空集合替代真实成员集合。

Maya 2024 当前 Body 的 Wrist_R 与局部代理网格通过：四条九点曲线创建、解除／重新绑定、测试动画真实 CV 变形、Loft／Skin／Wrap 局部网格、原版显示切换、保存重开、清理保留来源。局部网格保留 56 个顶点；编辑曲线使实际 Wrap 输出最大移动 0.3318414688，恢复编辑后回到原位置。来源模型在创建后改名仍可继续完整流程；Component Tags 偏好 1 在变形器创建后仍为 1。曲线与实际局部网格保存重开后均一致。验证入口为 validation/maya_original_corrective_curves_smoke.py，最终报告 corrective-curves-body-final/curves.json；曲线四方向 Bake 随后补通：临时隔离时间关键帧输入，避免后台全图求值覆盖采样姿态，并在结束或异常时恢复连接。四目标实际顶点比较通过，曲线清理后保存重开也继续比较。整次 Bake 的撤销重做与曲线／关键帧身份恢复列于最终报告。不代表真实默认角色外观已验收。

## QRotation 和 SDK 与原版图一致

validation/maya_original_qrotation_source_parity.py 在隔离场景加载未经修改的本地原版 MEL，仅用于验证；生产宿主不调用 ADV MEL。原版图和 Python 图分别在同一当前 Python Body 上取样 Shoulder_R / Wrist_R，各 16 个单轴、混合及正负旋转，误差均为 0。原版 asTweakSDKCurveForRotation 与 Python 曲线的 96 个权重取样误差也为 0。

证据：corrective-qrotation-source-parity/source-parity.json，状态 passed_graph_and_sdk_parity。原版 asCreateQRotateAttrs 在该隔离后台场景的过程尾部有 RuntimeError，报告单独记录；其完整 Q 图和属性已生成并求值。本结论限定为生成图及 SDK 的对照，不宣称原版过程整体无异常，也不证明 Python Body 与原版 Body 的整个图一致。

Wrist 主控制器 X=90 时，两套 Q 图均得到 (30.086361770953463, -2.474222437559329, 2.474222437559298)。Shoulder 纯 X=90 两套均得到零。应继续核对 Body Twist／Part 及完整烘焙链，不能用控制器角度替换已一致的关节 QRotation。

## 六方向烘焙与原版完整输出一致

本批用 Maya 2024 GUI 加载本地未经修改的 ADV 6.925 MEL 和真实原版面板，运行 asBakeIntoCorrectiveShapes。原版 MEL 与只读参考逐字节相同，SHA256 为 828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02。输入仍为同一 Python Body 与局部代理网格，验证准备将 Wrist 主 FK 改为原版识别名，并给旧式 buildPose.udAttr 填入该主 FK 的中立 TRS；其他肢体预先中立且全 FK。未替换任何原版过程，未把该对照宣称为原版 Body 构建对照。

原版六方向完整烘焙生成六个目标，无过程异常。X=±90 的来源／目的网格最大偏差均为 0.005312919616699219；Y=±90 为 0；Z=±90 为 9.5367431640625e-7。之前的 0.0053 偏差在这个输入上也出现在原版全过程中，不能继续据此判定 Python 翻译错误。

Python 六方向烘焙在六个姿态下、每个网格全部 42 个顶点（126 个坐标）与原版目的输出差异均为 0，来源输入差异也均为 0。六目标、起始姿态／选择恢复、单次撤销重做及保存重开通过。严格来源／目的一致性验证仍保持原标准、状态仍为失败，不改为宽容通过；当前通过的是完整原版输出一致性。

| 范围 | validation/results 报告 | 状态 |
| --- | --- | --- |
| 未修改原版 GUI 完整六方向 Bake | corrective-bake-original-gui/source-bake.json | original_bake_measured |
| Python 全顶点六姿态原版对照 | corrective-bake-full-native-parity/bake-parity.json | passed_source_parity |
| 带已有关键帧的 Bake／连接恢复／异常回滚 | corrective-bake-animated-native-parity/bake-parity.json | passed_source_parity |
| 时间曲线经 unitConversion 输入的 Bake | corrective-bake-converted-native-parity/bake-parity.json | passed_source_parity |
| 严格来源／目的网格一致性 | corrective-bake-source-parity-final/bake.json | failed，原版同样有该残差 |

验证入口为 maya_original_corrective_bake_source_parity.py（真实 GUI、延迟调用 main）、maya_original_corrective_bake_parity_smoke.py；原严格入口 maya_original_corrective_bake_smoke.py 保持独立。

## 混合 QRotation／镜像／SoftMods

修正原版 FK 身份映射在混合属性副本、setQRotatesCmd、混合镜像的临时摆姿态、重新编辑切 FK 中遗漏的接入。原版排除 FKExtra／FKIK 的规则扩展到已登记的对应角色。SoftMod 重编辑输入兼容 legacy groupParts，沿 inputGeometry 找到同一个原始网格再恢复既有链，不误用 groupParts.worldMesh。

asCreateCustomBlendedAttribute 原版将两路图属性均取自 driverObjs[0]；旧 Python 在第二路使用第二个发现对象，已改回原版连接及 dv 值。独立原版对照覆盖不同对象、负值／-1 翻号、clamp、两路连接与 dv，三组各五个输出采样误差为 0。报告 corrective-blended-native-parity/blended-parity.json，状态 passed_source_graph_parity。

当前 Body 混合 QRotation 的创建／实际雕刻／镜像／重新编辑／重新应用／批量应用／取消／保存重开由 maya_original_corrective_mixed_smoke.py 验证。普通雕刻及 SoftMod 均有运行记录；SoftMod 镜像实际最大移动 0.1999998093，按中立顶点对应关系比较世界 X 平面反射后的雕刻增量，误差为 0。最终报告 corrective-mixed-softmods/mixed.json。本项取消只验证已应用目标的几何保持，不宣称取消会保留已移到根层的 SoftMod Handle；原版取消也删除这类根层 Handle。

## 当前剩余范围

继续依据原版功能覆盖矩阵处理未验收分支，尤其真实默认角色外观、其余 Body／Preparation 差异和全部可选组合。Wrist 纯 X 重编辑、Inbetween／Twist 的更多组合、分层动画混合输入，以及单位换算输入下的交互雕刻／编辑仍未由本批覆盖。Bake 采样隔离支持直接时间曲线及 unitConversion 链，保留既有关键帧、UUID及实际连接边，驱动关键帧／约束继续参与计算；通过证据包括正常完成、撤销重做、保存重开和注入异常。

全量 Goal 活跃，不推送 GitHub。原生权重、顺序及带历史曲线 tweak 提示仍存在，不宣称零警告。
