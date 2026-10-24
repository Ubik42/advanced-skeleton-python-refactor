"""One complete native scene operation per Optimize button."""


class OptimizeOriginalRig:
    def __init__(self, host):
        self.host = host

    def apply(self, operation):
        self.host.preflight_original_optimize(operation)
        with self.host.transaction(operation):
            if operation == 'remove_unused_attributes':
                return self.host.remove_unused_original_attributes()
            if operation == 'tag_all_controllers':
                return self.host.tag_original_controllers()
            if operation == 'delete_unused_nodes':
                return self.host.delete_unused_original_nodes()
            if operation == 'delete_saved_uis':
                result = self.host.delete_saved_original_uis()
        if operation == 'delete_saved_uis':
            # Source flushUndo is outside the completed deletion chunk. Never
            # flush an open chunk or let the transaction attempt to undo it.
            self.host.flush_original_saved_ui_undo()
            return result
        raise ValueError('未知原版 Optimize 操作')
