# 原版 Face 嘴唇／Cage／Jaw 主链运行记录

日期：2026-10-01。Maya 2024 mayapy，公开入口 `MayaPanelController.face_original_build`。依据只读 ADV 6.925 MEL，未调用 ADV MEL 过程，未推送 GitHub。

## 输入和范围

新增 `validation/maya_original_face_lower_smoke.py`：一张连通的弯曲网格，双眼孔及嘴孔；Head 原生 Skin、双眼球，公开 Pre 和 Fit 入口创建三层 EyeLid、三层 Lip、16 个下半脸定位点及 Jaw 曲线。Include=`Skip Above Eyes`。这是原版拓扑及驱动图验证输入，不是官方 Sam、真实人物模型或视觉成品。

30 步顺序真实执行；Lip、LipFalloff、FaceCage、CageToSkin、Smile/Frown/Cheek、JawWeighing、JawOpen、LipUp/Down/Side、Snarl、Regions、Phonemes 和 Emotions 有实际输入。EyeBrow、Tongue、UpMidLo 缺少对应拟合输入，按原版跳过，不能算这些区域已验收。

## 本批源码修正

- Lip 共用 motionPath 及曲面采样器保留到上下唇处理结束，再与临时几何一起清理，继承 MEL 的节点生命周期。
- Lip Roll 保留原版严格大小比较、首个等距候选及上一轮最近控制器；撤掉先前自行添加的端点替代规则。
- Lip Falloff 的 MEL 字母编号转换改为正确的一基到零基转换，原版从 B 开始的拟合动画不再误写到 C。
- Lip、Cage、Jaw、UpMidLo 和 OPM Scale Reset 统一读取完整 16 项矩阵；SDK 追加输入包括尚未求值的连接索引。
- Jaw、UpMidLo、SoftMod 和 BS Layers 的 polySelectConstraint 使用 Maya 实际支持的 dist/distbound/distaxis/distpoint 参数，数值与原版保持一致。
- 原版 asDeformer 偏好作用域在 optionVar 不存在时也明确关闭 component tags，并恢复原值或原先不存在的状态。MouthOpen、SoftMod 编辑、Tongue、Eye Squash、HeadSquash、DeltaMush 共用该规则；未运行的区域只算代码修正。
- 原 MEL 的 LipDeform 只含设计 SoftMod，Maya 2024 无法从它推断 Skin。JawLayer 转移明确使用 asFaceWeightLips 已存入 JawOpenLayerSC 的采样权重，保留嘴部选区及原生 closest-point/joint 复制。
- Lip Falloff、主权重 holder 捕获／恢复明确 Skin 来源，避免多层历史下隐式选择错误。
- 多层重建分别保存 EyeLid/Lip/Cage/Jaw/UpMidLoc 的原生权重；保存后解除旧层对生产网格的影响，避免干扰新拟合采样。按原关节名称恢复同拓扑权重，避免同位置关节被最近关节匹配合并；写入仍通过原生命令，参与整次撤销。

## 集中 Maya 结果

| 输入 | 通过范围 | 本地结果目录 |
| --- | --- | --- |
| 普通默认 12 个 Lip 控件 | 一键 30 步、单次撤销重做、实际驱动、保存重开、原位重建、采样一致、自定义滑块属性 | `validation/results/face-lower-default-final-20261001` |
| 16 个 Lip 控件＋OPM | 同上，实际走非默认 Ribbon 重建和控制数量分支 | `validation/results/face-lower-count16-final-20261001` |
| Multi Skin Clusters | 同上，各层权重恢复后重建采样一致 | `validation/results/face-lower-multi-detach-20261001` |
| Multi Skin Clusters＋手工权重 | 基线前给 LipSC 手工写入 0.37；保存重开、重建后精确保留；整次重建撤销恢复旧 Skin UUID，重做后驱动一致 | `validation/results/face-lower-multi-authored-20261001` |

每项有 `face-stages.json`、拟合输入和最终 Maya 场景。手动入口的连贯 1→30 步构建记录在 `face-lower-connected-20261001`，其早期报告仅标 built；实际驱动以以上最终记录为准。

生产 Face 网格检查包括开口、嘴宽、上下唇、侧移、Roll、Pucker、嘴角二维 Smile 滑块、Cheek、Nose、aaa 和 happy；逐项验证非零变形、有限坐标、归零回原姿态。Head 移动 2 cm，整张脸跟随 2 cm。普通默认输入的开口最大位移约 0.208 cm，上唇移动约 0.434 cm，侧移约 0.384 cm，aaa 约 0.187 cm。数字是代理网格的连通性证据，不是人物形态质量评分。

眼睑 Multi 分支在新的分层保存流程下也重新跑一键、保存重开及重建，记录位于 `validation/results/face-eye-multi-lower-regression-20261001`。另外读取三个最终保存场景的原生 Skin 数组：普通和 16 控件场景的 1630 个顶点权重和误差最大为 2.22e-16；多层场景每层也归一，最大误差 9.75e-11。结果位于 `validation/results/face-lower-normalization-20261001.json`。

Maya 的部分 Jaw 权重设置仍产生锁定权重总量提示；构建未因此失败，最终生产变形、归零及权重归一检查通过。不能把这些记录称为无警告的全量验收。

## 剩余主项

完整上半脸 Brow／ForeHead 输入、真实 Tongue／Teeth、UpMidLo、NonSym／Cyclops、完整 Face 独立命名空间组合及官方角色视觉仍待验收。分层保存机制对未构建的 UpMidLoc，以及修改 Fit 后旧关节名称缺失时回到原版空间权重匹配的分支，只有代码接入证据。本批打通下半脸主链，不代表全量 ADV 源码复刻完成；Goal 保持活跃。
