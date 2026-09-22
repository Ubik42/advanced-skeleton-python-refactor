"""Chinese in-Maya workspace for the verified character application flows."""
from __future__ import annotations

from pathlib import Path

from .maya_panel_controller import MayaPanelController


_OPEN_PANELS = []


def create_panel(controller: MayaPanelController | None = None):
    """Create a panel inside an existing Maya Qt application; do not show it."""
    from PySide2 import QtCore, QtWidgets

    if QtWidgets.QApplication.instance() is None:
        raise RuntimeError("请在 Maya 图形会话中创建角色工作台")

    class CharacterPanel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.controller = controller or MayaPanelController()
            self.setObjectName("AdvPyCharacterPanel")
            self.setWindowTitle("角色工作台 · Advanced Skeleton Python")
            self.setMinimumSize(790, 590)
            self.resize(950, 710)
            self._busy = False
            self._build_ui()
            self.refresh_characters()

        def _build_ui(self):
            self.setStyleSheet("""
                QWidget#AdvPyCharacterPanel { background: #131923; color: #E7EAF0;
                    font-family: 'Microsoft YaHei UI', 'Noto Sans CJK SC'; font-size: 13px; }
                QWidget#AdvPyCharacterPanel QLabel,
                QWidget#AdvPyCharacterPanel QCheckBox { color: #DCE5EF; }
                QWidget#RoleRail { background: #0D141D; border-right: 1px solid #354456; }
                QLabel#Title { font-size: 24px; font-weight: 700; color: #F4F6FA; }
                QLabel#Subtitle { color: #A9B8C8; }
                QLabel#CurrentRole { color: #F3BE6E; font-size: 15px; font-weight: 600; }
                QGroupBox { border: 1px solid #354456; border-radius: 8px;
                    margin-top: 15px; padding: 12px 10px 8px; font-weight: 600; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px;
                    color: #C8D5E4; }
                QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1C2733;
                    color: #EDF2F7; border: 1px solid #496073; border-radius: 5px;
                    padding: 6px; selection-background-color: #A96631; }
                QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
                QDoubleSpinBox:focus,
                QComboBox:focus {
                    border: 2px solid #F3BE6E; }
                QComboBox QAbstractItemView { background: #1C2733;
                    color: #EDF2F7; selection-background-color: #3B526C; }
                QPushButton { background: #263649; color: #F0F4F9;
                    border: 1px solid #526478; border-radius: 6px;
                    padding: 7px 13px; min-height: 21px; }
                QPushButton:hover { background: #344C65; }
                QPushButton:pressed { background: #49677F; }
                QPushButton:disabled { color: #82909D; background: #202C38; }
                QPushButton#PrimaryAction { background: #DA9346; color: #171A20;
                    border-color: #E5AA6B; font-weight: 700; }
                QPushButton#PrimaryAction:hover { background: #F2B76F; }
                QTabWidget::pane { border: none; }
                QScrollArea { border: none; background: transparent; }
                QWidget#PageContent, QWidget#qt_scrollarea_viewport {
                    background: #131923; }
                QScrollBar:vertical { background: #16202B; width: 10px; }
                QScrollBar::handle:vertical { background: #536A7F;
                    border-radius: 5px; min-height: 28px; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0; }
                QTabBar::tab { background: #1D2936; color: #B8C7D7;
                    padding: 10px 10px; margin-right: 2px; }
                QTabBar::tab:selected { background: #334960; color: #FFFFFF;
                    border-bottom: 3px solid #F3BE6E; }
                QListWidget { background: transparent; border: none; color: #D5E0EA; }
                QListWidget::item { padding: 10px 8px; border-radius: 6px; }
                QListWidget::item:selected { background: #3B526C; color: #FFFFFF; }
                QCheckBox { spacing: 8px; }
            """)
            outer = QtWidgets.QHBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            rail = QtWidgets.QWidget(objectName="RoleRail")
            rail.setMinimumWidth(190)
            rail.setMaximumWidth(190)
            rail_layout = QtWidgets.QVBoxLayout(rail)
            rail_layout.setContentsMargins(18, 24, 14, 18)
            title = QtWidgets.QLabel("角色工作台", objectName="Title")
            subtitle = QtWidgets.QLabel("Fit → 控制 → 蒙皮\n姿态 → 动画 → 面部", objectName="Subtitle")
            subtitle.setWordWrap(True)
            rail_layout.addWidget(title)
            rail_layout.addWidget(subtitle)
            rail_layout.addSpacing(25)
            rail_layout.addWidget(QtWidgets.QLabel("场景命名空间"))
            self.roles = QtWidgets.QListWidget()
            self.roles.currentItemChanged.connect(self._role_changed)
            rail_layout.addWidget(self.roles, 1)
            refresh = QtWidgets.QPushButton("刷新角色")
            refresh.clicked.connect(self.refresh_characters)
            rail_layout.addWidget(refresh)
            outer.addWidget(rail)

            main = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(main)
            layout.setContentsMargins(20, 20, 20, 18)
            layout.setSpacing(12)
            self.current = QtWidgets.QLabel(objectName="CurrentRole")
            layout.addWidget(self.current)
            self.tabs = QtWidgets.QTabWidget()
            self.tabs.addTab(self._fit_page(), "Fit 与构建")
            self.tabs.addTab(self._skin_page(), "蒙皮")
            self.tabs.addTab(self._animation_page(), "姿态与动画")
            self.tabs.addTab(self._face_page(), "面部")
            self.tabs.addTab(self._mocap_page(), "动捕")
            self.tabs.addTab(self._publish_page(), "发布")
            layout.addWidget(self.tabs, 1)
            layout.addWidget(QtWidgets.QLabel("最近操作"))
            self.status = QtWidgets.QPlainTextEdit()
            self.status.setReadOnly(True)
            self.status.setMaximumHeight(82)
            self.status.setPlainText("选择场景命名空间，然后执行所需操作。")
            layout.addWidget(self.status)
            outer.addWidget(main, 1)

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
            layout.setHorizontalSpacing(13)
            layout.setVerticalSpacing(10)
            for label, widget in rows:
                layout.addRow(label, widget)
            return group, layout

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

        def _fit_page(self):
            page, stack = self._page()
            fit_out, self.fit_export_document = self._file_field("导出 Fit 文档", save=True)
            fit_in, self.fit_import_document = self._file_field("导入 Fit 文档")
            self.fit_container = QtWidgets.QLineEdit("FitSkeleton")
            group, form = self._group("01 · Fit 数据", [
                ("容器名称", self.fit_container), ("导出到", fit_out),
                ("从文件导入", fit_in)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("导出当前 Fit", self._export_fit))
            row.addWidget(self._button("从文档导入", self._import_fit))
            form.addRow(row)
            stack.addWidget(group)

            self.spine_segments = QtWidgets.QSpinBox()
            self.spine_segments.setRange(0, 63)
            self.spine_segments.setSpecialValueText("标准双段")
            self.head_aim = QtWidgets.QCheckBox("包含头部瞄准控制")
            group, form = self._group("02 · 完整角色", [
                ("脊柱配置", self.spine_segments), ("附加控制", self.head_aim)])
            form.addRow(self._button("构建并登记角色", self._build_character,
                                      primary=True))
            stack.addWidget(group)

            self.rebuild_namespace = QtWidgets.QLineEdit("CharacterRebuildStage")
            self.rebuild_extensions = QtWidgets.QPlainTextEdit()
            self.rebuild_extensions.setPlaceholderText(
                "每行一个附件根路径；如 |Root_M|…|Head_M|AdvPy_FaceControls")
            self.rebuild_extensions.setMaximumHeight(88)
            group, form = self._group("03 · 保留数据重建", [
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
            group, form = self._group("04 · 跨段数脊柱角色替换", [
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
            self.mesh = QtWidgets.QLineEdit()
            self.mesh.setPlaceholderText("|BodyMesh")
            self.skin = QtWidgets.QLineEdit("AdvPy_BodySkin")
            self.influences = QtWidgets.QPlainTextEdit()
            self.influences.setPlaceholderText("每行一个完整关节路径")
            self.influences.setMaximumHeight(95)
            self.max_influences = QtWidgets.QSpinBox()
            self.max_influences.setRange(1, 256)
            self.max_influences.setValue(4)
            self.maintain_maximum = QtWidgets.QCheckBox("限制最大影响数")
            self.maintain_maximum.setChecked(True)
            group, form = self._group("01 · 建立 Skin", [
                ("网格路径", self.mesh), ("Skin 名称", self.skin),
                ("影响关节", self.influences), ("最大影响数", self.max_influences),
                ("绑定设置", self.maintain_maximum)])
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
            stack.addWidget(group)
            self.surface_mode.currentIndexChanged.connect(self._surface_mode_changed)
            self._surface_mode_changed()
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
            stack.addWidget(group)

            self.limb_part = QtWidgets.QComboBox()
            self.limb_part.addItem("手臂", "arm")
            self.limb_part.addItem("腿部", "leg")
            self.limb_side = QtWidgets.QComboBox()
            self.limb_side.addItem("右侧", "R")
            self.limb_side.addItem("左侧", "L")
            self.limb_mode = QtWidgets.QComboBox()
            self.limb_mode.addItem("转为 IK", "ik")
            self.limb_mode.addItem("转为 FK", "fk")
            self.spine_mode = QtWidgets.QComboBox()
            self.spine_mode.addItem("转为 IK", "ik")
            self.spine_mode.addItem("转为 FK", "fk")
            group, form = self._group("04 · 区间模式转换", [
                ("部位", self.limb_part), ("侧别", self.limb_side),
                ("四肢目标模式", self.limb_mode),
                ("脊柱目标模式", self.spine_mode)])
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

        def _face_page(self):
            page, stack = self._page()
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
            form.addRow(self._button("构建面部控制", self._face_build, primary=True))
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
            stack.addStretch(1)
            return page

        def _publish_page(self):
            page, stack = self._page()
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
            self.fbx_value_tolerance = QtWidgets.QDoubleSpinBox()
            self.fbx_matrix_tolerance = QtWidgets.QDoubleSpinBox()
            for field in (self.fbx_value_tolerance, self.fbx_matrix_tolerance):
                field.setRange(0.0, 1000.0)
                field.setDecimals(4)
                field.setSingleStep(0.01)
                field.setEnabled(False)
            self.fbx_policy.currentIndexChanged.connect(
                lambda: self._fbx_policy_changed())
            group, form = self._group("01 · 烘焙并发布独立骨架", [
                ("输出文件", output), ("采样帧", frames),
                ("曲线策略", self.fbx_policy),
                ("旋转处理", self.fbx_euler_filter),
                ("通道容差", self.fbx_value_tolerance),
                ("矩阵容差", self.fbx_matrix_tolerance)])
            form.addRow(self._button("发布 FBX", self._publish_fbx, primary=True))
            stack.addWidget(group)
            stack.addWidget(QtWidgets.QLabel(
                "从当前角色构建 Root Motion 与独立导出骨架；目标文件已存在时拒绝覆盖。"))
            stack.addStretch(1)
            return page

        def _mocap_page(self):
            page, stack = self._page()
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
                self._path(self.fit_export_document), self.fit_container.text().strip())
            return f"已导出 {count} 个关节"

        def _import_fit(self):
            count = self.controller.fit_import(self._namespace(),
                self._path(self.fit_import_document), self.fit_container.text().strip())
            return f"已导入 {count} 个关节"

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

        def _capture_pose(self):
            count = self.controller.pose_capture(self._namespace(),
                self._path(self.pose_export_document))
            return f"已保存 {count} 个控制通道"

        def _apply_pose(self):
            count = self.controller.pose_apply(self._namespace(),
                self._path(self.pose_import_document))
            return f"已应用 {count} 个控制通道"

        def _apply_animation(self):
            count = self.controller.animation_apply(self._namespace(),
                self._path(self.animation_import_document))
            return f"已应用 {count} 帧"

        def _build_character(self):
            value = self.spine_segments.value()
            result = self.controller.body_build(self._namespace(),
                self.fit_container.text().strip(),
                spine_segments=value if value else None,
                head_aim=self.head_aim.isChecked())
            return f"角色已登记：{result.joint_count} 个关节、{result.channel_count} 个通道"

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

        def _bind_skin(self):
            influences = tuple(line.strip() for line in
                self.influences.toPlainText().splitlines() if line.strip())
            vertices = self.controller.skin_bind(self._namespace(),
                self.mesh.text().strip(), influences, self.skin.text().strip(),
                self.max_influences.value(),
                maintain_maximum=self.maintain_maximum.isChecked())
            return f"已绑定网格：{vertices} 个顶点"

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

        def _enable_space_animation(self):
            count = self.controller.animation_enable_spaces(self._namespace())
            return f"控制空间动画已启用：{count} 个控制通道"

        def _bake_limb_mode(self):
            count = self.controller.animation_bake_limb(self._namespace(),
                self.start_frame.value(), self.end_frame.value(),
                self.limb_part.currentData(), self.limb_side.currentData(),
                self.limb_mode.currentData(), self.frame_step.value())
            return f"四肢模式已转换：{count} 个采样帧"

        def _bake_spine_mode(self):
            count = self.controller.animation_bake_spine(self._namespace(),
                self.start_frame.value(), self.end_frame.value(),
                self.spine_mode.currentData(), self.frame_step.value())
            return f"脊柱模式已转换：{count} 个采样帧"

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
                progress=self._progress)
            return (f"FBX 已发布：{result.joints} 个关节、{result.frames} 帧、"
                    f"{result.bytes_written} 字节；SHA-256 {result.sha256[:12]}…")

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
            if current is None:
                self.current.setText("当前角色：未选择")
                return
            detail = current.data(QtCore.Qt.UserRole + 1)
            self.current.setText("当前角色：" + detail)

        def refresh_characters(self):
            previous = self.roles.currentItem()
            selected = previous.data(QtCore.Qt.UserRole) if previous else ":"
            self.roles.clear()
            for entry in self.controller.characters():
                title = ("根命名空间" if entry.namespace == ":" else entry.namespace)
                detail = (f"{title} · {entry.joint_count} 关节 / "
                          f"{entry.channel_count} 通道" if entry.registered
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
                QtWidgets.QApplication.restoreOverrideCursor()
                self._busy = False

        def _progress(self, stage):
            self.status.setPlainText("正在执行：" + stage)
            QtWidgets.QApplication.processEvents()

    return CharacterPanel()


def show_panel(controller: MayaPanelController | None = None):
    """Show the in-process panel from Maya's Python command line."""
    from PySide2 import QtCore, QtWidgets

    panel = create_panel(controller)
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
