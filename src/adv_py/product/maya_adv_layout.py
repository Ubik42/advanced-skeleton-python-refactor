"""AdvancedSkeleton-style navigation for the Python Maya implementation.

Original section order routes to the implemented Python business controls.
The reference MEL is not executed by navigation.
"""
from __future__ import annotations


ADV_SECTIONS = (
    ("Preparation", ("Model", "Rig", "Settings")),
    ("Body", ("Fit", "Edit", "Build", "Deform option1", "Deform option2",
              "Deform option3", "Deform option4", "Deform Shapers",
              "Deform DeltaMush", "Geometry Skeleton", "Geometry Muscular",
              "Geometry PolyBoxes", "Geometry Mannequin", "Geometry Skin Cut-Up",
              "Custom Controllers", "Squash Controller", "Motion System",
              "Control Curves", "Control Orient", "Control Mesh", "Game Engine",
              "Unreal Joints", "Partial Joints")),
    ("Face", ("Pre", "Fit", "Build", "Build ...", "Layers", "Tweaks", "DeltaMush",
              "HeadSquash", "WrinkleMap", "BlendShapes", "EditBlendShapes",
              "NewBlendShapes", "Custom Controllers")),
    ("Pose", ("Driving Systems", "Corrective Shapes", "Pose Functions")),
    ("Tools", ()), ("Display", ()), ("Optimize", ()), ("Updates", ()),
    ("Publish", ()), ("Export", ()), ("Demo", ()), ("About", ()),
)

