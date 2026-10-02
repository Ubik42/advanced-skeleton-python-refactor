# SDK 主构建与重建源码接入：当前离线状态

2026-10-02，本批未启动 Maya，不推送 GitHub。结论是代码接入，不是 Maya 整链验收通过。

只读依据为 `local/adv_6_925/AdvancedSkeleton.mel`，ADV 6.925。SHA256 为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`，本批未修改原文件。

## 本批接入

- 原版 Body 结束时的 DrivingSystem 恢复（85650–85773）：按原嵌套深度排序且保留相同深度的发现顺序；原生 duplicate 复制完整 SDK 曲线；恢复 min/max/soft 范围、输出 blendWeighted 及 buildPose。保留 MEL tokenize 跳过空项、单数字 input 索引和多数字后缀被剥空后警告继续的原规则。
- 驱动与被驱动对象均通过实际 FK／IK／Pole／FKIK 角色寻址。Fit 保存的原名不会因为 Python 控制器名称不同而误建新的驱动控制器；Fit 原属性名和稀疏数组索引保留。
- SDK 插层后的登记、图记录、构建姿态和返回计划通过原 UUID 更新路径；传统缩放模式保留原版 ScaleMPD 对第一条输出边的替换规则。
- 暂存重建先恢复 DrivingSystem 控制器，再插入原 SDK 层并恢复驱动定义、曲线及 Fit 数组。原版 QRotate、OPM-compatible 和组合驱动的节点类型、矩阵常量、数值参数、UD 属性及内部接线显式复制。未识别网络、缺少新 Body 端点或已有不同输入会停止暂存，不能静默把派生驱动变成普通数值。原角色的所有权和数据对照继续保留。
- 派生输出比较属性定义，不向已连接输出写入当前采样值；相同已存在属性的已捕获用户连接仍进入交接。DrivingSystem 的可动画自定义属性加入登记，派生或不可写输出不当作新的自由动画通道。
- AllSet 支持原版辅助过程先登记部分新节点、最后补全本次构建差集的顺序；SDK 后新增曲线和转换节点也进入最终登记。已有无关成员仍拒绝混入。
- RP 公共 FKIKBlend、FKVis／IKVis／autoVis、原版反向权重与显示链接入 0–10 模式。匹配使用原 FK、FKX、AlignIKTo、MainScaleMultiplyDivide 和原 Pole 采样步骤。QToes 反向滚动取 Roll 层下实际 descendant handle、末端 FK 控制器及世界 Euler；临时节点按 UUID 清理。Switch 按实际 IK 子控制器的 Roll→FK 对应关系打键，保留原两次切换、前一帧和选区末端关键帧规则。
- 本地同批还包含此前未提交的 SkinCage／SkinLoops／Optimize／Partial／SubWrap／CustomController、Fit 属性与轴、Face 原版节点和曲线处理等源码移植；本报告不为这些改动提供新的 Maya 通过结论。

## 离线证据

对照基线是提交 `755b794411d3c7377b64b0769f6301bcc97ba74e`。用同一 Python 运行时、UTF-8 环境和各自完整 tests 目录运行，基线取 Git archive 临时目录，未建立额外 Git 工作树。完整结果保存在 [离线对照 JSON](offline-source-port-baseline-2026-10-02.json)。以最终 JSON 的数量和新增失败列表为准。

新增检查覆盖源曲线文本、原轴和控制器角色、RP 模式、SDK 路径／缩放记录、嵌套 Fit 名称、派生属性与外部用户接线、实际 handle／FK／Euler 调用及临时节点异常清理、命名空间参数和部分 AllSet 登记。它们使用纯 Python 或命令记录接口，没有运行 Maya。

全套离线检查存在提交前已经有的失败和错误，不是全绿；同名失败集合对照只能说明本批没有增加这些离线失败，不能证明未覆盖的 Maya 行为等价。

## 剩余边界

当前 SDK 代码尚无新的 OPM／非 OPM 完整构建、保存重开、保留动画与 Skin 的重建、单次撤销重做证据。复杂嵌套、额外用户网络及 SDK 与 Spline 数量修改的组合也未做 Maya 验收。原版 CustomOrient、Reverse、Mirror、Detach／Attach 运行路径与重建交接现已接入 Python，旧 rotateAxis 写入路径已删除；旧场景迁移及完整 SDK 组合仍未真实验收，不能称控制器朝向功能已完全复刻。详见 [朝向源码接入记录](source-control-orient-current-offline.md)。

历史 Body 70／71 的左臂 IK 差异、完整 AutoPlace 默认资产与手指链、Face Mixed 完整撤销、Horse／Cat、FaceJoint 下颌、非标准轴及其余覆盖项继续保留。公共 RP 模式和匹配变化后，旧 Body 通过报告不能当作当前代码通过证据。Maya 复刻未确认，性能／架构优化及 Blender 迁移尚未开始，Goal 不标完成。
