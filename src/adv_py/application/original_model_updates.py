"""Original Updates buttons, each with one encompassing scene operation."""


class UpdateOriginalModel:
    def __init__(self, host):
        self.host = host

    def apply(self, operation):
        if operation not in ('green_fix', 'nan_fix'):
            raise ValueError('未知原版模型更新操作')
        with self.host.transaction('Green-fix' if operation == 'green_fix' else 'NaN-fix'):
            return (self.host.fix_original_reference_shaders() if operation == 'green_fix'
                    else self.host.fix_original_origin_skin_vertices())
