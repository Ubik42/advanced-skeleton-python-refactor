# 原版 Complete Face 主链：当前 Maya 2024 记录

2026-10-01。以 ADV 6.925 MEL 为只读依据，执行 Python 公开 Pre／Fit／Build 入口，不运行原版 ADV MEL 过程。原版流程仍是 30 步；本批补齐之前只有眼睑或下半脸输入的运行范围。

## 本批实现

- Tongue 在 Maya standalone 的 `getModifiers()` 返回空值时采用无修饰键 0，保留原版 Ctrl 键留权重盒行为。
- UpMidLo 的多层附属网格分支取消不存在的 Python `skinClusterChain` 调用，按 Maya 原生 `findRelatedSkinCluster` 的下游 Skin 顺序获取并重排，继续使用原版四影响和权重复制逻辑。
- 前次绑定捕获区分各网格原始 Head Skin 与 Face 附加层，避免把 Tongue／Teeth 的原始 Skin 当作 UpMidLo 层删除。除主 Face 的 EyeLid／Lip／Cage／Jaw／UpMidLo 外，也捕获眼球、眉毛、睫毛和其他头部网格上的原生 Face 层。
- 原始 Skin 继续使用源码的 closestPoint／closestJoint 复制；同拓扑附加层按关节身份恢复手工权重。恢复保留关节实际命名空间，避免将外部 Body Head 错映射为 Face 命名空间内的 Head。

## 已通过范围

`validation/maya_original_face_lower_smoke.py --complete --full --attachments` 使用连通曲面 Face、双眼、上下牙、舌头、双侧独立眉毛与睫毛网格。由公开入口创建 EyeLid／Lip 三圈、Jaw／Nose／Cheek、眉毛（含 Mid1）、ForeHead 三点边界、UpMidLo 和 Tongue Fit，Include=Complete。附件变换在绑定前按原版 Model Check 要求冻结。

普通与 Multi Skin Clusters 的 30 步完整入口、第一次构建的单次撤销重做、39 项实际变形／归零／Head 跟随检查、保存重开均通过。39 项包含下半脸控制、Brow 位移／Squeeze／OuterUpDown、Blink／Squint、上中下脸、上下牙、舌头中段／末段、Jaw 对下牙与舌头的跟随、rrr／lntd 对舌头的口型，以及五个独立附件／眼球的 Head 跟随。

独立 Maya 进程载入上述保存场景后，`validation/maya_original_face_complete_rebuild_smoke.py` 完成普通和 Multi 的完整重建、旧原生 Skin UUID 撤销恢复、重做、39 项变形采样保持一致、自定义属性保留、重建后保存重开。重建前后最大采样差为 0.0。Multi 还验证 LipSC 手工 0.37 权重和 Tongue 网格 UpMidLo 附加层 0.31 权重保留。

证据（运行产物为本机忽略文件）：

- `validation/results/face-complete-frozen-20261001/face-stages.json`
- `validation/results/face-complete-multi-frozen-20261001/face-stages.json`
- `validation/results/face-complete-frozen-rebuild-20261001/face-rebuild.json`
- `validation/results/face-complete-multi-frozen-rebuild-20261001/face-rebuild.json`
- `validation/results/face-eye-multi-complete-regression-20261001/face-stages.json`：原先眼睑 Multi 主链的保存、重建、滑块形状及属性回归通过。

可继续在 Maya 打开的完整绑定场景：`validation/results/face-complete-frozen-rebuild-20261001/face-rebuilt.mb`；多层版本在相应 multi-frozen-rebuild 目录。

## 边界与未完成

- 输入是用于检查图与蒙皮的代理模型；不是原版默认角色的外观等价证明，也不是 UI 排布／图形窗口验收。
- 运行使用 cage_smooth=1、jaw_smooth=1，降低代理输入的运行量；生产默认值未改。未证明原版所有可选 Fit、NonSym／Cyclops、Face 独立命名空间组合、其他眉毛中点、RigType／BlendShapes／Mixed、Wrinkle 或 ARKit 全部分支。
- 初期未冻结附件输入在权重暂存时丢失舌头末端权重：原版临时球体复制 outMesh 本地坐标，空间复制依赖模型已冻结。修正输入要求，不添加虚构的替代复制规则。
- 同进程构建→重开→重建→Undo/Redo 在普通和 Multi 中都留下 prefix 旧图，冻结输入后仍复现；独立进程重建的 Undo/Redo 及保存重开通过。调整删除顺序、扩大或清理撤销队列均未解决，已撤回这些尝试。此差异仍待定位，列为下一项最高优先级；不能将独立进程结果报告为所有连续操作通过。失败证据：`face-complete-frozen-live-rebuild-20261001`、`face-complete-multi-frozen-live-rebuild-20261001`。

全量 Goal 保持活跃；未推送 GitHub。
