"""Source export preparation operations in one native scene transaction."""


class PrepareRobloxDynamicHead:
    def __init__(self, host):
        self.host = host

    def apply(self, geometry):
        self.host.preflight_roblox_dynamic_head(geometry)
        with self.host.transaction('Roblox Dynamic Head'):
            return self.host.prepare_roblox_dynamic_head(geometry)


class PrepareOriginalExport:
    def __init__(self, host):
        self.host = host

    def apply(self, operation):
        if operation not in ('delete_unused_end_joints', 'delete_static_channels', 'rebuild_dag_pose'):
            raise ValueError('未知原版导出准备操作')
        self.host.preflight_export_preparation(operation)
        with self.host.transaction(operation):
            return self.host.prepare_original_export(operation)