# A row is (visible label, existing detail page, detail group title).
# Original headings stay in their original order; unsupported sections remain
# visibly inactive instead of implying that their MEL behavior was ported.
ADV_OPERATIONS = {
    ('Preparation', 'Settings'): (('GUI Colors', 0, '00 · Settings'),),
    ('Body', 'Deform option2'): (
        ('创建 Cage', 0, '00 · SkinCage'),
        ('删除 Cage', 0, '00 · SkinCage'),
        ('Left > Right', 0, '00 · SkinCage'),
        ('Right > Left', 0, '00 · SkinCage'),
        ('复制权重', 0, '00 · SkinCage'),
        ('"DeformationWidth"', 0, '00 · SkinCage'),
        ('Create Groin Locators', 0, '00 · SkinCage'),
        ('Adjust Groin area', 0, '00 · SkinCage'),
        ('Create Groin joint', 0, '00 · SkinCage'),
        ('Delete SkinCurves', 0, '00 · SkinCage'),
        ('Create Sliders', 0, '00 · SkinCage'),
        ('Delete Sliders', 0, '00 · SkinCage'),
        ('Print Commands', 0, '00 · SkinCage'),
    ),
    ('Body', 'Deform option3'): (
        ('Create Cage', 0, '00 · SubWrap'),
        ('Delete Cage', 0, '00 · SubWrap'),
        ('Wrap selected mesh', 0, '00 · SubWrap'),
        ('Detach', 0, '00 · SubWrap'),
        ('Attach', 0, '00 · SubWrap'),
        ('Exclude selected vertices', 0, '00 · SubWrap'),
    ),
    ('Body', 'Deform option4'): (
        ('创建 SkinLoop', 0, '00 · SkinLoops'),
        ('选择全部 SkinLoops', 0, '00 · SkinLoops'),
        ('绑定 SkinLoops', 0, '00 · SkinLoops'),
        ('复制 SkinLoop 权重', 0, '00 · SkinLoops'),
        ('创建 CutUp', 0, '00 · SkinLoops'),
        ('删除 CutUp', 0, '00 · SkinLoops'),
    ),
    ('Body', 'Deform Shapers'): (
        ('设置并加载插件', 0, '05 · Shapers'),
        ('创建 Shapers', 0, '05 · Shapers'),
        ('选择', 0, '05 · Shapers'),
        ('重新绑定', 0, '05 · Shapers'),
        ('删除', 0, '05 · Shapers'),
    ),
    ('Body', 'Geometry Skeleton'): (
        ('Create', 0, '00 · Skeleton'),
        ('Delete', 0, '00 · Skeleton'),
        ('Left>Right', 0, '00 · Skeleton'),
        ('Right>Left', 0, '00 · Skeleton'),
    ),
    ('Body', 'Geometry Muscular'): (
        ('Create', 0, '00 · Muscular'),
        ('Delete', 0, '00 · Muscular'),
    ),
    ('Body', 'Geometry PolyBoxes'): (
        ('Create', 0, '00 · PolyBoxes'),
        ('Delete', 0, '00 · PolyBoxes'),
        ('Left>Right', 0, '00 · PolyBoxes'),
        ('Right>Left', 0, '00 · PolyBoxes'),
        ('Boolean Create', 0, '00 · PolyBoxes'),
        ('Boolean Delete', 0, '00 · PolyBoxes'),
        ('Warp Create', 0, '00 · PolyBoxes'),
        ('Warp Delete', 0, '00 · PolyBoxes'),
        ('BoxSkin Create', 0, '00 · PolyBoxes'),
        ('BoxSkin Delete', 0, '00 · PolyBoxes'),
    ),
    ('Body', 'Geometry Mannequin'): (
        ('Create', 0, '00 · Mannequin'),
        ('Delete', 0, '00 · Mannequin'),
    ),
    ('Body', 'Geometry Skin Cut-Up'): (
        ('Create', 0, '00 · Skin Cut-Up'),
        ('Delete', 0, '00 · Skin Cut-Up'),
    ),
    ('Body', 'Control Mesh'): (
        ('创建 Control Mesh', 0, '10A · Control Mesh'),
        ('批量创建 Control Meshes', 0, '10A · Control Mesh'),
        ('着色并扩展 Control Meshes', 0, '10A · Control Mesh'),
        ('创建 IK Control Meshes', 0, '10A · Control Mesh'),
        ('删除所选 Control Meshes', 0, '10A · Control Mesh'),
        ('删除全部 Control Meshes', 0, '10A · Control Mesh'),
    ),
    ('Face', 'HeadSquash'): (
        ('创建 HeadSquash', 3, '03C · Face HeadSquash'),
        ('删除 HeadSquash', 3, '03C · Face HeadSquash'),
        ('优化 HeadSquash 影响范围', 3, '03C · Face HeadSquash'),
        ('加入所选对象', 3, '03C · Face HeadSquash'),
    ),
    ('Face', 'Layers'): (
        ('Normal', 3, '03a · Face Skin Layers'),
        ('刷新 SkinLayer 列表', 3, '03a · Face Skin Layers'),
    ),
    ('Face', 'Build ...'): (
        ('建立原版 Face 控制面板', 3, '03E · 原版 Face ctrlBox'),
        ('生成 Jaw 权重参考曲线', 3, '03D · Jaw 权重参考曲线'),
        ('原版 Face 首次准备', 3, '03O · 原版眼部绑定与修形'),
        ('按原版准备双侧 Fit', 3, '03O · 原版眼部绑定与修形'),
        ('建立原版 EyeBall 绑定', 3, '03O · 原版眼部绑定与修形'),
        ('建立原版 Pupil／Iris', 3, '03O · 原版眼部绑定与修形'),
        ('建立原版 EyeLid 绑定', 3, '03O · 原版眼部绑定与修形'),
        ('建立 Lip Ribbon 与控制驱动', 3, '03I · Lip 绑定'),
        ('建立 Lip Falloff 权重层', 3, '03G · Lip Falloff'),
        ('预览范围', 3, '03G · Lip Falloff'),
        ('更新范围与权重', 3, '03G · Lip Falloff'),
        ('Face Cage', 3, '03K · Face Cage'),
        ('Face 表情修形', 3, '03L · Face 表情修形'),
        ('更新 JawOpenLayer 嘴唇权重', 3, '03J · Jaw 绑定与修形'),
        ('Snarl 修形', 3, '03J · Jaw 绑定与修形'),
        ('完成 Snarl', 3, '03J · Jaw 绑定与修形'),
        ('建立 Tongue 控制链与蒙皮', 3, '03F · Tongue 绑定'),
        ('完成 Tongue，恢复模型显示', 3, '03F · Tongue 绑定'),
        ('建立第二控制盒区域投影', 3, '03H · Regions'),
        ('显示 Eye Aim 控制', 3, '03M · Eye Aim 与 UpMidLo'),
        ('建立 UpMidLo 控制与权重', 3, '03M · Eye Aim 与 UpMidLo'),
        ('建立音素驱动 Phonemes', 3, '03N · Phonemes 与 Emotions'),
        ('建立情绪驱动 Emotions', 3, '03N · Phonemes 与 Emotions'),
        ('记录所选 Extras 模型', 3, '03N · Phonemes 与 Emotions'),
        ('传递 Extras 权重', 3, '03N · Phonemes 与 Emotions'),
        ('完成 Face 关节绑定', 3, '03N · Phonemes 与 Emotions'),
    ),
    ("Preparation", "Model"): (
        ("创建 geo 模型组", 0, "00 · Model Clean"),
        ("Model Clean", 0, "00 · Model Clean"),
        ("检查选中模型", 0, "00 · 模型检查"),),
    ("Preparation", "Rig"): (
        ("新建绑定场景", 0, "00 · 绑定场景"),
        ("引用模型文件", 0, "00 · 绑定场景"),
        ("重新加载模型引用", 0, "00 · 绑定场景"),
        ("替换模型引用文件", 0, "00 · 绑定场景"),
        ("移除模型引用", 0, "00 · 绑定场景"),
        ("Skin", 0, "01 · 模型对象"),
        ("All", 0, "01 · 模型对象"),
        ("Right Eye", 0, "01 · 模型对象"),
        ("Left Eye", 0, "01 · 模型对象"),
        ("创建单关节道具绑定", 0, "02 · One Joint Prop"),
        ("FBX rig", 0, "02B · FBX rig"),
        ("读取 Body 构建选项", 0, "02A · Body 构建选项"),
        ("保存 Body 构建选项", 0, "02A · Body 构建选项")),
    ("Body", "Fit"): (
        ("导入原版 Fit 模板", 0, "01 · Fit 数据"),
        ("导入原版 Fit 部件", 0, "01 · Fit 数据"),
        ("导出原版 Fit／部件 .ma", 0, "01 · Fit 数据"),
        ("导出当前 Fit", 0, "01 · Fit 数据"),
        ("从文档导入", 0, "01 · Fit 数据"),
        ("缩放", 0, "01 · Fit 数据"),
        ("自动放置", 0, "01 · Fit 数据"),
        ("更新 PoleVector 显示", 0, "02 · Fit 编辑"),
        ("更新 Finger-up 显示", 0, "02 · Fit 编辑"),
        ("拉直腿部 PoleVector", 0, "02 · Fit 编辑"),
        ("拉直手臂 PoleVector", 0, "02 · Fit 编辑"),
        ("显示／隐藏关节朝向", 0, "02 · Fit 编辑"),
        ("显示／隐藏关节轴", 0, "02 · Fit 编辑"),
        ("吸附组件中心", 0, "02 · Fit 编辑"),
        ("复制位置", 0, "02 · Fit 编辑"),
        ("粘贴位置", 0, "02 · Fit 编辑"),
        ("锁定／解锁中心关节", 0, "02 · Fit 编辑"),
        ("FitMode", 0, "02 · Fit 编辑"),
        ("立即更新 Fit", 0, "02 · Fit 编辑")),
    ("Body", "Edit"): (
        ("添加 IK-Label", 0, "02 · Fit 编辑"),
        ("移除 IK-Label", 0, "02 · Fit 编辑"),
        ("更新 Fit 位置", 0, "02 · Fit 编辑"),
        ("更新 Fit 元数据", 0, "02 · Fit 编辑"),
        ("重新定向 Fit", 0, "02 · Fit 编辑"),
        ("创建 Fit SDK 属性", 0, "02 · Fit 编辑")),
    ("Body", "Build"): (
        ("构建并登记角色", 0, "03 · 完整角色"),
        ("迁移当前原版角色与蒙皮", 0, "原版角色迁移"),
        ("重建并保留数据", 0, "04 · 保留数据重建"),
        ("替换脊柱角色并保留数据", 0, "05 · 跨段数脊柱角色替换")),
    ("Body", "Deform option1"): (
        ("追加选择变形关节", 1, "00 · 原版 Skinning"),
        ("设置 Smooth Bind 选项", 1, "00 · 原版 Skinning"),
        ("绑定当前网格", 1, "01 · 建立 Skin"),
        ("导出网格与权重", 1, "03 · 跨场景源资产"),
        ("引用模型改拓扑后重绑并转移", 1, "04 · 跨拓扑权重转移")),
    ("Body", "Deform DeltaMush"): (
        ("硬化权重", 1, "05 · Delta Mush"),
        ("应用 Delta Mush", 1, "05 · Delta Mush"),
        ("Bake DeltaMush", 1, "05 · Delta Mush"),),
    ("Body", "Custom Controllers"): (
        ("SoftMod Tool", 0, "06 · 自定义控制器"),
        ("Create Skin Control", 0, "06 · 自定义控制器"),
        ("Create Cluster Control", 0, "06 · 自定义控制器"),
        ("Create SoftMod Control", 0, "06 · 自定义控制器"),
        ("Paint weights for selected Control", 0, "06 · 自定义控制器"),
        ("Mirror weights for selected Control", 0, "06 · 自定义控制器"),
        ("Add influenced object", 0, "06 · 自定义控制器"),
        ("Delete selected control", 0, "06 · 自定义控制器")),
    ("Body", "Squash Controller"): (
        ("创建 Squash Controller", 0, "07 · Squash Controller"),
        ("删除 Squash Controller", 0, "07 · Squash Controller")),
    ("Body", "Motion System"): (
        ("创建 HumanIK", 0, "08 · Motion System"),
        ("删除 HumanIK", 0, "08 · Motion System"),
        ("烘焙 HumanIK 到控制器", 0, "08 · Motion System")),
    ("Body", "Control Curves"): (
        ("缩放控制曲线", 0, "09 · Control Curves"),
        ("按 Skin 自动缩放", 0, "09 · Control Curves"),
        ("设置控制曲线颜色", 0, "09 · Control Curves"),
        ("镜像控制曲线形状", 0, "09 · Control Curves"),
        ("替换控制器图标", 0, "09 · Control Curves"),
        ("Copy to SubControls", 0, "09 · Control Curves"),
        ("Copy to ExtraControls", 0, "09 · Control Curves")),
    ("Body", "Control Orient"): (
        ("设置控制器局部轴", 0, "10 · Control Orient"),
        ("分离全部控制器", 0, "10 · Control Orient"),
        ("重新附着全部控制器", 0, "10 · Control Orient")),
    ("Body", "Game Engine"): (
        ("Root Motion Joint", 0, "10B · Game Engine"),
        ("Scale Behaviour", 0, "10B · Game Engine"),
        ("Custom oriented GameSkeleton", 0, "10B · Game Engine")),
    ("Body", "Unreal Joints"): (
        ("重命名为 Unreal 关节", 0, "11 · Unreal Joints"),
        ("恢复 ADV 关节名称", 0, "11 · Unreal Joints"),
        ("创建通用 Unreal IK 关节", 0, "11 · Unreal Joints"),
        ("删除通用 Unreal IK 关节", 0, "11 · Unreal Joints"),
        ("Mannequin 模板", 0, "11 · Unreal Joints"),
        ("模板文件", 0, "11 · Unreal Joints"),
        ("创建 Mannequin 骨架", 0, "11 · Unreal Joints"),
        ("转移蒙皮到 Mannequin", 0, "11 · Unreal Joints"),
        ("删除 Mannequin 骨架", 0, "11 · Unreal Joints"),
        ("启用 Unreal Twist 层级", 0, "11 · Unreal Joints"),
        ("恢复默认 Twist 层级", 0, "11 · Unreal Joints")),
    ("Body", "Partial Joints"): (
        ("包含控制器", 0, "12 · Partial Joints"),
        ("创建 Partial Joints", 0, "12 · Partial Joints"),
        ("删除 Partial Joints", 0, "12 · Partial Joints"),
        ("多段关节数", 0, "12 · Partial Joints"),
        ("自动加入现有蒙皮", 0, "12 · Partial Joints"),
        ("创建 Multi Partial Joints", 0, "12 · Partial Joints"),
        ("删除 Multi Partial Joints", 0, "12 · Partial Joints")),
    ("Face", "Pre"): (
        ("升级旧版 Face Fit", 3, "00 · 面部输入"),
        ("Mask", 3, "00 · 面部输入"),
        ("Face", 3, "00 · 面部输入"),
        ("All Head", 3, "00 · 面部输入"),
        ("编辑右侧", 3, "00 · 面部输入"),
        ("编辑左侧", 3, "00 · 面部输入"),
        ("关闭非对称", 3, "00 · 面部输入"),
        ("show both sides", 3, "00 · 面部输入"),
        ("Include", 3, "00 · 面部输入"),
        ("重选 Mask", 3, "00 · 面部输入"),
        ("重选 Face", 3, "00 · 面部输入"),
        ("重选 All Head", 3, "00 · 面部输入"),
        ('Choose Head Joint',3,'00 · 面部输入'),
        ('AutoFit',3,'00 · 面部输入'),
        ('Model Check',3,'00 · 面部输入'),
        ('Create',3,'00 · 面部输入'),
        ('import',3,'00 · 面部输入'),
        ('Update',3,'00 · 面部输入'),
        ("记录所选右眼", 3, "00 · 眼球输入与控制"),
        ("记录所选左眼", 3, "00 · 眼球输入与控制"),
        ("从标记生成目标", 3, "01 · 目标网格"),
        ("导出目标资产", 3, "02 · 可移植目标资产"),
        ("导入为目标网格", 3, "02 · 可移植目标资产")),
    ("Face", "Fit"): (
        ("建立 EyeBall Fit", 3, "01 · EyeBall Fit"),
        ("EyeLid Outer", 3, "02 · EyeLid Fit"),
        ("EyeLid Main", 3, "02 · EyeLid Fit"),
        ("EyeLid Inner", 3, "02 · EyeLid Fit"),
        ("重选 Outer", 3, "02 · EyeLid Fit"),
        ("重选 Main", 3, "02 · EyeLid Fit"),
        ("重选 Inner", 3, "02 · EyeLid Fit"),
        ("EyeLidMain2", 3, "02 · EyeLid Fit"),
        ("EyeLid assist", 3, "02 · EyeLid Fit"),
        ("Lip assist", 3, "03 · Lip Fit"),
        ("Face 定位点", 3, "04 · Face 定位点"),
        ("创建 UpMidLo 分区定位器", 3, "04 · Face 定位点"),
        ("创建 ForeHead 边界与区域 Fit", 3, "04 · Face 定位点"),
        ("记录所选 Tongue 网格或组件", 3, "05 · Tongue Fit"),
        ("创建 Tongue Fit", 3, "05 · Tongue Fit")),
    ("Face", "Build"): (
        ("检查 FaceSetup 输入", 3, "03 · 控制与变形器"),
        ("建立双侧眼睑关节与蒙皮", 3, "03 · 控制与变形器"),
        ("迁移同拓扑原版眼睑权重", 3, "03 · 控制与变形器"),
        ("读取眼睑修形", 3, "03 · 控制与变形器"),
        ("应用眼睑修形", 3, "03 · 控制与变形器"),
        ("构建面部控制", 3, "03 · 控制与变形器"),),
    ("Face", "DeltaMush"): (
        ("Create DeltaMush", 3, "03B · Face DeltaMush"),
        ("Delete DeltaMush", 3, "03B · Face DeltaMush"),
        ("Select eyeLidArea", 3, "03B · Face DeltaMush"),
        ("Select lipArea", 3, "03B · Face DeltaMush"),
        ("zero weight selected", 3, "03B · Face DeltaMush"),
        ("Paint DeltaMush", 3, "03B · Face DeltaMush")),
    ("Face", "Tweaks"): (
        ("Paint skin-weights", 3, "03A · Face Tweaks"),
        ("Hide Joints", 3, "03A · Face Tweaks"),
        ("Show Joints", 3, "03A · Face Tweaks"),
        ("select eyeBrowArea", 3, "03A · Face Tweaks"),
        ("select -d eyeBrowLine", 3, "03A · Face Tweaks"),
        ("select eyeLidArea", 3, "03A · Face Tweaks"),
        ("select -d eyeLidMain", 3, "03A · Face Tweaks"),
        ("select eyeLidOuter", 3, "03A · Face Tweaks"),
        ("select lipArea", 3, "03A · Face Tweaks"),
        ("select -d lipMain", 3, "03A · Face Tweaks"),
        ("select lipFalloffArea", 3, "03A · Face Tweaks"),
        ("WeightHammerVerts", 3, "03A · Face Tweaks")),
    ("Face", "BlendShapes"): (
        ("转换", 3, "03P · 原版驱动转 BlendShape"),
        ("连接 ARKit", 3, "03Q · ARKit 接线"),
        ("断开 ARKit", 3, "03Q · ARKit 接线"),
        ("应用面部动画", 3, "04 · 表情与口型动画"),
        ("登记资产版本", 3, "05 · 面部资产版本"),
        ("刷新版本", 3, "05 · 面部资产版本"),
        ("导出所选版本", 3, "05 · 面部资产版本"),
        ("合并资产版本", 3, "06 · 合并同一目标的三个版本")),
    ("Face", "WrinkleMap"): tuple((label,3,"03T · 原版 WrinkleMap") for label in (
        "创建／移除皱纹曲线","创建／移除 WrinkleMap","重新投影 Wrinkle UV","编辑皱纹",
        "应用并重新烘焙","取消皱纹编辑","读取 Wrinkle 设置","保存 Wrinkle 设置",
        "正常材质","查看凹凸","查看遮罩","查看凹凸文件")),
    ("Face", "EditBlendShapes"): (
        ("设置目标权重",3,"03R · 原版 BlendShape 编辑"),
        ("刷新 BlendShape 目标", 3, "03R · 原版 BlendShape 编辑"),
        ("提取 BlendShape 目标", 3, "03R · 原版 BlendShape 编辑"),
        ("重置编辑目标", 3, "03R · 原版 BlendShape 编辑"),
        ("完成并删除编辑目标", 3, "03R · 原版 BlendShape 编辑"),
        ("开始 BlendShape 向导", 3, "03R · 原版 BlendShape 编辑"),
        ("下一个 BlendShape 目标", 3, "03R · 原版 BlendShape 编辑"),
        ("停止 BlendShape 向导", 3, "03R · 原版 BlendShape 编辑"),
        ("提取所有 BlendShape 目标", 3, "03R · 原版 BlendShape 编辑"),
        ("DeltaMush 平滑所有目标", 3, "03R · 原版 BlendShape 编辑")),
    ("Face", "NewBlendShapes"): (
        ("新建 BlendShape 目标", 3, "03S · 原版新建 BlendShape"),),
    ("Face", "Custom Controllers"): (
        ("SoftMod Tool", 0, "07 · 自定义控制器"),
        ("Create Skin Control", 0, "07 · 自定义控制器"),
        ("Create Cluster Control", 0, "07 · 自定义控制器"),
        ("Create SoftMod Control", 0, "07 · 自定义控制器"),
        ("Paint weights for selected Control", 0, "07 · 自定义控制器"),
        ("Mirror weights for selected Control", 0, "07 · 自定义控制器"),
        ("Add influenced object", 0, "07 · 自定义控制器"),
        ("Delete selected control", 0, "07 · 自定义控制器")),
    ("Pose", "Driving Systems"): (
        ("启用四肢动画", 2, "03 · 动画通道"),
        ("启用拉伸匹配", 2, "03 · 动画通道"),
        ("启用可变脊柱", 2, "03 · 动画通道"),
        ("启用空间动画", 2, "03 · 动画通道"),
        ("升级旧 Spline FKIK", 2, "03 · 动画通道"),
        ("转换四肢模式", 2, "04 · 区间模式转换"),
        ("转换脊柱模式", 2, "04 · 区间模式转换"),
        ("在指定帧切换空间", 2, "05 · 控制空间事件"),
        ("创建 Driving System",2,"08 · 原版 Driving Systems"),
        ("自动查找并编辑驱动",2,"08 · 原版 Driving Systems"),
        ("编辑所选驱动属性",2,"08 · 原版 Driving Systems"),
        ("删除所选驱动属性",2,"08 · 原版 Driving Systems"),
        ("应用 Driving System 编辑",2,"08 · 原版 Driving Systems"),
        ("取消 Driving System 编辑",2,"08 · 原版 Driving Systems"),
        ("优化驱动控制器位置",2,"08 · 原版 Driving Systems"),
        ("升级旧 SDK 曲线",2,"08 · 原版 Driving Systems"),
        ("刷新原版驱动属性",2,"08 · 原版 Driving Systems"),
        ("查看驱动 SDK 曲线",2,"08 · 原版 Driving Systems"),
        ("更新驱动软范围",2,"08 · 原版 Driving Systems"),
        ("镜像右侧 SDK 到左侧",2,"08 · 原版 Driving Systems"),
        ("记录所选驱动通道",2,"08 · 原版 Driving Systems"),
        ("记录所选被驱动通道",2,"08 · 原版 Driving Systems"),
        ("建立原版 SDK 控制层",2,"08 · 原版 Driving Systems"),
        ("写入原版 SDK 键",2,"08 · 原版 Driving Systems"),
        ("静音所选 SDK",2,"08 · 原版 Driving Systems"),
        ("恢复 SDK 驱动",2,"08 · 原版 Driving Systems"),
        ("退出驱动预览",2,"08 · 原版 Driving Systems")),
    ("Pose", "Corrective Shapes"): tuple((label,2,"07 · 原版 Corrective Shapes") for label in (
        "创建 Corrective 形状","Corrective SoftMod 工具","编辑 Corrective","删除 Corrective","Corrective 曲线",
        "应用 Corrective","取消 Corrective","刷新 Corrective 目标","记录 Corrective 烘焙来源",
        "记录 Corrective 烘焙目标","烘焙到 Corrective","批量编辑全部 Corrective",
        "记录曲线变形网格","记录曲线变形控制器","隐藏曲线变形来源","创建变形曲线","解除曲线绑定","重新绑定曲线",
        "创建曲线测试动画","创建局部变形网格","显示原始网格","显示变形网格","烘焙曲线变形为 Corrective","清理曲线变形设置")),
    ("Pose", "Pose Functions"): (
        ("刷新原版保存姿态",2,"09 · 原版 Pose Functions"),
        ("保存原版命名姿态",2,"09 · 原版 Pose Functions"),
        ("应用原版命名姿态",2,"09 · 原版 Pose Functions"),
        ("删除原版命名姿态",2,"09 · 原版 Pose Functions"),
        ("所选通道加入原版构建姿态",2,"09 · 原版 Pose Functions"),
        ("返回原版构建姿态",2,"09 · 原版 Pose Functions"),
        ("禁用原版自定义朝向",2,"09 · 原版 Pose Functions"),
        ("启用原版自定义朝向",2,"09 · 原版 Pose Functions"),
        ("捕获姿态", 2, "01 · 当前姿态"),
        ("应用姿态", 2, "01 · 当前姿态"),
        ("返回构建姿态", 2, "01 · 当前姿态"),
        ("设置构建姿态", 2, "01 · 当前姿态"),
        ("捕获动画", 2, "02 · 全身动画"),
        ("应用动画", 2, "02 · 全身动画"),
        ("当前帧完整写键", 2, "02 · 全身动画"),
        ("检查兼容性", 2, "06 · 角色预设"),
        ("应用所选预设", 2, "06 · 角色预设")),
    ("Tools", None): (
        ("PoserDesigner", 4, "04 · PoserDesigner"),
        ("NameMatcher", 0, "02 · NameMatcher"),
        ("MoCapMatcher", 4, "03 · MoCapMatcher"),
        ("导入并写入控制", 4, "01 · 外部 FBX 驱动角色"),),
    ("Display", None): (
        ("MotionSystem 显示", 6, "00 · Display"),
        ("关节显示", 6, "00 · Display"),
        ("关节轴显示", 6, "00 · Display"),
        ("关节尺寸", 6, "00 · Display")),
    ("Optimize", None): (
        ("Delete Unused Nodes", 7, "00 · Optimize"),
        ("Remove Unused Influences", 7, "00 · Optimize"),
        ("Remove Unused Attributes", 7, "00 · Optimize"),
        ("Prune Small Weights", 7, "00 · Optimize"),
        ("Delete saved UIs", 7, "00 · Optimize"),
        ("Delete Unused joints", 7, "00 · Optimize"),
        ("Tag All Controllers", 7, "00 · Optimize"),
        ("Reduce EyeLid joints to 4", 7, "00 · Optimize"),
        ("Reduce EyeLid joints to 8", 7, "00 · Optimize"),
        ("Reduce Lip joints to 14", 7, "00 · Optimize"),
        ("Custom Reduce", 7, "00 · Optimize")),
    ("Updates", None): (
        ("Green-fix", 7, "00 · Updates"),
        ("NaN-fix", 7, "00 · Updates"),
        ("Face Fitting Update", 7, "00 · Updates")),
    ("Publish", None): (
        ('Set DisplayLayers to "R"', 5, '00 · Publish'),
        ('Set Joints to hidden', 5, '00 · Publish'),
        ('Go to Build Pose', 5, '00 · Publish'),
        ("Publish", 5, "00 · Publish"),
        ("导出独立 Maya 场景", 5, "01 · 导出迁移后的完整角色"),
        ("准备并烘焙发布骨架", 5, "02 · 烘焙并发布独立骨架")),
    ("Export", None): (
        ("Delete Unused Endjoints", 5, "00 · Export"),
        ("Delete Static channels", 5, "00 · Export"),
        ("Rebuild dagPose nodes", 5, "00 · Export"),
        ("Roblox Dynamic Head", 5, "00 · Export"),
        ("FBX export", 5, "00 · Export"),
        ("Mannequin export", 5, "00 · Export"),
        ("BodyRig export", 5, "00 · Export"),
        ("FaceRig export", 5, "00 · Export")),
}


