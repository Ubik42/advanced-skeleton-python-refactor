"""Chinese in-Maya workspace for the verified character application flows."""
from __future__ import annotations

from pathlib import Path

from .maya_panel_controller import MayaPanelController


_OPEN_PANELS = []

_HELP_PAGES = {
    '00 · Model Clean': 'asPreModelCleaner.html',
    '00 · 模型检查': 'asPreModelChecker.html',
    '02 · One Joint Prop': 'asOneJointProp.html',
    '02B · FBX rig': 'asFBXRig.html',
    '02 · NameMatcher': 'asNameMatcher.html',
    '01 · Fit 数据': 'asFitSkeletons.html',
    '02 · Fit 编辑': 'asFitAttributes.html',
}


def format_face_eye_lid_build_result(result: dict) -> str:
    mode = "简化眼睑；" if result.get("simpler_eyelid") else ""
    mirrored = ("；已从右侧 Fit 自动镜像左侧"
                if result.get("symmetric_mirror") else "")
    depth_changes = [f"{label} {result['eye_depth_alignment'][side]['applied_cm']:.3f} cm"
                     for side, label in (("Right", "右"), ("Left", "左"))
                     if result["eye_depth_alignment"][side]["applied_cm"] > 0]
    aligned = ("；眼球深度已自动校准：" + "、".join(depth_changes)
               if depth_changes else "")
    failed = [(label, result["eye_depth_alignment"][side])
              for side, label in (("Right", "右眼"), ("Left", "左眼"))
              if result["eye_depth_alignment"][side]["status"] not in
              ("aligned", "already_closed", "stationary_aperture")]
    reasons = {
        "missing_front_surface": "闭眼时缺少遮挡眼球的前表面",
        "calibration_rejected": "校准会破坏张眼可见性",
        "eye_joint_unavailable": "眼球关节不可调整",
        "insufficient_open_visibility": "张眼可见范围不足",
    }
    warning = ("；眼区验收未通过：" + "、".join(
        f"{label}闭眼仍有{detail.get('final_closed_visible', 0)}个采样点可见眼球"
        + (f"（所需深度{detail['required_cm']:.3f} cm，"
           f"上限{detail['depth_limit_cm']:.3f} cm）"
           if detail["status"] == "depth_limit_exceeded" else
           f"（{reasons.get(detail['status'], '深度校准未完成')}）")
        for label, detail in failed)
        + "；需修正眼区模型或 Fit 后重新验收"
        if failed else "")
    return (f"双侧眼睑控制已建立：{mode}{len(result['controls'])} 个控制器、"
            f"{len(result['eye_controls'])} 个眨眼主控、"
            f"{len(result['joints'])} 个分段关节；"
            + f"右侧区域 {result['area_vertices']['Right']} 顶点，"
            + f"左侧区域 {result['area_vertices']['Left']} 顶点"
            + mirrored + aligned + warning + "。")


