"""Build the original Face ctrlBox layout and its owned control graph."""
from adv_py.core.face_ctrl_box import SLIDERS
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceCtrlBox:
    def __init__(self,host): self.host=host
    def _prepare(self):
        source=self.host.capture_ctrl_box_input()
        names=["CtrlBoxSet","ctrlBox","ctrlBoxOffset","ctrlBoxTemplate","ctrlTemplate",
               "ctrlBox2","ctrlBox2Offset","ctrlBox2Constrained","tempLoc","tempLocFlip"]
        for name,x,y,half in SLIDERS:
            names.extend(("ctrlBox"+name,"ctrl"+name,"bwctrl"+name+"_translateX","bwctrl"+name+"_translateY"))
        options=source[-1]
        for option in ("Phonemes","Emotions","RobloxHead","ARKit","SnapChat"):
            if options[option]: names.extend(("ctrl"+option+"_M","ctrlBox"+option+"_M"))
        names.extend(self.host.ctrl_box_region_names(source))
        if options["SnapChat"] and not options["Emotions"]:
            raise FitSkeletonValidationError("原版 SnapChat 控件依赖 Emotions 图标，请先启用 Emotions")
        collisions=tuple(name for name in names if self.host.find_name_collisions(name))
        if collisions:
            raise FitSkeletonValidationError("原版 ctrlBox 节点名称已占用："+"、".join(collisions))
        return source

    def _create(self,source):
        before=self.host.capture_face_build_node_ids()
        controls=self.host.create_ctrl_box(source)
        self.host.validate_ctrl_box(controls)
        self.host.extend_face_build_pose(controls)
        self.host.register_face_module_nodes(before,"CtrlBoxSet")
        return controls

    def apply_in_transaction(self):
        self.host._require_transaction()
        return self._create(self._prepare())

    def apply(self):
        source=self._prepare()
        with self.host.transaction("建立原版 Face ctrlBox"):
            if self.host.capture_ctrl_box_input()!=source:
                raise RuntimeError("ctrlBox 输入在构建前变化")
            return self._create(source)
