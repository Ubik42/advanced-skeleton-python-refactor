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

## 连续重建与删除后重新绑定修复

`validation/maya_original_face_shell_smoke.py` 用 Maya 安装自带的 `polyConvertToShell` 命令作对照，不运行 ADV MEL 过程。单壳、双壳、多种种子、命名空间和父级路径的结果相同；取点不改变持久选区约束。真正分离的眼睑取点分支也通过撤销重做，临时网格／采样器清理、生产网格和 Skin 身份保持。

当前同一进程的完整构建→初次 Undo/Redo→保存重开→完整重建→Undo/Redo 已通过：

- `validation/results/face-complete-shell-fix-live/face-stages.json`：普通 Complete。
- `validation/results/face-complete-final-live-multi/face-stages.json`：最终代码的 Multi，Lip 0.37 与 Tongue 附加层 0.31 保留。
- `validation/results/face-complete-shell-fix-opm16/face-stages.json`：Complete＋16 个嘴唇控件＋OPM。
- `validation/results/face-shell-native-detached-fixed.json`：原生命令对照与分离眼睑原生撤销重做。

完整入口的检查同时断言 30 步／完成状态，核对 ForeHead Fit 曲线 CV 在 Undo/Redo 前后保持一致，避免仅凭 FaceMotionSystem 存在判断成功。原生 Attach Curve 的撤销警告仍存在，本批不宣称消除全部 Maya 警告。

删除主流程补入：清除 buildCompleted；分步 Prep 将完成标志置为 false；保留 Fit 曲线及其 Shape，删除曲线上临时 Face Skin；按原版删除仅由 Face 关节驱动的专用蒙皮层，保留原始 Head Skin 及全部输入模型。`validation/maya_original_face_delete_smoke.py` 检查删除／Undo／Redo、恢复后的 39 项变形、模型／Fit／Head／HeadSkin UUID 保留，再次执行完整 30 步、单次撤销重做与保存重开。普通与 Multi 均通过，证据为 `validation/results/face-complete-delete-final/face-delete.json` 和 `validation/results/face-complete-delete-final-multi/face-delete.json`。

## 边界与未完成

- 输入是用于检查图与蒙皮的代理模型；不是原版默认角色的外观等价证明，也不是 UI 排布／图形窗口验收。
- 运行使用 cage_smooth=1、jaw_smooth=1，降低代理输入的运行量；生产默认值未改。未证明原版所有可选 Fit、NonSym／Cyclops、Face 独立命名空间组合、其他眉毛中点、RigType／BlendShapes／Mixed、Wrinkle 或 ARKit 全部分支。
- 初期未冻结附件输入在权重暂存时丢失舌头末端权重：原版临时球体复制 outMesh 本地坐标，空间复制依赖模型已冻结。修正输入要求，不添加虚构的替代复制规则。
- 此前同进程重建重做中断已定位并修复：原版 `ConvertSelectionToShell` 的整块连通壳选择被错误翻译为 `polySelectConstraint(shell=True, mode=2)`，误入分离眼睑分支；该分支的通用组件 delete 还会中断原生重做。改用拓扑连通壳与明确的 `polyDelFacet`，保留原版范围、最近点和后续绑定逻辑。此前失败目录保留作诊断记录，不再代表当前代码。

全量 Goal 保持活跃；未推送 GitHub。
