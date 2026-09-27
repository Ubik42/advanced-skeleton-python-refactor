"""Chinese in-Maya workspace for the verified character application flows."""
from __future__ import annotations

from pathlib import Path

from .maya_panel_controller import MayaPanelController


_OPEN_PANELS = []


def format_face_eye_lid_build_result(result: dict) -> str:
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
    return (f"双侧眼睑控制已建立：{len(result['controls'])} 个控制器、"
            f"{len(result['eye_controls'])} 个眨眼主控、"
            f"{len(result['joints'])} 个分段关节；"
            + f"右侧区域 {result['area_vertices']['Right']} 顶点，"
            + f"左侧区域 {result['area_vertices']['Left']} 顶点"
            + mirrored + aligned + warning + "。")


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
            title.setWordWrap(True)
            subtitle = QtWidgets.QLabel("Fit → 控制 → 蒙皮\n姿态 → 动画\n面部 · 动捕 · 发布", objectName="Subtitle")
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

            self.model_check_results = QtWidgets.QPlainTextEdit()
            self.model_check_results.setReadOnly(True)
            self.model_check_results.setPlaceholderText(
                "选择多边形模型，检查父级变换、构建历史和左右对称性")
            self.model_check_results.setMaximumHeight(180)
            group, form = self._group("00 · 模型检查", [
                ("检查报告", self.model_check_results)])
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
            template_row = QtWidgets.QHBoxLayout()
            template_row.addWidget(self._button("创建基础身体示例 Fit",
                lambda: self._create_fit_template(False)))
            template_row.addWidget(self._button("创建五指身体示例 Fit",
                lambda: self._create_fit_template(True)))
            form.addRow(template_row)
            form.addRow(self._button("从所选标准骨架创建 Fit",
                                      self._fit_from_selected_skeleton))
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
            self.fit_metadata_field = QtWidgets.QComboBox()
            for label, value in (
                    ("Twist 关节数", "twist_joints"),
                    ("Bendy 控制器数", "bendy_controls"),
                    ("Inbetween 关节数", "inbetween_joints"),
                    ("UnTwister", "untwister"),
                    ("禁止镜像", "no_mirror"),
                    ("左侧禁止镜像", "no_mirror_left"),
                    ("Child Of Part", "child_of_part"),
                    ("Global 权重", "global_weight"),
                    ("Global Translate", "global_translate"),
                    ("World Orient Up", "world_orient_up"),
                    ("World Orient Forward", "world_orient_forward"),
                    ("IK Local Mode", "ik_local_mode")):
                self.fit_metadata_field.addItem(label, value)
            self.fit_metadata_value = QtWidgets.QLineEdit()
            self.fit_metadata_value.setPlaceholderText("整数、数值、true/false 或枚举值")
            self.fit_metadata_remove = QtWidgets.QCheckBox("删除所选字段")
            self.fit_orientation_children = QtWidgets.QPlainTextEdit()
            self.fit_orientation_children.setPlaceholderText(
                "分支关节每行：目标关节  指定直接子级\n例如：Root  Spine1")
            self.fit_orientation_children.setMaximumHeight(66)
            self.fit_orientation_mode = QtWidgets.QComboBox()
            self.fit_orientation_mode.addItem("按指定子级 Aim", "child")
            self.fit_orientation_mode.addItem("按 World Orient 元数据", "world")
            group, form = self._group("02 · Fit 编辑", [
                ("位置批量编辑", self.fit_position_edits),
                ("目标关节", self.fit_edit_joints),
                ("元数据字段", self.fit_metadata_field),
                ("字段值", self.fit_metadata_value),
                ("字段操作", self.fit_metadata_remove),
                ("朝向模式", self.fit_orientation_mode),
                ("分支子级映射", self.fit_orientation_children)])
            position_row = QtWidgets.QHBoxLayout()
            position_row.addWidget(self._button("更新 Fit 位置", self._edit_fit_positions))
            position_row.addWidget(self._button("重新定向 Fit", self._orient_fit))
            form.addRow(position_row)
            form.addRow(self._button("更新 Fit 元数据", self._edit_fit_metadata))
            stack.addWidget(group)

            self.spine_segments = QtWidgets.QSpinBox()
            self.spine_segments.setRange(0, 63)
            self.spine_segments.setSpecialValueText("自动读取 Fit")
            self.head_aim = QtWidgets.QCheckBox("包含头部瞄准控制")
            self.infer_missing_fit_labels = QtWidgets.QCheckBox(
                "按关节名补全缺失标签（原版 Fit 兼容）")
            self.build_meshes = QtWidgets.QPlainTextEdit()
            self.build_meshes.setPlaceholderText(
                "每行一个未绑定网格的完整路径；留空时可使用 Preparation / Skin")
            self.build_meshes.setMaximumHeight(76)
            self.build_source_root = QtWidgets.QLineEdit()
            self.build_source_root.setPlaceholderText(
                "来源骨架根关节完整路径；请先将来源置于绑定姿态")
            self.build_use_preparation_skin = QtWidgets.QCheckBox(
                "留空时使用 Preparation / Skin 记录")
            self.build_use_preparation_skin.setChecked(True)
            self.build_max_influences = QtWidgets.QSpinBox()
            self.build_max_influences.setRange(1, 256)
            self.build_max_influences.setValue(4)
            self.build_segment_influences = QtWidgets.QCheckBox(
                "构建四肢及可用的标准躯干、手指分段关节")
            self.build_segment_influences.setChecked(True)
            group, form = self._group("03 · 完整角色", [
                ("脊柱配置", self.spine_segments), ("附加控制", self.head_aim),
                ("Fit 标签", self.infer_missing_fit_labels),
                ("来源骨架", self.build_source_root),
                ("待绑定网格", self.build_meshes),
                ("准备输入", self.build_use_preparation_skin),
                ("分段变形", self.build_segment_influences),
                ("最大影响数", self.build_max_influences)])
            form.addRow(self._button("使用当前选中的网格",
                                      self._fill_selected_build_meshes))
            form.addRow(self._button("记录当前选中的骨架根关节",
                                      self._fill_selected_source_root))
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
            self.custom_control_mirror = QtWidgets.QCheckBox("mirror")
            self.custom_control_mirror.setChecked(True)
            self.custom_control_middle = QtWidgets.QCheckBox("middle")
            self.custom_control_mirror.toggled.connect(
                lambda enabled: self.custom_control_middle.setChecked(False)
                if enabled else None)
            self.custom_control_middle.toggled.connect(
                lambda enabled: self.custom_control_mirror.setChecked(False)
                if enabled else None)
            self.custom_control_local = QtWidgets.QCheckBox("local")
            self.custom_control_local.setChecked(True)
            self.custom_control_partial_parent = QtWidgets.QCheckBox(
                "50% joint as parent（仅 Body Skin）")
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
            group, form = self._group("06 · Custom Controllers", [
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
            form.addRow(QtWidgets.QLabel("First create a SoftMod:"))
            form.addRow(self._button("SoftMod Tool",
                                     self._open_custom_softmod_tool))
            form.addRow(QtWidgets.QLabel("Then:"))
            form.addRow(self._button("Create Skin Control",
                                     self._create_custom_skin))
            form.addRow(self._button("Create Cluster Control",
                                     self._create_custom_cluster))
            form.addRow(self._button("Create SoftMod Control",
                                     self._create_custom_softmod))
            form.addRow(QtWidgets.QLabel("Edit Cluster Control:"))
            form.addRow(self._button("Paint weights for selected Control",
                                     self._paint_custom_cluster))
            form.addRow(self._button("Mirror weights for selected Control",
                                     self._mirror_custom_cluster))
            form.addRow(QtWidgets.QLabel("Edit:"))
            form.addRow(self._button("Add influenced object",
                                     self._add_custom_softmod_mesh))
            form.addRow(QtWidgets.QLabel("Delete:"))
            form.addRow(self._button("Delete selected control",
                                     self._delete_custom_control))
            stack.addWidget(group)

            self.control_curve_targets = QtWidgets.QPlainTextEdit()
            self.control_curve_targets.setPlaceholderText(
                "每行一个控制器路径；留空时处理当前角色的全部已登记控制曲线")
            self.control_curve_targets.setMaximumHeight(76)
            self.control_curve_factor = QtWidgets.QDoubleSpinBox()
            self.control_curve_factor.setRange(.01, 100.)
            self.control_curve_factor.setDecimals(3)
            self.control_curve_factor.setSingleStep(.1)
            self.control_curve_factor.setValue(1.1)
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
            group, form = self._group("07 · Control Curves", [
                ("目标控制器", self.control_curve_targets),
                ("缩放倍率", self.control_curve_factor),
                ("颜色规则", self.control_curve_color_mode),
                ("Skin 网格", self.control_curve_skin),
                ("镜像方向", self.control_curve_mirror_side),
                ("自定义曲线", self.control_curve_custom_source)])
            form.addRow(self._button("缩放控制曲线", self._scale_control_curves))
            form.addRow(self._button("按 Skin 自动缩放", self._auto_scale_control_curves))
            form.addRow(self._button("设置控制曲线颜色", self._color_control_curves))
            form.addRow(self._button("镜像控制曲线形状", self._mirror_control_curves))
            form.addRow(self._button("替换控制器图标", self._swap_control_curves))
            stack.addWidget(group)

            self.control_orient_targets = QtWidgets.QPlainTextEdit()
            self.control_orient_targets.setPlaceholderText(
                "每行一个已登记控制器路径")
            self.control_orient_targets.setMaximumHeight(76)
            self.control_orient_child_selections = QtWidgets.QPlainTextEdit()
            self.control_orient_child_selections.setPlaceholderText(
                "分支关节填写：控制器名 = 直接子关节名；镜像时两侧分别填写")
            self.control_orient_child_selections.setMaximumHeight(64)
            self.control_orient_primary = QtWidgets.QComboBox()
            self.control_orient_secondary = QtWidgets.QComboBox()
            self.control_orient_world_up = QtWidgets.QComboBox()
            for axis in ("X", "Y", "Z", "-X", "-Y", "-Z"):
                self.control_orient_primary.addItem(axis, axis)
                self.control_orient_secondary.addItem(axis, axis)
                self.control_orient_world_up.addItem(axis, axis)
            self.control_orient_secondary.setCurrentIndex(1)
            self.control_orient_world_up.setCurrentIndex(1)
            self.control_orient_world_orient = QtWidgets.QCheckBox("World Orient")
            self.control_orient_world_match_mode = QtWidgets.QCheckBox("World Match")
            self.control_orient_world_orient.toggled.connect(
                self._control_orient_mode_changed)
            self.control_orient_world_match_mode.toggled.connect(
                self._control_orient_mode_changed)
            self.control_orient_curve_unaffected = QtWidgets.QCheckBox(
                "改变方向后保持曲线世界形状")
            self.control_orient_mirror = QtWidgets.QCheckBox("同时设置对侧控制器")
            self.control_orient_mirror.setChecked(True)
            self.control_orient_mirrored_behavior = QtWidgets.QCheckBox(
                "左右同轴旋转产生对称动作")
            self.control_orient_mirrored_behavior.setChecked(True)
            group, form = self._group("08 · Control Orient", [
                ("目标控制器", self.control_orient_targets),
                ("Primary Axis", self.control_orient_primary),
                ("Secondary Axis", self.control_orient_secondary),
                ("World Orient", self.control_orient_world_orient),
                ("World Match", self.control_orient_world_match_mode),
                ("Curve Unaffected", self.control_orient_curve_unaffected),
                ("Mirror", self.control_orient_mirror),
                ("Mirrored Behavior",
                 self.control_orient_mirrored_behavior)])
            form.addRow(self._button("设置控制器局部轴", self._set_control_orient_axis))
            form.addRow("扩展参考轴", self.control_orient_world_up)
            form.addRow("扩展子关节", self.control_orient_child_selections)
            form.addRow(self._button("朝向子关节（扩展）", self._set_control_orient_world_match))
            form.addRow(self._button("分离全部控制器", self._detach_control_orient_custom))
            form.addRow(self._button("重新附着全部控制器", self._attach_control_orient_custom))
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
            group, form = self._group("05 · Delta Mush", [])
            form.addRow(QtWidgets.QLabel("选择已蒙皮的多边形网格。"))
            form.addRow(self._button("硬化权重", self._harden_delta_mush_weights))
            form.addRow(self._button("应用 Delta Mush", self._apply_delta_mush))
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
            self.face_pre_mask = QtWidgets.QLineEdit()
            self.face_pre_mask.setReadOnly(True)
            self.face_pre_face = QtWidgets.QLineEdit()
            self.face_pre_face.setReadOnly(True)
            self.face_pre_all_head = QtWidgets.QLineEdit()
            self.face_pre_all_head.setReadOnly(True)
            self.face_eye_head = QtWidgets.QLineEdit()
            self.face_eye_head.setPlaceholderText("Head_M（Face Pre 默认）")
            group, form = self._group("00 · 面部输入", [
                ("Mask 多边形面", self.face_pre_mask),
                ("Face 网格", self.face_pre_face),
                ("All Head 网格", self.face_pre_all_head),
                ("Head 关节", self.face_eye_head)])
            for label, record, reselect in (
                    ("Mask", self._face_record_mask, self._face_reselect_mask),
                    ("Face", self._face_record_face, self._face_reselect_face),
                    ("All Head", self._face_record_all_head,
                     self._face_reselect_all_head)):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(self._button(label, record))
                row.addWidget(self._button("重选 " + label, reselect))
                form.addRow(row)
            self.face_fit_side_status = QtWidgets.QLabel("Fit 编辑侧：右侧")
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("编辑右侧", lambda: self._face_fit_switch_side("Right")))
            row.addWidget(self._button("编辑左侧", lambda: self._face_fit_switch_side("Left")))
            form.addRow(self.face_fit_side_status)
            form.addRow(row)
            self.face_include = QtWidgets.QComboBox()
            for label in ("Complete", "Skip Above Eyes", "Skip Below Eyes",
                          "Skip Above+Below Eyes"):
                self.face_include.addItem(label)
            form.addRow("Include", self.face_include)
            self.face_include.currentIndexChanged.connect(
                lambda _: self._run("设置 Face Include", self._face_save_include))
            stack.addWidget(group)
            self.face_eye_right = QtWidgets.QLineEdit()
            self.face_eye_right.setPlaceholderText("|model:RightEye")
            self.face_eye_left = QtWidgets.QLineEdit()
            self.face_eye_left.setPlaceholderText("|model:LeftEye")
            group, form = self._group("00 · 眼球输入与控制", [
                ("右眼网格", self.face_eye_right),
                ("左眼网格", self.face_eye_left)])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("记录所选右眼", self._face_record_right_eye))
            row.addWidget(self._button("记录所选左眼", self._face_record_left_eye))
            form.addRow(row)
            form.addRow(self._button("建立双眼控制与蒙皮",
                                     self._face_build_eyes, primary=True))
            stack.addWidget(group)
            self.face_fit_right_eye = QtWidgets.QLineEdit()
            self.face_fit_right_eye.setPlaceholderText("|model:RightEye")
            self.face_fit_left_eye = QtWidgets.QLineEdit()
            self.face_fit_left_eye.setPlaceholderText("|model:LeftEye")
            self.face_fit_head = QtWidgets.QLineEdit("Head_M")
            group, form = self._group("01 · EyeBall Fit", [
                ("右眼网格", self.face_fit_right_eye),
                ("左眼网格", self.face_fit_left_eye),
                ("Head 关节", self.face_fit_head)])
            form.addRow(self._button("建立 EyeBall Fit",
                                     self._face_fit_eye_ball, primary=True))
            stack.addWidget(group)
            group, form = self._group("02 · EyeLid Fit", [])
            form.addRow(QtWidgets.QLabel(
                "选择 Face 网格闭合眼睑边环，可加选一至两个眼角顶点；按 Outer → Main → Inner 建立。"))
            for layer in ("Outer", "Main", "Inner"):
                row = QtWidgets.QHBoxLayout()
                row.addWidget(self._button("EyeLid " + layer,
                    lambda layer=layer: self._face_fit_eye_lid(layer)))
                row.addWidget(self._button("重选 " + layer,
                    lambda layer=layer: self._face_fit_eye_lid_reselect(layer)))
                form.addRow(row)
            form.addRow(self._button("对称角色：右侧 Fit 镜像到左侧",
                                     self._face_fit_mirror_right_to_left))
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
            form.addRow(self._button("检查 FaceSetup 输入",
                                     self._face_build_inspect_inputs))
            form.addRow(self._button("建立双侧眼睑关节与蒙皮",
                                     self._face_build_eye_lids))
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
            for key, label in (("mirror", "mirror"), ("middle", "middle"),
                               ("local", "local"),
                               ("new_layer", "新建分层 SkinCluster")):
                face_custom[key] = QtWidgets.QCheckBox(label)
            face_custom["mirror"].setChecked(True)
            face_custom["local"].setChecked(True)
            face_custom["mirror"].toggled.connect(
                lambda enabled: face_custom["middle"].setChecked(False)
                if enabled else None)
            face_custom["middle"].toggled.connect(
                lambda enabled: face_custom["mirror"].setChecked(False)
                if enabled else None)
            group, form = self._group("07 · Custom Controllers", [
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
            form.addRow(self._button("SoftMod Tool",
                                     self._open_custom_softmod_tool))
            form.addRow(QtWidgets.QLabel("然后创建控制器："))
            form.addRow(self._button("Create Skin Control",
                lambda: self._create_custom_skin(face=True)))
            form.addRow(self._button("Create Cluster Control",
                lambda: self._create_custom_cluster(face=True)))
            form.addRow(self._button("Create SoftMod Control",
                lambda: self._create_custom_softmod(face=True)))
            form.addRow(QtWidgets.QLabel("编辑 Cluster Control："))
            form.addRow(self._button("Paint weights for selected Control",
                lambda: self._paint_custom_cluster(face=True)))
            form.addRow(self._button("Mirror weights for selected Control",
                lambda: self._mirror_custom_cluster(face=True)))
            form.addRow(QtWidgets.QLabel("编辑："))
            form.addRow(self._button("Add influenced object",
                lambda: self._add_custom_softmod_mesh(face=True)))
            form.addRow(QtWidgets.QLabel("删除："))
            form.addRow(self._button("Delete selected control",
                lambda: self._delete_custom_control(face=True)))
            stack.addWidget(group)
            stack.addStretch(1)
            return page

        def _publish_page(self):
            page, stack = self._page()
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
            result = self.controller.model_check()
            lines = [f"模型：{result.mesh}", f"顶点：{result.vertex_count}"]
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
            result = self.controller.preparation_one_joint_prop(self._namespace())
            return (f"单关节道具已构建：{len(result.meshes)} 件模型、"
                    f"{len(result.skins)} 套 Skin；控制器 Main")

        def _reselect_preparation_objects(self, role):
            objects = self.controller.preparation_reselect_objects(self._namespace(), role)
            self.preparation_object_fields[role].setText(" ".join(objects))
            return f"已重新选中 {role}：{len(objects)} 件模型"

        def _import_fit(self):
            count = self.controller.fit_import(self._namespace(),
                self._path(self.fit_import_document), self.fit_container.text().strip())
            return f"已导入 {count} 个关节"

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
            mode = "World Orient" if self.fit_orientation_mode.currentData() == "world" else "子级 Aim"
            return f"已按 {mode} 重新定向 {count} 个 Fit joint"

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
            result = self.controller.body_build(self._namespace(),
                self.fit_container.text().strip(),
                spine_segments=value if value else None,
                head_aim=self.head_aim.isChecked(),
                infer_missing_labels=self.infer_missing_fit_labels.isChecked(),
                meshes=meshes,
                maximum_influences=self.build_max_influences.value(),
                segment_influences=self.build_segment_influences.isChecked())
            return (f"角色已登记：{result.joint_count} 个关节、"
                    f"{result.segment_joint_count} 个分段变形关节、"
                    f"{result.channel_count} 个通道、{len(meshes)} 套 Skin")

        def _build_from_source(self):
            meshes = self._build_mesh_paths()
            selected_namespace = self._namespace()
            result = self.controller.body_build_from_source(
                selected_namespace, self.build_source_root.text().strip(),
                self.fit_container.text().strip(), meshes=meshes,
                maximum_influences=self.build_max_influences.value(),
                head_aim=self.head_aim.isChecked(),
                segment_influences=self.build_segment_influences.isChecked())
            if result.namespace != selected_namespace:
                self._next_role = result.namespace
            destination = (f"；新角色 {result.namespace}"
                if result.namespace != selected_namespace else "")
            return (f"已从来源骨架构建：{result.joint_count} 个 Body 关节、"
                    f"{result.segment_joint_count} 个分段变形关节、"
                    f"{len(meshes)} 套 Skin{destination}")

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
                self.control_orient_mirrored_behavior.isChecked())
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

        def _set_control_orient_world(self):
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_orient_world(
                self._namespace(), controls,
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked())
            self.control_orient_primary.setCurrentIndex(0)
            self.control_orient_secondary.setCurrentIndex(2)
            self.control_orient_mirrored_behavior.setChecked(False)
            return f"已将 {count} 个控制器对齐世界坐标轴；镜像行为已关闭"

        def _set_control_orient_world_axis_match(self):
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            count = self.controller.control_orient_world_axis_match(
                self._namespace(), controls,
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked())
            self.control_orient_primary.setCurrentIndex(0)
            self.control_orient_secondary.setCurrentIndex(2)
            self.control_orient_mirrored_behavior.setChecked(False)
            return f"已按变形关节的世界轴匹配 {count} 个控制器"

        def _set_control_orient_world_match(self):
            controls = tuple(line.strip() for line in
                self.control_orient_targets.toPlainText().splitlines()
                if line.strip())
            child_selections = []
            for line in self.control_orient_child_selections.toPlainText().splitlines():
                if not line.strip():
                    continue
                control, separator, child = line.partition("=")
                if not separator or not control.strip() or not child.strip():
                    raise ValueError("子关节指定应为：控制器名 = 直接子关节名")
                child_selections.append((control.strip(), child.strip()))
            count = self.controller.control_orient_world_match(
                self._namespace(), controls,
                self.control_orient_primary.currentData(),
                self.control_orient_secondary.currentData(),
                self.control_orient_world_up.currentData(),
                self.control_orient_curve_unaffected.isChecked(),
                self.control_orient_mirror.isChecked(),
                tuple(child_selections))
            self.control_orient_mirrored_behavior.setChecked(False)
            return f"已将 {count} 个控制器朝向子关节；镜像行为已关闭"

        def _detach_control_orient_custom(self):
            proxies = self.controller.control_orient_custom_detach(
                self._namespace())
            return f"已分离 {len(proxies)} 个控制器；旋转橙色预览曲线后重新附着"

        def _attach_control_orient_custom(self):
            count = self.controller.control_orient_custom_attach(
                self._namespace())
            return f"已重新附着 {count} 个控制器并保留手工方向"

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
                self.mesh.text().strip(), influences, self.skin.text().strip(),
                self.max_influences.value(),
                maintain_maximum=self.maintain_maximum.isChecked())
            return f"已绑定网格：{vertices} 个顶点"

        def _select_deform_joints(self):
            count = self.controller.skinning_select_deform_joints(self._namespace())
            return f"已追加选择 {count} 个变形关节；原有网格选择保留"

        def _set_smooth_bind_options(self):
            self.controller.skinning_set_smooth_bind_options()
            return "已设置原版 Smooth Bind 选项，并打开 Maya 绑定选项窗口"

        def _apply_delta_mush(self):
            count = self.controller.delta_mush_apply()
            return f"已为 {count} 个网格应用 Delta Mush"

        def _harden_delta_mush_weights(self):
            count = self.controller.delta_mush_harden_weights()
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

        def _face_record_right_eye(self):
            path = self.controller.face_eye_selected_mesh(self._namespace())
            self.face_eye_right.setText(path)
            self.face_fit_right_eye.setText(path)
            return "已记录右眼网格：" + path

        def _face_record_mask(self):
            mesh, count, scale = self.controller.face_pre_record_mask(
                self._namespace())
            self.face_pre_mask.setText(f"{mesh} · {count} 面")
            return f"已记录 Mask：{count} 个多边形面；面部高度 {scale:g} cm"

        def _face_record_face(self):
            meshes = self.controller.face_pre_record_objects(
                self._namespace(), "Face", self.face_eye_head.text().strip())
            self.face_pre_face.setText(meshes[0])
            return "已记录 Face 网格：" + meshes[0]

        def _face_record_all_head(self):
            meshes = self.controller.face_pre_record_objects(
                self._namespace(), "AllHead", self.face_eye_head.text().strip())
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
            path = self.controller.face_eye_selected_mesh(self._namespace())
            self.face_eye_left.setText(path)
            return "已记录左眼网格：" + path

        def _face_build_eyes(self):
            result = self.controller.face_eye_build(self._namespace(),
                self.face_eye_head.text().strip(),
                self.face_eye_right.text().strip(),
                self.face_eye_left.text().strip())
            return ("双眼控制已构建：左右眼各一套 Skin；"
                    "整体与独立眼球控制可用")

        def _face_fit_eye_ball(self):
            side = self.controller.face_fit_current_side(self._namespace())
            eye = (self.face_fit_left_eye if side == "Left"
                   else self.face_fit_right_eye)
            path = self.controller.face_fit_eye_ball(self._namespace(),
                eye.text().strip(),
                self.face_fit_head.text().strip())
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
            result = self.controller.face_build_eye_lids(self._namespace())
            return format_face_eye_lid_build_result(result)

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
                return
            detail = current.data(QtCore.Qt.UserRole + 1)
            self.current.setText("当前角色：" + detail)
            if hasattr(self, "face_fit_side_status"):
                try:
                    side = self.controller.face_fit_current_side(self._namespace())
                except ValueError:
                    side = "Right"
                self.face_fit_side_status.setText(
                    "Fit 编辑侧：" + ("左侧" if side == "Left" else "右侧"))
            if hasattr(self, "face_include"):
                try:
                    include = self.controller.face_build_get_include(
                        self._namespace())
                except ValueError:
                    include = "Complete"
                self.face_include.blockSignals(True)
                self.face_include.setCurrentText(include)
                self.face_include.blockSignals(False)
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
    """Show the AdvancedSkeleton-style navigation from Maya's command line."""
    from PySide2 import QtCore, QtWidgets

    from .maya_adv_layout import create_adv_panel
    panel = create_adv_panel(controller)
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
