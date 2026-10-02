# Fit 自动缩放与原生 RP Effector：2026-10-02 Maya 验收

本批以只读 ADV 6.925 MEL 的 `asFitAutoScale`／`asFitAutoPlace` 缩放阶段（51761–52019）、`asFitDeleteGuides` 的 SoftMod 清理（53484–53517）和原生 IK Handle／Effector 创建（80802–80806）为依据。源码 SHA256 保持 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

## 已贯通的行为

- 从 Body Pre 的 Skin／All／Right Eye 记录进入 Body Fit 的“缩放”按钮；每件 Skin 先运行原版顺序的模型检查，跳过对称检查，交互取消在 Fit 写入前结束。
- 按 Skin 合并模型的 boundingBoxMaxY 与 Fit 最大关节世界 Y 计算倍率；保留原版 Fit.sy 因子和 0.1 下限。先捕获全部位置再按父到子写回，更新 fat、容器曲线 CV 和 jointDisplayScale，重置 Fit.scale。
- 对象或多边形组件眼球转换临时几何，读取中心枢轴与深度半径，写 Eye 世界位置和 EyeEnd.translateX。
- 按原版 BlendShape→Wrap 流程反解 SoftMod 对 Fit 点的变形，移除临时几何和 SoftMods，恢复 Skin／All／Root 可见性与选择。生产代码只使用 Maya 自带 Wrap 命令，不调用 ADV MEL。
- 独立角色命名空间可读取外部 Skin／All／眼球组件；外部模型的可见性和其实际历史 SoftMods 被显式处理，其他生成节点仍遵循角色范围。临时副本使用唯一名称，避免同名 DAG 路径歧义。
- 来源 RP IK Handle 创建继承原版 numSpans=2、确定 Effector 名称、Fit 末端旋转顺序、Handle／Effector 隐藏锁定。登记审核检查 Effector 身份、连接、旋转顺序与锁定；重建捕获版本策略，旧角色不强制改名。

## 真实 Maya 结果

`validation/results/fit-auto-scale-source-parity/parity.json`：图形 Maya 中执行未经修改的原版 `asFitAutoScale`，对相同输入执行 Python，六类均 passed。

| 输入 | 49 个 Fit 关节世界矩阵最大差异 | fat／图标／全局关节显示差异 |
| --- | --- | --- |
| 普通 Skin | 0 | 0 |
| 已缩放 Fit | 0 | 0 |
| 多个 Skin | 0 | 0 |
| 对象眼球 | 0 | 0 |
| 顶点组件眼球 | 0 | 0 |
| SoftMod 模型 | 4.94665641781467e-9 | 0 |

六类各自的选择保持、Root／模型可见性、容器缩放、临时节点清理和撤销重做通过；异常回滚与保存重开通过。原版 SoftMod 构建历史确认框在受控测试场景选择 Continue Anyway，未改原版检查代码。

`validation/results/fit-auto-scale-current/auto-scale.json`：六类生产生命周期通过；无效模型／越界眼球组件拒绝及回滚通过；命名空间角色读取外部 Skin、多个 Skin、组件眼球、SoftMod、撤销重做和保存重开通过。

`validation/results/biped-source-native-effector-v1-nonopm.log`：完整 biped／四组 Spline／Bendy 创建、Skin、姿态与动画往返、保存重开、FBX、保留 Skin／原生动画的重建及撤销重做通过。

`validation/results/original-source-native-effector-v1-nonopm-pose.json`：108 Body／Part × 71 组严格原版对照仍为 70／71。唯一 left_arm_ik 最大差异 `0.00014226000311484688`，阈值仍为 `0.0001`。Effector 规则补齐没有消除该误差，不宣称 71／71。本批未重跑 OPM 全链；前批 OPM 70／71 记录不变。

## 尚未完成

完整 AutoPlace 的身体／手指扫描、投影与引导编辑还未实现；已有 AutoPlacing 编辑会话的撤销直指、肩／肘还原和完整 DeleteGuides 分支仍待移植，当前缩放入口明确拒绝该会话。Left Eye 不参与原版 AutoScale 的缩放返回阶段，本批未扩展其行为。六类缩放验收不等于完整 AutoPlace 或全部 ADV 已完成。

下一批以完整 Fit AutoPlace／DeleteGuides 连续移植为主，保留左臂 RP 的严格差异记录，继续覆盖矩阵其余源码分支。Goal 保持活跃；仅本地提交，不推送 GitHub。
