# Control Orient 与 Custom Orient Joints 源码接入记录

2026-10-02：本批没有启动 Maya，也没有推送 GitHub。所有结论限于代码接入与离线检查。

只读来源为 ADV 6.925 的 local/adv_6_925/AdvancedSkeleton.mel，SHA256：828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02。原文件未修改。

已接入的原版行为：

- Control Orient（5684 起）：原角色判定、Extra／Offset／Sub、CustomOrient 与 Reverse 插层、曲线位置保持、世界朝向与轴匹配、镜像行为及平移标志、原输入边替换与恢复命令。
- Detach／Attach（6212–6455）：移动真实控制器到原 MatrixHolder，保存父级与 UUID，按原 TRS 差异阈值重新插层；SDK 子层、登记成员和原图记录随路径变化更新。
- Mirror（12345–12630）：原排序、重复 Spine 分支、局部通道符号和世界反射采样。asInfoFromCtrl（25910）与 RlaChild（26125）的源分支另行复用。
- 构建姿态确认（55487）：原 OPM／非 OPM 检查和原版继续／返回姿态／取消流程。
- Custom Orient Joints（62359–62519）：创建、删除、局部轴显示、连接、断开、Skin 转移，接入 Game Engine 面板；六组 XYZ 旋转分支按源码保留，Z/X 保留两次旋转顺序。
- 重建先恢复原 Control Orient，再恢复 SDK；旧 rotateAxis 直接覆盖、校准 multiplyDivide 补偿与代理预览运行模块已删除。

离线对照以提交 755b794411d3c7377b64b0769f6301bcc97ba74e 为基线：916 个 Python 文件语法检查通过，核心模块导入通过。完整离线检查由基线 472 项变为 528 项，新增 56 项；两边均有 10 个失败、125 个错误，新增失败／错误集合为空。全套并非全绿，不能把这些结果当作 Maya 通过证据。完整数据见 [离线对照 JSON](offline-source-port-baseline-2026-10-02.json)。

尚未验收：真实原生约束、OPM／非 OPM、复杂 SDK 与 Spline 组合、旧 rotateAxis 场景迁移、保存重开、Skin 与动画保留重建、撤销重做。GameSkeleton 导出和 Skin 转移对 CharacterRegistry 的完整交接仍须核对。不能宣布整个 Python 复刻完成，也不能提前宣布优化或 Blender 迁移完成。

Maya 清理后当前进程数为零；恢复真实测试必须单实例串行，确认进程退出后才能启动下一次。
