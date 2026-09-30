"""Original driving catalogue and native SDK editing operations."""
class EditOriginalDrivingSystems:
    def __init__(self,host):self.host=host

    def catalog(self):return self.host.original_driving_catalog()

    def apply(self,action,*,control="",attribute="",driver="",driven="",driver_value=10.,driven_value=1.):
        if action not in ("graph","range","mirror","sdk_layer","sdk_key","remove_preview","mute","unmute"):
            raise ValueError("Driving Systems 操作无效")
        with self.host.transaction("原版 Driving Systems："+action):
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
