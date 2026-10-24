"""Original Selector callbacks; retain the source's historical align names."""


class EditOriginalSelector:
    def __init__(self, host):
        self.host = host

    def execute(self, command, name, controls, **options):
        with self.host.transaction('原版 Selector：' + command):
            if command == 'asSelect':
                return self.host.select_original_selector_controls(name, controls, **options)
            if command in ('asKey', 'asLinearKey'):
                return self.host.key_original_selector_controls(name, controls, linear=command == 'asLinearKey', **options)
            # Original MEL 10664–10677 deliberately maps the two align
            # procedure names opposite to their apparent direction names.
            directions = {'asAlignIK2FK': ('ik', False), 'asAlignFK2IK': ('fk', False),
                          'asSwitchIK2FK': ('fk', True), 'asSwitchFK2IK': ('ik', True)}
            if command not in directions:
                raise ValueError('未知原版 Selector 操作：' + command)
            mode, switch = directions[command]
            return self.host.align_original_selector_fkik(controls, mode, switch=switch, **options)