def create_panel(controller: MayaPanelController | None = None):
    """Create a panel inside an existing Maya Qt application; do not show it."""
    from PySide2 import QtCore, QtGui, QtWidgets

    if QtWidgets.QApplication.instance() is None:
        raise RuntimeError("请在 Maya 图形会话中创建角色工作台")

    class CharacterPanel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.controller = controller or MayaPanelController()
            self.setObjectName("AdvPyCharacterPanel")
            self.setWindowTitle("AdvancedSkeleton Python")
            self.setMinimumSize(330, 420)
            self.resize(425, 750)
            self._busy = False
            self._help_buttons = []
            self._help_hidden = self.controller.hide_help_buttons()
            self._build_ui()
            self._base_style = self.styleSheet()
            self._apply_panel_palette(self.controller.panel_palette())
            self.refresh_characters()
            self._refresh_face_fit_checks()

        def _build_ui(self):
            # The original tool is one vertical frame-layout panel. Keep the
            # existing business widgets in that panel instead of a navigation
            # window opening a second workbench.
            self.setStyleSheet("""
                QWidget#AdvPyCharacterPanel { background: #4C4C66;
                    font-family: 'Microsoft YaHei UI'; font-size: 12px; }
                QWidget#PageContent, QWidget#qt_scrollarea_viewport {
                    background: #4C4C66; }
                QScrollArea { border: none; }
                QToolButton#AdvPyCategory { background: #663333; color: white;
                    text-align: left; padding: 4px; }
                QToolButton#AdvPySection { background: #4C664C; color: white;
                    text-align: left; padding: 4px; }
                QPushButton { background: #597373; color: white;
                    min-height: 20px; padding: 3px 6px; }
                QComboBox { background: #1F4C52; color: white; }
                QGroupBox { color: white; border: 1px solid #757589;
                    margin-top: 12px; padding-top: 8px; }
                QGroupBox::title { subcontrol-origin: margin; left: 6px; }
                QLabel, QCheckBox { color: white; }
            """)
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(6, 6, 6, 6)
            outer.setSpacing(5)
            self.roles = QtWidgets.QListWidget(self)
            self.roles.hide()
            self.roles.currentItemChanged.connect(self._role_changed)
            namespace_row = QtWidgets.QHBoxLayout()
            namespace_row.addWidget(QtWidgets.QLabel('Namespace'))
            self.namespace_selector = QtWidgets.QComboBox()
            self.namespace_selector.setModel(self.roles.model())
            self.namespace_selector.currentIndexChanged.connect(self.roles.setCurrentRow)
            self.roles.currentRowChanged.connect(self.namespace_selector.setCurrentIndex)
            namespace_row.addWidget(self.namespace_selector, 1)
            refresh = QtWidgets.QToolButton()
            refresh.setText('Refresh')
            refresh.clicked.connect(self.refresh_characters)
            namespace_row.addWidget(refresh)
            outer.addLayout(namespace_row)
            self.current = QtWidgets.QLabel(self)
            self.current.hide()
            self.operation_page = self._advanced_skeleton_page()
            outer.addWidget(self.operation_page, 1)
            self.status = QtWidgets.QPlainTextEdit()
            self.status.setReadOnly(True)
            self.status.setMaximumHeight(52)
            outer.addWidget(self.status)

        def _page(self):
            page = QtWidgets.QScrollArea()
            page.setWidgetResizable(True)
            content = QtWidgets.QWidget()
            content.setObjectName("PageContent")
            stack = QtWidgets.QVBoxLayout(content)
            stack.setContentsMargins(0, 16, 0, 0)
            stack.setSpacing(15)
            page.setWidget(content)
            return page, stack

        def _group(self, title, rows):
            group = QtWidgets.QGroupBox(title)
            layout = QtWidgets.QFormLayout(group)
            layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
            layout.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
            layout.setHorizontalSpacing(13)
            layout.setVerticalSpacing(10)
            for label, widget in rows:
                layout.addRow(label, widget)
            help_page = _HELP_PAGES.get(title)
            if help_page:
                button = QtWidgets.QToolButton()
                button.setText('帮助')
                button.setObjectName('AdvPyHelpButton')
                button.setAccessibleName(title + ' 原版帮助')
                button.clicked.connect(lambda _, page=help_page:
                    self._open_help_page(page))
                button.setVisible(not self._help_hidden)
                layout.addRow(button)
                self._help_buttons.append(button)
            return group, layout

        def _open_help_page(self, page):
            from PySide2 import QtGui

            url = QtCore.QUrl('https://animationstudios.com.au/help/' + page)
            if not QtGui.QDesktopServices.openUrl(url):
                self.status.setPlainText('无法打开原版帮助页面：' + url.toString())

        def _fold(self, parent, title, *, opened=False, category=False):
            button = QtWidgets.QToolButton()
            button.setObjectName('AdvPyCategory' if category
                                 else 'AdvPySection')
            button.setText(title)
            button.setCheckable(True)
            button.setChecked(opened)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            button.setArrowType(QtCore.Qt.DownArrow if opened
                                else QtCore.Qt.RightArrow)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
            body = QtWidgets.QWidget()
            body.setVisible(opened)
            inner = QtWidgets.QVBoxLayout(body)
            inner.setContentsMargins(14, 4, 0, 10)
            inner.setSpacing(8)
            button.toggled.connect(body.setVisible)
            button.toggled.connect(lambda active, control=button:
                control.setArrowType(QtCore.Qt.DownArrow if active
                                     else QtCore.Qt.RightArrow))
            parent.addWidget(button)
            parent.addWidget(body)
            inner._adv_toggle = button
            return inner

        def _advanced_skeleton_page(self):
            # Reuse the existing operation widgets while arranging their
            # entrances in the order of the 6.925 MEL frame layouts.
            self._original_section_routes = {}
            sources = (self._fit_page(), self._skin_page(),
                       self._skin_cage_page(),
                       self._sub_wrap_page(),
                       self._skin_loop_page(),
                       self._geometry_skeleton_page(),
                       self._geometry_muscular_page(),
                       self._geometry_poly_boxes_page(),
                       self._geometry_mannequin_page(),
                       self._geometry_cut_up_page(),
                       self._animation_page(), self._face_page(),
                       self._mocap_page(), self._publish_page(),
                       self._display_page(), self._optimize_page())
            groups = {}
            for page in sources:
                source_layout = page.widget().layout()
                previous = None
                while source_layout.count():
                    item = source_layout.takeAt(0)
                    widget = item.widget()
                    if isinstance(widget, QtWidgets.QGroupBox):
                        title = widget.title()
                        if title in groups:
                            raise RuntimeError('Maya 面板栏目标题重复：' + title)
                        widget.setParent(None)
                        groups[title] = widget
                        previous = widget
                    elif widget is not None and previous is not None:
                        widget.setParent(previous)
                        previous.layout().addRow(widget)
                page.deleteLater()

            sections = (
                ('Preparation', (
                    ('Model', ('00 · Model Clean', '00 · 模型检查')),
                    ('Rig', ('00 · 绑定场景', '01 · 模型对象',
                             '02 · One Joint Prop', '02B · FBX rig',
                             '02A · Body 构建选项')),
                    ('Settings', ()))),
                ('Body', (
                    ('Fit', ('01 · Fit 数据',)),
                    ('Edit', ('02 · Fit 编辑',)),
                    ('Build', ('03 · 完整角色', '原版角色迁移',
                               '04 · 保留数据重建',
                               '05 · 跨段数脊柱角色替换')),
                    ('Deform option1', ('00 · 原版 Skinning',
                                           '01 · 建立 Skin', '02 · 权重文档',
                                           '03 · 跨场景源资产',
                                           '04 · 跨拓扑权重转移')),
                    ('Deform option2', ('00 · SkinCage',)),
                    ('Deform option3', ('00 · SubWrap',)),
                    ('Deform option4', ('00 · SkinLoops',)),
                    ('Deform Shapers', ('05 · Shapers',)),
                    ('Deform DeltaMush', ('05 · Delta Mush',)),
                    ('Geometry Skeleton', ('00 · Skeleton',)),
                    ('Geometry Muscular', ('00 · Muscular',)),
                    ('Geometry PolyBoxes', ('00 · PolyBoxes',)),
                    ('Geometry Mannequin', ('00 · Mannequin',)),
                    ('Geometry Skin Cut-Up', ('00 · Skin Cut-Up',)),
                    ('Custom Controllers', ('06 · 自定义控制器',)),
                    ('Squash Controller', ('07 · Squash Controller',)),
                    ('Motion System', ('08 · Motion System',)),
                    ('Control Curves', ('09 · Control Curves',)),
                    ('Control Orient', ('10 · Control Orient',)),
                    ('Control Mesh', ('10A · Control Mesh',)),
                    ('Game Engine', ('10B · Game Engine',)),
                    ('Unreal Joints', ('11 · Unreal Joints',)),
                    ('Partial Joints', ('12 · Partial Joints',)))),
                ('Face', (
                    ('Pre', ('00 · 面部输入', '00 · 眼球输入与控制',
                             '01 · 目标网格', '02 · 可移植目标资产')),
                    ('Fit', ('01 · EyeBall Fit', '02 · EyeLid Fit', '03 · Lip Fit', '04 · Face 定位点', '05 · Tongue Fit')),
                    ('Build', ('03 · 控制与变形器',)),
                    ('Build ...', ('03E · 原版 Face ctrlBox', '03D · Jaw 权重参考曲线', '03O · 原版眼部绑定与修形', '03I · Lip 绑定', '03G · Lip Falloff', '03K · Face Cage', '03L · Face 表情修形', '03J · Jaw 绑定与修形', '03F · Tongue 绑定', '03H · Regions', '03M · Eye Aim 与 UpMidLo', '03N · Phonemes 与 Emotions')),
                    ('Layers', ('03a · Face Skin Layers',)),
                    ('Tweaks', ('03A · Face Tweaks',)),
                    ('DeltaMush', ('03B · Face DeltaMush',)),
                    ('HeadSquash', ('03C · Face HeadSquash',)), ('WrinkleMap', ('03T · 原版 WrinkleMap',)),
                    ('BlendShapes', ('03P · 原版驱动转 BlendShape', '03Q · ARKit 接线', '04 · 表情与口型动画',
                                     '05 · 面部资产版本',
                                     '06 · 合并同一目标的三个版本')),
                    ('EditBlendShapes', ('03R · 原版 BlendShape 编辑',)), ('NewBlendShapes', ('03S · 原版新建 BlendShape',)),
                    ('Custom Controllers', ('07 · 自定义控制器',)))),
                ('Pose', (
                    ('Driving Systems', ('08 · 原版 Driving Systems', '03 · 动画通道',
                                         '04 · 区间模式转换',
                                         '05 · 控制空间事件')),
                    ('Corrective Shapes', ('07 · 原版 Corrective Shapes',)),
                    ('Pose Functions', ('09 · 原版 Pose Functions', '01 · 当前姿态',
                                        '02 · 全身动画',
                                        '06 · 角色预设')))),
                ('Tools', (('Tools', ('01 · 外部 FBX 驱动角色',
                                     '02 · NameMatcher','03 · MoCapMatcher','04 · PoserDesigner')),)),
                ('Display', (('Display', ('00 · Display',)),)),
                ('Optimize', (('Optimize', ('00 · Optimize',)),)),
                ('Updates', (('Updates', ('00 · Updates',)),)),
                ('Publish', (('Publish', ('00 · Publish', '01 · 导出迁移后的完整角色',
                                         '02 · 烘焙并发布独立骨架')),)),
                ('Export', (('Export', ('00 · Export',)),)),
                ('Demo', (('Demo', ()),)),
                ('About', (('About', ()),)),
            )
            page, stack = self._page()
            for category, children in sections:
                category_layout = self._fold(
                    stack, category, opened=category == 'Body', category=True)
                for title, names in children:
                    section_layout = self._fold(
                        category_layout, title,
                        opened=category == 'Body' and title == 'Build')
                    if names:
                        for name in names:
                            group = groups.pop(name)
                            group.setTitle(name.split(' · ', 1)[-1])
                            for label in group.findChildren(QtWidgets.QLabel):
                                label.setWordWrap(True)
                                label.setMinimumWidth(0)
                            from .maya_source_panel_rows import fit_group_rows
                            fit_group_rows(group)
                            section_layout.addWidget(group)
                            self._original_section_routes[name] = (
                                category_layout._adv_toggle, section_layout._adv_toggle, group)
                    elif category == 'Preparation' and title == 'Settings':
                        group = self._settings_group()
                        section_layout.addWidget(group)
                        self._original_section_routes['00 · Settings'] = (
                            category_layout._adv_toggle, section_layout._adv_toggle, group)
                    else:
                        section_layout.addWidget(QtWidgets.QLabel('尚未实现'))
            if groups:
                raise RuntimeError('Maya 面板操作未归入原版栏目：'
                                   + '、'.join(sorted(groups)))
            stack.addStretch(1)
            return page

        def _settings_group(self):
            from adv_py.core.panel_preferences import PANEL_COLOR_DEFAULTS

            palette = self.controller.panel_palette()
            group, form = self._group('GUI Colors', [])
            self.hide_help_enabled = QtWidgets.QCheckBox('隐藏帮助按钮')
            self.hide_help_enabled.setChecked(self._help_hidden)
            self.hide_help_enabled.toggled.connect(lambda hidden:
                self._run_panel_preference('隐藏帮助按钮',
                    lambda: self._set_hide_help_buttons(hidden)))
            form.addRow(self.hide_help_enabled)
            self.palette_enabled = QtWidgets.QCheckBox('使用自定义颜色')
            self.palette_enabled.setChecked(palette.enabled)
            self.palette_enabled.toggled.connect(lambda active: self._run_panel_preference(
                '自定义颜色', lambda: self._set_palette_enabled(active)))
            form.addRow(self.palette_enabled)
            self.palette_buttons = {}
            labels = {
                'Background': '背景', 'Level1': '一级栏目',
                'Level2': '二级栏目', 'Buttons': '按钮',
                'DropDowns': '下拉框', 'CheckBoxes': '复选框',
            }
            for kind, _ in PANEL_COLOR_DEFAULTS:
                button = QtWidgets.QPushButton('选择颜色')
                button.setObjectName('AdvPyPaletteSample')
                button.clicked.connect(lambda _, item=kind:
                    self._choose_palette_color(item))
                form.addRow(labels[kind], button)
                self.palette_buttons[kind] = button
            reset = QtWidgets.QPushButton('恢复默认颜色')
            reset.clicked.connect(lambda: self._run_panel_preference(
                '恢复默认颜色', self._reset_panel_palette))
            form.addRow(reset)
            form.addRow(QtWidgets.QLabel('界面语言：简体中文'))
            self._update_palette_samples(palette)
            return group

        def _update_palette_samples(self, palette):
            for kind, button in self.palette_buttons.items():
                rgb = palette.color(kind)
                red, green, blue = (round(channel * 255) for channel in rgb)
                button.setStyleSheet(
                    f'background: rgb({red}, {green}, {blue}); '
                    f'color: {self._palette_ink(rgb)}; '
                    'border: 1px solid #9BA8B5;')

        def _palette_ink(self, rgb):
            linear = tuple(channel / 12.92 if channel <= 0.04045
                           else ((channel + 0.055) / 1.055) ** 2.4
                           for channel in rgb)
            luminance = sum(weight * value for weight, value in zip(
                (0.2126, 0.7152, 0.0722), linear))
            return '#141A22' if luminance > 0.179 else '#F6FAFF'

        def _apply_panel_palette(self, palette):
            self._update_palette_samples(palette)
            if not palette.enabled:
                self.setStyleSheet(self._base_style)
                return
            def color(kind):
                return '#%02X%02X%02X' % tuple(
                    round(channel * 255) for channel in palette.color(kind))
            self.setStyleSheet(self._base_style + f'''
                QWidget#AdvPyCharacterPanel, QWidget#PageContent,
                QWidget#qt_scrollarea_viewport {{ background: {color('Background')};
                    color: {self._palette_ink(palette.color('Background'))}; }}
                QToolButton#AdvPyCategory {{ background: {color('Level1')};
                    color: {self._palette_ink(palette.color('Level1'))}; }}
                QToolButton#AdvPySection {{ background: {color('Level2')};
                    color: {self._palette_ink(palette.color('Level2'))}; }}
                QPushButton, QPushButton#PrimaryAction {{
                    background: {color('Buttons')};
                    color: {self._palette_ink(palette.color('Buttons'))}; }}
                QComboBox {{ background: {color('DropDowns')};
                    color: {self._palette_ink(palette.color('DropDowns'))}; }}
                QCheckBox::indicator:checked {{ background: {color('CheckBoxes')}; }}
            ''')

        def _set_palette_enabled(self, active):
            palette = self.controller.set_panel_palette_enabled(bool(active))
            self._apply_panel_palette(palette)
            return '已保存自定义颜色开关'

        def _set_hide_help_buttons(self, hidden):
            self._help_hidden = self.controller.set_hide_help_buttons(bool(hidden))
            for button in self._help_buttons:
                button.setVisible(not self._help_hidden)
            return '已保存帮助按钮显示设置'

        def _choose_palette_color(self, kind):
            from PySide2 import QtGui

            before = self.controller.panel_palette()
            chosen = QtWidgets.QColorDialog.getColor(
                QtGui.QColor.fromRgbF(*before.color(kind)), self,
                '选择面板颜色')
            if not chosen.isValid():
                return
            self._run_panel_preference('设置面板颜色', lambda: self._save_panel_color(
                kind, (chosen.redF(), chosen.greenF(), chosen.blueF())))

        def _run_panel_preference(self, label, callback):
            if self._busy:
                return
            self._busy = True
            try:
                self.status.setPlainText(callback())
            except (OSError, ValueError, RuntimeError) as error:
                self.status.setPlainText('操作失败：' + str(error))
                QtWidgets.QMessageBox.warning(self, label, str(error))
            finally:
                self._busy = False

        def _save_panel_color(self, kind, rgb):
            palette = self.controller.set_panel_color(kind, rgb)
            self._apply_panel_palette(palette)
            return '已保存面板颜色'

        def _reset_panel_palette(self):
            palette = self.controller.reset_panel_colors()
            previous = self.palette_enabled.blockSignals(True)
            self.palette_enabled.setChecked(False)
            self.palette_enabled.blockSignals(previous)
            self._apply_panel_palette(palette)
            return '已恢复默认颜色'

        def _file_field(self, caption, *, save=False, filter_text="JSON 文件 (*.json)"):
            holder = QtWidgets.QWidget()
            line = QtWidgets.QLineEdit()
            line.setPlaceholderText("选择文件路径")
            browse = QtWidgets.QPushButton("浏览…")
            browse.setAccessibleName("浏览" + caption)
            row = QtWidgets.QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(7)
            row.addWidget(line, 1)
            row.addWidget(browse)
            def choose():
                pick = (QtWidgets.QFileDialog.getSaveFileName if save else
                        QtWidgets.QFileDialog.getOpenFileName)
                path, _ = pick(self, caption, line.text(), filter_text)
                if path:
                    line.setText(path)
            browse.clicked.connect(choose)
            return holder, line

        def _button(self, label, callback, *, primary=False):
            button = QtWidgets.QPushButton(label)
            if primary:
                button.setObjectName("PrimaryAction")
            button.clicked.connect(lambda: self._run(label, callback))
            return button

        def _native_button_row(self, *actions):
            holder = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            for label, callback in actions:
                layout.addWidget(self._button(label, callback))
            return holder

        def _fit_page(self):
            page, stack = self._page()
            model_source, self.preparation_model_source = self._file_field(
                "选择 Maya 模型文件", filter_text="Maya 场景 (*.ma *.mb)")
            group, form = self._group("00 · 绑定场景", [
                ("模型文件", model_source)])
            prep_row = QtWidgets.QHBoxLayout()
            prep_row.addWidget(self._button("新建绑定场景", self._new_preparation_scene))
            prep_row.addWidget(self._button("引用模型文件", self._reference_preparation_model))
            form.addRow(prep_row)
            self.preparation_reference_namespace = QtWidgets.QLineEdit("model")
            self.preparation_reference_namespace.setPlaceholderText("model 或 model1")
            form.addRow("目标引用命名空间", self.preparation_reference_namespace)
            manage_row = QtWidgets.QHBoxLayout()
            manage_row.addWidget(self._button("重新加载模型引用",
                self._reload_preparation_model))
            manage_row.addWidget(self._button("替换模型引用文件",
                self._replace_preparation_model))
            manage_row.addWidget(self._button("移除模型引用",
                self._remove_preparation_model))
            form.addRow(manage_row)
            stack.addWidget(group)

            self.preparation_object_fields = {}
            group, form = self._group("01 · 模型对象", [])
            for role in ("Skin", "All", "Right Eye", "Left Eye"):
                field = QtWidgets.QLineEdit()
                field.setReadOnly(True)
                field.setPlaceholderText("未记录")
                self.preparation_object_fields[role] = field
                row = QtWidgets.QHBoxLayout()
                row.addWidget(field, 1)
                record = self._button("记录所选", lambda r=role:
                    self._record_preparation_objects(r))
                record.setObjectName("AdvPyPrepRecord" + role.replace(" ", ""))
                row.addWidget(record)
                reselect = self._button("重新选中", lambda r=role:
                    self._reselect_preparation_objects(r))
                reselect.setObjectName("AdvPyPrepReselect" + role.replace(" ", ""))
                row.addWidget(reselect)
                form.addRow(role, row)
            stack.addWidget(group)

            group, form = self._group("02 · One Joint Prop", [])
            form.addRow(QtWidgets.QLabel(
                "使用已记录的 Skin 与 All 模型，创建单关节道具绑定。"))
            form.addRow(self._button("创建单关节道具绑定",
                                     self._build_one_joint_prop, primary=True))
            stack.addWidget(group)

            group, form = self._group("02B · FBX rig", [])
            form.addRow(self._button("FBX rig", self._build_fbx_rig))
            stack.addWidget(group)

            self.name_matcher_rows = QtWidgets.QPlainTextEdit()
            self.name_matcher_rows.setPlaceholderText(
                '每行：Fit关节 来源关节基础名，例如 Root Hips')
            self.name_matcher_rows.setPlainText(
                'Root Hips\nSpine1 Spine\nChest Chest\nNeck Neck\n'
                'Head Head\nScapula Clavicle\nShoulder Shoulder\n'
                'Elbow Elbow\nWrist Hand\nHip Thigh\nKnee Calf\n'
                'Ankle Foot\nToes Toe')
            self.name_matcher_rows.setMaximumHeight(130)
            self.name_matcher_right = QtWidgets.QLineEdit('R')
            self.name_matcher_left = QtWidgets.QLineEdit('L')
            self.name_matcher_middle = QtWidgets.QLineEdit('')
            self.name_matcher_source_root = QtWidgets.QLineEdit()
            self.name_matcher_source_root.setPlaceholderText(
                '创建 Fit 后自动填入；也可填写外部骨架根路径')
            self.name_matcher_prefix = QtWidgets.QCheckBox('侧别在名称前')
            self.name_matcher_underscore = QtWidgets.QCheckBox('侧别用下划线分隔')
            self.name_matcher_underscore.setChecked(True)
            self.name_matcher_extra = QtWidgets.QCheckBox(
                '动捕连接 Extra 控制层')
            self.name_matcher_templates = QtWidgets.QComboBox()
            self.name_matcher_templates.addItem('自定义映射','')
            try:
                matcher_assets = self.controller.preparation_source_name_matcher_catalog()
            except ValueError:
                matcher_assets = ()
            for asset in matcher_assets:
                self.name_matcher_templates.addItem(asset.stem,asset.stem)
            group, form = self._group('02 · NameMatcher', [
                ('原版模板',self.name_matcher_templates),
                ('Fit／来源名称映射', self.name_matcher_rows),
                ('右侧标记', self.name_matcher_right),
                ('左侧标记', self.name_matcher_left),
                ('中间标记', self.name_matcher_middle),
                ('命名位置', self.name_matcher_prefix),
                ('分隔符', self.name_matcher_underscore),
                ('动捕控制层', self.name_matcher_extra),
                ('外部骨架根', self.name_matcher_source_root)])
            self.name_matcher_templates.currentIndexChanged.connect(self._load_source_name_matcher_template)
            form.addRow(self._button('导出 NameMatcher 配置', self._export_source_name_matcher_template))
            form.addRow(self._button('检查外部骨架', self._check_source_name_matcher))
            form.addRow(self._button('创建并放置 FitSkeleton',
                                     self._build_name_matcher_fit))
            form.addRow(self._button('一键创建角色并连接原 Skin／动画',
                                     self._build_name_matcher_character))
            form.addRow(self._button('保留来源动画骨架',
                                     self._keep_name_matcher_animation))
            form.addRow(self._button('将 Body 约束到外部骨架',
                                     self._connect_name_matcher_skeleton))
            form.addRow(self._button('保留动画烘焙到 FK',
                                     self._bake_name_matcher_animation))
            form.addRow(self._button('原 Skin 转接至 Body 关节',
                                     self._transfer_name_matcher_skin))
            form.addRow(self._button('动捕来源关节旋转归零',
                                     self._zero_out_name_matcher_mocap))
            form.addRow(self._button('连接外部动捕到角色控制器',
                                     self._connect_name_matcher_mocap))
            form.addRow(self._button('断开动捕骨架',
                                     self._disconnect_name_matcher_mocap))
            form.addRow(self._button('烘焙动捕到控制器',
                                     self._bake_name_matcher_mocap))
            stack.addWidget(group)

            self.body_option_fields = {}
            group, form = self._group("02A · Body 构建选项", [])
            for key, label in (
                    ("game_engine", "game engine"),
                    ("use_offset_parent_matrix", "Offset Parent Matrix"),
                    ("sub_controllers", "Sub Controllers"),
                    ("extra_controllers", "Extra Controllers")):
                field = QtWidgets.QCheckBox(label)
                self.body_option_fields[key] = field
                form.addRow(field)
            self.body_option_status = QtWidgets.QLabel("选择已有 Fit 后读取选项")
            form.addRow(self.body_option_status)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("读取 Body 构建选项",
                                       self._load_body_build_options))
            row.addWidget(self._button("保存 Body 构建选项",
                                       self._save_body_build_options))
            form.addRow(row)
            stack.addWidget(group)

            group, form = self._group("00 · Model Clean", [])
            form.addRow(self._button("创建 geo 模型组",
                                     self._create_model_geo_group))
            form.addRow(self._button("清理模型（OBJ 重建）",
                                     self._clean_model))
            stack.addWidget(group)

            self.model_check_results = QtWidgets.QPlainTextEdit()
            self.model_check_results.setReadOnly(True)
            self.model_check_results.setPlaceholderText(
                "选择多边形模型，检查父级变换、构建历史和左右对称性")
            self.model_check_results.setMaximumHeight(180)
            group, form = self._group("00 · 模型检查", [
                ("检查报告", self.model_check_results)])
            self.model_check_interactive = QtWidgets.QCheckBox("逐项确认检查问题")
            self.model_check_interactive.setChecked(True)
            self.model_check_skip_symmetry = QtWidgets.QCheckBox("跳过左右对称检查")
            form.addRow(self.model_check_interactive)
            form.addRow(self.model_check_skip_symmetry)
            form.addRow(self._button("检查选中模型", self._check_model))
            stack.addWidget(group)

            fit_out, self.fit_export_document = self._file_field("导出 Fit 文档", save=True)
            fit_in, self.fit_import_document = self._file_field("导入 Fit 文档")
            self.fit_container = QtWidgets.QLineEdit("FitSkeleton")
            self.external_fit_export = QtWidgets.QCheckBox(
                "兼容导出原版 Fit（缺失标签写入文档）")
            self.fit_template_scale = QtWidgets.QDoubleSpinBox()
            self.fit_template_scale.setRange(0.01, 1000.0)
            self.fit_template_scale.setDecimals(2)
            self.fit_template_scale.setValue(1.0)
            group, form = self._group("01 · Fit 数据", [
                ("容器名称", self.fit_container), ("导出到", fit_out),
                ("从文件导入", fit_in),
                ("模板缩放", self.fit_template_scale),
                ("导出模式", self.external_fit_export)])
            self.source_fit_templates = QtWidgets.QComboBox()
            self.source_fit_limbs = QtWidgets.QComboBox()
            for combo, limbs in ((self.source_fit_templates,False),(self.source_fit_limbs,True)):
                try:
                    assets = self.controller.fit_source_asset_catalog(limbs=limbs)
                except ValueError:
                    assets = ()
                for asset in assets:
                    combo.addItem(asset.name,str(asset))
                combo.setEnabled(bool(assets))
            native_template_row = QtWidgets.QHBoxLayout()
            native_template_row.addWidget(self.source_fit_templates)
            native_template_row.addWidget(self._button('导入原版 Fit 模板', self._source_fit_template_import))
            form.addRow('原版模板',native_template_row)
            native_limb_row = QtWidgets.QHBoxLayout()
            native_limb_row.addWidget(self.source_fit_limbs)
            native_limb_row.addWidget(self._button('导入原版 Fit 部件', self._source_fit_limb_import))
            form.addRow('原版部件',native_limb_row)
            form.addRow(self._button('导出原版 Fit／部件 .ma', self._source_fit_scene_export))
            template_row = QtWidgets.QHBoxLayout()
            template_row.addWidget(self._button("创建基础身体示例 Fit",
                lambda: self._create_fit_template(False)))
            template_row.addWidget(self._button("创建五指身体示例 Fit",
                lambda: self._create_fit_template(True)))
            form.addRow(template_row)
            form.addRow(self._button("从所选标准骨架创建 Fit",
                                      self._fit_from_selected_skeleton))
            auto_place_row=QtWidgets.QHBoxLayout()
            auto_place_row.addWidget(self._button('自动放置',self._fit_auto_place))
            auto_place_row.addWidget(self._button('缩放',self._fit_auto_scale))
            form.addRow('自动放置：',auto_place_row)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("导出当前 Fit", self._export_fit))
            row.addWidget(self._button("从文档导入", self._import_fit))
            form.addRow(row)
            stack.addWidget(group)

            self.fit_position_edits = QtWidgets.QPlainTextEdit()
            self.fit_position_edits.setPlaceholderText(
                "每行：关节名  本地X  本地Y  本地Z\n例如：Spine1  0  0  8")
            self.fit_position_edits.setMaximumHeight(82)
            self.fit_edit_joints = QtWidgets.QPlainTextEdit()
            self.fit_edit_joints.setPlaceholderText("每行一个 Fit joint 名称或完整路径")
            self.fit_edit_joints.setMaximumHeight(72)
            from adv_py.core.source_fit_attributes import SOURCE_FIT_ATTRIBUTE_TYPES
            self.fit_source_attribute = QtWidgets.QComboBox()
            for attribute in SOURCE_FIT_ATTRIBUTE_TYPES:
                self.fit_source_attribute.addItem(attribute, attribute)
            self.fit_source_attribute_help = QtWidgets.QLabel()
            self.fit_source_attribute_help.setWordWrap(True)
            self.fit_source_attribute.currentTextChanged.connect(self._update_source_fit_attribute_help)
            self._update_source_fit_attribute_help(self.fit_source_attribute.currentText())
            from adv_py.core.source_fit_labels import SOURCE_FIT_UI_LABELS
            self.fit_source_label = QtWidgets.QComboBox()
            for label in SOURCE_FIT_UI_LABELS:
                self.fit_source_label.addItem(label, label)
            self.fit_source_label_help = QtWidgets.QLabel()
            self.fit_source_label_help.setWordWrap(True)
            self.fit_source_label.currentTextChanged.connect(self._update_source_fit_label_help)
            self._update_source_fit_label_help(self.fit_source_label.currentText())
            self.fit_metadata_field = QtWidgets.QComboBox()
            for label, value in (
                    ("Twist 关节数", "twist_joints"),
                    ("Bendy 控制器数", "bendy_controls"),
                    ("Inbetween 关节数", "inbetween_joints"),
                    ("UnTwister", "untwister"),
                    ("末端 Control", "control"),
                    ("Tweaker Control（需 OPM）", "tweaker_control"),
                    ("隐藏 FK 控制", "no_control"),
                    ("不参与 Skin", "no_skin"),
                    ("FK 分段缩放补偿", "seg_scale_comp"),
                    ("COG", "cog"),
                    ("Aim", "aim"),
                    ("Foot Pivots", "foot_pivots"),
                    ("禁止镜像", "no_mirror"),
                    ("左侧禁止镜像", "no_mirror_left"),
                    ("Child Of Part", "child_of_part"),
                    ("Global 权重", "global_weight"),
                    ("Global Translate", "global_translate"),
                    ("Parent Constraint 目标", "parent_constraint"),
                    ("Point Constraint 目标", "point_constraint"),
                    ("Orient Constraint 目标", "orient_constraint"),
                    ("Constraint 保持控制器朝向", "orient_constraint_maintain_offset"),
                    ("Scale Constraint 目标", "scale_constraint"),
                    ("Follow 目标", "follow"),
                    ("Follow 左右切换", "follow_left_right"),
                    ("Follow 世界空间", "follow_world"),
                    ("Follow* 命名目标", "follow_by_name"),
                    ("Follow Spaces", "follow_spaces"),
                    ("IK Follow 目标", "ik_follow"),
                    ("AimAt 目标", "aim_at"),
                    ("AimAt 主轴", "aim_axis"),
                    ("AimAt Up 轴", "aim_up_axis"),
                    ("AimAt Up 来源", "aim_up_object"),
                    ("Geo Attach 网格", "geo_attach"),
                    ("Geo Attach 模式", "geo_attach_mode"),
                    ("Proximity Pin 网格", "proximity_pin"),
                    ("Root Main Extras 数量", "num_main_extras"),
                    ("Root Leg Lock", "leg_lock"),
                    ("Root Center Between Feet", "center_between_feet"),
                    ("World Orient Up", "world_orient_up"),
                    ("World Orient Forward", "world_orient_forward"),
                    ("IK Local Mode", "ik_local_mode")):
                self.fit_metadata_field.addItem(label, value)
            self.fit_metadata_value = QtWidgets.QLineEdit()
            self.fit_metadata_value.setPlaceholderText(
                "数值、开关、目标名或 Follow* 的 目标=10,目标=0")
            self.fit_metadata_remove = QtWidgets.QCheckBox("删除所选字段")
            self.fit_orientation_children = QtWidgets.QPlainTextEdit()
            self.fit_orientation_children.setPlaceholderText(
                "分支关节每行：目标关节  指定直接子级\n例如：Root  Spine1")
            self.fit_orientation_children.setMaximumHeight(66)
            self.fit_orientation_mode = QtWidgets.QComboBox()
            self.fit_orientation_mode.addItem("按 Fit 规则自动朝向", "child")
            self.fit_orientation_mode.addItem("按 World Orient 元数据", "world")
            self.fit_resample_start = QtWidgets.QLineEdit()
            self.fit_resample_start.setPlaceholderText("例如 Root")
            self.fit_resample_end = QtWidgets.QLineEdit()
            self.fit_resample_end.setPlaceholderText("例如 Chest")
            self.fit_resample_count = QtWidgets.QSpinBox()
            self.fit_resample_count.setRange(2, 99)
            self.fit_resample_count.setValue(3)
            group, form = self._group("02 · Fit 编辑", [
                ("位置批量编辑", self.fit_position_edits),
                ("目标关节", self.fit_edit_joints),
                ("元数据字段", self.fit_metadata_field),
                ("字段值", self.fit_metadata_value),
                ("字段操作", self.fit_metadata_remove),
                ("朝向模式", self.fit_orientation_mode),
                ("分支子级映射", self.fit_orientation_children),
                ("重采样起点", self.fit_resample_start),
                ("重采样终点", self.fit_resample_end),
                ("重采样关节总数", self.fit_resample_count)])
            attribute_row = QtWidgets.QHBoxLayout()
            attribute_row.addWidget(self.fit_source_attribute)
            attribute_row.addWidget(self._button('添加', self._add_source_fit_attributes))
            attribute_row.addWidget(self._button('移除', self._remove_source_fit_attributes))
            form.insertRow(0, '所选关节属性', attribute_row)
            form.insertRow(1, self.fit_source_attribute_help)
            label_row = QtWidgets.QHBoxLayout()
            label_row.addWidget(self.fit_source_label)
            label_row.addWidget(self._button('Add', self._add_source_fit_labels))
            label_row.addWidget(self._button('Remove', self._remove_source_fit_labels))
            form.insertRow(0, self.fit_source_label_help)
            form.insertRow(0, 'IK-Label', label_row)
            position_row = QtWidgets.QHBoxLayout()
            position_row.addWidget(self._button("更新 Fit 位置", self._edit_fit_positions))
            position_row.addWidget(self._button("重新定向 Fit", self._orient_fit))
            form.addRow(position_row)
            form.addRow(self._button("更新 Fit 元数据", self._edit_fit_metadata))
            form.addRow(self._button("重采样 Fit 关节链", self._resample_fit))
            form.addRow(self._button("创建／移除非对称 Fit 关节",
                                      self._body_toggle_fit_non_symmetry))
            self.fit_placement_buffer = None
            placement_row = QtWidgets.QHBoxLayout()
            placement_row.addWidget(self._button('吸附组件中心',self._fit_placement_snap))
            placement_row.addWidget(self._button('复制位置',self._fit_placement_copy))
            self.fit_placement_paste_button = self._button('粘贴位置',self._fit_placement_paste)
            self.fit_placement_paste_button.setEnabled(False)
            placement_row.addWidget(self.fit_placement_paste_button)
            form.addRow('Placement',placement_row)
            fit_mode_row = QtWidgets.QHBoxLayout()
            fit_mode_row.addWidget(self._button('锁定／解锁中心关节', self._fit_toggle_center_locks))
            fit_mode_row.addWidget(self._button('FitMode', self._fit_toggle_mode))
            fit_mode_row.addWidget(self._button('立即更新 Fit', self._fit_manual_update))
            form.addRow(fit_mode_row)
            self.fit_geometry_visible=QtWidgets.QCheckBox('显示几何')
            self.fit_geometry_visible.setChecked(False)
            self.fit_geometry_type=QtWidgets.QComboBox()
            for label,value in (('圆柱','cylinders'),('盒体','boxes'),('球体','spheres'),('骨形','bones')):
                self.fit_geometry_type.addItem(label,value)
            self.fit_geometry_gap=QtWidgets.QDoubleSpinBox()
            self.fit_geometry_gap.setRange(.01,1.)
            self.fit_geometry_gap.setSingleStep(.05)
            self.fit_geometry_gap.setValue(.75)
            geometry_row=QtWidgets.QHBoxLayout()
            geometry_row.addWidget(self.fit_geometry_visible)
            geometry_row.addWidget(self.fit_geometry_type)
            geometry_row.addWidget(self.fit_geometry_gap)
            geometry_row.addWidget(self._button('更新显示',self._fit_geometry_update))
            form.addRow('几何显示／间距',geometry_row)
            self.fit_pole_vectors_visible = QtWidgets.QCheckBox('显示 PoleVector 弯曲平面')
            pole_row = QtWidgets.QHBoxLayout()
            pole_row.addWidget(self.fit_pole_vectors_visible)
            pole_row.addWidget(self._button('更新 PoleVector 显示', self._fit_pole_vector_display))
            form.addRow(pole_row)
            self.fit_finger_up_visible = QtWidgets.QCheckBox('显示 Finger-up')
            finger_row = QtWidgets.QHBoxLayout()
            finger_row.addWidget(self.fit_finger_up_visible)
            finger_row.addWidget(self._button('更新 Finger-up 显示', self._fit_finger_up_display))
            form.addRow(finger_row)
            straight_row = QtWidgets.QHBoxLayout()
            straight_row.addWidget(self._button('拉直腿部 PoleVector',
                lambda: self._fit_straighten_pole_vector('Leg')))
            straight_row.addWidget(self._button('拉直手臂 PoleVector',
                lambda: self._fit_straighten_pole_vector('Arm')))
            form.addRow(straight_row)
            joint_display_row = QtWidgets.QHBoxLayout()
            joint_display_row.addWidget(self._button('显示／隐藏关节朝向',
                lambda: self._fit_toggle_joint_display('orient')))
            joint_display_row.addWidget(self._button('显示／隐藏关节轴',
                lambda: self._fit_toggle_joint_display('axis')))
            form.addRow(joint_display_row)
            form.addRow(self._button('创建 Fit SDK 属性', self._fit_sdk_create_attribute))
            self.fit_joint_display_size = QtWidgets.QDoubleSpinBox()
            self.fit_joint_display_size.setRange(.01, 10.)
            self.fit_joint_display_size.setDecimals(2)
            self.fit_joint_display_size.setValue(self.controller.fit_joint_display_scale())
            self.fit_joint_display_size.valueChanged.connect(
                lambda value: self.controller.fit_joint_display_scale(value))
            form.addRow('joint', self.fit_joint_display_size)
            stack.addWidget(group)

            self.spine_segments = QtWidgets.QSpinBox()
            self.spine_segments.setRange(0, 63)
            self.spine_segments.setSpecialValueText("自动读取 Fit")
            self.head_aim = QtWidgets.QCheckBox("包含头部瞄准控制")
            self.build_meshes = QtWidgets.QPlainTextEdit()
            self.build_meshes.setPlaceholderText(
                "每行一个未绑定网格的完整路径；留空时可使用 Preparation / Skin")
            self.build_meshes.setMaximumHeight(76)
            self.build_source_root = QtWidgets.QLineEdit()
            self.build_source_root.setPlaceholderText(
                "来源骨架根关节完整路径；请先将来源置于绑定姿态")
            self.build_use_preparation_skin = QtWidgets.QCheckBox(
                "将 Preparation / Skin 模型同时绑定")
            self.build_use_preparation_skin.setChecked(False)
            group, form = self._group("03 · 完整角色", [
                ("脊柱配置", self.spine_segments), ("附加控制", self.head_aim),
                ("来源骨架", self.build_source_root),
                ("待绑定网格", self.build_meshes),
                ("准备输入", self.build_use_preparation_skin)])
            form.addRow(self._button("使用当前选中的网格",
                                      self._fill_selected_build_meshes))
            form.addRow(self._button("记录当前选中的骨架根关节",
                                      self._fill_selected_source_root))
            form.addRow(self._button("Toggle Fit/Adv",
                                     self._body_toggle_fit_advanced))
            form.addRow(self._button("删除 Adv（保留 Fit）",
                                     self._body_delete_advanced))
            form.addRow(self._button("构建并登记角色", self._build_character,
                                      primary=True))
            form.addRow(self._button("从来源骨架直接构建角色",
                                      self._build_from_source))
            stack.addWidget(group)

            self.original_source_skin = QtWidgets.QLineEdit()
            self.original_source_skin.setPlaceholderText(
                "留空时自动识别场景中唯一的 Skin")
            group, form = self._group("原版角色迁移", [
                ("原版 Skin", self.original_source_skin)])
            form.addRow(QtWidgets.QLabel(
                "从当前原版 Fit 重建角色，并将原网格的完整权重迁移到新绑定。"))
            form.addRow(self._button("迁移当前原版角色与蒙皮",
                                     self._migrate_original_skin))
            stack.addWidget(group)

            self.rebuild_namespace = QtWidgets.QLineEdit("CharacterRebuildStage")
            self.rebuild_extensions = QtWidgets.QPlainTextEdit()
            self.rebuild_extensions.setPlaceholderText(
                "每行一个附件根路径；如 |Root_M|…|Head_M|AdvPy_FaceControls")
            self.rebuild_extensions.setMaximumHeight(88)
            group, form = self._group("04 · 保留数据重建", [
                ("暂存命名空间", self.rebuild_namespace),
                ("用户附件根", self.rebuild_extensions)])
            form.addRow(self._button("重建并保留数据", self._rebuild_character))
            stack.addWidget(group)

            self.spine_replacement = QtWidgets.QLineEdit()
            self.spine_replacement.setPlaceholderText("场景中已构建的目标角色命名空间")
            self.spine_skins = QtWidgets.QPlainTextEdit()
            self.spine_skins.setPlaceholderText("每行一个原 Skin 名称；与下方网格逐行对应")
            self.spine_meshes = QtWidgets.QPlainTextEdit()
            self.spine_meshes.setPlaceholderText("每行一个原网格完整 DAG 路径")
            self.spine_extensions = QtWidgets.QPlainTextEdit()
            self.spine_extensions.setPlaceholderText("每行一个原角色附件根完整路径；可留空")
            self.spine_assets = QtWidgets.QPlainTextEdit()
            self.spine_assets.setPlaceholderText("每行一个需保留的独立 DAG 资产根；可留空")
            self.spine_nodes = QtWidgets.QPlainTextEdit()
            self.spine_nodes.setPlaceholderText("每行一个需保留的独立 DG 节点；可留空")
            self.spine_graph_roots = QtWidgets.QPlainTextEdit()
            self.spine_graph_roots.setPlaceholderText("每行一个 DG 数据连接图根；可留空")
            for field in (self.spine_skins, self.spine_meshes,
                          self.spine_extensions, self.spine_assets,
                          self.spine_nodes, self.spine_graph_roots):
                field.setMaximumHeight(66)
            self.spine_replace_start = QtWidgets.QSpinBox()
            self.spine_replace_end = QtWidgets.QSpinBox()
            self.spine_replace_step = QtWidgets.QSpinBox()
            for field in (self.spine_replace_start, self.spine_replace_end):
                field.setRange(-100000, 100000)
            self.spine_replace_start.setValue(1)
            self.spine_replace_end.setValue(10)
            self.spine_replace_step.setRange(1, 100000)
            self.spine_replace_mode = QtWidgets.QComboBox()
            self.spine_replace_mode.addItem("FK 重采样", "fk")
            self.spine_replace_mode.addItem("IK 曲线迁移", "ik")
            self.spine_replace_mode.addItem("FK/IK 事件迁移", "hybrid")
            self.spine_replace_substeps = QtWidgets.QSpinBox()
            self.spine_replace_substeps.setRange(1, 8)
            self.spine_replace_mesh_gate = QtWidgets.QCheckBox("限制网格误差")
            self.spine_replace_mesh_gate.setChecked(True)
            self.spine_replace_body_gate = QtWidgets.QCheckBox("限制身体误差")
            self.spine_replace_mesh_limit = QtWidgets.QDoubleSpinBox()
            self.spine_replace_body_limit = QtWidgets.QDoubleSpinBox()
            for field in (self.spine_replace_mesh_limit,
                          self.spine_replace_body_limit):
                field.setRange(0., 1000.)
                field.setDecimals(6)
                field.setSingleStep(.001)
                field.setSuffix(" cm")
            self.spine_replace_mesh_limit.setValue(.1)
            self.spine_replace_body_limit.setValue(.01)
            self.spine_replace_mesh_gate.toggled.connect(
                self.spine_replace_mesh_limit.setEnabled)
            self.spine_replace_body_gate.toggled.connect(
                self.spine_replace_body_limit.setEnabled)
            self.spine_replace_body_limit.setEnabled(False)
            self.spine_replace_mode.currentIndexChanged.connect(
                self._spine_replace_mode_changed)
            times = QtWidgets.QWidget()
            time_grid = QtWidgets.QGridLayout(times)
            time_grid.setContentsMargins(0, 0, 0, 0)
            for index, (label, field) in enumerate((
                    ("起始", self.spine_replace_start),
                    ("结束", self.spine_replace_end),
                    ("步长", self.spine_replace_step))):
                row, column = divmod(index, 2)
                field.setMaximumWidth(120)
                time_grid.addWidget(QtWidgets.QLabel(label), row, column * 2)
                time_grid.addWidget(field, row, column * 2 + 1)
            limits = QtWidgets.QWidget()
            limit_rows = QtWidgets.QVBoxLayout(limits)
            limit_rows.setContentsMargins(0, 0, 0, 0)
            for gate, field in ((self.spine_replace_mesh_gate,
                                 self.spine_replace_mesh_limit),
                                (self.spine_replace_body_gate,
                                 self.spine_replace_body_limit)):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(gate)
                row.addStretch(1)
                row.addWidget(field)
                limit_rows.addLayout(row)
            group, form = self._group("05 · 跨段数脊柱角色替换", [
                ("目标命名空间", self.spine_replacement),
                ("原 Skin", self.spine_skins),
                ("原网格", self.spine_meshes),
                ("动画区间", times),
                ("迁移模式", self.spine_replace_mode),
                ("FK 帧间细分", self.spine_replace_substeps),
                ("误差上限", limits),
                ("附件根", self.spine_extensions),
                ("保留资产根", self.spine_assets),
                ("保留 DG 节点", self.spine_nodes),
                ("DG 图根", self.spine_graph_roots)])
            form.addRow(self._button("替换脊柱角色并保留数据",
                                      self._replace_spine_character))
            stack.addWidget(group)

            self.custom_softmod_source = QtWidgets.QLineEdit()
            self.custom_softmod_source.setPlaceholderText("已绘制的 SoftMod 节点路径")
            self.custom_control_name = QtWidgets.QLineEdit()
            self.custom_control_name.setPlaceholderText("例如 Bicep；侧别由位置确定")
            self.custom_control_mirror = QtWidgets.QCheckBox("启用")
            self.custom_control_mirror.setChecked(True)
            self.custom_control_middle = QtWidgets.QCheckBox("启用")
            self.custom_control_mirror.toggled.connect(
                lambda enabled: self.custom_control_middle.setChecked(False)
                if enabled else None)
            self.custom_control_middle.toggled.connect(
                lambda enabled: self.custom_control_mirror.setChecked(False)
                if enabled else None)
            self.custom_control_local = QtWidgets.QCheckBox("启用")
            self.custom_control_local.setChecked(True)
            self.custom_control_partial_parent = QtWidgets.QCheckBox(
                "启用 50% 父关节（仅 Body Skin）")
            self.custom_skin_cluster = QtWidgets.QLineEdit()
            self.custom_skin_cluster.setPlaceholderText(
                "留空使用唯一现有层；填节点名选现有层")
            self.custom_skin_new_layer = QtWidgets.QCheckBox(
                "新建分层 SkinCluster")
            self.custom_control_parent = QtWidgets.QLineEdit()
            self.custom_control_parent.setPlaceholderText(
                "可留空；默认选择最近的变形关节")
            self.custom_control_existing = QtWidgets.QLineEdit()
            self.custom_control_existing.setPlaceholderText(
                "已有 SoftMod 控制器路径")
            self.custom_control_mesh = QtWidgets.QLineEdit()
            self.custom_control_mesh.setPlaceholderText("新增受影响网格路径")
            group, form = self._group("06 · 自定义控制器", [
                ("SoftMod 区域", self.custom_softmod_source),
                ("控制器名称", self.custom_control_name),
                ("自动镜像", self.custom_control_mirror),
                ("中心控制", self.custom_control_middle),
                ("局部朝向", self.custom_control_local),
                ("父关节中间层", self.custom_control_partial_parent),
                ("目标蒙皮层", self.custom_skin_cluster),
                ("新建蒙皮层", self.custom_skin_new_layer),
                ("指定父关节", self.custom_control_parent),
                ("已有控制器", self.custom_control_existing),
                ("新增网格", self.custom_control_mesh)])
            form.addRow(QtWidgets.QLabel("先创建 SoftMod 区域："))
            form.addRow(self._button("打开 SoftMod Tool",
                                     self._open_custom_softmod_tool))
            form.addRow(QtWidgets.QLabel("然后创建控制器："))
            form.addRow(self._button("创建 Skin Control",
                                     self._create_custom_skin))
            form.addRow(self._button("创建 Cluster Control",
                                     self._create_custom_cluster))
            form.addRow(self._button("创建 SoftMod Control",
                                     self._create_custom_softmod))
            form.addRow(QtWidgets.QLabel("编辑 Cluster Control："))
            form.addRow(self._button("绘制所选控制器权重",
                                     self._paint_custom_cluster))
            form.addRow(self._button("镜像所选控制器权重",
                                     self._mirror_custom_cluster))
            form.addRow(QtWidgets.QLabel("编辑："))
            form.addRow(self._button("添加受影响对象",
                                     self._add_custom_softmod_mesh))
            form.addRow(QtWidgets.QLabel("删除："))
            form.addRow(self._button("删除所选控制器",
                                     self._delete_custom_control))
            stack.addWidget(group)

            self.squash_mirror = QtWidgets.QCheckBox("右侧创建时自动镜像左侧")
            self.squash_mirror.setChecked(True)
            group, form = self._group("07 · Squash Controller", [
                ("镜像", self.squash_mirror)])
            form.addRow(QtWidgets.QLabel("选择要影响的网格顶点"))
            form.addRow(self._button("创建 Squash Controller",
                                     self._create_squash_controller))
            form.addRow(self._button("删除 Squash Controller",
                                     self._delete_squash_controller))
            stack.addWidget(group)

            self.human_ik_definition_only = QtWidgets.QCheckBox(
                "仅创建 HumanIK 定义")
            group, form = self._group("08 · Motion System", [
                ("创建选项", self.human_ik_definition_only)])
            form.addRow(self._button("创建 HumanIK", self._create_human_ik))
            form.addRow(self._button("删除 HumanIK", self._delete_human_ik))
            form.addRow(self._button("烘焙 HumanIK 到控制器",
                                     self._bake_human_ik))
            stack.addWidget(group)

            self.control_curve_targets = QtWidgets.QPlainTextEdit()
            self.control_curve_targets.setPlaceholderText(
                "每行一个控制器路径；自动缩放、调色板、宽度与旋转留空使用 Maya 当前选择")
            self.control_curve_targets.setMaximumHeight(76)
            self.control_curve_factor = QtWidgets.QDoubleSpinBox()
            self.control_curve_factor.setRange(-3.402823466e38,3.402823466e38)
            self.control_curve_factor.setDecimals(3)
            self.control_curve_factor.setSingleStep(.1)
            self.control_curve_factor.setValue(1.)
            self.control_curve_color_mode = QtWidgets.QComboBox()
            self.control_curve_color_mode.addItem("按左右侧", "side")
            self.control_curve_color_mode.addItem("按控制类型", "type")
            self.control_curve_skin = QtWidgets.QLineEdit()
            self.control_curve_skin.setPlaceholderText("用于尺寸检测的 Skin 网格路径")
            self.control_curve_mirror_side = QtWidgets.QComboBox()
            self.control_curve_mirror_side.addItem("右侧 → 左侧", "R")
            self.control_curve_mirror_side.addItem("左侧 → 右侧", "L")
            self.control_curve_custom_source = QtWidgets.QLineEdit()
            self.control_curve_custom_source.setPlaceholderText(
                "自定义 NURBS 曲线 Transform 路径")
            group, form = self._group("09 · Control Curves", [
                ("目标控制器", self.control_curve_targets),
                ("缩放倍率", self.control_curve_factor),
                ("颜色规则", self.control_curve_color_mode),
                ("Skin 网格", self.control_curve_skin),
                ("镜像方向", self.control_curve_mirror_side),
                ("自定义曲线", self.control_curve_custom_source)])
            form.addRow(self._button("缩放控制曲线", self._scale_control_curves))
            form.addRow(self._button("按 Skin 自动缩放", self._auto_scale_control_curves))
            rotation_row=QtWidgets.QWidget()
            rotation_layout=QtWidgets.QHBoxLayout(rotation_row)
            rotation_layout.setContentsMargins(0,0,0,0)
            for axis in 'xyz':
                rotation_layout.addWidget(self._button(axis.upper()+' 90°',
                    lambda axis=axis:self._snap_rotate_control_curves(axis)))
            form.addRow('旋转曲线',rotation_row)
            self.control_curve_palette_index=0
            self.control_curve_custom_rgb=None
            palette=QtWidgets.QWidget()
            palette_layout=QtWidgets.QGridLayout(palette)
            palette_layout.setContentsMargins(0,0,0,0)
            palette_layout.setSpacing(2)
            self.control_curve_palette_buttons=QtWidgets.QButtonGroup(self)
            self.control_curve_palette_buttons.setExclusive(True)
            for index,rgb in enumerate(self.controller.control_curve_palette_colors()):
                button=QtWidgets.QPushButton('')
                button.setCheckable(True)
                button.setChecked(index==0)
                button.setToolTip('Maya 颜色索引 '+str(index))
                button.setMinimumSize(15,20)
                red,green,blue=(round(value*255) for value in rgb)
                button.setStyleSheet('QPushButton { background-color: rgb(%d,%d,%d); border: 1px solid #555; } '
                    'QPushButton:checked { border: 2px solid white; }'%(red,green,blue))
                button.clicked.connect(lambda checked=False,index=index:self._select_control_curve_palette(index))
                self.control_curve_palette_buttons.addButton(button,index)
                palette_layout.addWidget(button,index//16,index%16)
            form.addRow('原版调色板',palette)
            self.control_curve_palette_label=QtWidgets.QLabel('索引 0')
            form.addRow(self.control_curve_palette_label)
            form.addRow(self._button('编辑调色板颜色',self._choose_control_curve_palette_rgb))
            form.addRow(self._button('设置颜色',self._set_control_curve_palette))
            self.control_curve_width=QtWidgets.QSpinBox()
            self.control_curve_width.setRange(-1,100)
            self.control_curve_width.setValue(5)
            form.addRow('曲线宽度',self.control_curve_width)
            form.addRow(self._button('设置宽度',self._set_control_curve_width))
            self.control_curve_select_type=QtWidgets.QComboBox()
            self.control_curve_select_side=QtWidgets.QComboBox()
            from adv_py.core.control_curve_selection import CONTROL_CURVE_TYPES,CONTROL_CURVE_SIDES
            for value in CONTROL_CURVE_TYPES:self.control_curve_select_type.addItem(value,value)
            for value,label in zip(CONTROL_CURVE_SIDES,('右侧','左侧','中间','全部')):
                self.control_curve_select_side.addItem(label,value)
            self.control_curve_select_side.setCurrentIndex(3)
            form.addRow('选择类型',self.control_curve_select_type)
            form.addRow('选择侧别',self.control_curve_select_side)
            form.addRow(self._button('选择控制器',self._select_control_curves))
            form.addRow(self._button("设置控制曲线颜色", self._color_control_curves))
            form.addRow(self._button("镜像控制曲线形状", self._mirror_control_curves))
            form.addRow(self._button("替换控制器图标", self._swap_control_curves))
            form.addRow(self._button("Copy to SubControls",
                                     lambda: self._copy_control_curves("Sub")))
            form.addRow(self._button("Copy to ExtraControls",
                                     lambda: self._copy_control_curves("Extra")))
            stack.addWidget(group)

            self.control_orient_targets = QtWidgets.QPlainTextEdit()
            self.control_orient_targets.setPlaceholderText(
                "留空使用当前选择；也可每行填写一个控制器路径")
            self.control_orient_targets.setMaximumHeight(76)
            self.control_orient_primary = QtWidgets.QComboBox()
            self.control_orient_secondary = QtWidgets.QComboBox()
            for axis in ("X", "Y", "Z", "-X", "-Y", "-Z"):
                self.control_orient_primary.addItem(axis, axis)
                self.control_orient_secondary.addItem(axis, axis)
            self.control_orient_secondary.setCurrentIndex(1)
            self.control_orient_primary.currentIndexChanged.connect(self._control_orient_axis_changed)
            self.control_orient_secondary.currentIndexChanged.connect(self._control_orient_axis_changed)
            self.control_orient_world_orient = QtWidgets.QCheckBox("World Orient")
            self.control_orient_world_match_mode = QtWidgets.QCheckBox("World Match")
            self.control_orient_world_orient.toggled.connect(
                self._control_orient_mode_changed)
            self.control_orient_world_match_mode.toggled.connect(
                self._control_orient_mode_changed)
            self.control_orient_curve_unaffected = QtWidgets.QCheckBox(
                "改变方向后保持曲线世界形状")
            self.control_orient_curve_unaffected.setChecked(True)
            self.control_orient_mirror = QtWidgets.QCheckBox("同时设置对侧控制器")
            self.control_orient_mirror.setChecked(True)
            self.control_orient_mirrored_behavior = QtWidgets.QCheckBox(
                "左右同轴旋转产生对称动作")
            self.control_orient_mirrored_behavior.setChecked(True)
            self.control_orient_mirrored_translate = QtWidgets.QCheckBox("镜像平移")
            self.control_orient_attach_mirror = QtWidgets.QCheckBox("重新附着时镜像")
            self.control_orient_attach_mirror.setChecked(True)
            group, form = self._group("10 · Control Orient", [
                ("目标控制器", self.control_orient_targets),
                ("Primary Axis", self.control_orient_primary),
                ("Secondary Axis", self.control_orient_secondary),
                ("World Orient", self.control_orient_world_orient),
                ("World Match", self.control_orient_world_match_mode),
                ("Curve Unaffected", self.control_orient_curve_unaffected),
                ("Mirror", self.control_orient_mirror),
                ("Mirrored Behavior",
                 self.control_orient_mirrored_behavior),
                ("Mirrored Translate", self.control_orient_mirrored_translate)])
            form.addRow(self._button("设置控制器局部轴", self._set_control_orient_axis))
            form.addRow(self._button("分离全部控制器", self._detach_control_orient_custom))
            form.addRow(self.control_orient_attach_mirror)
            form.addRow(self._button("重新附着全部控制器", self._attach_control_orient_custom))
            stack.addWidget(group)

            self.control_mesh_mirror = QtWidgets.QCheckBox("自动创建对侧 Control Mesh")
            self.control_mesh_mirror.setChecked(True)
            group, form = self._group("10A · Control Mesh", [
                ("镜像", self.control_mesh_mirror)])
            form.addRow(QtWidgets.QLabel("先选一件模型上的面，最后选择控制器"))
            form.addRow(self._button("创建 Control Mesh",
                                     self._create_control_mesh))
            form.addRow(QtWidgets.QLabel("批量：选择已蒙皮网格对象"))
            form.addRow(self._button("批量创建 Control Meshes",
                                     self._create_control_meshes))
            form.addRow(self._button("着色并扩展 Control Meshes",
                                     self._colorize_control_meshes))
            form.addRow(self._button("创建 IK Control Meshes",
                                     self._create_ik_control_meshes))
            form.addRow(self._button("删除所选 Control Meshes",
                                     self._delete_selected_control_meshes))
            form.addRow(self._button("删除全部 Control Meshes",
                                     self._delete_all_control_meshes))
            stack.addWidget(group)

            group, form = self._group("10B · Game Engine", [])
            form.addRow('Root Motion Joint：', self._native_button_row(
                ('创建', self._create_game_engine_root_motion),
                ('删除', self._delete_game_engine_root_motion)))
            form.addRow('Scale Behaviour：', self._native_button_row(
                ('启用', self._enable_game_engine_scaling),
                ('禁用', self._disable_game_engine_scaling)))
            form.addRow(QtWidgets.QLabel('Custom oriented GameSkeleton：'))
            self.game_joint_primary = QtWidgets.QComboBox()
            self.game_joint_secondary = QtWidgets.QComboBox()
            self.game_joint_primary.addItems(('X', 'Y', 'Z'))
            self.game_joint_secondary.addItems(('X', 'Y', 'Z'))
            self.game_joint_secondary.setCurrentIndex(1)
            form.addRow('主轴', self.game_joint_primary)
            form.addRow('次轴', self.game_joint_secondary)
            form.addRow(self._native_button_row(
                ('创建', lambda: self._custom_orient_joints('create')),
                ('删除', lambda: self._custom_orient_joints('delete'))))
            form.addRow(self._button('显示坐标轴', lambda: self._custom_orient_joints('show_axis')))
            form.addRow(self._native_button_row(
                ('连接', lambda: self._custom_orient_joints('connect')),
                ('断开', lambda: self._custom_orient_joints('disconnect'))))
            form.addRow(self._button('转移蒙皮', lambda: self._custom_orient_joints('transfer_skin')))
            stack.addWidget(group)

            group, form = self._group("11 · Unreal Joints", [])
            form.addRow(QtWidgets.QLabel('Unreal Mannequin Skeleton：'))
            form.addRow(self._button('请先阅读', self._read_unreal_mannequin_note))
            form.addRow(self._native_button_row(
                ('创建', self._create_unreal_mannequin),
                ('删除', self._delete_unreal_mannequin)))
            form.addRow(self._button('转移蒙皮', self._transfer_unreal_mannequin_skin))
            form.addRow(QtWidgets.QLabel('或者：将关节重命名为 Mannequin 名称'))
            form.addRow(self._button('重命名为 Unreal', self._rename_to_unreal))
            form.addRow(self._button('恢复', self._restore_unreal_names))
            more = QtWidgets.QCheckBox('更多')
            form.addRow(more)
            more_group, more_form = self._group('更多选项', [])
            more_form.addRow('Unreal Root & IK joints：', self._native_button_row(
                ('创建', self._create_unreal_joints),
                ('删除', self._delete_unreal_joints)))
            more_form.addRow('Unreal TwistJoints hierarchy：', self._native_button_row(
                ('创建', self._create_unreal_twist_hierarchy),
                ('删除', self._delete_unreal_twist_hierarchy)))
            mannequin_file_widget, self.mannequin_file = self._file_field(
                'ADV asUnreal.ma', filter_text='Maya ASCII (*.ma)')
            self.mannequin_file.setPlaceholderText('留空使用原版 asUnreal.ma')
            more_form.addRow('原版模板路径（可留空）', mannequin_file_widget)
            more_group.setVisible(False)
            more.toggled.connect(more_group.setVisible)
            form.addRow(more_group)
            stack.addWidget(group)

            self.partial_include_controller = QtWidgets.QCheckBox("包含控制器")
            self.partial_multi_count = QtWidgets.QSpinBox()
            self.partial_multi_count.setRange(2, 128)
            self.partial_multi_count.setValue(12)
            self.partial_multi_bind = QtWidgets.QCheckBox("自动加入现有蒙皮")
            group, form = self._group("12 · Partial Joints", [
                ("单段", self.partial_include_controller),
                ("多段关节数", self.partial_multi_count),
                ("多段蒙皮", self.partial_multi_bind)])
            form.addRow(self._button("创建 Partial Joints",
                                     self._create_partial_joints))
            form.addRow(self._button("删除 Partial Joints",
                                     self._delete_partial_joints))
            form.addRow(self._button("创建 Multi Partial Joints",
                                     self._create_multi_partial_joints))
            form.addRow(self._button("删除 Multi Partial Joints",
                                     self._delete_partial_joints))
            stack.addWidget(group)
            self._spine_replace_mode_changed()
            stack.addStretch(1)
            return page

        def _spine_replace_mode_changed(self):
            fk = self.spine_replace_mode.currentData() == "fk"
            self.spine_replace_substeps.setEnabled(fk)
            if not fk:
                self.spine_replace_substeps.setValue(1)
                self.spine_replace_mesh_gate.setChecked(True)
            self.spine_replace_mesh_gate.setEnabled(fk)

        def _skin_page(self):
            page, stack = self._page()
            group, form = self._group("00 · 原版 Skinning", [])
            form.addRow(QtWidgets.QLabel("先选择待绑定网格，再追加变形关节并设置 Maya 绑定选项。"))
            form.addRow(self._button("追加选择变形关节", self._select_deform_joints))
            form.addRow(self._button("设置 Smooth Bind 选项", self._set_smooth_bind_options))
            stack.addWidget(group)
            self.mesh = QtWidgets.QLineEdit()
            self.mesh.setPlaceholderText("|BodyMesh")
            self.skin = QtWidgets.QLineEdit("AdvPy_BodySkin")
            self.influences = QtWidgets.QPlainTextEdit()
            self.influences.setPlaceholderText("每行一个完整关节路径")
            self.influences.setMaximumHeight(95)
            group, form = self._group("01 · 建立 Skin", [
                ("网格路径", self.mesh), ("Skin 名称", self.skin),
                ("影响关节", self.influences)])
            form.addRow(self._button("绑定当前网格", self._bind_skin,
                                      primary=True))
            stack.addWidget(group)

            weights_out, self.weights_export_document = self._file_field(
                "导出权重文档", save=True)
            weights_in, self.weights_import_document = self._file_field(
                "导入权重文档")
            mapping, self.mapping_document = self._file_field("映射文档")
            self.allow_missing = QtWidgets.QCheckBox("允许省略零权重关节")
            group, form = self._group("02 · 权重文档", [
                ("导出到", weights_out), ("从文件导入", weights_in),
                ("路径映射", mapping),
                ("缺失策略", self.allow_missing)])
            form.addRow(self._button("导出全部权重", self._export_skin))
            form.addRow(self._button("导入并复核权重", self._import_skin))
            stack.addWidget(group)

            self.surface_source_skin = QtWidgets.QLineEdit()
            self.surface_source_skin.setPlaceholderText("SourceSkin")
            self.surface_source_skin.setToolTip("导出源资产时使用；选择当前场景源网格时也作为转移来源")
            self.surface_source_mesh = QtWidgets.QLineEdit()
            self.surface_source_mesh.setPlaceholderText("|SourceMesh")
            self.surface_source_mesh.setToolTip("导出源资产时使用；选择当前场景源网格时也作为转移来源")
            asset_out, self.surface_asset_out = self._file_field(
                "导出蒙皮源资产", save=True)
            group, form = self._group("03 · 跨场景源资产", [
                ("源 Skin", self.surface_source_skin),
                ("源网格", self.surface_source_mesh),
                ("保存资产", asset_out)])
            form.addRow(self._button("导出网格与权重", self._export_skin_surface_source))
            stack.addWidget(group)

            self.surface_mode = QtWidgets.QComboBox()
            self.surface_mode.addItem("当前场景源网格", "scene")
            self.surface_mode.addItem("跨场景源资产", "asset")
            asset_in, self.surface_asset_in = self._file_field("读取蒙皮源资产")
            self.surface_target_skin = QtWidgets.QLineEdit()
            self.surface_target_skin.setPlaceholderText("TargetSkin")
            self.surface_target_mesh = QtWidgets.QLineEdit()
            self.surface_target_mesh.setPlaceholderText("|TargetMesh")
            self.surface_mapping_mode = QtWidgets.QComboBox()
            self.surface_mapping_mode.addItem("一对一路径映射", "mapping")
            self.surface_mapping_mode.addItem("一对多影响重分配", "redistribution")
            surface_mapping, self.surface_mapping = self._file_field("关节路径映射")
            surface_alignment, self.surface_alignment = self._file_field("三点刚体对齐")
            self.surface_distance = QtWidgets.QDoubleSpinBox()
            self.surface_distance.setRange(0., 1_000_000.)
            self.surface_distance.setDecimals(6)
            self.surface_distance.setSingleStep(.01)
            self.surface_distance.setValue(.01)
            self.surface_distance.setToolTip("目标顶点到源表面的最大允许距离，单位与场景一致")
            self.surface_discard = QtWidgets.QDoubleSpinBox()
            self.surface_discard.setRange(0., .999999)
            self.surface_discard.setDecimals(6)
            self.surface_discard.setSingleStep(.01)
            self.surface_discard.setValue(.000001)
            self.surface_discard.setToolTip("超过目标最大影响数时，允许裁掉的单顶点权重总量")
            self.surface_extra = QtWidgets.QCheckBox("允许目标多出关节，并清零其目标权重")
            self.surface_missing = QtWidgets.QCheckBox("映射可省略源中的零权重关节")
            group, form = self._group("04 · 跨拓扑权重转移", [
                ("来源方式", self.surface_mode),
                ("源资产", asset_in),
                ("目标 Skin", self.surface_target_skin),
                ("目标网格", self.surface_target_mesh),
                ("关节转换方式", self.surface_mapping_mode),
                ("关节转换文档", surface_mapping),
                ("刚体对齐", surface_alignment),
                ("最大表面距离", self.surface_distance),
                ("最大裁剪损失", self.surface_discard),
                ("目标关节策略", self.surface_extra),
                ("源关节策略", self.surface_missing)])
            form.addRow(self._button("预检并转移权重", self._transfer_skin_surface,
                                      primary=True))
            form.addRow(self._button("引用模型改拓扑后重绑并转移",
                                     self._rebind_skin_from_source_asset))
            stack.addWidget(group)
            self.surface_mode.currentIndexChanged.connect(self._surface_mode_changed)
            self._surface_mode_changed()
            group, form = self._group("05 · Shapers", [])
            shapers_status = self.controller.shapers_plugin_status()
            self.shapers_plugin_root = QtWidgets.QLineEdit(
                str(shapers_status.root) if shapers_status.root else "")
            self.shapers_plugin_root.setPlaceholderText(
                "AdvancedSkeletonFiles/div/shapers")
            root_row = QtWidgets.QHBoxLayout()
            root_row.addWidget(self.shapers_plugin_root, 1)
            browse = QtWidgets.QPushButton("浏览…")
            browse.clicked.connect(self._choose_shapers_plugin_root)
            root_row.addWidget(browse)
            form.addRow("插件目录", root_row)
            self.shapers_plugin_mode = QtWidgets.QComboBox()
            for label, value in (("自动选择", "automatic"),
                                 ("原生 C++", "native"),
                                 ("Python", "python")):
                self.shapers_plugin_mode.addItem(label, value)
            self.shapers_plugin_mode.setCurrentIndex(
                self.shapers_plugin_mode.findData(shapers_status.mode))
            form.addRow("实现方式", self.shapers_plugin_mode)
            self.shapers_plugin_autoload = QtWidgets.QCheckBox(
                "Maya 启动时自动加载")
            self.shapers_plugin_autoload.setChecked(shapers_status.autoload)
            self.shapers_plugin_status_label = QtWidgets.QLabel()
            self._refresh_shapers_plugin_status(shapers_status)
            form.addRow(self.shapers_plugin_autoload)
            form.addRow("当前状态", self.shapers_plugin_status_label)
            form.addRow(self._button("设置并加载插件", self._setup_shapers_plugin))
            self.shapers_loop_controls = QtWidgets.QSpinBox()
            self.shapers_loop_controls.setRange(3, 99)
            self.shapers_loop_controls.setValue(4)
            self.shapers_loop_snap = QtWidgets.QCheckBox("顶点吸附")
            self.shapers_loop_snap.setChecked(True)
            loop_row = QtWidgets.QHBoxLayout()
            loop_row.addWidget(self.shapers_loop_controls)
            loop_row.addWidget(self.shapers_loop_snap)
            form.addRow("闭环", loop_row)
            self.shapers_bridge_controls = QtWidgets.QSpinBox()
            self.shapers_bridge_controls.setRange(3, 99)
            self.shapers_bridge_controls.setValue(3)
            self.shapers_bridge_snap = QtWidgets.QCheckBox("顶点吸附")
            bridge_row = QtWidgets.QHBoxLayout()
            bridge_row.addWidget(self.shapers_bridge_controls)
            bridge_row.addWidget(self.shapers_bridge_snap)
            form.addRow("桥接", bridge_row)
            self.shapers_mirror = QtWidgets.QCheckBox("镜像")
            self.shapers_mirror.setChecked(True)
            form.addRow(self.shapers_mirror)
            form.addRow(self._button("创建 Shapers", self._create_shapers))
            form.addRow(QtWidgets.QLabel("选择或重绑当前角色已有的 Shapers 变形器。"))
            shapers_select = self._button("选择", self._select_shapers)
            shapers_rebind = self._button("重新绑定", self._rebind_shapers)
            for button, operation in ((shapers_select, "select"),
                                      (shapers_rebind, "rebind")):
                button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                button.customContextMenuRequested.connect(
                    lambda point, b=button, op=operation:
                    self._shapers_context_menu(b, point, op))
                form.addRow(button)
            form.addRow(self._button("删除", self._delete_shapers))
            stack.addWidget(group)
            group, form = self._group("05 · Delta Mush", [])
            form.addRow(QtWidgets.QLabel("选择已蒙皮的多边形网格。"))
            form.addRow(self._button("硬化权重", self._harden_delta_mush_weights))
            form.addRow(self._button("应用 Delta Mush", self._apply_delta_mush))
            form.addRow(self._button("Bake DeltaMush", self._bake_delta_mush))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _surface_mode_changed(self):
            scene_source = self.surface_mode.currentData() == "scene"
            self.surface_asset_in.setEnabled(not scene_source)

        def _animation_page(self):
            page, stack = self._page()
            pose_out, self.pose_export_document = self._file_field(
                "导出姿态文档", save=True)
            pose_in, self.pose_import_document = self._file_field("导入姿态文档")
            group, form = self._group("01 · 当前姿态", [
                ("导出到", pose_out), ("从文件导入", pose_in)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("捕获姿态", self._capture_pose))
            row.addWidget(self._button("应用姿态", self._apply_pose))
            form.addRow(row)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("返回构建姿态", self._go_to_build_pose))
            row.addWidget(self._button("设置构建姿态", self._set_build_pose))
            form.addRow(row)
            stack.addWidget(group)

            clip_out, self.animation_export_document = self._file_field(
                "导出动画文档", save=True)
            clip_in, self.animation_import_document = self._file_field(
                "导入动画文档")
            frames = QtWidgets.QWidget()
            frame_row = QtWidgets.QHBoxLayout(frames)
            frame_row.setContentsMargins(0, 0, 0, 0)
            self.start_frame = QtWidgets.QSpinBox()
            self.end_frame = QtWidgets.QSpinBox()
            self.frame_step = QtWidgets.QSpinBox()
            for field in (self.start_frame, self.end_frame, self.frame_step):
                field.setRange(-100000, 100000)
                field.setMaximumWidth(82)
            self.start_frame.setValue(1)
            self.end_frame.setValue(24)
            self.frame_step.setRange(1, 100000)
            self.frame_step.setValue(1)
            for label, field in (("起始", self.start_frame),
                                 ("结束", self.end_frame),
                                 ("步长", self.frame_step)):
                frame_row.addWidget(QtWidgets.QLabel(label))
                frame_row.addWidget(field)
            group, form = self._group("02 · 全身动画", [
                ("导出到", clip_out), ("从文件导入", clip_in),
                ("采样帧", frames)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("捕获动画", self._capture_animation))
            row.addWidget(self._button("应用动画", self._apply_animation))
            form.addRow(row)
            form.addRow(self._button("当前帧完整写键", self._key_current_pose))
            stack.addWidget(group)

            group, form = self._group("03 · 动画通道", [])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("启用四肢动画", self._enable_limb_animation))
            row.addWidget(self._button("启用拉伸匹配", self._enable_stretch_matching))
            form.addRow(row)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("启用可变脊柱", self._enable_spline_animation))
            row.addWidget(self._button("启用空间动画", self._enable_space_animation))
            form.addRow(row)
            form.addRow(self._button("升级旧 Spline FKIK", self._upgrade_source_spline_mode))
            form.addRow(self._button("升级旧 Spline 对齐参考", self._upgrade_source_spline_alignment))
            stack.addWidget(group)

            self.limb_part = QtWidgets.QComboBox()
            self.limb_part.addItem("手臂", "arm")
            self.limb_part.addItem("腿部", "leg")
            self.limb_side = QtWidgets.QComboBox()
            self.limb_side.addItem("右侧", "R")
            self.limb_side.addItem("左侧", "L")
            self.limb_side.addItem("中线", "M")
            self.limb_mode = QtWidgets.QComboBox()
            self.limb_mode.addItem("转为 IK", "ik")
            self.limb_mode.addItem("转为 FK", "fk")
            self.spine_mode = QtWidgets.QComboBox()
            self.spine_mode.addItem("转为 IK", "ik")
            self.spine_mode.addItem("转为 FK", "fk")
            self.spline_system = QtWidgets.QComboBox()
            self.spline_system.addItem("读取后选择 Spline 系统", None)
            group, form = self._group("04 · 区间模式转换", [
                ("部位", self.limb_part), ("侧别", self.limb_side),
                ("四肢目标模式", self.limb_mode),
                ("脊柱目标模式", self.spine_mode),
                ("Spline 系统", self.spline_system)])
            form.addRow(self._button("读取当前角色 IK 系统", self._load_limb_systems))
            form.addRow(self._button("当前姿态切换来源 IK 系统", self._match_source_limb_mode))
            form.addRow(self._button("读取当前角色 Spline 系统", self._load_spline_systems))
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("对齐 FK / IK", lambda: self._match_source_spline_mode(True)))
            row.addWidget(self._button("切换 FK / IK", lambda: self._match_source_spline_mode(False)))
            form.addRow(row)
            form.addRow(QtWidgets.QLabel("使用上方的起始帧、结束帧和采样步长。"))
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("转换四肢模式", self._bake_limb_mode))
            row.addWidget(self._button("转换脊柱模式", self._bake_spine_mode))
            form.addRow(row)
            stack.addWidget(group)

            self.space_key = QtWidgets.QComboBox()
            for label, key in (("头部", "head"), ("右手", "hand_R"),
                               ("左手", "hand_L"), ("右脚", "foot_R"),
                               ("左脚", "foot_L")):
                self.space_key.addItem(label, key)
            self.space_mode = QtWidgets.QComboBox()
            self.space_mode.addItem("跟随身体", "body")
            self.space_mode.addItem("跟随全局", "global")
            self.space_frame = QtWidgets.QSpinBox()
            self.space_frame.setRange(-100000, 100000)
            self.space_frame.setValue(1)
            group, form = self._group("05 · 控制空间事件", [
                ("控制位置", self.space_key), ("目标空间", self.space_mode),
                ("切换帧", self.space_frame)])
            form.addRow(self._button("在指定帧切换空间", self._switch_animation_space))
            stack.addWidget(group)

            group, form = self._group("08 · 原版 Driving Systems", [])
            self.original_driving_mode = QtWidgets.QComboBox()
            self.original_driving_mode.addItems(["创建新控制器","使用已有控制器","从所选对象驱动"])
            self.original_driving_control = QtWidgets.QComboBox()
            self.original_driving_control.setEditable(True)
            self.original_driving_attribute = QtWidgets.QLineEdit()
            self.original_driving_attribute.setPlaceholderText("留空时自动命名 driver1、driver2…")
            self.original_driving_mirror = QtWidgets.QCheckBox("镜像")
            self.original_driving_mirror.setChecked(True)
            self.original_driving_q_rotations = QtWidgets.QCheckBox("QRotations")
            self.original_driving_q_rotations.setChecked(True)
            self.original_driving_mode.currentIndexChanged.connect(self._original_driving_mode_changed)
            self.original_driving_test_symmetry = QtWidgets.QCheckBox("编辑时预览对称")
            self.original_driving_test_symmetry.setChecked(True)
            self.original_driving_affected = QtWidgets.QCheckBox("仅显示受影响控制器")
            form.addRow("驱动方式",self.original_driving_mode)
            form.addRow("控制器名称",self.original_driving_control)
            form.addRow("属性名称",self.original_driving_attribute)
            form.addRow(self.original_driving_mirror)
            form.addRow(self.original_driving_q_rotations)
            form.addRow(self._button("创建 Driving System",lambda:self._original_driving_action("create")))
            self.original_driving_targets = QtWidgets.QComboBox()
            form.addRow("驱动属性",self.original_driving_targets)
            form.addRow(self._button("刷新原版驱动属性",self._original_driving_refresh))
            for label,action in (("查看驱动 SDK 曲线","graph"),("更新驱动软范围","range"),("镜像右侧 SDK 到左侧","mirror"),
                                 ("静音所选 SDK","mute"),("恢复 SDK 驱动","unmute"),("退出驱动预览","remove_preview")):
                form.addRow(self._button(label,lambda action=action:self._original_driving_action(action)))
            form.addRow(self.original_driving_test_symmetry)
            form.addRow(self.original_driving_affected)
            for label,action in (("自动查找并编辑驱动","auto_edit"),("编辑所选驱动属性","edit"),("删除所选驱动属性","delete"),
                                 ("应用 Driving System 编辑","apply_edit"),("取消 Driving System 编辑","cancel_edit"),
                                 ("优化驱动控制器位置","optimize"),("升级旧 SDK 曲线","upgrade_curves")):
                form.addRow(self._button(label,lambda action=action:self._original_driving_action(action)))
            self.original_driving_driver = QtWidgets.QLineEdit()
            self.original_driving_driven = QtWidgets.QLineEdit()
            self.original_driving_driver_value = QtWidgets.QDoubleSpinBox()
            self.original_driving_driven_value = QtWidgets.QDoubleSpinBox()
            for box in (self.original_driving_driver_value,self.original_driving_driven_value):
                box.setDecimals(3);box.setRange(-100000,100000)
            self.original_driving_driver_value.setValue(10)
            self.original_driving_driven_value.setValue(1)
            form.addRow("驱动通道",self.original_driving_driver)
            form.addRow(self._button("记录所选驱动通道",lambda:self._original_driving_record("driver")))
            form.addRow("被驱动通道",self.original_driving_driven)
            form.addRow(self._button("记录所选被驱动通道",lambda:self._original_driving_record("driven")))
            form.addRow("驱动值",self.original_driving_driver_value)
            form.addRow("目标值",self.original_driving_driven_value)
            form.addRow(self._button("建立原版 SDK 控制层",lambda:self._original_driving_action("sdk_layer")))
            form.addRow(self._button("写入原版 SDK 键",lambda:self._original_driving_action("sdk_key")))
            self._original_driving_mode_changed()
            stack.addWidget(group)

            group, form = self._group("09 · 原版 Pose Functions", [])
            self.original_pose_name = QtWidgets.QComboBox()
            self.original_pose_name.setEditable(True)
            self.original_pose_name.setEditText("pose1")
            self.original_pose_overwrite = QtWidgets.QCheckBox("覆盖同名姿态")
            form.addRow("姿态名称",self.original_pose_name)
            form.addRow(self.original_pose_overwrite)
            for label,action in (("刷新原版保存姿态","catalog"),("保存原版命名姿态","store"),("应用原版命名姿态","apply"),
                                 ("删除原版命名姿态","delete"),("所选通道加入原版构建姿态","add_build_pose"),
                                 ("返回原版构建姿态","neutral"),("禁用原版自定义朝向","disable_orients"),("启用原版自定义朝向","enable_orients")):
                form.addRow(self._button(label,lambda action=action:self._original_pose_functions(action)))
            stack.addWidget(group)

            self.corrective_q_rotations = QtWidgets.QCheckBox("QRotations")
            self.corrective_q_rotations.setChecked(True)
            self.corrective_use_softmods = QtWidgets.QCheckBox("使用 SoftMods")
            self.corrective_mirror = QtWidgets.QCheckBox("镜像")
            self.corrective_mirror.setChecked(True)
            group, form = self._group("07 · 原版 Corrective Shapes", [])
            form.addRow(QtWidgets.QLabel("先摆出需要修正的姿态，再选择角色网格。"))
            form.addRow(self.corrective_q_rotations)
            form.addRow(self.corrective_use_softmods)
            form.addRow(self._button("创建 Corrective 形状",lambda:self._corrective_shapes("create")))
            self.corrective_softmod_button = self._button("Corrective SoftMod 工具",lambda:self._corrective_shapes("softmod"))
            self.corrective_softmod_button.setVisible(False)
            self.corrective_use_softmods.toggled.connect(self.corrective_softmod_button.setVisible)
            form.addRow(self.corrective_softmod_button)
            form.addRow(QtWidgets.QLabel("右键点击编辑、删除或曲线按钮，选择已有 Corrective 目标。"))
            row = QtWidgets.QHBoxLayout()
            for label,action in (("编辑 Corrective","edit"),("删除 Corrective","delete"),("Corrective 曲线","graph")):
                button = self._button(label,lambda action=action:self._corrective_select_action(action))
                button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                button.customContextMenuRequested.connect(lambda point,button=button,action=action:self._corrective_popup(button,action,point))
                row.addWidget(button)
            form.addRow(row)
            form.addRow(self.corrective_mirror)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("应用 Corrective",lambda:self._corrective_shapes("apply")))
            row.addWidget(self._button("取消 Corrective",lambda:self._corrective_shapes("cancel")))
            form.addRow(row)
            self.corrective_targets = QtWidgets.QComboBox()
            form.addRow("已有目标",self.corrective_targets)
            form.addRow(self._button("刷新 Corrective 目标",self._corrective_refresh))
            self.corrective_source = QtWidgets.QLineEdit()
            self.corrective_destination = QtWidgets.QLineEdit()
            form.addRow("烘焙来源网格",self.corrective_source)
            form.addRow(self._button("记录 Corrective 烘焙来源",lambda:self._corrective_record_mesh("source")))
            form.addRow("烘焙目标网格",self.corrective_destination)
            form.addRow(self._button("记录 Corrective 烘焙目标",lambda:self._corrective_record_mesh("destination")))
            self.corrective_axes = {}
            row = QtWidgets.QHBoxLayout()
            for label in ("+x","+y","+z","-x","-y","-z"):
                box = QtWidgets.QCheckBox(label)
                box.setChecked(True)
                self.corrective_axes[label] = box
                row.addWidget(box)
            form.addRow("烘焙旋转方向",row)
            form.addRow(self._button("烘焙到 Corrective",lambda:self._corrective_shapes("bake")))
            form.addRow(self._button("批量编辑全部 Corrective",lambda:self._corrective_shapes("batch")))
            form.addRow(QtWidgets.QLabel("Curve-Based Deformations"))
            self.corrective_curve_mesh = QtWidgets.QLineEdit()
            self.corrective_curve_control = QtWidgets.QLineEdit()
            form.addRow("曲线变形网格",self.corrective_curve_mesh)
            form.addRow(self._button("记录曲线变形网格",lambda:self._corrective_curve_record("mesh")))
            form.addRow("FK 控制器",self.corrective_curve_control)
            form.addRow(self._button("记录曲线变形控制器",lambda:self._corrective_curve_record("control")))
            for label,action in (("隐藏曲线变形来源","hide"),("创建变形曲线","create"),("解除曲线绑定","unbind"),
                                 ("重新绑定曲线","rebind"),("创建曲线测试动画","animate"),("创建局部变形网格","mesh"),
                                 ("显示原始网格","original"),("显示变形网格","new"),("烘焙曲线变形为 Corrective","bake"),
                                 ("清理曲线变形设置","cleanup")):
                form.addRow(self._button(label,lambda action=action:self._corrective_curve_shapes(action)))
            stack.addWidget(group)

            self.preset_directory = QtWidgets.QLineEdit()
            self.preset_directory.setPlaceholderText("含姿态或动画 JSON 的文件夹")
            self.preset_names = QtWidgets.QComboBox()
            group, form = self._group("06 · 角色预设", [
                ("预设目录", self.preset_directory),
                ("可用预设", self.preset_names)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("检查兼容性", self._inspect_presets))
            row.addWidget(self._button("应用所选预设", self._apply_preset))
            form.addRow(row)
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _add_face_original_option(self, form, option):
            if option.items:
                control = QtWidgets.QComboBox()
                control.addItems(option.items)
                control.setCurrentText(option.default)
                form.addRow(option.label, control)
                signal = control.currentIndexChanged
            else:
                control = QtWidgets.QCheckBox(option.label)
                control.setChecked(option.default)
                form.addRow(control)
                signal = control.toggled
            self.face_original_option_controls[option.attribute] = control
            if option.attribute == 'MultiSkinClusters':
                control.setEnabled(self.controller.face_multi_skin_clusters_supported())
            signal.connect(lambda _, name=option.attribute:
                self._run('记录 Face '+name, lambda: self._face_original_option_changed(name)))

        def _face_page(self):
            page, stack = self._page()
            self.face_fit_state_controls={}
            self.face_pre_mask = QtWidgets.QLineEdit()
            self.face_pre_mask.setReadOnly(True)
            self.face_pre_face = QtWidgets.QLineEdit()
            self.face_pre_face.setReadOnly(True)
            self.face_pre_all_head = QtWidgets.QLineEdit()
            self.face_pre_all_head.setReadOnly(True)
            self.face_eye_head = QtWidgets.QLineEdit()
            self.face_eye_head.setReadOnly(True)
            self.face_eye_head.setPlaceholderText("Head_M（Face Pre 默认）")
            self.face_pre_skin=QtWidgets.QLineEdit()
            self.face_pre_skin.editingFinished.connect(self._face_skin_input_changed)
            group, form = self._group("00 · 面部输入", [
                ("Mask 多边形面", self.face_pre_mask),
                ("Face 网格", self.face_pre_face),
                ("All Head 网格", self.face_pre_all_head)])
            for label, record, reselect in (
                    ("Mask", self._face_record_mask, self._face_reselect_mask),
                    ("Face", self._face_record_face, self._face_reselect_face),
                    ("All Head", self._face_record_all_head,
                     self._face_reselect_all_head)):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(self._button(label, record))
                row.addWidget(self._button("重选 " + label, reselect))
                form.addRow(row)
            for label,part in (("记录所选上牙","UpperTeeth"),("记录所选下牙","LowerTeeth"),
                               ("记录所选眉毛","Eyebrow"),("记录所选睫毛","EyeLash")):
                form.addRow(self._button(label,lambda part=part: self._face_teeth_record(part)))
            form.addRow(self._button("升级旧版 Face Fit", self._face_upgrade_original_fit))
            self.face_fit_side_status = QtWidgets.QLabel("Fit 编辑侧：右侧")
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("编辑右侧", lambda: self._face_fit_switch_side("Right")))
            row.addWidget(self._button("编辑左侧", lambda: self._face_fit_switch_side("Left")))
            row.addWidget(self._button('关闭非对称', lambda: self._face_fit_display('side_off')))
            form.addRow(self.face_fit_side_status)
            form.addRow(row)
            form.addRow(self._button('show both sides', lambda: self._face_fit_display('show_both')))
            form.addRow(self._button('Model Check',self._face_original_model_check))
            from adv_py.core.original_face_options import ORIGINAL_FACE_OPTIONS
            self.face_original_option_controls = {}
            for option in ORIGINAL_FACE_OPTIONS:
                if not option.advanced:
                    self._add_face_original_option(form, option)
            self.face_include = self.face_original_option_controls['Include']
            self.face_simpler_eye_lid = self.face_original_option_controls['SimplerEyeLid']
            self.face_pre_advanced_toggle=QtWidgets.QCheckBox('advanced')
            self.face_pre_advanced=QtWidgets.QWidget()
            advanced_form=QtWidgets.QFormLayout(self.face_pre_advanced)
            advanced_form.setContentsMargins(0,0,0,0)
            self.face_pre_game_engine_options = QtWidgets.QWidget()
            game_options_form = QtWidgets.QFormLayout(self.face_pre_game_engine_options)
            game_options_form.setContentsMargins(0,0,0,0)
            for option in ORIGINAL_FACE_OPTIONS:
                if option.attribute in ('UseMaxInf', 'MaxInf'):
                    self._add_face_original_option(game_options_form, option)
            advanced_form.addRow(self.face_pre_game_engine_options)
            self.face_pre_game_engine_options.setVisible(False)
            advanced_form.addRow(QtWidgets.QLabel('不使用 AdvancedSkeleton 身体绑定时的 Face 输入'))
            advanced_form.addRow(self._button('Choose Head Joint',self._face_record_head_joint),self.face_eye_head)
            advanced_form.addRow('Face 几何上的 SkinCluster',self.face_pre_skin)
            for option in ORIGINAL_FACE_OPTIONS:
                if option.attribute in ('LegacyFaceJointOrient', 'SkipFaceJointOrient'):
                    self._add_face_original_option(advanced_form, option)
            advanced_form.addRow(self._button('AutoFit',self._face_auto_fit))
            offset_group = QtWidgets.QGroupBox('Offset Face（多头角色）')
            offset_layout = QtWidgets.QHBoxLayout(offset_group)
            for label, callback in (('Create', self._face_offset_create),
                                    ('import', self._face_offset_import), ('Update', self._face_offset_update)):
                offset_layout.addWidget(self._button(label, callback))
            advanced_form.addRow(offset_group)
            self.face_pre_advanced.setVisible(False)
            self.face_pre_advanced_toggle.toggled.connect(self.face_pre_advanced.setVisible)
            form.addRow(self.face_pre_advanced_toggle)
            form.addRow(self.face_pre_advanced)
            stack.addWidget(group)
            self.face_eye_right = QtWidgets.QLineEdit()
            self.face_eye_right.setReadOnly(True)
            self.face_eye_right.setPlaceholderText("|model:RightEye")
            self.face_eye_left = QtWidgets.QLineEdit()
            self.face_eye_left.setReadOnly(True)
            self.face_eye_left.setPlaceholderText("|model:LeftEye")
            group, form = self._group("00 · 眼球输入与控制", [
                ("右眼网格", self.face_eye_right),
                ("左眼网格", self.face_eye_left)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("记录所选右眼", self._face_record_right_eye))
            row.addWidget(self._button("记录所选左眼", self._face_record_left_eye))
            form.addRow(row)
            stack.addWidget(group)
            self.face_fit_right_eye = QtWidgets.QLineEdit()
            self.face_fit_right_eye.setReadOnly(True)
            self.face_fit_right_eye.setPlaceholderText("|model:RightEye")
            self.face_fit_left_eye = QtWidgets.QLineEdit()
            self.face_fit_left_eye.setReadOnly(True)
            self.face_fit_left_eye.setPlaceholderText("|model:LeftEye")
            self.face_fit_head = QtWidgets.QLineEdit("Head_M")
            self.face_fit_head.setReadOnly(True)
            group, form = self._group("01 · EyeBall Fit", [
                ("右眼网格", self.face_fit_right_eye),
                ("左眼网格", self.face_fit_left_eye),
                ("Head 关节", self.face_fit_head)])
            eye_ball_row=QtWidgets.QHBoxLayout()
            eye_ball_row.addWidget(self._button("建立 EyeBall Fit",
                                     self._face_fit_eye_ball, primary=True))
            eye_ball_row.addWidget(self._face_fit_state_check('EyeBall'))
            form.addRow(eye_ball_row)
            for section in ('Pupil','Iris'):
                row=self._native_button_row(
                    ('创建所选 '+section+' 边环 Fit',lambda section=section:self._face_fit_marker(section)),
                    ('重选',lambda section=section:self._face_fit_display('reselect',section)),
                    ('hide',lambda section=section:self._face_fit_display('hide',section)))
                row.layout().addWidget(self._face_fit_state_check(section))
                form.addRow(row)
            stack.addWidget(group)
            group, form = self._group("02 · EyeLid Fit", [])
            form.addRow(QtWidgets.QLabel(
                "选择 Face 网格闭合眼睑边环，可加选一至两个眼角顶点；按 Outer → Main → Inner 建立。"))
            for layer in ("Outer", "Main", "Inner"):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(self._button("EyeLid " + layer,
                    lambda layer=layer: self._face_fit_eye_lid(layer)))
                row.addWidget(self._face_fit_state_check('EyeLid',layer))
                row.addWidget(self._button("重选 " + layer,
                    lambda layer=layer: self._face_fit_eye_lid_reselect(layer)))
                row.addWidget(self._button('hide',
                    lambda layer=layer: self._face_fit_display('hide', 'EyeLid', layer)))
                form.addRow(row)
            form.addRow(self._button('EyeLid assist',
                lambda: self._face_fit_display('assist', 'EyeLid')))
            form.addRow(self._button("对称角色：右侧 Fit 镜像到左侧",
                                     self._face_fit_mirror_right_to_left))
            extra_lid = QtWidgets.QCheckBox('Optional extra EyeLidMain')
            extra_lid_row = QtWidgets.QWidget()
            extra_lid_layout = QtWidgets.QHBoxLayout(extra_lid_row)
            extra_lid_layout.setContentsMargins(0, 0, 0, 0)
            extra_lid_layout.addWidget(self._button('EyeLidMain2',
                lambda: self._face_fit_eye_lid('Main2')))
            extra_lid_layout.addWidget(self._face_fit_state_check('EyeLidMain2'))
            extra_lid_layout.addWidget(self._button('重选 Main2',
                lambda: self._face_fit_eye_lid_reselect('Main2')))
            extra_lid_layout.addWidget(self._button('hide',
                lambda: self._face_fit_display('hide', 'EyeLidMain2')))
            extra_lid_row.setVisible(False)
            extra_lid.toggled.connect(extra_lid_row.setVisible)
            form.addRow(extra_lid)
            form.addRow(extra_lid_row)
            stack.addWidget(group)
            group, form = self._group("03 · Lip Fit", [])
            form.addRow(QtWidgets.QLabel(
                "选择完整嘴唇边环，可加选三个顶点：上唇中心、下唇中心、右侧嘴角。按 Outer → Main → Inner 建立。"))
            for part in ("Outer","Main","Inner"):
                row=QtWidgets.QHBoxLayout()
                row.addWidget(self._button("Lip "+part,
                    lambda part=part: self._face_fit_lip(part)))
                row.addWidget(self._face_fit_state_check('Lip',part))
                row.addWidget(self._button("重选 "+part,
                    lambda part=part: self._face_fit_lip(part,reselect=True)))
                row.addWidget(self._button("交换上下",
                    lambda part=part: self._face_fit_lip_swap(part)))
                row.addWidget(self._button('hide',
                    lambda part=part: self._face_fit_display('hide', 'Lip', part)))
                form.addRow(row)
            form.addRow(self._button('Lip assist', lambda: self._face_fit_display('assist', 'Lip')))
            stack.addWidget(group)
            group, form = self._group("04 · Face 定位点", [])
            from adv_py.core.face_fit_markers import MARKER_SHADERS
            for section in MARKER_SHADERS:
                actions = self._native_button_row(
                    ('创建 Fit', lambda section=section: self._face_fit_marker(section)),
                    ('重选', lambda section=section: self._face_fit_display('reselect', section)),
                    ('hide', lambda section=section: self._face_fit_display('hide', section)))
                actions.layout().addWidget(self._face_fit_state_check(section))
                form.addRow(section, actions)
            for section,label in (('UpMidLo','创建 UpMidLo 分区定位器'),
                                  ('ForeHead','创建 ForeHead 边界与区域 Fit')):
                row=self._native_button_row(
                    (label,lambda section=section:self._face_fit_marker(section)),
                    ('hide',lambda section=section:self._face_fit_display('hide',section)))
                row.layout().addWidget(self._face_fit_state_check(section))
                form.addRow(row)
            stack.addWidget(group)
            group, form = self._group("05 · Tongue Fit", [])
            form.addRow(self._button("记录所选 Tongue 网格或组件",
                lambda: self._face_tongue("record")))
            tongue_row=self._native_button_row(
                ('创建 Tongue Fit',lambda:self._face_tongue('fit')),
                ('hide',lambda:self._face_fit_display('hide','Tongue')))
            tongue_row.layout().addWidget(self._face_fit_state_check('Tongue'))
            form.addRow(tongue_row)
            stack.addWidget(group)
            self.face_neutral = QtWidgets.QLineEdit()
            self.face_neutral.setPlaceholderText("|FaceNeutral")
            self.face_target = QtWidgets.QLineEdit()
            self.face_target.setPlaceholderText("|SmileTarget")
            self.face_name = QtWidgets.QLineEdit()
            self.face_name.setPlaceholderText("smile_R")
            self.face_kind = QtWidgets.QComboBox()
            self.face_kind.addItem("表情", "expression")
            self.face_kind.addItem("口型", "viseme")
            landmarks, self.face_landmarks_document = self._file_field("顶点标记文档")
            group, form = self._group("01 · 目标网格", [
                ("中性网格", self.face_neutral), ("目标路径", self.face_target),
                ("通道名称", self.face_name), ("通道类别", self.face_kind),
                ("顶点标记", landmarks)])
            form.addRow(self._button("从标记生成目标", self._face_generate))
            stack.addWidget(group)

            asset_out, self.face_asset_out = self._file_field("导出面部目标资产", save=True)
            asset_in, self.face_asset_in = self._file_field("导入面部目标资产")
            group, form = self._group("02 · 可移植目标资产", [
                ("导出到", asset_out), ("从文件导入", asset_in)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("导出目标资产", self._face_asset_export))
            row.addWidget(self._button("导入为目标网格", self._face_asset_import))
            form.addRow(row)
            stack.addWidget(group)

            specification, self.face_build_document = self._file_field("面部构建文档")
            self.face_control_name = QtWidgets.QLineEdit("AdvPy_FaceControls")
            self.face_deformer_name = QtWidgets.QLineEdit("AdvPy_FaceBlendShape")
            group, form = self._group("03 · 控制与变形器", [
                ("构建文档", specification), ("控制名称", self.face_control_name),
                ("变形器名称", self.face_deformer_name)])
            delete_row = QtWidgets.QHBoxLayout()
            delete_row.addWidget(self._button("Delete Adv",
                                             self._face_delete_advanced))
            self.face_keep_build_pose = QtWidgets.QCheckBox(
                "保留 Face 构建姿态记录")
            self.face_keep_build_pose.setChecked(True)
            delete_row.addWidget(self.face_keep_build_pose)
            form.addRow(delete_row)
            form.addRow(self._button("Toggle Fit/Adv",
                                     self._face_build_toggle_fit_advanced))
            form.addRow(self._button("检查 FaceSetup 输入",
                                     self._face_build_inspect_inputs))
            form.addRow(self._button("Build Advanced Face", self._face_original_build, primary=True))
            self.face_original_manual_restore = QtWidgets.QCheckBox("手动运行 RebuildRestore")
            form.addRow(self.face_original_manual_restore)
            form.addRow(self._button("RebuildRestore", self._face_original_restore))

            form.addRow(self._button("建立双侧眼睑关节与蒙皮",
                                     self._face_build_eye_lids))
            form.addRow(self._button("返回 Face 构建姿态",
                                     self._face_go_to_build_pose))
            form.addRow(self._button("设置 Face 构建姿态",
                                     self._face_set_build_pose))
            self.face_original_head = QtWidgets.QLineEdit()
            self.face_original_head.setPlaceholderText(
                "当前场景中的原版头部网格，例如 Source:model:skin")
            form.addRow("原版头部", self.face_original_head)
            form.addRow(self._button("迁移同拓扑原版眼睑权重",
                                     self._face_build_original_eye_lid_skin))
            self.face_outer_side = QtWidgets.QComboBox()
            self.face_outer_side.addItem("右眼", "Right")
            self.face_outer_side.addItem("左眼", "Left")
            self.face_lid_layer = QtWidgets.QComboBox()
            self.face_lid_layer.addItem("Outer", "Outer")
            self.face_lid_layer.addItem("Main", "Main")
            self.face_outer_arc = QtWidgets.QComboBox()
            self.face_outer_arc.addItem("上眼睑", "upper")
            self.face_outer_arc.addItem("下眼睑", "lower")
            self.face_outer_loaded_key = None
            self.face_outer_side.currentIndexChanged.connect(
                self._face_outer_selection_changed)
            self.face_lid_layer.currentIndexChanged.connect(
                self._face_outer_selection_changed)
            self.face_outer_arc.currentIndexChanged.connect(
                self._face_outer_selection_changed)
            eye_part = QtWidgets.QHBoxLayout()
            eye_part.addWidget(self.face_outer_side)
            eye_part.addWidget(self.face_lid_layer)
            eye_part.addWidget(self.face_outer_arc)
            form.addRow("眼睑闭眼修形", eye_part)
            self.face_outer_offsets = []
            offsets = QtWidgets.QHBoxLayout()
            for axis in "XYZ":
                field = QtWidgets.QDoubleSpinBox()
                field.setRange(-1000., 1000.)
                field.setDecimals(6)
                field.setSingleStep(.01)
                field.setToolTip("眨眼值为 10 时的局部 " + axis + " 位移")
                offsets.addWidget(QtWidgets.QLabel(axis))
                offsets.addWidget(field)
                self.face_outer_offsets.append(field)
            form.addRow("局部位移", offsets)
            outer_actions = QtWidgets.QHBoxLayout()
            outer_actions.addWidget(self._button("读取眼睑修形",
                                                 self._face_outer_blink_read))
            outer_actions.addWidget(self._button("应用眼睑修形",
                                                 self._face_outer_blink_apply))
            form.addRow(outer_actions)
            form.addRow(self._button("构建面部控制", self._face_build, primary=True))
            stack.addWidget(group)

            group, form = self._group("03E · 原版 Face ctrlBox", [])
            form.addRow(self._button("建立原版 Face 控制面板",self._face_build_ctrl_box))
            stack.addWidget(group)
            group, form = self._group("03D · Jaw 权重参考曲线", [])
            form.addRow(QtWidgets.QLabel(
                "使用 Jaw、Cheek、Nose、Throat Fit 标记与 upperLipOuterCurve，生成四条 Jaw 权重参考曲线。"))
            form.addRow(self._button("生成 Jaw 权重参考曲线",
                                     self._face_build_jaw_fit_curves))
            stack.addWidget(group)

            group, form = self._group("03I · Lip 绑定", [])
            form.addRow(self._button("建立 Lip Ribbon 与控制驱动",self._face_build_lip))

            stack.addWidget(group)
            self.face_lip_falloff_outer=QtWidgets.QSpinBox()
            self.face_lip_falloff_outer.setRange(0,9999); self.face_lip_falloff_outer.setValue(3)
            self.face_lip_falloff_inner=QtWidgets.QSpinBox()
            self.face_lip_falloff_inner.setRange(0,9999); self.face_lip_falloff_inner.setValue(2)
            self.face_lip_falloff_iterations=QtWidgets.QSpinBox()
            self.face_lip_falloff_iterations.setRange(0,9999); self.face_lip_falloff_iterations.setValue(5)
            self.face_lip_falloff_multi=QtWidgets.QCheckBox("Multi Skin Clusters")
            group, form = self._group("03G · Lip Falloff", [
                ("外侧扩展",self.face_lip_falloff_outer),
                ("内侧扩展",self.face_lip_falloff_inner),
                ("平滑迭代",self.face_lip_falloff_iterations),
                ("",self.face_lip_falloff_multi)])
            form.addRow(self._button("建立 Lip Falloff 权重层",lambda: self._face_lip_falloff("build")))
            form.addRow(self._button("预览范围",lambda: self._face_lip_falloff("preview")))
            form.addRow(self._button("更新范围与权重",lambda: self._face_lip_falloff("update")))
            stack.addWidget(group)
            self.face_cage_smooth=QtWidgets.QSpinBox()
            self.face_cage_smooth.setRange(0,9999); self.face_cage_smooth.setValue(0)
            group, form = self._group("03K · Face Cage", [("平滑轮数",self.face_cage_smooth)])
            for label,action in (("建立 Face Cage 与投射控制","build"),("Cage 权重转到模型","transfer"),
                                 ("更新 Cage 平滑与权重","update"),("移除 Cage 权重，恢复备份","remove"),
                                 ("完成 Face Cage","finish"),("建立 EyeBrow Region 与驱动","brow")):
                form.addRow(self._button(label,lambda action=action: self._face_cage(action)))
            stack.addWidget(group)
            group, form = self._group("03L · Face 表情修形", [])
            for label,stage in (("Squint","squint"),("Smile Pull","smile"),("Frown Pull","frown"),
                                ("Cheek","cheek"),("Cheek Raiser","cheek_raiser")):
                row=QtWidgets.QHBoxLayout()
                row.addWidget(self._button(label+" 修形",lambda stage=stage: self._face_expression(stage)))
                row.addWidget(self._button("完成 "+label,lambda stage=stage: self._face_expression(stage+"_finish")))
                form.addRow(row)
            stack.addWidget(group)
            self.face_jaw_smooth=QtWidgets.QSpinBox()
            self.face_jaw_smooth.setRange(0,9999); self.face_jaw_smooth.setValue(50)
            group, form = self._group("03J · Jaw 绑定与修形", [("平滑迭代",self.face_jaw_smooth)])
            for label,action in (("建立 Jaw 权重层与 Teeth","build"),("更新 Jaw 曲线边界权重","update"),
                                 ("完成 Jaw 权重与跟随","finish"),("Jaw Open 修形","open"),
                                 ("完成 Jaw Open","open_finish"),("Lip Up 修形","lip_up"),
                                 ("完成 Lip Up","lip_up_finish"),("Lip Down 修形","lip_down"),
                                 ("完成 Lip Down","lip_down_finish"),("Lip Side 修形","lip_side"),
                                 ("完成 Lip Side","lip_side_finish")):
                form.addRow(self._button(label,lambda action=action: self._face_jaw(action)))
            form.addRow(self._button("更新 JawOpenLayer 嘴唇权重",self._face_jaw_lip_weights))
            form.addRow(self._button("Snarl 修形",lambda: self._face_expression("snarl")))
            form.addRow(self._button("完成 Snarl",lambda: self._face_expression("snarl_finish")))
            stack.addWidget(group)
            group, form = self._group("03F · Tongue 绑定", [])
            form.addRow(self._button("建立 Tongue 控制链与蒙皮",
                lambda: self._face_tongue("build")))
            form.addRow(self._button("完成 Tongue，恢复模型显示",
                lambda: self._face_tongue("finish")))
            stack.addWidget(group)
            group, form = self._group("03M · Eye Aim 与 UpMidLo", [])
            form.addRow(self._button("显示 Eye Aim 控制",lambda: self._face_expression("eye_aim")))
            form.addRow(self._button("建立 UpMidLo 控制与权重",lambda: self._face_expression("up_mid_lo")))
            stack.addWidget(group)
            group, form = self._group("03N · Phonemes 与 Emotions", [])
            form.addRow(self._button("建立音素驱动 Phonemes",lambda: self._face_expression("phonemes")))
            form.addRow(self._button("建立情绪驱动 Emotions",lambda: self._face_expression("emotions")))
            form.addRow(self._button("记录所选 Extras 模型",lambda: self._face_teeth_record("Extras")))
            form.addRow(self._button("传递 Extras 权重",lambda: self._face_expression("extras")))
            form.addRow(self._button("完成 Face 关节绑定",lambda: self._face_expression("finish")))
            stack.addWidget(group)
            group, form = self._group("03O · 原版眼部绑定与修形", [])
            form.addRow(self._button("原版 Face 首次准备",lambda:self._face_expression("prep_first")))
            form.addRow(self._button("按原版准备双侧 Fit",lambda:self._face_expression("prepare_fit_sides")))
            form.addRow(self._button("建立原版 EyeBall 绑定",lambda:self._face_expression("eye_ball")))
            form.addRow(self._button("建立原版 Pupil／Iris",lambda:self._face_expression("pupil_iris")))
            form.addRow(self._button("建立原版 EyeLid 绑定",lambda:self._face_expression("eye_lid")))
            for stage,label in (("blink","Blink"),("wide","Wide")):
                row=QtWidgets.QHBoxLayout()
                row.addWidget(self._button(label+" 修形",lambda stage=stage:self._face_expression(stage)))
                row.addWidget(self._button("完成 "+label,lambda stage=stage:self._face_expression(stage+"_finish")))
                form.addRow(row)
            stack.addWidget(group)
            group, form = self._group("03H · Regions", [])
            form.addRow(self._button("建立第二控制盒区域投影",self._face_regions))
            stack.addWidget(group)
            group, form = self._group("03a · Face Skin Layers", [])
            self.face_skin_layers_group = group
            form.addRow(self._button("Normal",
                lambda: self._face_skin_layers_show("Normal")))
            form.addRow(self._button("刷新 SkinLayer 列表",
                                     self._face_skin_layers_refresh))
            self.face_skin_layers_buttons = QtWidgets.QWidget()
            self.face_skin_layers_layout = QtWidgets.QVBoxLayout(
                self.face_skin_layers_buttons)
            form.addRow(self.face_skin_layers_buttons)
            stack.addWidget(group)

            group, form = self._group("03A · Face Tweaks", [])
            self.face_tweaks_keep_offset = QtWidgets.QCheckBox("keep offset")
            form.addRow("Swap controllers to Spheres",
                        self.face_tweaks_keep_offset)
            form.addRow(self._button("Swap", self._face_tweaks_swap_spheres))
            form.addRow(self._button("Paint skin-weights",
                                     self._face_tweaks_paint))
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Hide Joints",
                lambda: self._face_tweaks_joints_visible(False)))
            row.addWidget(self._button("Show Joints",
                lambda: self._face_tweaks_joints_visible(True)))
            form.addRow(row)
            form.addRow(self._button("Detach controllers",
                                     self._face_tweaks_detach_controllers))
            form.addRow(self._button("Attach controllers",
                                     self._face_tweaks_attach_controllers))
            for label, area, subtract in (
                    ("select eyeBrowArea", "eyeBrowArea", False),
                    ("select -d eyeBrowLine", "eyeBrowLineArea", True),
                    ("select eyeLidArea", "eyeLidArea", False),
                    ("select -d eyeLidMain", "eyeLidMainArea", True),
                    ("select eyeLidOuter", "eyeLidOuterArea", False),
                    ("select lipArea", "lipArea", False),
                    ("select -d lipMain", "lipMainArea", True),
                    ("select lipFalloffArea", "lipFalloffArea", False)):
                form.addRow(self._button(label,
                    lambda area=area, subtract=subtract:
                    self._face_tweaks_select(area, subtract)))
            self.face_tweaks_iterations = QtWidgets.QSpinBox()
            self.face_tweaks_iterations.setRange(1, 100)
            self.face_tweaks_iterations.setValue(5)
            form.addRow("Iterations", self.face_tweaks_iterations)
            form.addRow(self._button("WeightHammerVerts",
                                     self._face_tweaks_smooth))
            stack.addWidget(group)

            group, form = self._group("03B · Face DeltaMush", [])
            form.addRow(self._button("Create DeltaMush",
                                     self._face_delta_mush_create))
            form.addRow(self._button("Delete DeltaMush",
                                     self._face_delta_mush_delete))
            form.addRow(self._button("Select eyeLidArea",
                lambda: self._face_delta_mush_select("eyeLidArea")))
            form.addRow(self._button("Select lipArea",
                lambda: self._face_delta_mush_select("lipArea")))
            form.addRow(self._button("zero weight selected",
                                     self._face_delta_mush_zero_selected))
            form.addRow(self._button("Paint DeltaMush",
                                     self._face_delta_mush_paint))
            stack.addWidget(group)

            group, form = self._group("03C · Face HeadSquash", [])
            form.addRow(self._button("创建 HeadSquash",
                lambda: self._face_head_squash("create")))
            form.addRow(self._button("删除 HeadSquash",
                lambda: self._face_head_squash("delete")))
            form.addRow(QtWidgets.QLabel("限定头部影响，避免身体其他部位被压缩"))
            form.addRow(self._button("优化 HeadSquash 影响范围",
                lambda: self._face_head_squash("optimize")))
            form.addRow(QtWidgets.QLabel("选择头发等对象后，将它加入头部压缩变形"))
            form.addRow(self._button("加入所选对象",
                lambda: self._face_head_squash("include")))
            stack.addWidget(group)

            self.face_bs_keep_joints = QtWidgets.QCheckBox("保留关节")
            self.face_bs_keep_targets = QtWidgets.QCheckBox("保留 BlendShape 目标对象")
            group, form = self._group("03P · 原版驱动转 BlendShape", [])
            form.addRow(QtWidgets.QLabel("将 DrivingSystems 转换为 BlendShape"))
            form.addRow(self.face_bs_keep_joints)
            form.addRow(self.face_bs_keep_targets)
            form.addRow(self._button("转换", self._face_original_bs_convert))
            stack.addWidget(group)
            self.face_arkit_source = QtWidgets.QLineEdit()
            self.face_arkit_source.setPlaceholderText("外部 ARKit BlendShape 节点；创建原版控制器时留空")
            self.face_arkit_mouth_close = QtWidgets.QCheckBox("mouthClose 包含张嘴运动")
            group, form = self._group("03Q · ARKit 接线", [("BlendShape 节点", self.face_arkit_source)])
            form.addRow(self.face_arkit_mouth_close)
            form.addRow(self._button("连接 ARKit", self._face_original_arkit_connect))
            form.addRow(self._button("断开 ARKit", self._face_original_arkit_disconnect))
            stack.addWidget(group)

            self.face_wrinkle_shader = QtWidgets.QLineEdit()
            self.face_wrinkle_shader.setPlaceholderText("Face 多材质时指定 Shader")
            self.face_wrinkle_image_path = QtWidgets.QLineEdit()
            self.face_wrinkle_dimensions = []
            for value in (1024,1024,512,512):
                box = QtWidgets.QSpinBox()
                box.setRange(1,32768)
                box.setValue(value)
                self.face_wrinkle_dimensions.append(box)
            self.face_wrinkle_format = QtWidgets.QComboBox()
            self.face_wrinkle_format.addItems(("png","tga"))
            self.face_wrinkle_group = QtWidgets.QComboBox()
            self.face_wrinkle_group.addItems(("All","ForeHead","Frown","CrowsFeet","BunnyLines","SmileLine"))
            self.face_wrinkle_element = QtWidgets.QComboBox()
            self.face_wrinkle_element.addItems(("Curves","Mask","Test"))
            group, form = self._group("03T · 原版 WrinkleMap", [("Shader",self.face_wrinkle_shader)])
            form.addRow(self._button("创建／移除皱纹曲线",lambda:self._face_wrinkles("curves")))
            form.addRow(self._button("创建／移除 WrinkleMap",lambda:self._face_wrinkles("map")))
            form.addRow(self._button("重新投影 Wrinkle UV",lambda:self._face_wrinkles("uv")))
            form.addRow("皱纹组",self.face_wrinkle_group)
            form.addRow("编辑类型",self.face_wrinkle_element)
            form.addRow(self._button("编辑皱纹",lambda:self._face_wrinkles("edit")))
            form.addRow(self._button("应用并重新烘焙",lambda:self._face_wrinkles("apply")))
            form.addRow(self._button("取消皱纹编辑",lambda:self._face_wrinkles("cancel")))
            form.addRow(self._button("读取 Wrinkle 设置",lambda:self._face_wrinkles("settings")))
            form.addRow("贴图目录",self.face_wrinkle_image_path)
            for label,box in zip(("凹凸宽度","凹凸高度","遮罩宽度","遮罩高度"),self.face_wrinkle_dimensions):
                form.addRow(label,box)
            form.addRow("贴图格式",self.face_wrinkle_format)
            form.addRow(self._button("保存 Wrinkle 设置",lambda:self._face_wrinkles("save_settings")))
            for label,action in (("正常材质","view_normal"),("查看凹凸","view_bump"),("查看遮罩","view_masks"),("查看凹凸文件","view_file")):
                form.addRow(self._button(label,lambda checked=False,action=action:self._face_wrinkles(action)))
            stack.addWidget(group)

            self.face_bs_auto_mirror = QtWidgets.QCheckBox("自动镜像")
            self.face_bs_auto_mirror.setChecked(True)
            self.face_bs_targets = QtWidgets.QComboBox()
            self.face_bs_targets.addItem("当前控制器姿态", None)
            self.face_bs_weight = QtWidgets.QDoubleSpinBox()
            self.face_bs_weight.setRange(0,1)
            self.face_bs_weight.setSingleStep(.01)
            self.face_bs_weight.setDecimals(3)
            self.face_bs_weight.setValue(1)
            self.face_bs_wizard_step = 0
            self.face_bs_wizard_status = QtWidgets.QLabel("向导尚未开始")
            self.face_bs_delta_multiplier = QtWidgets.QDoubleSpinBox()
            self.face_bs_delta_multiplier.setRange(.01, 100)
            self.face_bs_delta_multiplier.setValue(1.3)
            group, form = self._group("03R · 原版 BlendShape 编辑", [])
            form.addRow(self.face_bs_auto_mirror)
            form.addRow("编辑目标", self.face_bs_targets)
            form.addRow("目标权重", self.face_bs_weight)
            form.addRow(self._button("设置目标权重", lambda: self._face_bs_edit("weight")))
            form.addRow(self._button("刷新 BlendShape 目标", self._face_bs_targets_refresh))
            form.addRow(self._button("提取 BlendShape 目标", lambda: self._face_bs_edit("extract")))
            form.addRow(self._button("重置编辑目标", lambda: self._face_bs_edit("reset")))
            form.addRow(self._button("完成并删除编辑目标", lambda: self._face_bs_edit("delete")))
            form.addRow(self._button("开始 BlendShape 向导", lambda: self._face_bs_edit("wizard_start")))
            form.addRow(self._button("下一个 BlendShape 目标", lambda: self._face_bs_edit("wizard_next")))
            form.addRow(self.face_bs_wizard_status)
            form.addRow(self._button("停止 BlendShape 向导", lambda: self._face_bs_edit("wizard_stop")))
            form.addRow(self._button("提取所有 BlendShape 目标", lambda: self._face_bs_edit("extract_all")))
            form.addRow("DeltaMush 倍率", self.face_bs_delta_multiplier)
            form.addRow(self._button("DeltaMush 平滑所有目标", lambda: self._face_bs_edit("delta_mush_all")))
            stack.addWidget(group)
            self.face_bs_new_attribute = QtWidgets.QLineEdit()
            self.face_bs_new_attribute.setPlaceholderText("默认 Untitled")
            self.face_bs_new_control = QtWidgets.QLineEdit()
            self.face_bs_new_control.setPlaceholderText("已有控制器或新名称；默认 ctrlUntitled")
            self.face_bs_new_mirror = QtWidgets.QCheckBox("镜像创建左右目标")
            self.face_bs_new_mirror.setChecked(True)
            group, form = self._group("03S · 原版新建 BlendShape", [
                ("驱动属性", self.face_bs_new_attribute), ("驱动控制器", self.face_bs_new_control)])
            form.addRow(self.face_bs_new_mirror)
            form.addRow(self._button("新建 BlendShape 目标", lambda: self._face_bs_edit("new")))
            stack.addWidget(group)

            performance, self.face_performance_document = self._file_field("面部动画文档")
            self.face_control_path = QtWidgets.QLineEdit()
            self.face_control_path.setPlaceholderText("|Head_M|AdvPy_FaceControls")
            group, form = self._group("04 · 表情与口型动画", [
                ("控制路径", self.face_control_path), ("动画文档", performance)])
            form.addRow(self._button("应用面部动画", self._face_performance_apply))
            stack.addWidget(group)

            self.face_library_directory = QtWidgets.QLineEdit()
            self.face_library_directory.setPlaceholderText("面部资产版本目录")
            asset_source, self.face_library_source = self._file_field("登记目标资产")
            self.face_library_release = QtWidgets.QLineEdit("1.0.0")
            self.face_library_versions = QtWidgets.QComboBox()
            asset_destination, self.face_library_destination = self._file_field(
                "导出资产版本", save=True)
            group, form = self._group("05 · 面部资产版本", [
                ("版本目录", self.face_library_directory),
                ("资产文件", asset_source),
                ("登记版本", self.face_library_release),
                ("已有版本", self.face_library_versions),
                ("导出到", asset_destination)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("登记资产版本", self._face_library_add))
            row.addWidget(self._button("刷新版本", self._face_library_refresh))
            row.addWidget(self._button("导出所选版本", self._face_library_export))
            form.addRow(row)
            stack.addWidget(group)

            self.face_merge_base = QtWidgets.QLineEdit()
            self.face_merge_left = QtWidgets.QLineEdit()
            self.face_merge_right = QtWidgets.QLineEdit()
            self.face_merge_release = QtWidgets.QLineEdit()
            for field, hint in ((self.face_merge_base, "基础版本，如 1.0.0"),
                (self.face_merge_left, "左侧版本，如 1.1.0"),
                (self.face_merge_right, "右侧版本，如 1.2.0"),
                (self.face_merge_release, "新版本，如 1.3.0")):
                field.setPlaceholderText(hint)
            group, form = self._group("06 · 合并同一目标的三个版本", [
                ("基础版本", self.face_merge_base),
                ("左侧版本", self.face_merge_left),
                ("右侧版本", self.face_merge_right),
                ("合并为", self.face_merge_release)])
            form.addRow(self._button("合并资产版本", self._face_library_merge))
            stack.addWidget(group)

            face_custom = self.face_custom_controls = {}
            for key in ("source", "name", "parent", "existing", "mesh",
                        "skin_cluster"):
                face_custom[key] = QtWidgets.QLineEdit()
            face_custom["source"].setPlaceholderText("已绘制的 SoftMod 节点路径")
            face_custom["name"].setPlaceholderText("例如 Cheek；侧别由位置确定")
            face_custom["parent"].setPlaceholderText(
                "可留空；默认使用 FaceFitSkeleton.HeadJoint")
            face_custom["existing"].setPlaceholderText("已有面部控制器路径")
            face_custom["mesh"].setPlaceholderText("新增受影响网格路径")
            face_custom["skin_cluster"].setPlaceholderText(
                "留空使用唯一现有层；填节点名选现有层")
            for key, label in (("mirror", "启用"), ("middle", "启用"),
                               ("local", "启用"),
                               ("new_layer", "启用")):
                face_custom[key] = QtWidgets.QCheckBox(label)
            face_custom["mirror"].setChecked(True)
            face_custom["local"].setChecked(True)
            face_custom["mirror"].toggled.connect(
                lambda enabled: face_custom["middle"].setChecked(False)
                if enabled else None)
            face_custom["middle"].toggled.connect(
                lambda enabled: face_custom["mirror"].setChecked(False)
                if enabled else None)
            group, form = self._group("07 · 自定义控制器", [
                ("SoftMod 区域", face_custom["source"]),
                ("控制器名称", face_custom["name"]),
                ("自动镜像", face_custom["mirror"]),
                ("中心控制", face_custom["middle"]),
                ("局部朝向", face_custom["local"]),
                ("目标蒙皮层", face_custom["skin_cluster"]),
                ("新建蒙皮层", face_custom["new_layer"]),
                ("指定父关节", face_custom["parent"]),
                ("已有控制器", face_custom["existing"]),
                ("新增网格", face_custom["mesh"])])
            form.addRow(QtWidgets.QLabel("先创建 SoftMod 区域："))
            form.addRow(self._button("打开 SoftMod Tool",
                                     self._open_custom_softmod_tool))
            form.addRow(QtWidgets.QLabel("然后创建控制器："))
            form.addRow(self._button("创建 Skin Control",
                lambda: self._create_custom_skin(face=True)))
            form.addRow(self._button("创建 Cluster Control",
                lambda: self._create_custom_cluster(face=True)))
            form.addRow(self._button("创建 SoftMod Control",
                lambda: self._create_custom_softmod(face=True)))
            form.addRow(QtWidgets.QLabel("编辑 Cluster Control："))
            form.addRow(self._button("绘制所选控制器权重",
                lambda: self._paint_custom_cluster(face=True)))
            form.addRow(self._button("镜像所选控制器权重",
                lambda: self._mirror_custom_cluster(face=True)))
            form.addRow(QtWidgets.QLabel("编辑："))
            form.addRow(self._button("添加受影响对象",
                lambda: self._add_custom_softmod_mesh(face=True)))
            form.addRow(QtWidgets.QLabel("删除："))
            form.addRow(self._button("删除所选控制器",
                lambda: self._delete_custom_control(face=True)))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _publish_page(self):
            page, stack = self._page()
            publish_group, publish_form = self._group('00 · Publish', [])
            self.original_publish_entries = QtWidgets.QTableWidget(0, 2)
            self.original_publish_entries.setHorizontalHeaderLabels(['Name', 'Script'])
            self.original_publish_entries.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.original_publish_entries.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.original_publish_entries.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            publish_form.addRow(self._button('Set DisplayLayers to "R"', self._publish_reference_layers))
            publish_form.addRow(self._button('Set Joints to hidden', lambda: self._set_rig_display('joints', False)))
            publish_form.addRow(self._button('Go to Build Pose', self._publish_build_pose))
            publish_form.addRow(self._button('Publish', self._publish_original_scene, primary=True))
            advanced = QtWidgets.QCheckBox('advanced')
            publish_form.addRow(advanced)
            advanced_content = QtWidgets.QWidget()
            advanced_form = QtWidgets.QFormLayout(advanced_content)
            advanced_form.setContentsMargins(0, 0, 0, 0)
            advanced_form.addRow(QtWidgets.QLabel('Publish Multi Files:'))
            advanced_form.addRow(self._button('add', lambda: self._original_publish_entry_dialog(False)))
            advanced_form.addRow(self.original_publish_entries)
            advanced_form.addRow(self._button('edit', lambda: self._original_publish_entry_dialog(True)))
            advanced_form.addRow(self._button('delete', self._delete_original_publish_entry))
            advanced_form.addRow(self._button('Refresh', self._refresh_original_publish_entries))
            publish_form.addRow(advanced_content)
            advanced_content.setVisible(False)
            advanced.toggled.connect(advanced_content.setVisible)
            self._refresh_original_publish_entries()
            stack.addWidget(publish_group)
            native_group, native_form = self._group('00 · Export', [])
            native_form.addRow(QtWidgets.QLabel('For Game-Engine Export:'))
            native_form.addRow(self._button('Delete Unused Endjoints',
                lambda: self._prepare_original_export('delete_unused_end_joints')))
            native_form.addRow(self._button('Delete Static channels',
                lambda: self._prepare_original_export('delete_static_channels')))
            native_form.addRow(self._button('Rebuild dagPose nodes',
                lambda: self._prepare_original_export('rebuild_dag_pose')))
            native_form.addRow(self._button('Roblox Dynamic Head', self._export_roblox_dynamic_head))
            native_form.addRow(self._button('FBX export', self._export_original_fbx))
            native_form.addRow(QtWidgets.QLabel('Unreal:'))
            native_form.addRow(self._button('Mannequin export', self._export_unreal_mannequin))
            native_form.addRow(QtWidgets.QLabel('json data:'))
            native_form.addRow(self._button('BodyRig export', self._export_original_body_rig))
            native_form.addRow(self._button('FaceRig export', self._export_unreal_face_solver))
            stack.addWidget(native_group)
            maya_output, self.maya_output = self._file_field(
                "独立 Maya 场景", save=True, filter_text="Maya Binary (*.mb)")
            maya_group, maya_form = self._group(
                "01 · 导出迁移后的完整角色", [("输出文件", maya_output)])
            maya_form.addRow(self._button("导出独立 Maya 场景",
                                           self._publish_maya_scene, primary=True))
            maya_form.addRow(QtWidgets.QLabel(
                "仅适用于从原版引用迁移的本地角色；导出网格、Skin、控制器与动画。"))
            stack.addWidget(maya_group)
            output, self.fbx_output = self._file_field("发布 FBX", save=True,
                                                       filter_text="FBX 文件 (*.fbx)")
            frames = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(frames)
            row.setContentsMargins(0, 0, 0, 0)
            self.fbx_start = QtWidgets.QSpinBox()
            self.fbx_end = QtWidgets.QSpinBox()
            self.fbx_step = QtWidgets.QSpinBox()
            for field in (self.fbx_start, self.fbx_end, self.fbx_step):
                field.setRange(-100000, 100000)
            self.fbx_start.setValue(1)
            self.fbx_end.setValue(24)
            self.fbx_step.setRange(1, 100000)
            self.fbx_step.setValue(1)
            for label, field in (("起始", self.fbx_start), ("结束", self.fbx_end),
                                 ("步长", self.fbx_step)):
                row.addWidget(QtWidgets.QLabel(label))
                row.addWidget(field)
            self.fbx_policy = QtWidgets.QComboBox()
            self.fbx_policy.addItem("完整采样", "sampled_linear")
            self.fbx_policy.addItem("无损线性精简", "lossless_linear")
            self.fbx_policy.addItem("有界线性精简", "bounded_linear")
            self.fbx_euler_filter = QtWidgets.QCheckBox("整理旋转跨圈跳变（Euler Filter）")
            self.fbx_include_skins = QtWidgets.QCheckBox("包含当前角色的已绑定网格与 Skin")
            self.fbx_value_tolerance = QtWidgets.QDoubleSpinBox()
            self.fbx_matrix_tolerance = QtWidgets.QDoubleSpinBox()
            for field in (self.fbx_value_tolerance, self.fbx_matrix_tolerance):
                field.setRange(0.0, 1000.0)
                field.setDecimals(4)
                field.setSingleStep(0.01)
                field.setEnabled(False)
            self.fbx_policy.currentIndexChanged.connect(
                lambda: self._fbx_policy_changed())
            group, form = self._group("02 · 烘焙并发布独立骨架", [
                ("输出文件", output), ("采样帧", frames),
                ("曲线策略", self.fbx_policy),
                ("旋转处理", self.fbx_euler_filter),
                ("角色网格", self.fbx_include_skins),
                ("通道容差", self.fbx_value_tolerance),
                ("矩阵容差", self.fbx_matrix_tolerance)])
            form.addRow(self._button("发布 FBX", self._publish_fbx, primary=True))
            form.addRow(QtWidgets.QLabel(
                "从当前角色构建 Root Motion 与独立导出骨架；目标文件已存在时拒绝覆盖。"))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def open_original_section(self, group, section, subsection=None):
            route = self._original_section_routes.get(group)
            if route is None:
                raise ValueError('操作栏目不存在：' + group)
            category_button, section_button, widget = route
            category_button.setChecked(True)
            section_button.setChecked(True)
            self.custom_control_face = section == 'Face'
            self.setWindowTitle('AdvancedSkeleton Python / ' + section
                                + (' / ' + subsection if subsection else ''))
            self.show()
            self.operation_page.ensureWidgetVisible(widget, 10, 12)
            # The whole group can be taller than the viewport. Navigate to its
            # heading instead of centering it midway through the operations.
            top = widget.mapTo(self.operation_page.widget(), QtCore.QPoint(0, 0))
            self.operation_page.verticalScrollBar().setValue(max(0, top.y() - 12))
            self.operation_page.horizontalScrollBar().setValue(0)

        def _publish_original_scene(self):
            result = self.controller.original_publish(self._namespace())
            if result is None:
                return '已取消 Publish。'
            failures = [item['script_error'] for item in result if item['script_error']]
            return ('已按原版导出：\n' + '\n'.join(item['destination'] for item in result)
                    + ('\n自定义脚本错误：\n' + '\n'.join(failures) if failures else ''))

        def _publish_reference_layers(self):
            result = self.controller.original_publish_reference_layers(self._namespace())
            return f'已将 {len(result)} 个 DisplayLayer 设为 R。'

        def _publish_build_pose(self):
            count = self.controller.original_publish_build_pose(self._namespace())
            return f'已复位 {count} 个 Body / Face 构建姿态通道。'

        def _refresh_original_publish_entries(self):
            # optionVar is global and the UI reads it before role population.
            entries = self.controller.original_publish_entries(':')
            table = self.original_publish_entries
            table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(entry.name))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry.script))
            return f'已读取 {len(entries)} 个原版 Publish 配置。'

        def _delete_original_publish_entry(self):
            row = self.original_publish_entries.currentRow()
            if row < 0:
                raise ValueError('请选择要删除的 Publish 配置')
            self.controller.original_publish_delete_entry(self._namespace(), row)
            return self._refresh_original_publish_entries()

        def _original_publish_entry_dialog(self, edit):
            from adv_py.core.original_publish import original_publish_template
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Edit' if edit else 'Add')
            form = QtWidgets.QFormLayout(dialog)
            name = QtWidgets.QLineEdit()
            script = QtWidgets.QPlainTextEdit()
            template = QtWidgets.QComboBox()
            template.addItems(['*new', 'BodyOnly', 'LoOnly', 'Default'])
            form.addRow('Name:', name)
            form.addRow('Script:', script)
            if edit:
                row = self.original_publish_entries.currentRow()
                if row < 0:
                    raise ValueError('请选择要编辑的 Publish 配置')
                name.setText(self.original_publish_entries.item(row, 0).text())
                name.setReadOnly(True)
                script.setPlainText(self.original_publish_entries.item(row, 1).text())
            else:
                form.addRow('use template:', template)
                def use_template(*_):
                    entry = original_publish_template(template.currentText())
                    name.setText(entry.name)
                    script.setPlainText(entry.script)
                template.currentIndexChanged.connect(use_template)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if (getattr(dialog, 'exec', None) or dialog.exec_)() == QtWidgets.QDialog.Accepted:
                self.controller.original_publish_save_entry(self._namespace(), name.text(), script.toPlainText())
            return self._refresh_original_publish_entries()

        def _skin_cage_page(self):
            page, stack = self._page()
            group, form = self._group("00 · SkinCage", [])
            form.addRow(QtWidgets.QLabel("Cage"))
            form.addRow(self._button("创建 Cage", self._create_skin_cage))
            form.addRow(self._button("删除 Cage", self._delete_skin_cage))
            form.addRow(QtWidgets.QLabel("Mirror"))
            form.addRow(self._button("Left > Right",
                                     lambda: self._mirror_skin_cage("L")))
            form.addRow(self._button("Right > Left",
                                     lambda: self._mirror_skin_cage("R")))
            form.addRow(QtWidgets.QLabel("选择待变形网格或其顶点，然后复制 Cage 权重。"))
            form.addRow(self._button("复制权重", self._copy_skin_cage_weights))
            form.addRow(QtWidgets.QLabel("Adjust"))
            form.addRow(self._button('"DeformationWidth"',
                                     self._skin_cage_deformation_width))
            form.addRow(self._button("Create Groin Locators",
                                     self._skin_cage_groin_locators))
            form.addRow(self._button("Adjust Groin area",
                                     self._skin_cage_adjust_groin))
            form.addRow(self._button("Create Groin joint",
                                     self._skin_cage_groin_joint))
            form.addRow(self._button("Delete SkinCurves",
                                     self._skin_cage_delete_curves))
            form.addRow(QtWidgets.QLabel("Sliders：先选择 SkinCage 截面曲线。"))
            self.skin_cage_sliders_include_controller = QtWidgets.QCheckBox(
                "include controller")
            form.addRow(self.skin_cage_sliders_include_controller)
            form.addRow(self._button("Create Sliders",
                                     self._skin_cage_create_sliders))
            form.addRow(self._button("Delete Sliders",
                                     self._skin_cage_delete_sliders))
            form.addRow(QtWidgets.QLabel("Re-use：将当前可见 SkinCurves 形状输出到 Script Editor。"))
            self.skin_cage_reuse_xform = QtWidgets.QCheckBox("xform")
            self.skin_cage_reuse_xform.setChecked(True)
            self.skin_cage_reuse_shape = QtWidgets.QCheckBox("shape")
            self.skin_cage_reuse_shape.setChecked(True)
            self.skin_cage_reuse_catch = QtWidgets.QCheckBox("catch")
            for option in (self.skin_cage_reuse_xform,
                           self.skin_cage_reuse_shape,
                           self.skin_cage_reuse_catch):
                form.addRow(option)
            form.addRow(self._button("Print Commands",
                                     self._print_skin_cage_reuse))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _sub_wrap_page(self):
            page, stack = self._page()
            group, form = self._group("00 · SubWrap", [])
            form.addRow(QtWidgets.QLabel("SubWrap"))
            form.addRow(self._button("Create Cage", self._sub_wrap_create_cage))
            form.addRow(self._button("Delete Cage", self._sub_wrap_delete_cage))
            form.addRow(QtWidgets.QLabel("选择待变形网格对象，然后建立包裹。"))
            form.addRow(self._button("Wrap selected mesh",
                                     self._sub_wrap_wrap_selected))
            form.addRow(self._button("Detach", self._sub_wrap_detach))
            form.addRow(self._button("Attach", self._sub_wrap_attach))
            form.addRow(QtWidgets.QLabel("选择网格顶点，从 Wrap 中排除并交给 Skin。"))
            form.addRow(self._button("Exclude selected vertices",
                                     self._sub_wrap_exclude_selected))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _skin_loop_page(self):
            page, stack = self._page()
            self.skin_loop_mirror = QtWidgets.QCheckBox("自动镜像到对侧")
            self.skin_loop_mirror.setChecked(True)
            group, form = self._group("00 · SkinLoops", [
                ("镜像", self.skin_loop_mirror)])
            form.addRow(QtWidgets.QLabel(
                "先选择闭合网格边，最后选择对应 FK 控制器。"))
            form.addRow(self._button("创建 SkinLoop", self._create_skin_loop))
            form.addRow(self._button("选择全部 SkinLoops",
                                     self._select_all_skin_loops))
            form.addRow(QtWidgets.QLabel(
                "选择带 SkinLoop 的网格对象，按边环关节绑定权重。"))
            form.addRow(self._button("绑定 SkinLoops", self._bind_skin_loops))
            form.addRow(QtWidgets.QLabel(
                "选择待复制权重的网格或其组件，再复制已绑定 SkinLoop 网格的权重。"))
            form.addRow(self._button("复制 SkinLoop 权重",
                                     self._copy_skin_loop_weights))
            form.addRow(QtWidgets.QLabel(
                "选择带 SkinLoop 的网格对象，创建随关节运动的 CutUp 分片。"))
            form.addRow(self._button("创建 CutUp", self._create_skin_loop_cut_up))
            form.addRow(self._button("删除 CutUp", self._delete_skin_loop_cut_up))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _geometry_cut_up_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Skin Cut-Up", [])
            form.addRow(QtWidgets.QLabel(
                "选择已蒙皮网格，按每个面的主导关节生成几何分片。"))
            form.addRow(self._button("Create", self._geometry_cut_up_create))
            form.addRow(self._button("Delete", self._geometry_cut_up_delete))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _geometry_skeleton_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Skeleton", [])
            form.addRow(QtWidgets.QLabel(
                "从本机 ADV 6.925 原版骨形模板生成当前 Body 的骨骼几何。"))
            form.addRow(self._button("Create", self._geometry_skeleton_create))
            form.addRow(self._button("Delete", self._geometry_skeleton_delete))
            form.addRow(self._button("Left>Right",
                                     self._geometry_skeleton_mirror_l2r))
            form.addRow(self._button("Right>Left",
                                     self._geometry_skeleton_mirror_r2l))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _geometry_muscular_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Muscular", [])
            form.addRow(QtWidgets.QLabel(
                "先创建 Skeleton，再从原版模板创建肌肉曲面。"))
            form.addRow(self._button("Create", self._geometry_muscular_create))
            form.addRow(self._button("Delete", self._geometry_muscular_delete))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _geometry_poly_boxes_page(self):
            page, stack = self._page()
            group, form = self._group("00 · PolyBoxes", [])
            form.addRow(QtWidgets.QLabel(
                "按 Fit 骨段体积创建跟随 Body 关节的盒体。"))
            form.addRow(self._button("Create", self._geometry_poly_boxes_create))
            form.addRow(self._button("Delete", self._geometry_poly_boxes_delete))
            form.addRow(self._button("Left>Right",
                                     self._geometry_poly_boxes_mirror_l2r))
            form.addRow(self._button("Right>Left",
                                     self._geometry_poly_boxes_mirror_r2l))
            form.addRow("Boolean", self._button(
                "Create", self._geometry_boolean_create))
            form.addRow(self._button("Delete", self._geometry_boolean_delete))
            form.addRow("Warp", self._button(
                "Create", self._geometry_warp_create))
            form.addRow(self._button("Delete", self._geometry_warp_delete))
            form.addRow("BoxSkin", self._button(
                "Create", self._geometry_box_skin_create))
            form.addRow(self._button("Delete", self._geometry_box_skin_delete))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _geometry_mannequin_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Mannequin", [])
            form.addRow(QtWidgets.QLabel(
                "使用原版 asGeometry 模板创建 Body Mannequin。"))
            form.addRow(self._button("Create", self._geometry_mannequin_create))
            form.addRow(self._button("Delete", self._geometry_mannequin_delete))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _display_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Display", [])
            for label, operation in (("MotionSystem", "motion"),
                                     ("Joints", "joints"),
                                     ("Joint axis", "axes")):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(self._button(
                    "隐藏", lambda op=operation: self._set_rig_display(op, False)))
                row.addWidget(self._button(
                    "显示", lambda op=operation: self._set_rig_display(op, True)))
                form.addRow(label, row)
            self.display_joint_size = QtWidgets.QDoubleSpinBox()
            self.display_joint_size.setRange(0.01, 10.0)
            self.display_joint_size.setDecimals(2)
            self.display_joint_size.setSingleStep(0.1)
            self.display_joint_size.setValue(1.0)
            form.addRow("Joint Size", self.display_joint_size)
            form.addRow(self._button("设置关节尺寸", lambda:
                self._set_rig_display("joint_size",
                                      self.display_joint_size.value())))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _set_rig_display(self, operation, value):
            state = self.controller.rig_display(
                self._namespace(), operation, value)
            return ("已设置 " + operation + "；当前关节尺寸 "
                    + f"{state.joint_size:.2f}")

        def _optimize_page(self):
            page, stack = self._page()
            group, form = self._group("00 · Optimize", [])
            form.addRow(self._button('Delete Unused Nodes',
                                     lambda: self._original_optimize('delete_unused_nodes')))
            form.addRow(self._button("Remove Unused Influences",
                                     self._remove_unused_skin_influences))
            form.addRow(self._button("Remove Unused Attributes",
                                     lambda: self._original_optimize('remove_unused_attributes')))
            form.addRow(self._button("Prune Small Weights",
                                     self._prune_small_skin_weights))
            form.addRow(self._button('Delete saved UIs',
                                     lambda: self._original_optimize('delete_saved_uis')))
            form.addRow(self._button("Delete Unused joints",
                lambda: self._prepare_original_export('delete_unused_end_joints')))
            form.addRow(QtWidgets.QLabel('Tag Controller:'))
            form.addRow(self._button("Tag All Controllers",
                                     lambda: self._original_optimize('tag_all_controllers')))
            form.addRow(QtWidgets.QLabel('Face-joints reduction for GameEngine:'))
            form.addRow(self._button('Reduce EyeLid joints to 4',
                                     lambda: self._face_joint_reduction('EyeLid', 4)))
            form.addRow(self._button('Reduce EyeLid joints to 8',
                                     lambda: self._face_joint_reduction('EyeLid', 8)))
            form.addRow(self._button('Reduce Lip joints to 14',
                                     lambda: self._face_joint_reduction('Lip', 14)))
            form.addRow(self._button('Custom Reduce', self._custom_face_reduction_dialog))
            stack.addWidget(group)
            updates, update_form = self._group('00 · Updates', [])
            update_form.addRow(QtWidgets.QLabel('Model update functions:'))
            update_form.addRow(self._button('Green-fix', lambda: self._original_model_update('green_fix')))
            update_form.addRow(self._button('NaN-fix', lambda: self._original_model_update('nan_fix')))
            update_form.addRow(self._button('Face Fitting Update',
                lambda: self._original_model_update('face_fitting_update')))
            stack.addWidget(updates)
            stack.addStretch(1)
            return page

        def _remove_unused_skin_influences(self):
            skins, removed = self.controller.remove_unused_skin_influences(
                self._namespace())
            return f"已检查 {skins} 个 Skin，清理 {removed} 个无效影响关节。"

        def _original_model_update(self, operation):
            result = self.controller.original_model_update(self._namespace(), operation)
            if operation == 'face_fitting_update':
                return ('已取消 Face Fitting 更新。' if result is None else
                        f'已按原版顺序重新应用 {len(result)} 项 Face Fitting。')
            return (f'已按原版修复 {len(result)} 个着色归属。' if operation == 'green_fix'
                    else f'已按原版对 {len(result)} 个原点顶点执行 Weight Hammer。')

        def _original_optimize(self, operation):
            result = self.controller.original_optimize(self._namespace(), operation)
            messages = {
                'remove_unused_attributes': f'已按原版清理 {len(result)} 个无用属性。',
                'tag_all_controllers': f'已按原版创建 {len(result)} 个控制器标签。',
                'delete_unused_nodes': f'已按 Maya 原生流程删除 {len(result)} 个无用节点。',
                'delete_saved_uis': f'已删除 {len(result)} 个保存的 UI 节点并清空撤销记录；保存重开后生效。',
            }
            return messages[operation]

        def _face_joint_reduction(self, kind, count):
            self.controller.face_joint_reduction(self._namespace(), kind, count)
            return f'已按原版完成 {kind} 关节缩减到 {count}。'

        def _custom_face_reduction_dialog(self):
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Custom Face Joint Reduce')
            form = QtWidgets.QFormLayout(dialog)
            kind = QtWidgets.QComboBox()
            kind.addItems(['EyeLid', 'Lip'])
            every = QtWidgets.QComboBox()
            for value, label in ((2, '2nd'), (3, '3rd'), (4, '4th'), (5, '5th')):
                every.addItem(label, value)
            current = QtWidgets.QLineEdit()
            current.setReadOnly(True)
            reduced = QtWidgets.QLineEdit()
            reduced.setReadOnly(True)
            message = QtWidgets.QLabel()
            message.setWordWrap(True)
            form.addRow('Joints:', kind)
            form.addRow('current count is:', current)
            form.addRow('keep every:', every)
            form.addRow('new count will be:', reduced)
            form.addRow(message)
            buttons = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(buttons)
            row.setContentsMargins(0, 0, 0, 0)
            preview_button = QtWidgets.QPushButton('Preview')
            apply_button = QtWidgets.QPushButton('Apply')
            close_button = QtWidgets.QPushButton('Close')
            for button in (preview_button, apply_button, close_button):
                row.addWidget(button)
            form.addRow(buttons)
            namespace = self._namespace()

            def update_counts(*_):
                try:
                    old, new = self.controller.custom_face_joint_reduction_counts(
                        namespace, kind.currentText(), every.currentData())
                    current.setText(str(old))
                    reduced.setText(str(new))
                    message.setText('(Selects the joints that will be kept)')
                except (ValueError, RuntimeError) as error:
                    current.clear()
                    reduced.clear()
                    message.setText(str(error))

            def execute(preview):
                try:
                    plan = self.controller.custom_face_joint_reduction(
                        namespace, kind.currentText(), every.currentData(), preview=preview)
                    message.setText(f'已选择 {len(plan.kept)} 个保留关节。' if preview
                                    else f'已完成缩减，原版计数为 {plan.reported_count}。')
                except (ValueError, RuntimeError) as error:
                    message.setText('操作失败：' + str(error))
                    QtWidgets.QMessageBox.warning(dialog, '操作未完成', str(error))

            kind.currentIndexChanged.connect(update_counts)
            every.currentIndexChanged.connect(update_counts)
            preview_button.clicked.connect(lambda: execute(True))
            apply_button.clicked.connect(lambda: execute(False))
            close_button.clicked.connect(dialog.reject)
            update_counts()
            (getattr(dialog, 'exec', None) or dialog.exec_)()
            return 'Custom Face Joint Reduce 已关闭。'

        def _prune_small_skin_weights(self):
            meshes = self.controller.prune_small_skin_weights(
                self._namespace())
            return f"已对 {meshes} 个网格 Shape 执行原版 0.01 阈值修剪。"

        def _mocap_page(self):
            page, stack = self._page()
            poser,poser_form=self._group('04 · PoserDesigner',[])
            poser_form.addRow(self._button('PoserDesigner',
                lambda:self.controller.original_poser_window(self._namespace())))
            stack.addWidget(poser)
            group,form=self._group('03 · MoCapMatcher',[])
            form.addRow(self._button('打开原版动捕映射面板',
                lambda:self.controller.tools_source_mocap_matcher(self._namespace())))
            stack.addWidget(group)
            source, self.mocap_source = self._file_field("导入动捕 FBX",
                filter_text="FBX 文件 (*.fbx)")
            mapping, self.mocap_mapping = self._file_field("动捕映射预设")
            self.mocap_namespace = QtWidgets.QLineEdit("ExternalTake")
            self.mocap_mode = QtWidgets.QComboBox()
            self.mocap_mode.addItem("全身 FK", "fk")
            self.mocap_mode.addItem("四肢 IK", "limb-ik")
            self.mocap_mode.addItem("全身 IK", "full-ik")
            frames = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(frames)
            row.setContentsMargins(0, 0, 0, 0)
            self.mocap_start = QtWidgets.QSpinBox()
            self.mocap_end = QtWidgets.QSpinBox()
            self.mocap_step = QtWidgets.QSpinBox()
            for field in (self.mocap_start, self.mocap_end, self.mocap_step):
                field.setRange(-100000, 100000)
            self.mocap_start.setValue(1)
            self.mocap_end.setValue(24)
            self.mocap_step.setRange(1, 100000)
            self.mocap_step.setValue(1)
            for label, field in (("起始", self.mocap_start), ("结束", self.mocap_end),
                                 ("步长", self.mocap_step)):
                row.addWidget(QtWidgets.QLabel(label))
                row.addWidget(field)
            group, form = self._group("01 · 外部 FBX 驱动角色", [
                ("动捕文件", source), ("映射预设", mapping),
                ("来源命名空间", self.mocap_namespace),
                ("控制模式", self.mocap_mode), ("采样帧", frames)])
            form.addRow(self._button("导入并写入控制", self._mocap_retarget,
                                      primary=True))
            stack.addWidget(group)
            stack.addWidget(QtWidgets.QLabel(
                "来源 FBX 将导入独立命名空间；该名称在当前场景中必须尚未使用。"))
            stack.addStretch(1)
            return page

        def _fbx_policy_changed(self):
            bounded = self.fbx_policy.currentData() == "bounded_linear"
            self.fbx_value_tolerance.setEnabled(bounded)
            self.fbx_matrix_tolerance.setEnabled(bounded)
            if bounded:
                self.fbx_value_tolerance.setValue(0.05)
                self.fbx_matrix_tolerance.setValue(0.2)
            else:
                self.fbx_value_tolerance.setValue(0.0)
                self.fbx_matrix_tolerance.setValue(0.0)

        def _namespace(self):
            item = self.roles.currentItem()
            if item is None:
                raise ValueError("请先选择场景命名空间")
            return item.data(QtCore.Qt.UserRole)

        def _path(self, line):
            value = line.text().strip()
            if not value:
                raise ValueError("请选择文档路径")
            return Path(value)

        def _export_fit(self):
            count = self.controller.fit_export(self._namespace(),
                self._path(self.fit_export_document),
                self.fit_container.text().strip(),
                external_compatibility=self.external_fit_export.isChecked())
            return f"已导出 {count} 个关节"

        def _create_fit_template(self, with_fingers):
            count = self.controller.fit_create_template(
                self._namespace(), self.fit_container.text().strip(),
                with_fingers=with_fingers,
                scale=self.fit_template_scale.value())
            return f"已创建 {count} 个 Fit 关节；调整关节位置后可构建 Body"

        def _fit_auto_scale(self):
            result=self.controller.fit_auto_scale(self._namespace(),self.fit_container.text().strip())
            if getattr(result,'finished',False):
                return '已结束 AutoPlace 引导并还原手指、肩肘及模型'
            if result.plan is None:
                return '未找到 Fit 关节，请先导入 FitSkeleton'
            return f'已按 Skin 缩放 {len(result.plan.positions)} 个 Fit 关节' + ('，并放置 Eye' if result.eye_placed else '')

        def _fit_auto_place(self):
            result=self.controller.fit_auto_place(self._namespace(),self.fit_container.text().strip())
            if getattr(result,'finished',False):return '已结束 AutoPlace 引导并还原模型'
            if not result.guides_active:return '未识别到原版模板所需的身体与手指形态，已清理引导'
            return f'已按原版扫描放置 {result.joints} 个 Fit 关节；可调整引导手柄，再点击自动放置结束'

        def _fit_from_selected_skeleton(self):
            selected_namespace = self._namespace()
            count, target_namespace = self.controller.fit_from_selected_skeleton(
                selected_namespace, self.fit_container.text().strip())
            if target_namespace != selected_namespace:
                self._next_role = target_namespace
            destination = (f"；新角色 {target_namespace}"
                if target_namespace != selected_namespace else "")
            return f"已从来源骨架创建 {count} 个 Fit 关节{destination}"

        def _check_model(self):
            result = self.controller.model_check(
                interactive=self.model_check_interactive.isChecked(),
                skip_symmetry=self.model_check_skip_symmetry.isChecked())
            lines = [f"模型：{result.mesh}", f"顶点：{result.vertex_count}"]
            if not result.symmetry_checked:
                lines.append("左右对称性：未检查")
            if result.clean:
                lines.append("通过：变换、历史和左右对称性均未发现问题")
            else:
                for issue in result.transform_issues:
                    lines.append(f"变换  {issue.path}.{issue.attribute}: "
                                 f"{issue.value:g}（默认 {issue.expected:g}）")
                for issue in result.history_issues:
                    lines.append(f"历史  {issue.name} [{issue.node_type}]")
                for issue in result.symmetry_issues[:100]:
                    lines.append(f"对称  顶点 {issue.vertex} → {issue.closest_vertex}: "
                                 f"偏差 {issue.distance:.6g} cm")
                if len(result.symmetry_issues) > 100:
                    lines.append(f"其余 {len(result.symmetry_issues) - 100} 处对称偏差已在模型上选中")
            self.model_check_results.setPlainText("\n".join(lines))
            return (f"模型检查完成：{len(result.transform_issues)} 项变换、"
                    f"{len(result.history_issues)} 项历史、"
                    f"{len(result.symmetry_issues)} 处对称偏差")

        def _create_model_geo_group(self):
            moved = self.controller.model_create_geo_group()
            return f"geo 模型组已建立；归入 {len(moved)} 个顶层对象"

        def _clean_model(self):
            result = self.controller.model_clean()
            return f"模型清理完成：重建 {len(result.plan.meshes)} 个网格"

        def _new_preparation_scene(self):
            if self.controller.preparation_scene_modified():
                choice = QtWidgets.QMessageBox.question(
                    self, "新建绑定场景", "当前场景有未保存的修改。是否先保存？",
                    QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard |
                    QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
                if choice == QtWidgets.QMessageBox.Cancel:
                    return "已取消新建场景"
                if choice == QtWidgets.QMessageBox.Save:
                    name = self.controller.preparation_scene_name()
                    if not name:
                        name, _ = QtWidgets.QFileDialog.getSaveFileName(
                            self, "保存当前 Maya 场景", "", "Maya 场景 (*.ma *.mb)")
                        if not name:
                            return "已取消新建场景"
                        self.controller.preparation_save_scene(Path(name))
                    else:
                        self.controller.preparation_save_scene()
            self.controller.preparation_new_scene()
            return "已打开空白绑定场景"

        def _reference_preparation_model(self):
            source = self._path(self.preparation_model_source)
            result = self.controller.preparation_reference_model(source)
            self.preparation_reference_namespace.setText(result.namespace)
            return (f"已引用 {source.name} 到 {result.namespace}；"
                    f"{len(result.top_nodes)} 个顶层对象位于 Hi 显示层")

        def _reload_preparation_model(self):
            result = self.controller.preparation_reload_model(
                self.preparation_reference_namespace.text().strip())
            return (f"已重新加载 {result.namespace}：{result.source.name}，"
                    f"{len(result.top_nodes)} 个顶层对象")

        def _replace_preparation_model(self):
            result = self.controller.preparation_replace_model(
                self.preparation_reference_namespace.text().strip(),
                self._path(self.preparation_model_source))
            return (f"已替换 {result.namespace} 的模型文件：{result.source.name}，"
                    f"{len(result.top_nodes)} 个顶层对象")

        def _remove_preparation_model(self):
            result = self.controller.preparation_remove_model(
                self.preparation_reference_namespace.text().strip())
            return f"已移除 {result.namespace} 的模型引用：{result.source.name}"

        def _record_preparation_objects(self, role):
            objects = self.controller.preparation_record_objects(self._namespace(), role)
            self.preparation_object_fields[role].setText(" ".join(objects))
            return f"已记录 {role}：{len(objects)} 件模型"

        def _build_one_joint_prop(self):
            from adv_py.core.body_build_options import BodyBuildOptions
            options = BodyBuildOptions(**{key: field.isChecked()
                for key, field in self.body_option_fields.items()})
            result = self.controller.preparation_one_joint_prop(
                self._namespace(), build_options=options)
            return (f"单关节道具已构建：{len(result.meshes)} 件模型、"
                    f"{len(result.skins)} 套 Skin；控制器 {result.control.rsplit('|', 1)[-1]}")

        def _build_fbx_rig(self):
            from adv_py.application.fbx_rig_import import FBXRigCancelled
            try:
                result = self.controller.preparation_fbx_rig()
            except FBXRigCancelled as exc:
                return str(exc)
            return (f"FBX rig 已建立：{len(result.connected_control_names)} "
                    f"个 FK 控制器接回原骨架，"
                    f"{result.ik_limb_count} 条可切换 IK/FK 的手脚链；"
                    "原 Skin 已保留。")

        def _name_matcher_mapping_rows(self):
            rows = []
            for line in self.name_matcher_rows.toPlainText().splitlines():
                parts = line.strip().split()
                if not parts:
                    continue
                if len(parts) != 2:
                    raise ValueError('NameMatcher 每行必须是 Fit关节 来源基础名')
                rows.append((parts[0], parts[1]))
            return tuple(rows)

        def _name_matcher_rule_kwargs(self):
            return dict(
                right=self.name_matcher_right.text().strip(),
                left=self.name_matcher_left.text().strip(),
                middle=self.name_matcher_middle.text().strip(),
                side_before_name=self.name_matcher_prefix.isChecked(),
                side_underscore=self.name_matcher_underscore.isChecked())

        def _source_fit_preparation(self):
            from adv_py.core.source_fit_import import SourceFitPreparation
            return SourceFitPreparation(
                skin=self.preparation_object_fields['Skin'].text(),
                all_objects=self.preparation_object_fields['All'].text(),
                right_eye=self.preparation_object_fields['Right Eye'].text(),
                left_eye=self.preparation_object_fields['Left Eye'].text(),
                **{key:field.isChecked() for key,field in self.body_option_fields.items()})

        def _load_source_name_matcher_template(self, *_):
            name = self.name_matcher_templates.currentData()
            if not name:return
            template = self.controller.preparation_source_name_matcher_template(name)
            self.name_matcher_rows.setPlainText('\n'.join(
                row.fit_joint+' '+row.source_base for row in template.rows))
            self.name_matcher_right.setText(template.rules.right)
            self.name_matcher_left.setText(template.rules.left)
            self.name_matcher_middle.setText(template.rules.middle)
            self.name_matcher_prefix.setChecked(template.rules.side_before_name)
            self.name_matcher_underscore.setChecked(template.rules.side_underscore)

        def _check_source_name_matcher(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                from maya import cmds
                selected = cmds.ls(selection=True,long=True,type='joint') or ()
                if len(selected)!=1:raise ValueError('请选中来源骨架根关节或填写来源入口')
                root = selected[0]
            checked = self.controller.preparation_name_matcher_check(self._namespace(),root)
            if checked is None:return '已取消 NameMatcher 检查。'
            self.name_matcher_source_root.setText(checked)
            return '已执行原版 NameMatcher 检查。'

        def _export_source_name_matcher_template(self):
            from adv_py.adapters.maya_source_name_matcher import source_name_matcher_directory
            try:
                directory = str(source_name_matcher_directory())
            except ValueError:
                directory = ''
            filename,_ = QtWidgets.QFileDialog.getSaveFileName(
                self,'导出 NameMatcher 配置',directory,'NameMatcher (*.txt)')
            if not filename:return '已取消 NameMatcher 配置导出。'
            destination = self.controller.preparation_source_name_matcher_export(
                Path(filename),self._name_matcher_mapping_rows(),**self._name_matcher_rule_kwargs())
            return f'已导出原版 NameMatcher 配置：{destination}'

        def _build_name_matcher_fit(self):
            selected_namespace = self._namespace()
            result, namespace = self.controller.preparation_name_matcher_fit(
                selected_namespace, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs(),
                template_name=self.name_matcher_templates.currentData() or None,
                preparation=self._source_fit_preparation())
            if namespace != selected_namespace:
                self._next_role = namespace
            self.name_matcher_source_root.setText(result.source_root)
            return (f'NameMatcher 已在 {namespace} 创建 Fit：'
                    f'{result.placed} 个关节已放置；'
                    + (('未找到：' + '、'.join(result.missing))
                       if result.missing else '全部映射均找到来源。'))

        def _build_name_matcher_character(self):
            selected_namespace = self._namespace()
            result, namespace = (
                self.controller.preparation_name_matcher_character(
                    selected_namespace, self._name_matcher_mapping_rows(),
                    **self._name_matcher_rule_kwargs(),
                    template_name=self.name_matcher_templates.currentData() or None,
                    preparation=self._source_fit_preparation()))
            if namespace != selected_namespace:
                self._next_role = namespace
            self.name_matcher_source_root.setText(result.fit.source_root)
            return (f'NameMatcher 已在 {namespace} 创建 Body 与控制器；'
                    f'{result.attachment.connected} 个外部骨架关节已连接，'
                    + (f'{result.skins_preserved} 套原 Skin 保留；'
                       if result.skins_preserved else '来源未带 Skin；')
                    + (f'动画已烘焙到 {result.animation.controls} 个 FK 控制器。'
                       if result.animation else '来源骨架无动画。')
                    + ((' 未匹配：' + '、'.join(sorted(set(
                        result.fit.missing + result.attachment.missing))))
                       if result.fit.missing or result.attachment.missing
                       else ''))

        def _connect_name_matcher_skeleton(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 外部骨架根路径')
            result = self.controller.tools_name_matcher_connect(
                self._namespace(), root, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs())
            return (f'NameMatcher 已连接 {result.connected} 个外部关节；'
                    + (('未找到：' + '、'.join(result.missing))
                       if result.missing else '全部映射目标均已连接。'))

        def _keep_name_matcher_animation(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 外部骨架根路径')
            result = self.controller.tools_name_matcher_keep_animation(
                self._namespace(), root)
            return (f'NameMatcher 已保留动画骨架：'
                    f'{result.animated_channels} 条关节通道。')

        def _bake_name_matcher_animation(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 外部骨架根路径')
            result = self.controller.tools_name_matcher_bake_kept_animation(
                self._namespace(), root, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs())
            return (f'NameMatcher 已将保留动画烘焙到 '
                    f'{result.controls} 个 FK 控制器，'
                    f'{result.first_frame:g}–{result.last_frame:g} 帧；'
                    + (('未匹配：' + '、'.join(result.missing))
                       if result.missing else '映射完成。'))

        def _transfer_name_matcher_skin(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 外部骨架根路径')
            result = self.controller.tools_name_matcher_transfer_skin(
                self._namespace(), root, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs())
            return (f'NameMatcher 已将 {result.skins} 套 Skin 的'
                    f'{result.matrix_links} 条影响矩阵转接到 Body；'
                    f'保留 {result.retained_branches} 条未映射关节分支、'
                    f'{result.preserved_transforms} 个模型层级；'
                    + (('未找到：' + '、'.join(result.missing))
                       if result.missing else '全部映射目标均已找到。'))

        def _connect_name_matcher_mocap(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 动捕骨架根路径')
            result = self.controller.tools_name_matcher_mocap(
                self._namespace(), root, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs(),
                use_extra=self.name_matcher_extra.isChecked())
            return (f'NameMatcher 已连接 {result.connected_controls} 个控制器；'
                    + (('未匹配：' + '、'.join(result.missing))
                       if result.missing else '全部可用映射已连接。'))

        def _zero_out_name_matcher_mocap(self):
            root = self.name_matcher_source_root.text().strip()
            if not root:
                raise ValueError('请填写 NameMatcher 动捕骨架根路径')
            result = self.controller.tools_name_matcher_zero_out(
                self._namespace(), root, self._name_matcher_mapping_rows(),
                **self._name_matcher_rule_kwargs())
            return (f'NameMatcher 已归零 {result.joints} 个动捕关节；'
                    + (('未匹配：' + '、'.join(result.missing))
                       if result.missing else '全部可用映射已处理。'))

        def _disconnect_name_matcher_mocap(self):
            count = self.controller.tools_name_matcher_disconnect(
                self._namespace())
            return f'NameMatcher 已断开 {count} 条动捕约束。'

        def _bake_name_matcher_mocap(self):
            result = self.controller.tools_name_matcher_bake(
                self._namespace())
            return (f'NameMatcher 已烘焙 {result.controls} 个控制器，'
                    f'范围 {result.first_frame:g}–{result.last_frame:g} 帧。')

        def _load_body_build_options(self):
            options = self.controller.body_build_options(
                self._namespace(), self.fit_container.text().strip())
            for key, field in self.body_option_fields.items():
                field.setChecked(getattr(options, key))
            self.body_option_status.setText("选项已从当前 Fit 读取")
            return "已读取当前 Fit 的 Body 构建选项"

        def _save_body_build_options(self):
            from adv_py.core.body_build_options import BodyBuildOptions

            options = BodyBuildOptions(**{
                key: field.isChecked()
                for key, field in self.body_option_fields.items()})
            self.controller.set_body_build_options(
                self._namespace(), options,
                self.fit_container.text().strip())
            self.body_option_status.setText("选项已保存到当前 Fit")
            return "已保存四项 Body 构建选项；下次构建将从 Fit 读取"

        def _reselect_preparation_objects(self, role):
            objects = self.controller.preparation_reselect_objects(self._namespace(), role)
            self.preparation_object_fields[role].setText(" ".join(objects))
            return f"已重新选中 {role}：{len(objects)} 件模型"

        def _import_fit(self):
            count = self.controller.fit_import(self._namespace(),
                self._path(self.fit_import_document), self.fit_container.text().strip())
            return f"已导入 {count} 个关节"

        def _source_fit_template_import(self):
            source = self.source_fit_templates.currentData()
            if not source:
                raise ValueError('缺少原版 Fit 模板资产目录')
            namespace = self._namespace()
            merge, policy = False, 'existing'
            if self.controller.fit_source_import_has_joints(namespace):
                dialog = QtWidgets.QMessageBox(self)
                dialog.setWindowTitle('导入 Fit 模板')
                dialog.setText('FitSkeleton 已经存在')
                replace = dialog.addButton('替换',QtWidgets.QMessageBox.AcceptRole)
                combine = dialog.addButton('合并',QtWidgets.QMessageBox.ActionRole)
                cancel = dialog.addButton('取消',QtWidgets.QMessageBox.RejectRole)
                dialog.setDefaultButton(replace)
                dialog.setEscapeButton(cancel)
                (getattr(dialog,'exec',None) or dialog.exec_)()
                if dialog.clickedButton() not in (replace,combine):
                    return '已取消原版 Fit 模板导入。'
                merge = dialog.clickedButton() is combine
                if merge:
                    options = QtWidgets.QMessageBox(self)
                    options.setWindowTitle('合并 Fit 模板')
                    options.setText('同名关节如何处理？')
                    buttons = [(options.addButton(label,QtWidgets.QMessageBox.ActionRole),value)
                        for label,value in (('保留已有','existing'),('保留导入','imported'),
                                            ('重命名导入并保留两者','both'))]
                    options.setDefaultButton(buttons[0][0])
                    (getattr(options,'exec',None) or options.exec_)()
                    policy = next((value for button,value in buttons
                                   if options.clickedButton() is button),'both')
            preparation = self._source_fit_preparation()
            joints = self.controller.fit_source_import(namespace,Path(source),merge=merge,
                policy=policy,preparation=preparation)
            self._load_body_build_options()
            follow = self._source_import_matcher_scan()
            return f'已导入原版 {self.source_fit_templates.currentText()}：{len(joints)} 个 Fit 关节。'+follow

        def _source_import_matcher_scan(self):
            namespace = self._namespace()
            detection = self.controller.fit_source_matcher_detect(namespace)
            if detection is None:return ''
            from maya import cmds
            def confirm(title,message):
                return cmds.confirmDialog(title=title,message=message,button=('Yes','No'),
                    defaultButton='Yes',dismissString='No')=='Yes'
            if not confirm('Align ?','External skeleton detected.\n\nAlign joints with this skeleton ?'):
                return ''
            if not self.controller.fit_source_matcher_prepare(namespace,detection):
                return ' 已取消外部骨架准备。'
            index = self.name_matcher_templates.findData(detection.template or '')
            if index<=0 and self.name_matcher_templates.count()>1:index=1
            if index>=0:self.name_matcher_templates.setCurrentIndex(index)
            rows = self._name_matcher_mapping_rows()
            rules = self._name_matcher_rule_kwargs()
            template = self.name_matcher_templates.currentData() or None
            fit = self.controller.fit_source_matcher_align(namespace,detection,rows,
                template_name=template,preparation=self._source_fit_preparation(),**rules)
            self.name_matcher_source_root.setText(fit.source_root)
            if template not in ('MetaHuman','Unreal5') and confirm('Straighten ?','Straighten Arms and Legs ?'):
                self.controller.fit_straighten_pole_vector(namespace,'Leg')
                self.controller.fit_straighten_pole_vector(namespace,'Arm')
                cmds.refresh()
            if not confirm('Build ?','Proceed to Build AdvancedSkeleton and attach ?'):
                return f' 已按外部骨架放置 {fit.placed} 个 Fit 关节，保留供继续编辑。'
            result = self.controller.fit_source_matcher_attach(namespace,fit.source_root,rows,**rules)
            return f' 已构建 {result.joints} 个 Body 关节，连接 {result.connected} 个外部关节。'

        def _source_fit_limb_import(self):
            source = self.source_fit_limbs.currentData()
            if not source:
                raise ValueError('缺少原版 Fit 部件资产目录')
            branches = self.controller.fit_source_limb_import(self._namespace(),Path(source))
            return f'已导入原版 {self.source_fit_limbs.currentText()}：{len(branches)} 个分支。'

        def _source_fit_scene_export(self):
            from adv_py.adapters.maya_source_fit_import import source_fit_asset_directory
            namespace = self._namespace()
            limb = self.controller.fit_source_export_is_limb(namespace)
            try:
                directory = str(source_fit_asset_directory(limbs=limb))
            except ValueError:
                directory = ''
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,'导出原版 Fit 部件' if limb else '导出原版 Fit',directory,
                'Maya ASCII (*.ma)')
            if not filename:
                return '已取消原版 Fit 导出。'
            destination = self.controller.fit_source_export(namespace,Path(filename))
            return f'已导出原版 Fit 场景：{destination}'

        def _fit_joint_lines(self):
            joints = tuple(line.strip() for line in
                self.fit_edit_joints.toPlainText().splitlines() if line.strip())
            if not joints:
                raise ValueError("请至少填写一个 Fit joint")
            return joints

        def _edit_fit_positions(self):
            edits = []
            for number, line in enumerate(
                    self.fit_position_edits.toPlainText().splitlines(), 1):
                if not line.strip():
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) != 4:
                    raise ValueError(f"位置编辑第 {number} 行必须包含关节名和三个数值")
                try:
                    position = tuple(float(value) for value in parts[1:])
                except ValueError as error:
                    raise ValueError(f"位置编辑第 {number} 行包含无效数值") from error
                edits.append((parts[0], position))
            if not edits:
                raise ValueError("请至少填写一行 Fit 位置编辑")
            count = self.controller.fit_edit_positions(self._namespace(),
                tuple(edits), self.fit_container.text().strip())
            return f"已更新 {count} 个 Fit joint 的位置"

        def _edit_fit_metadata(self):
            count = self.controller.fit_edit_metadata(self._namespace(),
                self._fit_joint_lines(), self.fit_metadata_field.currentData(),
                self.fit_metadata_value.text(),
                remove=self.fit_metadata_remove.isChecked())
            return f"已更新 {count} 项 Fit 元数据"

        def _update_source_fit_label_help(self, label):
            from adv_py.core.source_fit_labels import source_fit_label_help
            self.fit_source_label_help.setText(source_fit_label_help(label))

        def _update_source_fit_attribute_help(self, attribute):
            from adv_py.core.source_fit_attributes import source_fit_attribute_help
            self.fit_source_attribute_help.setText(source_fit_attribute_help(attribute))

        def _add_source_fit_labels(self):
            count = self.controller.fit_source_labels(self._namespace(),
                self.fit_source_label.currentData())
            return f'已向 {count} 个所选关节添加原版 IK-Label'

        def _remove_source_fit_labels(self):
            count = self.controller.fit_source_labels(self._namespace(),
                self.fit_source_label.currentData(), remove=True)
            return f'已关闭 {count} 个所选关节的标签显示，保留标签数据'

        def _add_source_fit_attributes(self):
            count = self.controller.fit_source_attributes(self._namespace(),
                self.fit_source_attribute.currentData())
            return f'已向 {count} 个所选关节添加原版 Fit 属性'

        def _remove_source_fit_attributes(self):
            count = self.controller.fit_source_attributes(self._namespace(),
                self.fit_source_attribute.currentData(), remove=True)
            return f'已从 {count} 个所选关节移除原版 Fit 属性'

        def _fit_geometry_update(self):
            count=self.controller.fit_geometry_update(self._namespace(),
                visible=self.fit_geometry_visible.isChecked(),
                geometry_type=self.fit_geometry_type.currentData(),
                gap=self.fit_geometry_gap.value())
            return f'Fit 几何显示已更新：{count} 个骨段'

        def _fit_manual_update(self):
            self.controller.fit_manual_update(self._namespace(), self.fit_container.text().strip())
            return '已按原版顺序更新 Fit 名称、标签、缩放和朝向。'

        def _fit_placement_snap(self):
            joint = self.controller.fit_placement_snap(self._namespace())
            return f'已吸附 {joint} 到所选组件中心。' if joint else '没有选择对象。'

        def _fit_placement_copy(self):
            self.fit_placement_buffer = self.controller.fit_placement_copy(self._namespace())
            self.fit_placement_paste_button.setEnabled(True)
            self.fit_placement_paste_button.setToolTip(' '.join(str(value) for value in self.fit_placement_buffer))
            return '已复制移动工具的位置。'

        def _fit_placement_paste(self):
            if self.fit_placement_buffer is None:
                raise ValueError('请先复制位置')
            count = self.controller.fit_placement_paste(self._namespace(),self.fit_placement_buffer)
            return f'已向 {count} 个所选对象粘贴位置。'

        def _fit_toggle_center_locks(self):
            enabled = self.controller.fit_toggle_center_locks(self._namespace(), self.fit_container.text().strip())
            return '已锁定中心关节。' if enabled else '已解除中心关节锁定。'

        def _fit_toggle_mode(self):
            enabled = self.controller.fit_toggle_mode(self._namespace())
            return '已开启 FitMode。' if enabled else '已关闭 FitMode。'

        def _fit_pole_vector_display(self):
            enabled = self.fit_pole_vectors_visible.isChecked()
            count = self.controller.fit_pole_vector_display(self._namespace(), enabled)
            return f'PoleVector 显示已更新：{count} 个 IK 平面。' if enabled else '已关闭 PoleVector 显示。'

        def _fit_straighten_pole_vector(self, limb):
            changed = self.controller.fit_straighten_pole_vector(self._namespace(), limb)
            return f'已拉直 {limb} PoleVector。' if changed else f'{limb} 的必要 Fit 关节不存在，已跳过。'

        def _fit_toggle_joint_display(self, kind):
            enabled = self.controller.fit_toggle_joint_display(self._namespace(), kind)
            name = '关节轴' if kind == 'axis' else '关节朝向'
            return f'已显示{name}。' if enabled else f'已隐藏{name}。'

        def _fit_finger_up_display(self):
            requested = self.fit_finger_up_visible.isChecked()
            enabled = self.controller.fit_finger_up_display(self._namespace(), requested)
            self.fit_finger_up_visible.setChecked(enabled)
            # Native Finger-up clears the shared visualizers before building.
            self.fit_pole_vectors_visible.setChecked(False)
            self.fit_geometry_visible.setChecked(False)
            return '已创建原版 Finger-up 显示。' if enabled else 'Finger-up 显示已关闭或取消。'

        def _fit_sdk_create_attribute(self):
            from adv_py.core.source_fit_sdk import SourceFitSDKOptions, source_fit_sdk_prompt
            namespace = self._namespace()
            plan = self.controller.fit_sdk_capture(namespace)
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('创建 Fit SDK 属性')
            form = QtWidgets.QFormLayout(dialog)
            message = QtWidgets.QLabel(source_fit_sdk_prompt(plan.message))
            message.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            form.addRow(message)
            attribute = QtWidgets.QLineEdit(plan.suggested_attribute)
            value = QtWidgets.QDoubleSpinBox()
            minimum = QtWidgets.QDoubleSpinBox()
            maximum = QtWidgets.QDoubleSpinBox()
            for box in (value, minimum, maximum):
                box.setRange(-1e9, 1e9)
                box.setDecimals(1)
            value.setValue(10.)
            maximum.setValue(10.)
            has_min = QtWidgets.QCheckBox('Min')
            has_max = QtWidgets.QCheckBox('Max')
            has_min.setChecked(True)
            has_max.setChecked(True)
            has_min.toggled.connect(minimum.setEnabled)
            has_max.toggled.connect(maximum.setEnabled)
            form.addRow('属性名称', attribute)
            form.addRow('驱动值', value)
            form.addRow(has_min, minimum)
            form.addRow(has_max, maximum)
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if (getattr(dialog, 'exec', None) or dialog.exec_)() != QtWidgets.QDialog.Accepted:
                return '已取消 Fit SDK 属性创建。'
            count = self.controller.fit_sdk_create_attribute(namespace, plan,
                SourceFitSDKOptions(attribute.text(), value.value(),
                    minimum.value() if has_min.isChecked() else None,
                    maximum.value() if has_max.isChecked() else None))
            return f'已为 {count} 个 Fit 通道创建线性 SDK 键。'

        def _orient_fit(self):
            selections = []
            for number, line in enumerate(
                    self.fit_orientation_children.toPlainText().splitlines(), 1):
                if not line.strip():
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) != 2:
                    raise ValueError(f"分支子级映射第 {number} 行必须包含目标和直接子级")
                selections.append((parts[0], parts[1]))
            count = self.controller.fit_orient(self._namespace(),
                self._fit_joint_lines(), self.fit_container.text().strip(),
                child_selections=tuple(selections),
                world=self.fit_orientation_mode.currentData() == "world")
            mode = "World Orient" if self.fit_orientation_mode.currentData() == "world" else "Fit 规则"
            return f"已按 {mode} 重新定向 {count} 个 Fit joint"

        def _resample_fit(self):
            start = self.fit_resample_start.text().strip()
            end = self.fit_resample_end.text().strip()
            count = self.fit_resample_count.value()
            created = self.controller.fit_resample(
                self._namespace(), start, end, count,
                self.fit_container.text().strip())
            return f"Fit 关节链已重采样为 {created + 2} 节"

        def _export_skin(self):
            count = self.controller.skin_export(self._namespace(),
                self.skin.text().strip(), self.mesh.text().strip(),
                self._path(self.weights_export_document))
            return f"已导出 {count} 个顶点的权重"

        def _export_skin_surface_source(self):
            count = self.controller.skin_surface_source_export(self._namespace(),
                self.surface_source_skin.text().strip(),
                self.surface_source_mesh.text().strip(),
                self._path(self.surface_asset_out))
            return f"已封装 {count} 个顶点的网格与权重"

        def _transfer_skin_surface(self):
            asset_mode = self.surface_mode.currentData() == "asset"
            mapping = self.surface_mapping.text().strip()
            redistribution = self.surface_mapping_mode.currentData() == "redistribution"
            alignment = self.surface_alignment.text().strip()
            result = self.controller.skin_surface_transfer(self._namespace(),
                self.surface_target_skin.text().strip(),
                self.surface_target_mesh.text().strip(),
                self.surface_distance.value(),
                source_asset=self._path(self.surface_asset_in) if asset_mode else None,
                source_skin="" if asset_mode else self.surface_source_skin.text().strip(),
                source_mesh="" if asset_mode else self.surface_source_mesh.text().strip(),
                mapping_file=Path(mapping) if mapping and not redistribution else None,
                redistribution_file=Path(mapping) if mapping and redistribution else None,
                alignment_file=Path(alignment) if alignment else None,
                max_discarded_weight=self.surface_discard.value(),
                allow_target_extra_influences=self.surface_extra.isChecked(),
                allow_unweighted_missing=self.surface_missing.isChecked())
            return (f"已转移 {result.vertices} 个顶点的权重；"
                    f"{result.changed_vertices} 个顶点发生变化，"
                    f"最大表面距离 {result.max_surface_distance:.6g}")

        def _rebind_skin_from_source_asset(self):
            if self.surface_mode.currentData() != "asset":
                raise ValueError("重绑前请先选“跨场景源资产”，并读取改拓扑前导出的资产")
            result = self.controller.skin_rebind_from_source_asset(
                self._namespace(), self.surface_target_skin.text().strip(),
                self.surface_target_mesh.text().strip(),
                self._path(self.surface_asset_in), self.surface_distance.value(),
                max_discarded_weight=self.surface_discard.value())
            return (f"已重绑并转移 {result.vertices} 个顶点的权重；"
                    f"{result.changed_vertices} 个顶点重新写入，"
                    f"最大表面距离 {result.maximum_distance:.6g}")

        def _capture_pose(self):
            count = self.controller.pose_capture(self._namespace(),
                self._path(self.pose_export_document))
            return f"已保存 {count} 个控制通道"

        def _apply_pose(self):
            count = self.controller.pose_apply(self._namespace(),
                self._path(self.pose_import_document))
            return f"已应用 {count} 个控制通道"

        def _go_to_build_pose(self):
            count = self.controller.pose_to_build(self._namespace())
            return f"已复位 {count} 个构建姿态通道"

        def _set_build_pose(self):
            count = self.controller.pose_set_build(self._namespace())
            return f"已保存 {count} 个构建姿态覆盖通道"

        def _apply_animation(self):
            count = self.controller.animation_apply(self._namespace(),
                self._path(self.animation_import_document))
            return f"已应用 {count} 帧"

        def _build_mesh_paths(self):
            meshes = tuple(line.strip() for line in
                self.build_meshes.toPlainText().splitlines() if line.strip())
            if not meshes and self.build_use_preparation_skin.isChecked():
                meshes = self.controller.preparation_read_objects(
                    self._namespace(), "Skin")
            return meshes

        def _fill_selected_build_meshes(self):
            meshes = self.controller.selected_meshes()
            if not meshes:
                raise ValueError("请在 Maya 场景中选中至少一个网格对象")
            self.build_meshes.setPlainText("\n".join(meshes))
            return f"已填入 {len(meshes)} 件网格"

        def _fill_selected_source_root(self):
            from maya import cmds

            selection = cmds.ls(selection=True, long=True, type="joint") or []
            if len(selection) != 1:
                raise ValueError("请只选中来源骨架的根关节")
            self.build_source_root.setText(selection[0])
            return "已记录来源骨架根关节"

        def _build_character(self):
            value = self.spine_segments.value()
            meshes = self._build_mesh_paths()
            selected_namespace = self._namespace()
            result = self.controller.body_build(selected_namespace,
                self.fit_container.text().strip(),
                spine_segments=value if value else None,
                head_aim=self.head_aim.isChecked(),
                meshes=meshes)
            if result.namespace != selected_namespace:
                self._next_role = result.namespace
            destination = (f"；新角色 {result.namespace}"
                           if result.namespace != selected_namespace else "")
            return (f"角色已登记：{result.joint_count} 个关节、"
                    f"{result.segment_joint_count} 个分段变形关节、"
                    f"{result.channel_count} 个通道、{len(meshes)} 套 Skin"
                    f"{destination}"
                    + ("；" + result.issue if result.issue else ""))

        def _build_from_source(self):
            meshes = self._build_mesh_paths()
            selected_namespace = self._namespace()
            segments = self.spine_segments.value()
            result = self.controller.body_build_from_source(
                selected_namespace, self.build_source_root.text().strip(),
                self.fit_container.text().strip(), meshes=meshes,
                head_aim=self.head_aim.isChecked(),
                spine_segments=segments if segments else None)
            if result.namespace != selected_namespace:
                self._next_role = result.namespace
            destination = (f"；新角色 {result.namespace}"
                if result.namespace != selected_namespace else "")
            return (f"已从来源骨架构建：{result.joint_count} 个 Body 关节、"
                    f"{result.segment_joint_count} 个分段变形关节、"
                    f"{len(meshes)} 套 Skin{destination}"
                    + ("；" + result.issue if result.issue else ""))

        def _migrate_original_skin(self):
            source_namespace = self._namespace()
            result = self.controller.original_skin_migrate(
                source_namespace, self.original_source_skin.text())
            target_namespace = (result.skin.rsplit(":", 1)[0]
                if ":" in getattr(result, "skin", "") else source_namespace)
            if target_namespace != source_namespace:
                self._next_role = target_namespace
            destination = (f"；新角色 {target_namespace}"
                if target_namespace != source_namespace else "")
            return (f"已迁移 {result.vertices} 个顶点、"
                    f"{result.influences} 个影响关节；"
                    f"登记 {result.body_joints} 个 Body 关节；"
                    f"保留 {result.animation_curves} 条动画曲线；"
                    f"共 {len(result.migrated_skins)} 个网格{destination}")

        def _rebuild_character(self):
            extensions = tuple(line.strip() for line in
                self.rebuild_extensions.toPlainText().splitlines() if line.strip())
            result = self.controller.body_rebuild(self._namespace(),
                self.rebuild_namespace.text().strip(), extensions,
                progress=self._progress)
            return (f"角色已原位重建并保留数据：{result.joint_count} 个关节、"
                    f"{result.channel_count} 个通道")

        def _replace_spine_character(self):
            lines = lambda field: tuple(line.strip() for line in
                field.toPlainText().splitlines() if line.strip())
            skins = lines(self.spine_skins)
            meshes = lines(self.spine_meshes)
            if len(skins) != len(meshes) or not skins:
                raise ValueError("原 Skin 与原网格须逐行对应，且至少填写一组")
            result = self.controller.spine_replace(self._namespace(),
                self.spine_replacement.text().strip(), tuple(zip(skins, meshes)),
                start=self.spine_replace_start.value(),
                end=self.spine_replace_end.value(),
                step=self.spine_replace_step.value(),
                mode=self.spine_replace_mode.currentData(),
                fk_substeps=self.spine_replace_substeps.value(),
                max_mesh_error=(self.spine_replace_mesh_limit.value()
                    if self.spine_replace_mesh_gate.isChecked() else None),
                max_body_error=(self.spine_replace_body_limit.value()
                    if self.spine_replace_body_gate.isChecked() else None),
                extensions=lines(self.spine_extensions),
                retained_assets=lines(self.spine_assets),
                retained_nodes=lines(self.spine_nodes),
                retained_graph_roots=lines(self.spine_graph_roots),
                progress=self._progress)
            return (f"跨段数角色已替换：{result.frames} 个写键时刻、"
                    f"{result.fk_groups} 组 FK 控制、{result.skin_count} 个 Skin")

        def _scale_control_curves(self):
            controls = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_scale(
                self._namespace(), controls, self.control_curve_factor.value())
            return f"已缩放 {count} 个控制曲线"

        def _color_control_curves(self):
            controls = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_color(
                self._namespace(), controls,
                self.control_curve_color_mode.currentData())
            return f"已为 {count} 个控制曲线设置颜色"

        def _auto_scale_control_curves(self):
            controls = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_auto_scale(
                self._namespace(), controls, self.control_curve_skin.text())
            return f"已按 Skin 自动缩放 {count} 个控制曲线"

        def _control_curve_style_targets(self):
            return tuple(line.strip() for line in self.control_curve_targets.toPlainText().splitlines() if line.strip())

        def _select_control_curves(self):
            targets=self.controller.select_control_curves(self._namespace(),
                self.control_curve_select_type.currentData(),self.control_curve_select_side.currentData())
            return f'已选择 {len(targets)} 个控制器'

        def _select_control_curve_palette(self,index):
            self.control_curve_palette_index=index
            self.control_curve_custom_rgb=None
            self.control_curve_palette_label.setText('索引 '+str(index))

        def _choose_control_curve_palette_rgb(self):
            colors=self.controller.control_curve_palette_colors()
            rgb=self.control_curve_custom_rgb or colors[self.control_curve_palette_index]
            initial=QtGui.QColor.fromRgbF(*rgb)
            color=QtWidgets.QColorDialog.getColor(initial,self,'编辑调色板颜色')
            if color.isValid():
                self.control_curve_custom_rgb=(color.redF(),color.greenF(),color.blueF())
                self.control_curve_palette_label.setText('索引 %d · RGB %.3f, %.3f, %.3f'%
                    (self.control_curve_palette_index,*self.control_curve_custom_rgb))

        def _set_control_curve_palette(self):
            count=self.controller.control_curves_palette(self._namespace(),self._control_curve_style_targets(),
                self.control_curve_palette_index,rgb=self.control_curve_custom_rgb)
            return f'已设置 {count} 个控制器形状的颜色'

        def _set_control_curve_width(self):
            count=self.controller.control_curves_width(self._namespace(),self._control_curve_style_targets(),
                self.control_curve_width.value())
            return f'已设置 {count} 个控制曲线的宽度'

        def _snap_rotate_control_curves(self,axis):
            count=self.controller.control_curves_snap_rotate(self._namespace(),self._control_curve_style_targets(),axis)
            return f'已将 {count} 个控制曲线绕 {axis.upper()} 旋转 90 度'

        def _mirror_control_curves(self):
            controls = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_mirror(
                self._namespace(), controls,
                self.control_curve_mirror_side.currentData())
            return f"已镜像 {count} 对控制曲线"

        def _swap_control_curves(self):
            targets = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_swap(
                self._namespace(), targets,
                self.control_curve_custom_source.text())
            return f"已替换 {count} 个控制器图标"

        def _copy_control_curves(self, variant):
            controls = tuple(line.strip() for line in
                self.control_curve_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_curves_copy_to_variant(
                self._namespace(), controls, variant)
            return f"已复制 {count} 个主控曲线到 {variant} 控制层"

        def _create_control_mesh(self):
            count = self.controller.create_control_mesh(
                self._namespace(),
                mirror=self.control_mesh_mirror.isChecked())
            return f"已创建 {count} 个 Control Mesh"

        def _create_control_meshes(self):
            count = self.controller.create_control_meshes(self._namespace())
            return f"已批量创建 {count} 个 Control Mesh"

        def _colorize_control_meshes(self):
            count = self.controller.colorize_control_meshes(self._namespace())
            return f"已着色 {count} 个 Control Mesh"

        def _create_ik_control_meshes(self):
            count = self.controller.create_ik_control_meshes(self._namespace())
            return f"已创建 {count} 个 IK Control Mesh"

        def _delete_selected_control_meshes(self):
            count = self.controller.delete_control_meshes(
                self._namespace(), selected_only=True)
            return f"已删除 {count} 个 Control Mesh"

        def _delete_all_control_meshes(self):
            count = self.controller.delete_control_meshes(
                self._namespace(), selected_only=False)
            return f"已删除 {count} 个 Control Mesh"

        def _set_control_orient_axis(self):
            if self.control_orient_world_orient.isChecked():
                return self._set_control_orient_world()
            if self.control_orient_world_match_mode.isChecked():
                return self._set_control_orient_world_axis_match()
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_orient_axis(
                self._namespace(), controls,
                self.control_orient_primary.currentData(),
                self.control_orient_secondary.currentData(),
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked(),
                self.control_orient_mirrored_behavior.isChecked(),
                self.control_orient_mirrored_translate.isChecked())
            return f"已设置 {count} 个控制器的局部轴"

        def _control_orient_mode_changed(self, checked):
            if checked:
                sender = self.sender()
                other = (self.control_orient_world_match_mode
                         if sender is self.control_orient_world_orient
                         else self.control_orient_world_orient)
                other.setChecked(False)
            manual = not (self.control_orient_world_orient.isChecked()
                          or self.control_orient_world_match_mode.isChecked())
            self.control_orient_primary.setEnabled(manual)
            self.control_orient_secondary.setEnabled(manual)

        def _control_orient_axis_changed(self, index):
            primary = self.control_orient_primary.currentIndex()
            secondary = self.control_orient_secondary.currentIndex()
            if primary % 3 == secondary % 3:
                self.control_orient_secondary.setCurrentIndex(0 if secondary == 5 else secondary + 1)

        def _set_control_orient_world(self):
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_orient_world(
                self._namespace(), controls,
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked(),
                self.control_orient_mirrored_behavior.isChecked(),
                self.control_orient_mirrored_translate.isChecked(),
                self.control_orient_primary.currentData(),
                self.control_orient_secondary.currentData())
            return f"已将 {count} 个控制器对齐世界坐标轴"

        def _set_control_orient_world_axis_match(self):
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_orient_world_axis_match(
                self._namespace(), controls,
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked(),
                self.control_orient_mirrored_behavior.isChecked(),
                self.control_orient_mirrored_translate.isChecked(),
                self.control_orient_primary.currentData(),
                self.control_orient_secondary.currentData())
            return f"已按变形关节的世界轴匹配 {count} 个控制器"

        def _detach_control_orient_custom(self):
            controls = self.controller.control_orient_custom_detach(
                self._namespace())
            return f"已分离 {len(controls)} 个控制器；调整控制器方向后重新附着"

        def _attach_control_orient_custom(self):
            count = self.controller.control_orient_custom_attach(
                self._namespace(), self.control_orient_attach_mirror.isChecked())
            return f"已重新附着 {count} 个控制器并保留手工方向"

        def _create_unreal_joints(self):
            plan = self.controller.unreal_joints_create(self._namespace())
            return f"已创建 {len(plan.joints)} 个通用 Unreal IK 关节"

        def _custom_orient_joints(self, action):
            result = self.controller.custom_orient_joints(self._namespace(), action,
                self.game_joint_primary.currentText(), self.game_joint_secondary.currentText())
            if action == 'transfer_skin':
                back, skins = result
                return f"已将 {len(skins)} 个蒙皮的影响连接转回 ADV 骨架" if back else f"已将 {len(skins)} 个蒙皮的影响连接转到 GameSkeleton"
            return 'Custom Orient Joints 操作已完成'

        def _delete_unreal_joints(self):
            self.controller.unreal_joints_delete(self._namespace())
            return "已删除通用 Unreal IK 关节"

        def _read_unreal_mannequin_note(self):
            QtWidgets.QMessageBox.information(self, 'Warning',
                '手动创建 Mannequin 骨架并转移蒙皮后，绑定将不再兼容 '
                'AdvancedSkeleton 的重建及部分功能。\n\n'
                '主控制器会缩放到 Mannequin 高度，模型会复制到场景根级 Geometry。\n\n'
                '如果只是导出到 Unreal 并使用 Mannequin 蓝图，请使用 Export 栏中的 '
                'Mannequin export。')
            return '已显示原版 Mannequin 使用说明'

        def _create_unreal_mannequin(self):
            from maya import cmds
            ctrl_button = bool(cmds.getModifiers() & 4)
            options = self._mannequin_options_dialog(manual=True)
            if options is None:
                return '已取消 Mannequin 创建'
            plan = self.controller.unreal_mannequin_create(
                self._namespace(), self.mannequin_file.text().strip(),
                options.template, options.scale_adv_to_template,
                options.match_template_pose, ctrl_button=ctrl_button)
            return '已创建 ' + plan.template + ' 骨架' if plan is not None else '已取消 Mannequin 创建'

        def _transfer_unreal_mannequin_skin(self):
            count = self.controller.unreal_mannequin_transfer_skin(
                self._namespace())
            return f"已转移 {count} 件网格的蒙皮"

        def _delete_unreal_mannequin(self):
            self.controller.unreal_mannequin_delete(self._namespace())
            return "已删除 Mannequin 骨架并恢复原始 Geometry"

        def _export_original_fbx(self):
            result = self.controller.original_fbx_export(self._namespace())
            return 'FBX 已导出：' + str(result) if result else '已取消 FBX 导出'

        def _prepare_original_export(self, operation):
            result = self.controller.original_export_preparation(self._namespace(), operation)
            return '已取消导出准备' if result is None else '原版导出准备已完成'

        def _export_roblox_dynamic_head(self):
            plan = self.controller.roblox_dynamic_head_export(
                self._namespace(), self.face_pre_face.text().strip())
            return f'Roblox Dynamic Head 已写入 {len(plan.channels)} 个通道的逐帧动画'

        def _export_original_body_rig(self):
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, 'BodyRig export', '', 'JSON 文件 (*.json)')
            if not filename:
                return '已取消 BodyRig 导出'
            result = self.controller.original_body_rig_export(self._namespace(), filename)
            return 'BodyRig 已导出：' + str(result)

        def _mannequin_options_dialog(self, *, manual=False):
            from adv_py.core.original_fbx_export import MannequinExportOptions
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Mannequin')
            form = QtWidgets.QFormLayout(dialog)
            form.addRow(QtWidgets.QLabel('为 Unreal 创建骨架' if manual else
                                        '1：为 Unreal 创建骨架\n2：导出 FBX\n3：恢复绑定'))
            template = QtWidgets.QComboBox()
            template.addItems(('UE4', 'UE5 (Simple)', 'UE5 (Full)'))
            template.setCurrentText('UE5 (Simple)')
            form.addRow('Unreal Mannequin', template)
            scale = QtWidgets.QCheckBox('匹配 Mannequin 比例')
            pose = QtWidgets.QCheckBox('匹配 Mannequin 姿态')
            unused = QtWidgets.QCheckBox('删除无用关节')
            keep = QtWidgets.QCheckBox('保留 Mannequin 关节')
            for box in (scale, pose, unused):
                box.setChecked(True)
            for box in (scale, pose):
                form.addRow(box)
            use_namespace = QtWidgets.QCheckBox('命名空间')
            namespace = QtWidgets.QLineEdit()
            namespace.setEnabled(False)
            use_namespace.toggled.connect(namespace.setEnabled)
            if not manual:
                for box in (unused, keep):
                    form.addRow(box)
                form.addRow(use_namespace, namespace)
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            run_dialog = getattr(dialog, 'exec', None) or dialog.exec_
            if run_dialog() != QtWidgets.QDialog.Accepted:
                return None
            return MannequinExportOptions(template.currentText(),
                scale.isChecked(), pose.isChecked(), unused.isChecked(),
                keep.isChecked(), namespace.text().strip() if use_namespace.isChecked() else '')

        def _export_unreal_mannequin(self):
            from maya import cmds
            # Native captures Ctrl before the options dialog opens.
            ctrl_button = bool(cmds.getModifiers() & 4)
            options = self._mannequin_options_dialog()
            if options is None:
                return '已取消 Mannequin 导出'
            result = self.controller.unreal_mannequin_export(self._namespace(),
                None, self.mannequin_file.text().strip(), options,
                ctrl_button=ctrl_button)
            return 'Mannequin FBX 已导出：' + str(result) if result else '已取消 Mannequin 导出'

        def _export_unreal_face_solver(self):
            destination, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, 'FaceRig export', '', 'JSON 文件 (*.json)')
            if not destination:
                return '已取消 FaceRig 导出'
            if not destination.lower().endswith('.json'):
                destination += '.json'
            result = self.controller.unreal_face_solver_export(self._namespace(), destination)
            return 'FaceRig JSON 已导出：' + str(result) if result else '已取消 FaceRig 导出'

        def _create_unreal_twist_hierarchy(self):
            count = self.controller.unreal_twist_hierarchy(self._namespace(), True)
            return f"已调整 {count} 个 Twist 层级关节"

        def _delete_unreal_twist_hierarchy(self):
            count = self.controller.unreal_twist_hierarchy(self._namespace(), False)
            return f"已恢复 {count} 个 Twist 层级关节"

        def _enable_game_engine_scaling(self):
            count = self.controller.game_engine_scaling(self._namespace(), True)
            return f"已切换 {count} 个 Body 关节的 Game Engine Scaling"

        def _create_game_engine_root_motion(self):
            self.controller.game_engine_root_motion(self._namespace(), True)
            return "已创建 Game Engine Root Motion"

        def _delete_game_engine_root_motion(self):
            self.controller.game_engine_root_motion(self._namespace(), False)
            return "已删除 Game Engine Root Motion"

        def _disable_game_engine_scaling(self):
            count = self.controller.game_engine_scaling(self._namespace(), False)
            return f"已恢复 {count} 个 Body 关节的 Maya Scaling"

        def _rename_to_unreal(self):
            plan = self.controller.unreal_rename(self._namespace())
            return f"已将 {len(plan.names)} 个 ADV 关节重命名为 Unreal 层级"

        def _restore_unreal_names(self):
            self.controller.unreal_restore_names(self._namespace())
            return "已恢复 ADV 关节名称与原层级"

        def _create_squash_controller(self):
            plans = self.controller.squash_controller_create(
                self._namespace(), mirror=self.squash_mirror.isChecked())
            return "已创建 Squash Controller：" + "、".join(
                plan.control for plan in plans)

        def _delete_squash_controller(self):
            controls = self.controller.squash_controller_delete(
                self._namespace())
            return f"已删除 {len(controls)} 个 Squash Controller"

        def _create_human_ik(self):
            plan = self.controller.human_ik_create(
                self._namespace(), create_control_rig=(
                    not self.human_ik_definition_only.isChecked()))
            return f"已映射 {len(plan.assignments)} 个 HumanIK 关节槽位"

        def _delete_human_ik(self):
            self.controller.human_ik_delete(self._namespace())
            return "已删除 HumanIK 并恢复 MotionSystem 显示"

        def _bake_human_ik(self):
            plan = self.controller.human_ik_bake(self._namespace())
            return (f"已将 HumanIK 烘焙到 {len(plan.controls)} 个控制器；"
                    f"帧范围 {plan.first_frame:g}～{plan.last_frame:g}")

        def _create_partial_joints(self):
            specs = self.controller.partial_joints_create(
                self._namespace(),
                include_controller=self.partial_include_controller.isChecked())
            return f"已创建 {len(specs)} 个 Partial Joints"

        def _create_multi_partial_joints(self):
            specs = self.controller.partial_joints_create(
                self._namespace(), count=self.partial_multi_count.value(),
                auto_bind=self.partial_multi_bind.isChecked())
            return f"已创建 {len(specs)} 组 Multi Partial Joints"

        def _delete_partial_joints(self):
            specs = self.controller.partial_joints_delete(self._namespace())
            return f"已删除 {len(specs)} 组 Partial Joints"

        def _custom_fields(self, face=False):
            if face:
                return self.face_custom_controls
            return {
                "source": self.custom_softmod_source,
                "name": self.custom_control_name,
                "parent": self.custom_control_parent,
                "existing": self.custom_control_existing,
                "mesh": self.custom_control_mesh,
                "mirror": self.custom_control_mirror,
                "middle": self.custom_control_middle,
                "local": self.custom_control_local,
                "partial_parent": self.custom_control_partial_parent,
                "skin_cluster": self.custom_skin_cluster,
                "new_layer": self.custom_skin_new_layer,
            }

        def _create_custom_softmod(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_softmod_create(
                self._namespace(), fields["source"].text().strip(),
                fields["name"].text().strip(),
                fields["parent"].text().strip(),
                face=face, mirror=fields["mirror"].isChecked(),
                middle=fields["middle"].isChecked(),
                local=fields["local"].isChecked())
            fields["existing"].setText(state.control)
            paired = ("及对侧" if fields["mirror"].isChecked()
                      and state.control.endswith("_R") else "")
            return f"已创建 SoftMod 控制器{paired}：{state.control}"

        def _open_custom_softmod_tool(self):
            self.controller.custom_softmod_tool()
            return "已打开 SoftMod 工具"

        def _create_custom_cluster(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_cluster_create(
                self._namespace(), fields["source"].text().strip(),
                fields["name"].text().strip(),
                fields["parent"].text().strip(),
                face=face, mirror=fields["mirror"].isChecked(),
                middle=fields["middle"].isChecked(),
                local=fields["local"].isChecked())
            fields["existing"].setText(state.control)
            paired = ("及对侧" if fields["mirror"].isChecked()
                      and state.control.endswith("_R") else "")
            return f"已创建 Cluster 控制器{paired}：{state.control}"

        def _create_custom_skin(self, face=False):
            fields = self._custom_fields(face)
            chosen_skin = fields["skin_cluster"].text().strip()
            if fields["new_layer"].isChecked() and chosen_skin:
                raise ValueError("新建蒙皮层时不应填写现有 SkinCluster")
            state = self.controller.custom_skin_create(
                self._namespace(), fields["source"].text().strip(),
                fields["name"].text().strip(),
                fields["parent"].text().strip(),
                face=face, mirror=fields["mirror"].isChecked(),
                middle=fields["middle"].isChecked(),
                local=fields["local"].isChecked(),
                partial_parent=(fields["partial_parent"].isChecked()
                                if not face else False),
                skin_cluster=("*new" if fields["new_layer"].isChecked()
                              else chosen_skin or None))
            fields["existing"].setText(state.control)
            paired = ("及对侧" if fields["mirror"].isChecked()
                      and state.control.endswith("_R") else "")
            return f"已创建 Skin 控制器{paired}：{state.control}"

        def _add_custom_softmod_mesh(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_softmod_add_mesh(
                self._namespace(), fields["existing"].text().strip(),
                fields["mesh"].text().strip(), face=face)
            return f"当前影响 {len(state.influenced_meshes)} 件网格"

        def _paint_custom_cluster(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_cluster_paint(
                self._namespace(), fields["existing"].text().strip(),
                face=face)
            return f"已打开 Cluster 权重绘制：{state.control}"

        def _mirror_custom_cluster(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_cluster_mirror(
                self._namespace(), fields["existing"].text().strip(),
                face=face)
            return f"已镜像 Cluster 权重：{state.control}"

        def _delete_custom_control(self, face=False):
            fields = self._custom_fields(face)
            state = self.controller.custom_control_delete(
                self._namespace(), fields["existing"].text().strip(),
                face=face)
            fields["existing"].clear()
            return f"已删除自定义控制器：{state.control}"

        def _bind_skin(self):
            influences = tuple(line.strip() for line in
                self.influences.toPlainText().splitlines() if line.strip())
            vertices = self.controller.skin_bind(self._namespace(),
                self.mesh.text().strip(), influences, self.skin.text().strip())
            return f"已绑定网格：{vertices} 个顶点"

        def _select_deform_joints(self):
            count = self.controller.skinning_select_deform_joints(self._namespace())
            return f"已追加选择 {count} 个变形关节；原有网格选择保留"

        def _set_smooth_bind_options(self):
            self.controller.skinning_set_smooth_bind_options()
            return "已设置原版 Smooth Bind 选项，并打开 Maya 绑定选项窗口"

        def _create_skin_cage(self):
            count = self.controller.skin_cage_create(
                self._namespace(),
                include_controller=self.skin_cage_sliders_include_controller.isChecked())
            return f"已生成 SkinCage：{count} 条关节链"

        def _delete_skin_cage(self):
            count = self.controller.skin_cage_delete(self._namespace())
            return f"已删除 {count} 个 SkinCage 节点"

        def _mirror_skin_cage(self, source_side):
            count = self.controller.skin_cage_mirror(
                self._namespace(), source_side,
                include_controller=self.skin_cage_sliders_include_controller.isChecked())
            return f"已镜像 {count} 对 SkinCage 截面曲线"

        def _skin_cage_deformation_width(self):
            count = self.controller.skin_cage_deformation_width(
                self._namespace())
            return f"已调整 {count} 个 SkinCage 起始／末端截面的变形宽度"

        def _skin_cage_groin_locators(self):
            self.controller.skin_cage_groin_locators(self._namespace())
            return "已创建 GroinStart 和 GroinSide 定位器"

        def _skin_cage_adjust_groin(self):
            count = self.controller.skin_cage_adjust_groin(
                self._namespace(),
                include_controller=self.skin_cage_sliders_include_controller.isChecked())
            return f"已调整右髋截面并镜像 {count} 对 SkinCage 曲线"

        def _skin_cage_groin_joint(self):
            self.controller.skin_cage_groin_joint(self._namespace())
            return "已创建 Groin_M 并加入 SkinCage 蒙皮"

        def _skin_cage_delete_curves(self):
            count = self.controller.skin_cage_delete_curves(
                self._namespace())
            return f"已移除 {count} 个 SkinCage 曲线／管体节点"

        def _skin_cage_create_sliders(self):
            count = self.controller.skin_cage_create_sliders(
                self._namespace(), include_controller=(
                    self.skin_cage_sliders_include_controller.isChecked()))
            return f"已创建 {count} 组 SkinCage Sliders"

        def _skin_cage_delete_sliders(self):
            count = self.controller.skin_cage_delete_sliders(
                self._namespace())
            return f"已删除 {count} 组 SkinCage Sliders"

        def _sub_wrap_create_cage(self):
            self.controller.sub_wrap_create_cage(self._namespace())
            return "已创建 SubWrap 笼体"

        def _sub_wrap_delete_cage(self):
            self.controller.sub_wrap_delete_cage(self._namespace())
            return "已删除 SubWrap 笼体"

        def _sub_wrap_wrap_selected(self):
            count = self.controller.sub_wrap_wrap_selected(self._namespace())
            return f"已包裹 {count} 个网格"

        def _sub_wrap_detach(self):
            count = self.controller.sub_wrap_detach(self._namespace())
            return f"已解除 {count} 个 SubWrap 网格"

        def _sub_wrap_attach(self):
            count = self.controller.sub_wrap_attach(self._namespace())
            return f"已恢复 {count} 个 SubWrap 网格"

        def _sub_wrap_exclude_selected(self):
            count = self.controller.sub_wrap_exclude_selected(
                self._namespace())
            return f"已排除 {count} 个 Wrap 顶点"

        def _geometry_cut_up_create(self):
            count = self.controller.geometry_cut_up_create(self._namespace())
            return f"已创建 {count} 个 Skin Cut-Up 几何分片"

        def _geometry_skeleton_create(self):
            count = self.controller.geometry_skeleton_create(self._namespace())
            return f"已创建 {count} 个原版骨形网格"

        def _geometry_skeleton_delete(self):
            self.controller.geometry_skeleton_delete(self._namespace())
            return "已删除骨骼几何"

        def _geometry_skeleton_mirror_l2r(self):
            count = self.controller.geometry_skeleton_mirror(
                self._namespace(), "L")
            return f"已镜像 {count} 对骨骼几何"

        def _geometry_skeleton_mirror_r2l(self):
            count = self.controller.geometry_skeleton_mirror(
                self._namespace(), "R")
            return f"已镜像 {count} 对骨骼几何"

        def _geometry_muscular_create(self):
            curves, groups = self.controller.geometry_muscular_create(
                self._namespace())
            return f"已创建 {curves} 条肌肉曲线、{groups} 组对侧肌肉"

        def _geometry_muscular_delete(self):
            self.controller.geometry_muscular_delete(self._namespace())
            return "已删除 Muscular 几何"

        def _geometry_poly_boxes_create(self):
            count = self.controller.geometry_poly_boxes_create(self._namespace())
            return f"已创建 {count} 个 PolyBoxes 盒体"

        def _geometry_poly_boxes_delete(self):
            self.controller.geometry_poly_boxes_delete(self._namespace())
            return "已删除 PolyBoxes 几何"

        def _geometry_poly_boxes_mirror_l2r(self):
            count = self.controller.geometry_poly_boxes_mirror(
                self._namespace(), "L")
            return f"已镜像 {count} 对 PolyBoxes 盒体"

        def _geometry_poly_boxes_mirror_r2l(self):
            count = self.controller.geometry_poly_boxes_mirror(
                self._namespace(), "R")
            return f"已镜像 {count} 对 PolyBoxes 盒体"

        def _geometry_box_skin_create(self):
            count = self.controller.geometry_box_skin_create(self._namespace())
            return f"已创建 {count} 顶点的 BoxSkin 网格"

        def _geometry_box_skin_delete(self):
            self.controller.geometry_box_skin_delete(self._namespace())
            return "已删除 BoxSkin"

        def _geometry_boolean_create(self):
            count = self.controller.geometry_boolean_create(self._namespace())
            return f"已创建 {count} 个 Boolean 几何体"

        def _geometry_boolean_delete(self):
            self.controller.geometry_boolean_delete(self._namespace())
            return "已删除 Boolean 几何体"

        def _geometry_warp_create(self):
            count = self.controller.geometry_warp_create(self._namespace())
            return f"已创建 {count} 个 Warp 几何体"

        def _geometry_warp_delete(self):
            self.controller.geometry_warp_delete(self._namespace())
            return "已删除 Warp 几何体"

        def _geometry_mannequin_create(self):
            count = self.controller.geometry_mannequin_create(self._namespace())
            return f"已创建 {count} 个 Mannequin 网格"

        def _geometry_mannequin_delete(self):
            self.controller.geometry_mannequin_delete(self._namespace())
            return "已删除 Mannequin 几何"

        def _geometry_cut_up_delete(self):
            self.controller.geometry_cut_up_delete(self._namespace())
            return "已删除 Skin Cut-Up 几何分片"

        def _copy_skin_cage_weights(self):
            count = self.controller.skin_cage_copy_weights(self._namespace())
            return f"已复制 SkinCage 权重到 {count} 个网格"

        def _print_skin_cage_reuse(self):
            count = self.controller.skin_cage_print_reuse(
                self._namespace(),
                transforms=self.skin_cage_reuse_xform.isChecked(),
                shapes=self.skin_cage_reuse_shape.isChecked(),
                catch=self.skin_cage_reuse_catch.isChecked())
            return f"已输出 {count} 条 SkinCage 复用命令"

        def _create_skin_loop(self):
            count = self.controller.skin_loops_create(
                self._namespace(), mirror=self.skin_loop_mirror.isChecked())
            return f"已创建 {count} 个 SkinLoop"

        def _select_all_skin_loops(self):
            count = self.controller.skin_loops_select_all(self._namespace())
            return f"已选择 {count} 个 SkinLoop 的网格边"

        def _copy_skin_loop_weights(self):
            count = self.controller.skin_loops_copy_weights(self._namespace())
            return f"已复制 SkinLoop 权重到 {count} 个网格"

        def _bind_skin_loops(self):
            count = self.controller.skin_loops_bind(self._namespace())
            return f"已绑定 {count} 个 SkinLoop 网格"

        def _delete_skin_loop_cut_up(self):
            self.controller.skin_loops_delete_cut_up(self._namespace())
            return "已删除当前角色的 CutUp 几何组和显示层"

        def _create_skin_loop_cut_up(self):
            count = self.controller.skin_loops_create_cut_up(self._namespace())
            return f"已创建 {count} 个 CutUp 分片"

        def _apply_delta_mush(self):
            count = self.controller.delta_mush_apply(self._namespace())
            return f"已为 {count} 个网格应用 Delta Mush"

        def _bake_delta_mush(self):
            mesh = self.controller.delta_mush_bake(self._namespace())
            return "已为 Body 网格打开 Maya Bake Deformer 工具：" + mesh

        def _select_shapers(self, node=None):
            count = self.controller.shapers_select(self._namespace(), node)
            return f"已选择 {count} 个 Shapers 变形器"

        def _choose_shapers_plugin_root(self):
            chosen = QtWidgets.QFileDialog.getExistingDirectory(
                self, "选择 Shapers 插件目录",
                self.shapers_plugin_root.text().strip())
            if chosen:
                self.shapers_plugin_root.setText(chosen)

        def _setup_shapers_plugin(self):
            root = self.shapers_plugin_root.text().strip()
            if not root:
                raise ValueError("请选择原版 Shapers 插件目录")
            result = self.controller.shapers_setup(
                Path(root), mode=self.shapers_plugin_mode.currentData(),
                autoload=self.shapers_plugin_autoload.isChecked())
            self._refresh_shapers_plugin_status()
            if result.restart_required:
                return ("已配置插件；当前 Maya 已加载另一种 Shapers 实现。"
                        "保存场景并重启 Maya 后生效：" + str(result.selected_file))
            return "Shapers 插件已加载：" + str(result.selected_file)

        def _refresh_shapers_plugin_status(self, status=None):
            status = status or self.controller.shapers_plugin_status()
            if status.loaded_file:
                mode = "原生 C++" if status.mode == "native" else "Python"
                loading = "自动加载" if status.autoload else "手动加载"
                self.shapers_plugin_status_label.setText(f"已加载 {mode} · {loading}")
                self.shapers_plugin_status_label.setToolTip(str(status.loaded_file))
            else:
                self.shapers_plugin_status_label.setText("未加载")
                self.shapers_plugin_status_label.setToolTip("")

        def _create_shapers(self):
            count = self.controller.shapers_create(
                self._namespace(),
                loop_controls=self.shapers_loop_controls.value(),
                snap_vertices=self.shapers_loop_snap.isChecked(),
                mirror=self.shapers_mirror.isChecked(),
                bridge_controls=self.shapers_bridge_controls.value(),
                bridge_snap_vertices=self.shapers_bridge_snap.isChecked())
            return f"已创建 {count} 条 Shapers 控制曲线"

        def _rebind_shapers(self, node=None):
            count = self.controller.shapers_rebind(self._namespace(), node)
            return f"已重新绑定 {count} 个 Shapers 变形器"

        def _delete_shapers(self):
            result = self.controller.shapers_delete(self._namespace())
            message = (f"已删除 {result.deformers} 个 Shapers 变形器，"
                       f"清理 {result.collapsed_shapes} 个生成形状层")
            if result.cleanup_errors:
                message += "；未清理完成：" + "；".join(result.cleanup_errors)
            return message

        def _shapers_context_menu(self, button, point, operation):
            nodes = self.controller.shapers_list(self._namespace())
            menu = QtWidgets.QMenu(button)
            if not nodes:
                empty = menu.addAction("当前角色没有 Shapers 变形器")
                empty.setEnabled(False)
            else:
                callback = (self._select_shapers if operation == "select"
                            else self._rebind_shapers)
                label = "选择" if operation == "select" else "重新绑定"
                for node in nodes:
                    action = menu.addAction(node)
                    action.triggered.connect(
                        lambda checked=False, target=node:
                        self._run(label, lambda: callback(target)))
            menu.exec_(button.mapToGlobal(point))

        def _harden_delta_mush_weights(self):
            count = self.controller.delta_mush_harden_weights(self._namespace())
            return f"已硬化 {count} 个网格的蒙皮权重"

        def _import_skin(self):
            mapping = self.mapping_document.text().strip()
            changed = self.controller.skin_import(self._namespace(),
                self._path(self.weights_import_document), Path(mapping) if mapping else None,
                allow_unweighted_missing=self.allow_missing.isChecked())
            return f"权重已恢复：{changed} 个顶点发生变化"

        def _capture_animation(self):
            frames = self.controller.animation_capture(self._namespace(),
                self._path(self.animation_export_document), self.start_frame.value(),
                self.end_frame.value(), self.frame_step.value())
            return f"已保存 {frames} 帧全身动画"

        def _key_current_pose(self):
            count = self.controller.animation_key_current(self._namespace())
            return f"当前帧已写入 {count} 个控制通道的关键帧"

        def _enable_limb_animation(self):
            count = self.controller.animation_enable_limb(self._namespace())
            return f"四肢动画已启用：{count} 个控制通道"

        def _enable_stretch_matching(self):
            count = self.controller.animation_enable_stretch(self._namespace())
            return f"拉伸匹配已启用：{count} 个控制通道"

        def _enable_spline_animation(self):
            count = self.controller.animation_enable_spline(self._namespace())
            return f"可变脊柱动画已启用：{count} 个控制通道"

        def _upgrade_source_spline_mode(self):
            before = self.controller._host(self._namespace()).read_character_registration()
            after = self.controller.animation_upgrade_source_spline(self._namespace())
            return "旧 Spline 已升级为原版独立 FKIK 控制器（0–10）" if before != after else "当前 Spline 无需升级"

        def _upgrade_source_spline_alignment(self):
            extensions = tuple(line.strip() for line in
                self.rebuild_extensions.toPlainText().splitlines() if line.strip())
            result = self.controller.animation_upgrade_source_spline_alignment(
                self._namespace(), self.rebuild_namespace.text().strip(), extensions=extensions)
            return (f'已通过保留数据重建，升级 {len(result.systems)} 组 Spline 对齐参考'
                    if result.systems else '当前来源 Spline 对齐参考无需升级')

        def _enable_space_animation(self):
            count = self.controller.animation_enable_spaces(self._namespace())
            return f"控制空间动画已启用：{count} 个控制通道"

        def _bake_limb_mode(self):
            count = self.controller.animation_bake_limb(self._namespace(),
                self.start_frame.value(), self.end_frame.value(),
                self.limb_part.currentData(), self.limb_side.currentData(),
                self.limb_mode.currentData(), self.frame_step.value())
            return f"四肢模式已转换：{count} 个采样帧"

        def _load_limb_systems(self):
            rows=self.controller.animation_limb_systems(self._namespace())
            previous=self.limb_part.currentData()
            self.limb_part.clear()
            for label in dict.fromkeys(label for label,_ in rows):
                self.limb_part.addItem({'arm':'手臂','leg':'腿部'}.get(label,label),label)
            index=self.limb_part.findData(previous)
            if index>=0:
                self.limb_part.setCurrentIndex(index)
            return f"已读取 {len(rows)} 组 IK 系统与侧别"

        def _match_source_limb_mode(self):
            result=self.controller.animation_match_source_limb(self._namespace(),
                self.limb_part.currentData(),self.limb_side.currentData(),
                self.limb_mode.currentData())
            if result is False:return '没有切换：FKIKBlend 需要处于源模式端点'
            return '当前来源 IK 系统已完成姿态切换'

        def _bake_spine_mode(self):
            count = self.controller.animation_bake_spine(self._namespace(),
                self.start_frame.value(), self.end_frame.value(),
                self.spine_mode.currentData(), self.frame_step.value())
            return f"脊柱模式已转换：{count} 个采样帧"

        def _load_spline_systems(self):
            systems=self.controller.animation_spline_systems(self._namespace())
            self.spline_system.clear()
            for system in systems:
                self.spline_system.addItem(system or '主 Spline',system)
            return f'已读取 {len(systems)} 个 Spline 系统'

        def _match_source_spline_mode(self,align_only=False):
            changed=self.controller.animation_match_source_spline(self._namespace(),
                self.spine_mode.currentData(),self.spline_system.currentData(),align_only=align_only)
            return ('Spline 控制器已对齐' if align_only else 'Spline 模式已切换') if changed else '当前模式无法切换，请查看 Maya 提示'

        def _switch_animation_space(self):
            mode = self.controller.animation_switch_space(self._namespace(),
                self.space_key.currentData(), self.space_mode.currentData(),
                self.space_frame.value())
            return f"控制空间已在第 {self.space_frame.value()} 帧切换为{('身体' if mode == 'body' else '全局')}"

        def _face_generate(self):
            vertices = self.controller.face_generate(self._namespace(),
                self.face_neutral.text().strip(), self.face_name.text().strip(),
                self.face_kind.currentData(), self.face_target.text().strip(),
                self._path(self.face_landmarks_document))
            return f"已生成面部目标：{vertices} 个顶点"

        def _face_asset_export(self):
            changes = self.controller.face_asset_export(self._namespace(),
                self.face_neutral.text().strip(), self.face_name.text().strip(),
                self.face_kind.currentData(), self.face_target.text().strip(),
                self._path(self.face_asset_out))
            return f"已导出目标资产：{changes} 个变化顶点"

        def _face_asset_import(self):
            changes = self.controller.face_asset_import(self._namespace(),
                self.face_neutral.text().strip(), self._path(self.face_asset_in),
                self.face_target.text().strip())
            return f"已导入目标网格：{changes} 个变化顶点"

        def _face_build(self):
            channels = self.controller.face_build(self._namespace(),
                self._path(self.face_build_document),
                self.face_control_name.text().strip(),
                self.face_deformer_name.text().strip())
            return f"面部控制已构建：{channels} 个通道"

        def _face_delta_mush_create(self):
            deformer = self.controller.face_delta_mush_create(self._namespace())
            return "已创建 Face DeltaMush：" + deformer

        def _face_delta_mush_delete(self):
            removed = self.controller.face_delta_mush_delete(self._namespace())
            return "已删除 Face DeltaMush" if removed else "当前没有 Face DeltaMush"

        def _face_delta_mush_select(self, area):
            count = self.controller.face_delta_mush_select_area(
                self._namespace(), area)
            return f"已选择 {area}：{count} 项"

        def _face_delta_mush_zero_selected(self):
            deformers = self.controller.face_delta_mush_zero_selected(
                self._namespace())
            return f"所选区域 {len(deformers)} 个 DeltaMush 权重已归零"

        def _face_delta_mush_paint(self):
            deformer = self.controller.face_delta_mush_paint(self._namespace())
            return "已打开 DeltaMush 权重绘制：" + deformer

        def _face_tweaks_select(self, area, subtract):
            count = self.controller.face_tweaks_select_area(
                self._namespace(), area, subtract=subtract)
            action = "扣除" if subtract else "选择"
            return f"已{action} {area}；当前选择 {count} 项"

        def _face_tweaks_smooth(self):
            iterations = self.face_tweaks_iterations.value()
            skin = self.controller.face_tweaks_smooth_weights(
                self._namespace(), iterations)
            return f"已平滑 {skin} 的所选权重：{iterations} 次迭代"

        def _face_tweaks_paint(self):
            joint = self.controller.face_tweaks_paint_skin(self._namespace())
            return "已打开 Face Skin 权重绘制：" + joint

        def _face_tweaks_joints_visible(self, visible):
            restored = self.controller.face_tweaks_set_joints_visible(
                self._namespace(), visible)
            if visible:
                return f"已显示角色关节；恢复 {restored} 个旧 Fit 关节的绘制样式"
            return "已隐藏角色关节"

        def _face_tweaks_swap_spheres(self):
            controls = self.controller.face_tweaks_swap_spheres(
                self._namespace(),
                keep_offset=self.face_tweaks_keep_offset.isChecked())
            return f"已替换 {len(controls)} 个 Face 控制器形状"

        def _face_skin_layers_refresh(self):
            layout = self.face_skin_layers_layout
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            layers = self.controller.face_skin_layers_available(
                self._namespace())
            visible = self.controller.face_skin_layers_visible(self._namespace())
            self.face_skin_layers_group.setVisible(visible)
            route = self._original_section_routes.get('03a · Face Skin Layers')
            if route:
                _, section, group = route
                section.setVisible(visible)
                group.parentWidget().setVisible(visible and section.isChecked())
            for layer in layers:
                layout.addWidget(self._button(layer,
                    lambda layer=layer: self._face_skin_layers_show(layer)))
            return f"已读取 {len(layers)} 个 Face SkinLayer"

        def _face_skin_layers_show(self, layer):
            targets = self.controller.face_skin_layers_show(
                self._namespace(), layer)
            return f"已显示 Face SkinLayer：{layer}（{len(targets)} 个层对象）"

        def _face_build_toggle_fit_advanced(self):
            fit_visible = self.controller.face_build_toggle_fit_advanced(
                self._namespace())
            return "已显示 Face Fit" if fit_visible else "已显示 Face 绑定控制"

        def _body_toggle_fit_advanced(self):
            fit_visible = self.controller.body_toggle_fit_advanced(
                self._namespace())
            return "已显示 Body Fit" if fit_visible else "已显示 Body 绑定控制"

        def _body_toggle_fit_non_symmetry(self):
            changed = self.controller.body_toggle_fit_non_symmetry(
                self._namespace())
            return "已切换非对称 Fit 分支：" + str(len(changed))

        def _body_delete_advanced(self):
            removed = self.controller.body_delete_advanced(
                self._namespace())
            return "已删除 Body Adv，Fit 已保留" if removed else "当前没有 Body Adv"

        def _face_tweaks_detach_controllers(self):
            skins = self.controller.face_tweaks_detach_controllers(
                self._namespace())
            return f"已分离 {len(skins)} 个 Face SkinCluster"

        def _face_tweaks_attach_controllers(self):
            controls = self.controller.face_tweaks_attach_controllers(
                self._namespace())
            return f"已重新附着 Face 控制器；调整 {len(controls)} 个朝向层"

        def _face_record_right_eye(self):
            geometry=self.controller.face_pre_record_eye(self._namespace(),'Right')
            if geometry is None:return '已取消记录右眼输入。'
            path=' '.join(geometry)
            self.face_eye_right.setText(path)
            self.face_fit_right_eye.setText(path)
            return "已记录右眼网格：" + path

        def _face_offset_create(self):
            result = self.controller.face_offset_create(self._namespace())
            if result is None:
                return '已取消 Offset Face 创建'
            return 'Offset Face 场景已建立，请保存当前文件：'+result['file']

        def _face_offset_import(self):
            from adv_py.core.original_offset_face import OriginalOffsetFaceImportOptions
            namespace, joints, name_swap, directory = self.controller.face_offset_import_choices(self._namespace())
            file, _ = QtWidgets.QFileDialog.getOpenFileName(self, '导入 FaceSetup 文件', directory,
                                                          'Maya 场景 (*.ma *.mb)')
            if not file:
                return '已取消 Offset Face 导入'
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Offset Face 导入选项')
            layout = QtWidgets.QFormLayout(dialog)
            namespace_field = QtWidgets.QLineEdit(namespace)
            head = QtWidgets.QComboBox()
            head.addItems(joints)
            swap = QtWidgets.QCheckBox('name-swap')
            swap.setChecked(name_swap)
            search = QtWidgets.QLineEdit('_A')
            replacement = QtWidgets.QLineEdit('_B')
            search.setEnabled(name_swap)
            replacement.setEnabled(name_swap)
            swap.toggled.connect(search.setEnabled)
            swap.toggled.connect(replacement.setEnabled)
            layout.addRow('名称（例如 FaceRight）', namespace_field)
            layout.addRow('Head 关节', head)
            layout.addRow(swap)
            layout.addRow('查找', search)
            layout.addRow('替换', replacement)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addRow(buttons)
            if dialog.exec() != QtWidgets.QDialog.Accepted:
                return '已取消 Offset Face 导入'
            options = OriginalOffsetFaceImportOptions(namespace_field.text(), head.currentText(),
                swap.isChecked(), search.text(), replacement.text())
            result = self.controller.face_offset_import(self._namespace(), file, options)
            return 'Offset Face 已导入：'+result['namespace']+' → '+result['head_joint']

        def _face_offset_update(self):
            result = self.controller.face_offset_update(self._namespace())
            return '已取消 Offset Face 更新' if result is None else f'已更新 {len(result)} 个 Offset Face'

        def _face_auto_fit(self):
            result = self.controller.face_auto_fit(self._namespace(),
                options=self._face_original_option_values())
            if result is None:
                return '未匹配原版已知 Face 模板，或已取消 AutoFit'
            if not result.finished:
                return result.profile+' AutoFit 已中止，Face 输入保留在当前进度'
            if result.build_result is not None:
                return result.profile+' AutoFit 和原版 Face 构建步骤已执行'
            return result.profile+f' AutoFit 已创建 {len(result.rows)} 项 Fit；未继续构建 Face'

        def _face_original_model_check(self):
            result = self.controller.face_original_model_check(self._namespace())
            return f'Face 模型检查结束：{result.vertex_count} 个顶点'

        def _face_record_mask(self):
            result = self.controller.face_pre_record_mask(self._namespace(),
                options=self._face_original_option_values())
            if result is None:
                return '已取消 Face Mask 创建。'
            mesh, count, scale = result
            self.face_pre_mask.setText(f"{mesh} · {count} 面")
            return f"已记录 Mask：{count} 个多边形面；面部高度 {scale:g} cm"

        def _face_record_head_joint(self):
            head=self.controller.face_pre_record_head_joint(self._namespace())
            self.face_eye_head.setText(head.rsplit('|',1)[-1])
            self.face_fit_head.setText(head.rsplit('|',1)[-1])
            return '已记录 Head 关节：'+head

        def _face_skin_input_changed(self):
            if self.face_pre_skin.isModified():
                value = self.face_pre_skin.text()
                def apply():
                    self.controller.face_pre_set_skin_cluster(self._namespace(), value)
                    self.face_pre_skin.setModified(False)
                    return '已记录 Face SkinCluster：' + value
                self._run('记录 Face SkinCluster', apply)

        def _face_record_face(self):
            meshes = self.controller.face_pre_record_objects(
                self._namespace(), "Face", None)
            if meshes is None:
                return '已取消记录 Face 输入。'
            self.face_pre_face.setText(' '.join(meshes))
            return "已记录 Face 网格：" + ' '.join(meshes)

        def _face_record_all_head(self):
            meshes = self.controller.face_pre_record_objects(
                self._namespace(), "AllHead", None)
            if meshes is None:
                return '已取消记录 All Head 输入。'
            self.face_pre_all_head.setText(" ".join(meshes))
            return f"已记录 All Head：{len(meshes)} 件网格"

        def _face_reselect_mask(self):
            count = self.controller.face_pre_reselect(self._namespace(), "Mask")
            return f"已重选 Mask：{count} 个多边形面"

        def _face_reselect_face(self):
            count = self.controller.face_pre_reselect(self._namespace(), "Face")
            return f"已重选 Face：{count} 件网格"

        def _face_reselect_all_head(self):
            count = self.controller.face_pre_reselect(self._namespace(), "AllHead")
            return f"已重选 All Head：{count} 件网格"

        def _face_record_left_eye(self):
            geometry=self.controller.face_pre_record_eye(self._namespace(),'Left')
            if geometry is None:return '已取消记录左眼输入。'
            path=' '.join(geometry)
            self.face_eye_left.setText(path)
            return "已记录左眼网格：" + path

        def _face_fit_eye_ball(self):
            side = self.controller.face_fit_current_side(self._namespace())
            eye = (self.face_fit_left_eye if side == "Left"
                   else self.face_fit_right_eye)
            path = self.controller.face_fit_eye_ball(self._namespace(),
                eye.text().strip(),
                self.face_fit_head.text().strip())
            if path is None:
                return '已取消 EyeBall Fit 创建。'
            eye_label = "左眼" if side == "Left" else "右眼"
            return f"已建立{eye_label} EyeBall Fit：" + path

        def _face_fit_mirror_right_to_left(self):
            result = self.controller.face_fit_mirror_right_to_left(
                self._namespace(), self.face_fit_left_eye.text().strip())
            return ("已镜像左右眼睑 Fit："
                    + f"{result['mapped_vertices']} 个对应顶点、"
                    + f"{len(result['layers'])} 层闭合边环")

        def _face_fit_switch_side(self, side):
            current = self.controller.face_fit_switch_side(self._namespace(), side)
            self.face_fit_side_status.setText(
                "Fit 编辑侧：" + ("左侧" if current == "Left" else "右侧"))
            return "已切换 Face Fit 编辑侧：" + current

        def _face_fit_display(self, operation, section='', part=''):
            result = self.controller.face_fit_display(self._namespace(), operation, section, part)
            if operation == 'reselect':
                return f'已重选 {section}{part}：{len(result)} 个组件。'
            if operation == 'hide':
                return f'{section}{part} 已显示。' if result else f'{section}{part} 已隐藏。'
            if operation == 'assist':
                return f'{section} Assist 已添加。' if result else f'{section} Assist 已移除。'
            if operation == 'side_off':
                return '已关闭 Face Fit 非对称编辑。'
            return f'已显示 {len(result)} 个 Face Fit 分组。'

        def _face_fit_state_check(self,section,part=''):
            check=QtWidgets.QCheckBox()
            check.setEnabled(False)
            check.setToolTip('取消勾选可按原版删除 '+section+part+' Fit')
            check.toggled.connect(lambda checked,s=section,p=part:
                None if checked else self._run('删除 '+s+p+' Fit',
                    lambda:self._face_fit_delete(s,p)))
            self.face_fit_state_controls[(section,part)]=check
            return check

        def _face_original_option_values(self):
            from adv_py.core.original_face_options import ORIGINAL_FACE_OPTIONS
            return {option.attribute: (self.face_original_option_controls[option.attribute].currentText()
                if option.items else self.face_original_option_controls[option.attribute].isChecked())
                for option in ORIGINAL_FACE_OPTIONS}

        def _save_face_original_options(self):
            return self.controller.face_set_original_options(
                self._namespace(), self._face_original_option_values())

        def _face_original_option_changed(self, name):
            values = {name: self._face_original_option_values()[name]}
            if name in ('ARKit', 'SnapChat') and values[name]:
                other = 'SnapChat' if name == 'ARKit' else 'ARKit'
                widget = self.face_original_option_controls[other]
                blocked = widget.blockSignals(True)
                try:
                    widget.setChecked(False)
                finally:
                    widget.blockSignals(blocked)
                values[other] = False
            if name == 'GameEngine':
                self.face_pre_game_engine_options.setVisible(values[name])
            result = self.controller.face_set_original_options(self._namespace(), values,
                switch_side=name == 'NonSym')
            return 'Face 选项已保存' if result is not None else 'Face 选项已设置，记录 Mask 后保存到场景'

        def _refresh_face_original_options(self):
            controls = getattr(self, 'face_original_option_controls', {})
            if not controls:
                return
            values = self.controller.face_read_original_options(self._namespace())
            if values is None:
                return
            from adv_py.core.original_face_options import ORIGINAL_FACE_OPTIONS
            for option in ORIGINAL_FACE_OPTIONS:
                widget = controls[option.attribute]
                blocked = widget.blockSignals(True)
                try:
                    if option.items:
                        widget.setCurrentText(values[option.attribute])
                    else:
                        widget.setChecked(values[option.attribute])
                finally:
                    widget.blockSignals(blocked)
            self.face_pre_game_engine_options.setVisible(values['GameEngine'])

        def _refresh_face_fit_checks(self):
            self._refresh_face_original_options()
            if hasattr(self,'face_eye_head'):
                fields=self.controller.face_pre_input_fields(self._namespace())
                for name,widget in (('Mask',self.face_pre_mask),('Face',self.face_pre_face),
                                    ('AllHead',self.face_pre_all_head),('HeadJoint',self.face_eye_head),
                                    ('SkinCluster',self.face_pre_skin),('RightEye',self.face_eye_right),
                                    ('LeftEye',self.face_eye_left),('RightEye',self.face_fit_right_eye),
                                    ('LeftEye',self.face_fit_left_eye)):
                    if widget is self.face_pre_skin and widget.hasFocus() and widget.isModified():
                        continue
                    widget.setText(fields[name])
                self.face_fit_head.setText(fields['HeadJoint'])
            controls=getattr(self,'face_fit_state_controls',{})
            if not controls:
                return
            states=self.controller.face_fit_states(self._namespace(),tuple(controls))
            for key,check in controls.items():
                blocked=check.blockSignals(True)
                try:
                    check.setChecked(states[key])
                    check.setEnabled(states[key])
                finally:
                    check.blockSignals(blocked)

        def _face_fit_delete(self,section,part):
            removed=self.controller.face_fit_display(self._namespace(),'delete',section,part)
            if removed is None:
                return '已取消删除 '+section+part+' Fit。'
            return '已删除 '+section+part+' Fit。'

        def _face_fit_eye_lid(self, layer):
            upper, lower = self.controller.face_fit_eye_lid(
                self._namespace(), layer)
            suffix = "及区域网格" if layer == "Inner" else ""
            return f"已建立 EyeLid {layer}：上、下两条曲线{suffix}"

        def _face_fit_eye_lid_reselect(self, layer):
            count = self.controller.face_fit_eye_lid_reselect(
                self._namespace(), layer)
            return f"已重选 EyeLid {layer}：{count} 条边"

        def _face_save_include(self):
            include = self.controller.face_build_set_include(
                self._namespace(), self.face_include.currentText())
            return "Face Include 已保存：" + include

        def _face_build_inspect_inputs(self):
            report = self.controller.face_build_inspect_inputs(self._namespace())
            if report["ready"]:
                return ("FaceSetup 输入齐全：" + report["include"]
                        + f"，Fit 标记 {report['required_fit_count']} 项。")
            return ("FaceSetup 尚缺 " + str(len(report["missing"]))
                    + " 项：" + "、".join(report["missing"]))

        def _face_build_eye_lids(self):
            result = self.controller.face_build_eye_lids(
                self._namespace(),
                simpler_eyelid=self.face_simpler_eye_lid.isChecked())
            return format_face_eye_lid_build_result(result)

        def _face_delete_advanced(self):
            removed = self.controller.face_delete_advanced(
                self._namespace(),
                keep_build_pose=self.face_keep_build_pose.isChecked())
            return ("已删除 Face 绑定，Fit 和 Skin 已保留" if removed
                    else "当前没有 Face 绑定")

        def _face_go_to_build_pose(self):
            count = self.controller.face_go_to_build_pose(self._namespace())
            return f"已复位 {count} 个 Face 构建姿态通道"

        def _face_set_build_pose(self):
            count = self.controller.face_set_build_pose(self._namespace())
            return f"已保存 {count} 个 Face 构建姿态覆盖通道"

        def _face_build_original_eye_lid_skin(self):
            result = self.controller.face_build_original_eye_lid_skin(
                self._namespace(), self.face_original_head.text())
            return ("已迁移原版眼睑权重："
                    f"{result['vertex_count']} 个顶点、"
                    f"{result['mapped_segment_influences']} 个分段影响关节、"
                    f"{len(result['auxiliary_joints'])} 个外围关节；"
                    f"{result['approximated_segments']} 个分段作最近编号映射。")

        def _face_outer_blink_read(self):
            side = self.face_outer_side.currentData()
            layer = self.face_lid_layer.currentData()
            arc = self.face_outer_arc.currentData()
            values = self.controller.face_lid_blink_read(self._namespace(),
                                                         side, layer, arc)
            for field, value in zip(self.face_outer_offsets, values):
                field.setValue(value)
            self.face_outer_loaded_key = (self._namespace(), side, layer, arc)
            return ("已读取" + ("右" if side == "Right" else "左")
                    + ("上" if arc == "upper" else "下")
                    + "眼睑 " + layer + " 修形")

        def _face_outer_selection_changed(self, *_):
            self.face_outer_loaded_key = None

        def _face_outer_blink_apply(self):
            side = self.face_outer_side.currentData()
            layer = self.face_lid_layer.currentData()
            arc = self.face_outer_arc.currentData()
            if self.face_outer_loaded_key != (self._namespace(), side,
                                              layer, arc):
                raise ValueError("先读取当前眼睑的闭眼修形")
            values = tuple(field.value() for field in self.face_outer_offsets)
            self.controller.face_lid_blink_apply(self._namespace(), side,
                                                 layer, arc, values)
            return ("已应用" + ("右" if side == "Right" else "左")
                    + ("上" if arc == "upper" else "下")
                    + "眼睑 " + layer + " 修形")

        def _face_performance_apply(self):
            frames = self.controller.face_performance_apply(self._namespace(),
                self.face_control_path.text().strip(),
                self._path(self.face_performance_document))
            return f"已应用 {frames} 帧面部动画"

        def _face_library_dir(self):
            value = self.face_library_directory.text().strip()
            if not value:
                raise ValueError("请填写面部资产版本目录")
            return Path(value)

        def _face_library_refresh(self):
            entries = self.controller.face_library_list(self._face_library_dir())
            self.face_library_versions.clear()
            for entry in entries:
                if entry.valid:
                    self.face_library_versions.addItem(
                        f"{entry.name} · {entry.release}",
                        (entry.name, entry.release))
            invalid = [entry for entry in entries if not entry.valid]
            return (f"有效版本 {self.face_library_versions.count()} 个，"
                    f"损坏引用 {len(invalid)} 个。"
                    + ("\n" + "\n".join(f"{item.name}/{item.release}：{item.reason}"
                        for item in invalid[:3]) if invalid else ""))

        def _face_fit_lip(self,part,*,reselect=False):
            result=self.controller.face_fit_lip(self._namespace(),part,reselect=reselect)
            if reselect: return f"已重选 {result} 个 Lip {part} 组件"
            return f"已建立 Lip {part} Fit，共 {len(result)} 侧上下曲线"

        def _face_fit_lip_swap(self,part):
            self.controller.face_fit_lip_swap(self._namespace(),part)
            return "已按原版交换右侧 Lip "+part+" 上下曲线及预览管"

        def _face_regions(self):
            result=self.controller.face_regions(self._namespace())
            if result is None: return "按原版条件跳过 Regions：缺少 Lip Main Fit"
            return f"已接入 {len(result)} 个第二控制盒区域图标"

        def _face_build_lip(self):
            result=self.controller.face_lip_build(self._namespace())
            if result is None: return "按原版条件跳过 Lip：缺少 Lip Main Fit"
            return f"已建立 Lip Ribbon、Sticky 与表情驱动：{len(result['controls'])} 个控制器"

        def _face_cage(self,action):
            result=self.controller.face_cage(self._namespace(),action,
                None if action=="build" else self.face_cage_smooth.value())
            if result is None: return "按原版条件跳过 Face Cage 阶段"
            if isinstance(result,dict) and "smooth_passes" in result:
                self.face_cage_smooth.setValue(result["smooth_passes"])
            return "Face Cage 操作完成："+action

        def _face_bs_targets_refresh(self):
            targets = self.controller.face_original_blendshape_targets(self._namespace())
            self.face_bs_targets.clear()
            self.face_bs_targets.addItem("当前控制器姿态", None)
            for target in targets:
                self.face_bs_targets.addItem(target, target)
            return "已读取 " + str(len(targets)) + " 个原版驱动目标"

        def _original_driving_mode_changed(self, index=None):
            mode=self.original_driving_mode.currentIndex()
            self.original_driving_control.setEditable(mode!=1)
            self.original_driving_control.setEnabled(mode!=2)
            self.original_driving_attribute.setReadOnly(mode==2)
            self.original_driving_q_rotations.setVisible(mode==2)

        def _original_driving_refresh(self):
            targets=self.controller.original_driving_catalog(self._namespace())
            self.original_driving_targets.clear()
            current=self.original_driving_control.currentText()
            self.original_driving_control.clear()
            self.original_driving_control.addItems(list(dict.fromkeys(target.control for target in targets if not target.control.endswith("_L"))))
            self.original_driving_control.setEditText(current)
            for target in targets:
                self.original_driving_targets.addItem(target.control+"."+target.attribute+" / "+str(len(target.curves))+" SDK",target)
            return "已读取 "+str(len(targets))+" 个原版驱动属性"

        def _original_driving_record(self, role):
            from maya import cmds,mel
            selected=cmds.ls(selection=True,long=True,type="transform") or []
            channelbox=mel.eval("global string $gChannelBoxName; $gChannelBoxName;")
            attributes=cmds.channelBox(channelbox,query=True,selectedMainAttributes=True) or []
            if len(selected)!=1 or len(attributes)!=1:raise ValueError("请选择一个控制器，并在 Channel Box 选择一个通道")
            field=self.original_driving_driver if role=="driver" else self.original_driving_driven
            field.setText(selected[0]+"."+attributes[0])
            return "已记录驱动通道"

        def _original_driving_action(self, action):
            target=self.original_driving_targets.currentData()
            control=target.control if target else ""
            attribute=target.attribute if target else ""
            if action in ("graph","range","mirror","mute","edit","delete") and not target:raise ValueError("请先刷新并选择驱动属性")
            driver=self.original_driving_driver.text().strip()
            driven=self.original_driving_driven.text().strip()
            namespace=self._namespace()
            def local(value):
                return value.rsplit("|",1)[-1].removeprefix(namespace+":") if namespace!=":" else value.rsplit("|",1)[-1]
            if action=="sdk_layer":
                control=local(driven.split(".",1)[0])
                if not control:raise ValueError("请记录被驱动控制器")
            if action=="create":
                mode=self.original_driving_mode.currentIndex()
                control=local(self.original_driving_control.currentText().strip())
                attribute=self.original_driving_attribute.text().strip()
                if mode==1 and not control:raise ValueError("请先刷新并选择已有驱动控制器")
                if mode==2:
                    if "." not in driver:raise ValueError("请先记录所选对象的驱动通道")
                    control,attribute=local(driver).rsplit(".",1)
                    from maya import cmds
                    attribute=cmds.attributeQuery(attribute,node=driver.rsplit(".",1)[0],longName=True)
            if action=="mirror" and control.endswith("_R"):control=control[:-2]+"_L"
            result=self.controller.original_driving_systems(namespace,action,control=control,attribute=attribute,
                driver=local(driver),driven=local(driven),driver_value=self.original_driving_driver_value.value(),
                driven_value=self.original_driving_driven_value.value(),mirror=self.original_driving_mirror.isChecked(),
                q_rotations=self.original_driving_q_rotations.isChecked(),test_symmetry=self.original_driving_test_symmetry.isChecked(),
                show_only_affected=self.original_driving_affected.isChecked(),
                drive_from_selected=action=="create" and self.original_driving_mode.currentIndex()==2)
            if action in ("create","apply_edit","delete"):
                self._original_driving_refresh()
            return "原版 Driving Systems 操作完成："+action

        def _original_pose_functions(self, action):
            options={"name":self.original_pose_name.currentText().strip(),"overwrite":self.original_pose_overwrite.isChecked()}
            if action in ('neutral','t_pose','clean_animation'):options['ui_name']='bodySetup'
            if action=="add_build_pose":
                from maya import cmds,mel
                selected=cmds.ls(selection=True,long=True,type="transform") or []
                namespace=self._namespace()
                options["objects"]=tuple(node.rsplit("|",1)[-1].removeprefix(namespace+":") if namespace!=":" else node.rsplit("|",1)[-1] for node in selected)
                channelbox=mel.eval("global string $gChannelBoxName; $gChannelBoxName;")
                options["attributes"]=tuple(cmds.channelBox(channelbox,query=True,selectedMainAttributes=True) or [])
            result=self.controller.original_pose_functions(self._namespace(),action,**options)
            if action in ("catalog","store","delete"):
                current=self.original_pose_name.currentText()
                names=result if action=="catalog" else self.controller.original_pose_functions(self._namespace(),"catalog")
                self.original_pose_name.clear();self.original_pose_name.addItems(list(names));self.original_pose_name.setEditText(current)
            return "原版 Pose Functions 操作完成："+action

        def _corrective_curve_record(self, role):
            if role=="mesh":
                nodes=self.controller.selected_meshes()
            else:
                from maya import cmds
                nodes=cmds.ls(selection=True,long=True,type="transform") or []
            if len(nodes)!=1:raise ValueError("请选择一个网格或 FK 控制器")
            field=self.corrective_curve_mesh if role=="mesh" else self.corrective_curve_control
            field.setText(nodes[0])
            return "已记录曲线变形来源"

        def _corrective_curve_shapes(self, action):
            result=self.controller.original_corrective_shapes(self._namespace(),"curve_"+action,
                source=self.corrective_curve_mesh.text().strip(),fk_control=self.corrective_curve_control.text().strip(),
                use_soft_mods=self.corrective_use_softmods.isChecked(),mirror=self.corrective_mirror.isChecked())
            return "原版曲线变形操作完成："+action

        def _corrective_refresh(self):
            targets = self.controller.original_corrective_targets(self._namespace())
            self.corrective_targets.clear()
            for target in targets:
                label = target.deform_object+" / "+target.driver_object+" / "+target.driver_attribute+" / "+str(target.value)
                self.corrective_targets.addItem(label+("（过渡）" if target.inbetween else ""),target)
            return "已读取 " + str(len(targets)) + " 个 Corrective 目标"

        def _corrective_record_mesh(self, role):
            meshes = self.controller.selected_meshes()
            if len(meshes) != 1:
                raise ValueError("请选择一个网格对象")
            field = self.corrective_source if role == "source" else self.corrective_destination
            field.setText(meshes[0])
            return "已记录 Corrective 烘焙网格"

        def _corrective_select_action(self, action):
            target = self.corrective_targets.currentData()
            if target is None and action != "graph":
                raise ValueError("请刷新目标后选择，或右键打开 Corrective 目标菜单")
            return self._corrective_shapes(action,target)

        def _corrective_popup(self, button, action, point):
            def show_menu():
                targets = self.controller.original_corrective_targets(self._namespace(),edit=action=="edit")
                menu = QtWidgets.QMenu(button)
                levels = {():menu}
                for target in targets:
                    path = (target.deform_object,target.driver_object,target.driver_attribute,
                            "pos" if target.value>=0 else "neg")
                    for index in range(1,len(path)+1):
                        prefix = path[:index]
                        if prefix not in levels:
                            levels[prefix] = levels[prefix[:-1]].addMenu(prefix[-1])
                    item = levels[path].addAction(str(target.value)+("（过渡）" if target.inbetween else ""))
                    item.setEnabled(action!="delete" or target.deletable)
                    item.setData(target)
                chosen = menu.exec_(button.mapToGlobal(point))
                return self._corrective_shapes(action,chosen.data()) if chosen else "Corrective 目标选择已取消"
            self._run("读取 Corrective 目标",show_menu)

        def _corrective_shapes(self, action, target=None):
            result = self.controller.original_corrective_shapes(self._namespace(),action,target=target,
                q_rotations=self.corrective_q_rotations.isChecked(),use_soft_mods=self.corrective_use_softmods.isChecked(),
                mirror=self.corrective_mirror.isChecked(),source=self.corrective_source.text().strip(),
                destination=self.corrective_destination.text().strip(),
                axes=tuple(self.corrective_axes[label].isChecked() for label in ("+x","-x","+y","-y","+z","-z")))
            if action == "create" and result["q_rotations"]:
                self.corrective_q_rotations.setChecked(True)
            return "原版 Corrective 操作完成：" + action

        def _face_wrinkles(self, action):
            options = dict(wrinkle=self.face_wrinkle_group.currentText(),element=self.face_wrinkle_element.currentText(),
                shader=self.face_wrinkle_shader.text().strip() or None)
            if action == "save_settings":
                values = [box.value() for box in self.face_wrinkle_dimensions]
                options.update(image_path=self.face_wrinkle_image_path.text().strip() or None,
                    map_width=values[0],map_height=values[1],mask_width=values[2],mask_height=values[3],
                    format=self.face_wrinkle_format.currentText())
            result = self.controller.face_original_wrinkles(self._namespace(),action,**options)
            if action in ("settings","save_settings"):
                self.face_wrinkle_image_path.setText(result["imagePath"])
                for box,attr in zip(self.face_wrinkle_dimensions,("mapWidth","mapHeight","maskWidth","maskHeight")):
                    box.setValue(result[attr])
                self.face_wrinkle_format.setCurrentText(result["format"])
            return "原版 WrinkleMap 操作完成：" + action

        def _face_bs_edit(self, action):
            result = self.controller.face_edit_original_blendshapes(self._namespace(), action,
                target=self.face_bs_targets.currentData(), step=self.face_bs_wizard_step,
                auto_mirror=self.face_bs_auto_mirror.isChecked(), multiplier=self.face_bs_delta_multiplier.value(),
                attribute=self.face_bs_new_attribute.text().strip(), control=self.face_bs_new_control.text().strip(),
                mirror=self.face_bs_new_mirror.isChecked(), weight=self.face_bs_weight.value())
            if isinstance(result, dict) and "step" in result:
                self.face_bs_wizard_step = result["step"]
                self.face_bs_wizard_status.setText(str(result["step"]) + "/" + str(result["total"]) +
                    ("，全部完成" if result["finished"] else "，" + result["driver"] + " = " + str(result["value"])))
            return "原版 BlendShape 操作完成：" + action

        def _face_original_bs_convert(self):
            result = self.controller.face_convert_original_blendshapes(self._namespace(),
                keep_joints=self.face_bs_keep_joints.isChecked(),
                keep_targets=self.face_bs_keep_targets.isChecked())
            return "Face 转换完成，共生成 " + str(len(result["targets"])) + " 个驱动目标"

        def _face_original_arkit_connect(self):
            result = self.controller.face_connect_original_arkit(self._namespace(),
                self.face_arkit_source.text().strip() or None,
                mouth_close_includes_open=self.face_arkit_mouth_close.isChecked())
            return "已连接 " + str(len(result["channels"])) + " 个通道，缺少 " + str(len(result["missing_channels"])) + " 个来源通道"

        def _face_original_arkit_disconnect(self):
            self.controller.face_disconnect_original_arkit(self._namespace())
            return "已断开 ARKit 并返回 Face 构建姿态"

        def _face_upgrade_original_fit(self):
            result = self.controller.face_upgrade_original_fit(self._namespace())
            return "旧 Face Fit 已升级，请重新完成 Pre 和 Fit" if result["upgraded"] else "Face Fit 无需升级"

        def _face_original_build(self):
            self._save_face_original_options()
            from adv_py.core.face_lip_falloff import LipFalloffOptions
            options = LipFalloffOptions(outer=self.face_lip_falloff_outer.value(),
                inner=self.face_lip_falloff_inner.value(), iterations=self.face_lip_falloff_iterations.value())
            result = self.controller.face_original_build(self._namespace(),
                manually_restore=self.face_original_manual_restore.isChecked(),
                cage_smooth=None, jaw_smooth=self.face_jaw_smooth.value(), lip_falloff=options)
            return "Face 构建结束，等待手动恢复" if result["restore_pending"] else "原版 Face 构建步骤执行完成"

        def _face_original_restore(self):
            result = self.controller.face_original_restore(self._namespace())
            return "Face 重建恢复完成" if result is not None else "没有待恢复的 Face 重建"

        def _face_expression(self,stage):
            result=self.controller.face_expression(self._namespace(),stage)
            return "Face 表情阶段完成："+stage if result else "当前阶段已完成或按原版条件跳过"

        def _face_jaw(self,action):
            result=self.controller.face_jaw(self._namespace(),action,self.face_jaw_smooth.value())
            return "Jaw 操作完成："+action if result is not None else "当前没有 Lip 输入，Jaw 阶段已跳过"

        def _face_teeth_record(self,part):
            values=self.controller.face_teeth_record(self._namespace(),part)
            if values is None:
                return '已取消记录 '+part+' 输入。'
            return "已记录 "+part+" 输入："+str(len(values))

        def _face_mouth_open_design(self):
            self.controller.face_mouth_open_design(self._namespace())
            return "已建立 Mouth Open SoftMod、衰减曲线与原版张嘴修形关键帧"

        def _face_jaw_lip_weights(self):
            count=self.controller.face_jaw_lip_weights(self._namespace())
            return f"已更新 JawOpenLayer 嘴唇权重：{count} 个顶点"

        def _face_lip_falloff(self,action):
            result=self.controller.face_lip_falloff(self._namespace(),
                outer=self.face_lip_falloff_outer.value(),inner=self.face_lip_falloff_inner.value(),
                iterations=self.face_lip_falloff_iterations.value(),preview=action=="preview",
                update=action=="update",multi_skin_clusters=self.face_lip_falloff_multi.isChecked())
            if result is None: return "按原版条件跳过 Lip Falloff：缺少 Lip Main Fit"
            if result["preview"]: return f"已预览 Lip Falloff 范围：{result['vertices']} 个顶点"
            return f"已更新 Lip Falloff：{result['vertices']} 个顶点，生成权重层"

        def _face_fit_marker(self,section):
            result=self.controller.face_fit_marker(self._namespace(),section)
            if result is None:
                return '按原版条件取消 '+section+' Fit 创建。'
            return "已创建原版 "+section+" Fit："+("、".join(result) if isinstance(result,tuple) else result)

        def _face_build_ctrl_box(self):
            controls=self.controller.face_build_ctrl_box(self._namespace())
            return f"已建立原版 Face 控制面板：{len(controls)} 个控制器"

        def _face_tongue(self,action):
            result=self.controller.face_tongue(self._namespace(),action)
            if action=="record":
                return f"已记录 {len(result)} 项 Tongue 输入" if result is not None else '已取消记录 Tongue 输入。'
            if action=="fit": return f"已创建 {len(result)} 个 Tongue Fit 定位器"
            if action=="finish": return "已完成 Tongue，恢复模型显示" if result else "当前没有 Tongue Fit"
            if result is None: return "按原版条件跳过 Tongue：缺少 Lip Main、Tongue Fit 或 Tongue 输入"
            return f"已建立 {len(result['controls'])} 个 Tongue 控制器，处理 {result['vertices']} 个顶点"

        def _face_build_jaw_fit_curves(self):
            curves = self.controller.face_build_jaw_fit_curves(self._namespace())
            return f"已建立 {len(curves)} 条 Jaw 权重参考曲线，保存在 Face Fit 中"

        def _face_head_squash(self, action):
            result = self.controller.face_head_squash(self._namespace(), action)
            if action == "create":
                return f"已创建 HeadSquash：{len(result.controls)} 个控制器、晶格、样条 IK 与体积补偿"
            if action == "delete":
                return "已删除 HeadSquash" if result else "当前角色没有 HeadSquash"
            if action == "optimize":
                return (f"HeadSquash 保留 {result['retained_vertices']} 个头部顶点，"
                        f"移除 {result['removed_vertices']} 个其他顶点")
            return f"已将 {result} 个所选对象或组件加入 HeadSquash"

        def _face_library_add(self):
            entry = self.controller.face_library_add(self._face_library_dir(),
                self._path(self.face_library_source),
                self.face_library_release.text().strip())
            self._face_library_refresh()
            return f"已登记资产：{entry.name} · {entry.release}"

        def _face_library_export(self):
            selected = self.face_library_versions.currentData()
            if not selected:
                raise ValueError("请先刷新并选择有效的面部资产版本")
            output = self.controller.face_library_export(self._face_library_dir(),
                *selected, self._path(self.face_library_destination))
            return f"已导出资产版本：{output}"

        def _face_library_merge(self):
            entry = self.controller.face_library_merge(self._face_library_dir(),
                self.face_name.text().strip(), self.face_merge_base.text().strip(),
                self.face_merge_left.text().strip(),
                self.face_merge_right.text().strip(),
                self.face_merge_release.text().strip())
            self._face_library_refresh()
            return f"已合并资产版本：{entry.name} · {entry.release}"

        def _inspect_presets(self):
            entries = self.controller.presets(self._namespace(),
                Path(self.preset_directory.text().strip()))
            self.preset_names.clear()
            for entry in entries:
                if entry.applicable:
                    label = "姿态" if entry.kind == "pose" else "动画"
                    self.preset_names.addItem(f"{entry.filename} · {label}", entry.filename)
            rejected = [entry for entry in entries if not entry.applicable]
            return (f"可用 {self.preset_names.count()} 个预设；不可用 {len(rejected)} 个。"
                    + ("\n" + "\n".join(f"{entry.filename}：{entry.reason}"
                        for entry in rejected[:3]) if rejected else ""))

        def _apply_preset(self):
            filename = self.preset_names.currentData()
            if not filename:
                raise ValueError("请先检查并选择一个可用预设")
            count = self.controller.preset_apply(self._namespace(),
                Path(self.preset_directory.text().strip()), filename)
            return f"已应用预设：{filename}，{count} 个通道或采样帧"

        def _publish_fbx(self):
            result = self.controller.publish_fbx(self._namespace(),
                self._path(self.fbx_output), self.fbx_start.value(),
                self.fbx_end.value(), self.fbx_step.value(),
                self.fbx_policy.currentData(),
                self.fbx_value_tolerance.value(),
                self.fbx_matrix_tolerance.value(),
                euler_filter=self.fbx_euler_filter.isChecked(),
                include_skins=self.fbx_include_skins.isChecked(),
                progress=self._progress)
            return (f"FBX 已发布：{result.joints} 个关节、{result.frames} 帧、"
                    f"{result.bytes_written} 字节；SHA-256 {result.sha256[:12]}…")

        def _publish_maya_scene(self):
            size = self.controller.publish_migrated_maya_scene(
                self._namespace(), self._path(self.maya_output))
            return f"独立 Maya 角色场景已导出：{size} 字节"

        def _mocap_retarget(self):
            result = self.controller.mocap_retarget(self._namespace(),
                self._path(self.mocap_source), self._path(self.mocap_mapping),
                self.mocap_namespace.text().strip(), self.mocap_start.value(),
                self.mocap_end.value(), self.mocap_step.value(),
                self.mocap_mode.currentData(), progress=self._progress)
            return (f"动捕已写入：{result.source_joints} 个来源关节、"
                    f"{result.frames} 帧；来源根 {result.source_root}")

        def _role_changed(self, current, previous):
            del previous
            if hasattr(self, "face_outer_loaded_key"):
                self.face_outer_loaded_key = None
            if current is None:
                self.current.setText("当前角色：未选择")
                if hasattr(self, "body_option_fields"):
                    for field in self.body_option_fields.values():
                        field.setChecked(False)
                    self.body_option_status.setText("选择已有 Fit 后读取选项")
                return
            detail = current.data(QtCore.Qt.UserRole + 1)
            self.current.setText("当前角色：" + detail)
            if hasattr(self, "face_skin_layers_layout"):
                self._face_skin_layers_refresh()
            if hasattr(self, "body_option_fields"):
                try:
                    self._load_body_build_options()
                except ValueError:
                    for field in self.body_option_fields.values():
                        field.setChecked(False)
                    self.body_option_status.setText("当前角色尚无可读取的 Fit")
            if hasattr(self, "face_fit_side_status"):
                try:
                    side = self.controller.face_fit_current_side(self._namespace())
                except ValueError:
                    side = "Right"
                self.face_fit_side_status.setText(
                    "Fit 编辑侧：" + ("左侧" if side == "Left" else "右侧"))
            self._refresh_face_original_options()
            if hasattr(self, "preparation_object_fields"):
                for role, field in self.preparation_object_fields.items():
                    try:
                        objects = self.controller.preparation_read_objects(
                            self._namespace(), role)
                        field.setText(" ".join(objects))
                    except ValueError as error:
                        field.setText("记录需更新：" + str(error))

        def refresh_characters(self):
            previous = self.roles.currentItem()
            selected = getattr(self, "_next_role", None) or (
                previous.data(QtCore.Qt.UserRole) if previous else ":")
            self._next_role = None
            self.roles.clear()
            for entry in self.controller.characters():
                title = ("根命名空间" if entry.namespace == ":" else entry.namespace)
                detail = (f"{title} · {entry.joint_count} 关节 / "
                          f"{entry.channel_count} 通道" if entry.registered
                          else f"{title} · {entry.joint_count} 关节 / 通用 FK"
                          if entry.mode == "generic_fk"
                          else f"{title} · 未登记")
                item = QtWidgets.QListWidgetItem(title)
                item.setToolTip(entry.issue or detail)
                item.setData(QtCore.Qt.UserRole, entry.namespace)
                item.setData(QtCore.Qt.UserRole + 1, detail)
                self.roles.addItem(item)
                if entry.namespace == selected:
                    self.roles.setCurrentItem(item)
            if self.roles.currentItem() is None and self.roles.count():
                self.roles.setCurrentRow(0)

        def _run(self, label, callback):
            if self._busy:
                return
            self._busy = True
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            self.status.setPlainText("正在执行：" + label)
            QtWidgets.QApplication.processEvents()
            try:
                message = callback()
                self.status.setPlainText(message)
                self.refresh_characters()
            except (OSError, ValueError, RuntimeError) as error:
                self.status.setPlainText("操作失败：" + str(error))
                QtWidgets.QMessageBox.warning(self, "操作未完成", str(error))
            finally:
                # Restore checkbox state after Cancel or transaction rollback.
                # This is a scene read, not a new fitting operation.
                try:
                    self._refresh_face_fit_checks()
                except (ValueError,RuntimeError):
                    for check in getattr(self,'face_fit_state_controls',{}).values():
                        check.setEnabled(False)
                QtWidgets.QApplication.restoreOverrideCursor()
                self._busy = False

        def _progress(self, stage):
            self.status.setPlainText("正在执行：" + stage)
            QtWidgets.QApplication.processEvents()

    return CharacterPanel()


def show_panel(controller: MayaPanelController | None = None):
    """Show the AdvancedSkeleton-style navigation from Maya's command line."""
    from PySide2 import QtCore, QtWidgets

    panel = create_panel(controller)
    try:
        from adv_py.adapters.maya_panel_window import attach_to_maya_dock
        attach_to_maya_dock(panel)
    except (ImportError, RuntimeError):
        try:
            from adv_py.adapters.maya_panel_window import attach_to_maya_window
            attach_to_maya_window(panel)
        except (ImportError, RuntimeError):
            pass
    panel.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    _OPEN_PANELS.append(panel)
    panel.destroyed.connect(lambda: _OPEN_PANELS.remove(panel)
                            if panel in _OPEN_PANELS else None)
    panel.show()
    return panel


def show_name_matcher_detail(source_root: str = ""):
    """Open the original NameMatcher entry after FBX source detection."""
    from shiboken2 import isValid

    panel = next((item for item in reversed(_OPEN_PANELS)
                  if isValid(item)), None)
    if panel is None:
        panel = show_panel()
    panel.open_original_section("02 · NameMatcher", "Tools", None)
    if source_root:
        panel.name_matcher_source_root.setText(source_root)
    panel.show()
    panel.raise_()
    return panel
