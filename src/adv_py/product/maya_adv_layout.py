"""AdvancedSkeleton-style navigation for the Python Maya implementation.

Only the navigation hierarchy is mirrored.  The reference MEL and assets are
not imported into, or distributed with, this implementation.
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
    ("Face", ("Pre", "Fit", "Build", "Build ...", "Tweaks", "DeltaMush",
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
    ("Body", "Fit"): (
        ("导出当前 Fit", 0, "01 · Fit 数据"),
        ("从文档导入", 0, "01 · Fit 数据")),
    ("Body", "Edit"): (
        ("更新 Fit 位置", 0, "02 · Fit 编辑"),
        ("更新 Fit 元数据", 0, "02 · Fit 编辑"),
        ("重新定向 Fit", 0, "02 · Fit 编辑")),
    ("Body", "Build"): (
        ("构建并登记角色", 0, "03 · 完整角色"),
        ("重建并保留数据", 0, "04 · 保留数据重建"),
        ("替换脊柱角色并保留数据", 0, "05 · 跨段数脊柱角色替换")),
    ("Body", "Deform option1"): (
        ("绑定当前网格", 1, "01 · 建立 Skin"),),
    ("Body", "Deform option2"): (
        ("导出全部权重", 1, "02 · 权重文档"),
        ("导入并复核权重", 1, "02 · 权重文档")),
    ("Body", "Deform option3"): (
        ("导出网格与权重", 1, "03 · 跨场景源资产"),
        ("预检并转移权重", 1, "04 · 跨拓扑权重转移")),
    ("Body", "Control Curves"): (
        ("缩放控制曲线", 0, "06 · Control Curves"),
        ("按 Skin 自动缩放", 0, "06 · Control Curves"),
        ("设置控制曲线颜色", 0, "06 · Control Curves"),
        ("镜像控制曲线形状", 0, "06 · Control Curves")),
    ("Face", "Pre"): (
        ("从标记生成目标", 3, "01 · 目标网格"),
        ("导出目标资产", 3, "02 · 可移植目标资产"),
        ("导入为目标网格", 3, "02 · 可移植目标资产")),
    ("Face", "Build"): (
        ("构建面部控制", 3, "03 · 控制与变形器"),),
    ("Face", "BlendShapes"): (
        ("应用面部动画", 3, "04 · 表情与口型动画"),
        ("登记资产版本", 3, "05 · 面部资产版本"),
        ("刷新版本", 3, "05 · 面部资产版本"),
        ("导出所选版本", 3, "05 · 面部资产版本"),
        ("合并资产版本", 3, "06 · 合并同一目标的三个版本")),
    ("Pose", "Driving Systems"): (
        ("启用四肢动画", 2, "03 · 动画通道"),
        ("启用拉伸匹配", 2, "03 · 动画通道"),
        ("启用可变脊柱", 2, "03 · 动画通道"),
        ("启用空间动画", 2, "03 · 动画通道"),
        ("转换四肢模式", 2, "04 · 区间模式转换"),
        ("转换脊柱模式", 2, "04 · 区间模式转换"),
        ("在指定帧切换空间", 2, "05 · 控制空间事件")),
    ("Pose", "Pose Functions"): (
        ("捕获姿态", 2, "01 · 当前姿态"),
        ("应用姿态", 2, "01 · 当前姿态"),
        ("捕获动画", 2, "02 · 全身动画"),
        ("应用动画", 2, "02 · 全身动画"),
        ("当前帧完整写键", 2, "02 · 全身动画"),
        ("检查兼容性", 2, "06 · 角色预设"),
        ("应用所选预设", 2, "06 · 角色预设")),
    ("Tools", None): (
        ("导入并写入控制", 4, "01 · 外部 FBX 驱动角色"),),
    ("Publish", None): (
        ("准备并烘焙发布骨架", 5, "01 · 烘焙并发布独立骨架"),),
    ("Export", None): (
        ("发布 FBX", 5, "01 · 烘焙并发布独立骨架"),),
}


def create_adv_panel(controller=None):
    """Create the narrow, accordion-based entry panel inside a Qt session."""
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
                self.detail.tabs.tabBar().hide()
            self.detail.tabs.setCurrentIndex(tab)
            self.detail.setWindowTitle("AdvancedSkeleton Python / " + section +
                                       (" / " + subsection if subsection else ""))
            self.detail.findChild(QtWidgets.QLabel, "Title").setText(
                section + (" / " + subsection if subsection else ""))
            self.detail.findChild(QtWidgets.QLabel, "Subtitle").setText(
                "Python 操作参数")
            page = self.detail.tabs.widget(tab)
            for widget in page.findChildren(QtWidgets.QGroupBox):
                selected = widget.title() == group
                widget.setVisible(selected)
                if selected:
                    page.ensureWidgetVisible(widget, 10, 12)
            self.detail.show()
            self.detail.raise_()
            self.detail.activateWindow()

    return Accordion()
