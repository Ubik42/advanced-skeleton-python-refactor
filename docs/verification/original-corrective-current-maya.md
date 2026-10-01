# 原版 Corrective Shapes：当前 Maya 运行记录

更新：2026-10-01。对应 ADV 6.925 的 asCreateCorrectiveShapes、asCorrectiveDuplicate、asConnectCorrective、asEditCorrectiveShape、asCancelCorrective、asExitCorrectiveMode 和原版 FaceRebuildRestore。目标仍是继承原版逻辑，不另建绑定系统。

## 已完成的实际流程

Maya 2024 独立进程使用已完成的 30 步 Complete Face 代理场景，检验最终生产网格的实际顶点位置，除节点存在外还比较雕刻目标、完整驱动、半幅驱动和归零后的结果。

- 创建修形、雕刻、原生 invertShape 应用，单次撤销重做。
- 再次编辑并替换已有目标；增加 0.5 中间修形；保存并重新打开。
- 完整重建 Face，再撤销重做，保留原 Corrective BlendShape UUID、驱动与实际顶点变形；撤销时恢复旧 Head Skin UUID。
- 删除中间目标及完整目标，恢复未修形的蒙皮结果。
- 普通 Skin 与 Multi Skin 以上流程均通过。Multi 输入保留前批手工 Lip 权重 0.37，不把已有蒙皮变形当作修形位移。
- 独立 FaceActor 命名空间的以上完整流程通过，包括整个 Face 重建。
- Brow 左右镜像使用原生 Wrap：右侧与镜像左侧实际顶点随各自驱动变形，应用撤销重做、归零、保存重开以及分别删除均通过。
- 旧 Corrective 场景导入 ImportedActor 命名空间后仍能编辑；生产模型改名后取消可恢复显示，未完成雕刻保存重开后可以继续应用，实际顶点达到雕刻目标。

原版 Apply／Cancel 经 asExitCorrectiveMode → asDsRemoveTestAnimation 恢复构建姿态。因此应用后驱动归零是原版行为；检查修形时再次设置驱动，不修改此行为。

## 本批修正

重复模型的 Shape 使用完整路径，避免与原网格同名的短名称歧义。已绑定来源优先从原生 BlendShape 附着图读取；新雕刻和隐藏来源增加 message 连接，旧字符串数据仍兼容，导入、改名和保存重开可继续操作。

Multi Skin 的历史查询返回下游在前。修形依原版 front-of-chain 意图置于整个 Skin 链前端，避免落到部分蒙皮层之后抵消已有变形。

完整 Face 的 EyeLash、眼球以及旧 ForeHead／眼睑选择记录在调用原生 Maya 命令前按当前角色解析。Maya Skin 编辑及撤销重做产生的根空间 bindPose，只在所有成员属于当前角色时移入角色命名空间；共享或外部姿态从 Face 的临时清理集合移除。归档前和清理前均处理，不通过放宽命名空间删除限制绕过问题。

## 可重复入口和结果

入口：validation/maya_original_corrective_face_smoke.py、validation/maya_original_corrective_mirror_smoke.py、validation/maya_original_corrective_import_smoke.py。结果保存在忽略目录 validation/results，不把二进制场景加入仓库。

| 输入／分支 | 报告 | 结果 |
| --- | --- | --- |
| 普通 Complete Face | corrective-root-final/corrective.json | passed |
| Multi Skin | corrective-multi-stack-fixed/corrective.json | passed |
| FaceActor 完整重建 | corrective-faceactor-ownership-final/corrective.json | passed |
| Brow 镜像 | corrective-mirror-first/corrective-mirror.json | passed |
| 导入、改名、未完成雕刻重开 | corrective-import-final/corrective-import.json | passed |

报告均位于 validation/results。普通及 FaceActor 的 face-correctives.mb 是带完整和中间目标的保存点；face-current.mb 是删除修形后的最终场景。早期失败日志保留作诊断，不作为通过证据。

## 尚未覆盖

输入为连通代理头部，并非 ADV 默认人物的完整外观对照。QRotations、SoftMod Chains、批处理／六方向 Bake、Curve-Based Deformations 以及全部可选参数没有由本批实际流程证明；其他原版栏目缺口仍按功能覆盖矩阵继续完成。Maya 仍输出权重归一化及部分原生节点顺序提示，不宣称零警告。全量 Goal 保持活跃，不推送 GitHub。
