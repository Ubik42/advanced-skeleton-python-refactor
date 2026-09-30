# 旧 Fit、BlendShape 编辑与 WrinkleMap 静态检查

2026-09-30。本批只读取和解析 Python 代码及原版只读 MEL，没有运行 Maya，没有调用新写的构建／编辑／烘焙函数，没有运行测试套件，也没有推送 GitHub。

750 个 Python 文件通过语法解析；189 个 Maya 适配类的 C3 继承顺序可解；新增 Face 宿主 self 调用和显式关键字参数均能在组合宿主解析。新增场景命令已声明角色命名空间边界；本地包导入路径存在。Face 的 WrinkleMap、EditBlendShapes 和 NewBlendShapes 操作映射到第 3 号 Face 详情页，按钮标签与实际组一致。git diff --check 通过。

这些检查只能确认代码的静态接入。真实网格、SDK 权重写入、Wrap、UV lattice context、surfaceSampler、MImage 的 png／tga 输出和材质查看等仍须最后集中进行 Maya 验收。不能把本记录当作原版行为等价或完整复刻完成的证据。
