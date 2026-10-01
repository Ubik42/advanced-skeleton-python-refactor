# 原版 Face 眼球／完整眼睑主链运行记录

日期：2026-10-01。运行环境：Maya 2024 mayapy。入口：`MayaPanelController.face_original_build`，实现为 Python 原生场景命令；没有加载或调用原版 ADV MEL 过程。对照依据为本机只读 AdvancedSkeleton 6.925 的 asFacePrep、asFaceEyeBall、asFaceEyeLid、各 Fit Finish、asFaceFinish 和 asFaceRebuildRestore。

## 本批修正

- Face 基础跟随约束先解析 Head 完整 DAG 路径，OPM 设置复用 Face／Body 的同一读取规则。
- 按原版保留可选区域判断之前的操作：Lip 即使没有嘴部也完成 EyeWide；FaceCage 即使没有 Cage 区域也移除拟合动画并隐藏控件；SmilePull 完成 Squint；UpMidLo 保留原版显隐操作。避免跳过整个过程而漏掉前一阶段收尾。
- 分步重置、SDK 捕获和嘴部侧移捕获使用完整 Shape 路径，避免同名曲线歧义。
- BlendWeighted 新输入按已有逻辑索引及连接追加，处理未求值的多属性 size=0，避免覆盖 Blink／恢复 SDK 的已有输入。
- 眼球、眼睑、Pupil／Iris 的矩阵读取支持 Maya 标量及数组返回形状；修复 OPM Fleshy、EyeBase、Multi Skin Clusters 中的错误取首元素。
- 原生 cycleCheck 去除不存在的 edit 标志。
- 模板滑块使用稳定 Shape 名称；重建形状恢复限定在旧控制器下，并兼容旧匿名单曲线模板。
- 主 Skin 重建明确复制到指定 Skin；旧分层 Skin 尚在历史中时以多 Skin 在前端重建主 Skin，避免重复绑定失败。
- Face 部件输入按角色解析逻辑名称；几何／法线约束解析同角色定位目标，同时保留明确外部模型地址；Finish 的旧节点 UUID 查询统一经过角色边界，防止把原有 Head Skin 错计入 FaceAllSet。

## Maya 已通过范围

输入是双眼环代理网格，包含原生 Head Skin、眼球、由公开 Pre／Fit 入口生成的 Outer／Main／Inner。使用原版 Include=`Skip Above+Below Eyes`；完整 EyeLid 与旧单独 Eyes Only builder 是不同实现。

| 场景 | 已通过 |
| --- | --- |
| 普通一键入口 | 30 步按原版顺序执行，未包含区域正常跳过；左右眼球转动、Blink／Wide／Squint、真实眼睑 Skin、Head 跟随；整次撤销重做；保存重开；原位重建；用户滑块形状／颜色／属性恢复 |
| OPM 一键入口 | 构建、左右眼驱动、保存重开、撤销重做、重建 |
| EyeBase＋EyeSocket＋OPM | 一键构建、左右眼驱动、保存重开、撤销重做、重建 |
| SimplerEyeLid | 手动连续 1→30 步、左右眼驱动、保存重开 |
| Multi Skin Clusters | 一键构建、真实 Skin 驱动与 Head 跟随、保存重开、撤销重做、原位重建及采样一致、用户滑块形状／颜色／属性恢复 |
| FaceActor 独立命名空间＋OPM | 一键构建、真实 Skin 驱动与 Head 跟随、保存重开、撤销重做、原位重建及采样一致、用户滑块形状／颜色／属性恢复 |

集中脚本：`validation/maya_original_face_stages_smoke.py`。本地证据位于忽略目录 `validation/results/face-original-full-final-20261001`、`face-original-multi-final-20261001`、`face-original-namespace-20261001`，每项有 face-stages.json 和 Maya 场景。补充选项记录：`face-original-opm-20261001`、`face-original-options-20261001`、`face-original-simpler-20261001`。

## 明确限制及下一项

代理只验证原版输入和驱动图连通性，不证明真实角色闭眼形态等价。完整嘴唇、Jaw、Cage、眉毛、Tongue、Phonemes／Emotions 尚未获得当前整链运行证据；NonSym、Cyclops、真实睫毛与 Pupil／Iris 也不在本批验收范围。原版 Sam 文件确实存在，但本机该 Sam 只有 Body 绑定，没有 FaceFitSkeleton，不能冒充完整 Face Fit 输入。不得把 30 步顺序通过解释成所有 30 个区域均已实际构建。

下一最高优先项为完整 Face Fit 输入到 Lip／Jaw／Cage 的运行与源码缺口修复。保留原版逻辑与场景图，不用旧 Eyes Only 的经验性闭眼修形替代原版 EyeLid。全量 Goal 仍活跃，不推送 GitHub。