def create_adv_panel(controller=None):
    """Legacy navigation facade retained for historical validation scripts.

    The public Maya launcher uses maya_panel.create_panel directly.
    """
    from PySide2 import QtCore, QtWidgets
    from .maya_panel import create_panel

    class Accordion(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName("AdvPyAccordion")
            self.setWindowTitle("AdvancedSkeleton Python")
            self.resize(425, 750)
            self.setMinimumWidth(330)
            self.detail = None
            self.controller = controller
            self.section_buttons = {}
            self.operation_buttons = {}
            self.setStyleSheet("""
                QWidget#AdvPyAccordion { background: #424242; color: #dddddd;
                    font-family: 'Microsoft YaHei UI', 'Arial'; font-size: 13px; }
                QWidget#AdvAccordionBody { background: #424242; color: #dddddd; }
                QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport {
                    background: #424242; border: 0; }
                QPushButton[sectionHeader="true"] { background: #606060;
                    color: #dddddd; border: 0;
                    text-align: left; font-size: 15px; font-weight: 600;
                    padding: 5px 12px; min-height: 22px; }
                QPushButton[sectionHeader="true"]:hover { background: #707070; }
                QPushButton[sectionHeader="true"]:checked { background: #666666; }
                QPushButton { background: #606060; color: #eeeeee; border: 0;
                    min-height: 27px; padding: 3px 8px; text-align: center; }
                QPushButton:hover { background: #777777; }
                QPushButton:disabled { color: #aaaaaa; background: #515151; }
                QLabel#Inactive { color: #aaaaaa; padding: 5px 9px; }
            """)
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(3, 3, 3, 3)
            outer.setSpacing(0)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            outer.addWidget(scroll)
            body = QtWidgets.QWidget()
            body.setObjectName("AdvAccordionBody")
            scroll.setWidget(body)
            self.stack = QtWidgets.QVBoxLayout(body)
            self.stack.setContentsMargins(0, 0, 0, 0)
            self.stack.setSpacing(2)
            for section, subsections in ADV_SECTIONS:
                if subsections:
                    self._add_section(section, subsections)
                else:
                    self._add_leaf(section, None, self.stack, indent=0)
            self.stack.addStretch(1)

        def _toggle(self, button, content):
            button.setCheckable(True)
            title = button.text()
            button.setText(">  " + title)
            button.toggled.connect(content.setVisible)
            button.toggled.connect(lambda checked: button.setText(
                ("v  " if checked else ">  ") + title))
            content.hide()

        def _add_section(self, section, subsections):
            header = QtWidgets.QPushButton()
            header.setText(section)
            header.setProperty("sectionHeader", True)
            header.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
            header.setObjectName("AdvSection_" + section)
            self.stack.addWidget(header)
            content = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(16, 1, 16, 1)
            layout.setSpacing(2)
            self.stack.addWidget(content)
            self._toggle(header, content)
            self.section_buttons[(section, None)] = header
            for subsection in subsections:
                self._add_leaf(section, subsection, layout, indent=1)

        def _add_leaf(self, section, subsection, layout, *, indent):
            title = subsection or section
            entries = ADV_OPERATIONS.get((section, subsection), ())
            header = QtWidgets.QPushButton()
            header.setText(title)
            header.setProperty("sectionHeader", True)
            header.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
            header.setObjectName("AdvSection_" + section + "_" + (subsection or "root"))
            layout.addWidget(header)
            content = QtWidgets.QWidget()
            row = QtWidgets.QVBoxLayout(content)
            row.setContentsMargins(24 if indent else 38, 3, 18, 7)
            row.setSpacing(3)
            layout.addWidget(content)
            self._toggle(header, content)
            self.section_buttons[(section, subsection)] = header
            if entries:
                for label, tab, group in entries:
                    button = QtWidgets.QPushButton(label)
                    button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                         QtWidgets.QSizePolicy.Fixed)
                    button.clicked.connect(lambda _checked=False, t=tab, g=group,
                                           s=section, sub=subsection:
                                           self.open_detail(t, g, s, sub))
                    row.addWidget(button)
                    self.operation_buttons[(section, subsection, label)] = button
            else:
                unavailable = QtWidgets.QLabel("尚未实现", objectName="Inactive")
                row.addWidget(unavailable)

        def open_detail(self, tab, group, section, subsection):
            from shiboken2 import isValid
            if self.detail is None or not isValid(self.detail):
                self.detail = create_panel(self.controller)
                self.detail.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
                try:
                    from adv_py.adapters.maya_panel_window import attach_to_maya_window
                    attach_to_maya_window(self.detail)
                except (ImportError, RuntimeError):
                    pass
            # Detail now uses source-ordered accordion sections. Tab indices
            # from the former panel are retained only as external route data.
            self.detail.open_original_section(group, section, subsection)
            self.detail.raise_()
            self.detail.activateWindow()

    return Accordion()
