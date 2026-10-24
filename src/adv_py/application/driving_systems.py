"""Original Driving Systems creation and time-axis editing use cases."""
from adv_py.core.driving_systems import DrivingCreateOptions

class EditOriginalDrivingSystems:
    def __init__(self,host):self.host=host
    def catalog(self):return self.host.original_driving_catalog()

    def apply(self,action,*,control="",attribute="",driver="",driven="",driver_value=10.,driven_value=1.,
              mirror=True,q_rotations=True,test_symmetry=True,show_only_affected=False,
              drive_from_selected=False,curve_name="",curve_text=""):
        allowed=("create","edit","auto_edit","apply_edit","cancel_edit","delete","optimize","upgrade_curves",
                 "graph","range","mirror","sdk_layer","sdk_key","remove_preview","mute","unmute","reuse","restore_fit")
        if action not in allowed:raise ValueError("Driving Systems 操作无效")
        if action=='reuse':
            from adv_py.core.original_anim_curve_text import parse_original_curve_text
            if not control or not attribute or not curve_name:raise ValueError('复用驱动需要控制器、属性和曲线名')
            parse_original_curve_text(curve_text)
            from adv_py.adapters.maya_native_node_cast import prepare_native_node_cast
            prepare_native_node_cast(self.host)
        with self.host.transaction("原版 Driving Systems："+action):
            if action=='restore_fit':return self.host.restore_original_driving_from_fit()
            if action=='reuse':
                return self.host.reuse_original_driving_system(control,attribute,curve_name,curve_text)
            if action=="create":
                self.host._transaction_changed=True
                self.host.remove_original_driving_symmetry_preview()
                plan=self.host.capture_original_driving_create(DrivingCreateOptions(control,attribute,mirror,q_rotations,drive_from_selected))
                return self.host.create_original_driving_system(plan)
            if action=="edit":return self.host.edit_original_driving_attribute(control,attribute,test_symmetry=test_symmetry,show_only_affected=show_only_affected)
            if action=="auto_edit":return self.host.auto_find_and_edit_original_driving(test_symmetry=test_symmetry,show_only_affected=show_only_affected)
            if action=="apply_edit":return self.host.apply_original_driving_edit()
            if action=="cancel_edit":return self.host.cancel_original_driving_edit()
            if action=="delete":return self.host.delete_original_driving_attribute(control,attribute)
            if action=="optimize":return self.host.optimize_original_driving_controllers()
            if action=="upgrade_curves":return self.host.update_original_driving_curve_versions()
            if action=="graph":return self.host.graph_original_driving_attribute(control,attribute)
            if action=="range":return self.host.update_original_driving_soft_range(control,attribute)
            if action=="mirror":return self.host.mirror_original_driving_attribute(control,attribute)
            if action=="sdk_layer":return self.host.create_original_driving_sdk_layer(control)
            if action=="remove_preview":
                self.host._transaction_changed=True
                return self.host.remove_original_driving_test_animation()
            if action=="mute":return self.host.mute_original_driving_sdks(self.host.original_driving_curves(control,attribute))
            if action=="unmute":return self.host.unmute_original_driving_sdks()
            if not driver or not driven:raise ValueError("请填写驱动与被驱动通道")
            if not self.host._cmds.objExists(driver) or not self.host._cmds.objExists(driven):raise ValueError("驱动与被驱动通道不存在")
            return self.host.add_original_face_sdk(driver,driven,driver_value,driven_value)


class EditOriginalPoseFunctions:
    def __init__(self,host):self.host=host
    def catalog(self):return self.host.original_stored_pose_names()
    def apply(self,action,*,name="",overwrite=False,objects=(),attributes=(),ui_name='',ui_state=None):
        if action not in ("store","apply","delete","add_build_pose","disable_orients","enable_orients","neutral","t_pose","clean_animation","mirror"):
            raise ValueError("原版 Pose Functions 操作无效")
        with self.host.transaction("原版 Pose Functions："+action):
            if action=="store":return self.host.store_original_named_pose(name,overwrite=overwrite)
            if action=="apply":return self.host.apply_original_named_pose(name)
            if action=="delete":return self.host.delete_original_named_pose(name)
            if action=="add_build_pose":return self.host.add_original_build_pose_channels(objects,attributes)
            if action in ("neutral","t_pose"):
                return self.host.go_to_original_control_build_pose(ui_name,t_pose=action=="t_pose",**(ui_state or {}))
            if action=="clean_animation":return self.host.clean_original_control_animation(ui_name,**(ui_state or {}))
            if action=="mirror":return self.host.mirror_original_control_pose(ui_name,**(ui_state or {}))
            return self.host.toggle_original_custom_orients(action=="enable_orients")
