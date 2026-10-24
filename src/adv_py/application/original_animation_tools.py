"""Original Anim menu operations share the existing character transaction."""


class EditOriginalAnimationTools:
    def __init__(self, host):
        self.host = host

    def execute(self, action, selection=None):
        operations = {
            'quick_ik': self.host.create_original_quick_ik,
            'switch_pivot': self.host.switch_original_control_pivot,
            'pivot_control': self.host.add_original_pivot_controls,
            'switch_fkik': self.host.auto_switch_original_fkik,
        }
        if action not in operations:
            raise ValueError('未知原版动画操作：' + action)
        with self.host.transaction('原版动画操作：' + action):
            return operations[action](selection)
