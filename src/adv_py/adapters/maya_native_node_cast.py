"""Native node swapping with an explicit Maya undo owner."""
from pathlib import Path


def prepare_native_node_cast(host):
    """Load before opening the build chunk; plugin loading is not a rig edit."""
    raw = getattr(host._cmds, 'raw', host._cmds)
    plugin = Path(__file__).resolve().parents[1] / 'maya_plugins/native_node_cast.py'
    if not raw.pluginInfo(str(plugin), query=True, loaded=True):
        if getattr(host, '_transaction_active', False):
            raise RuntimeError('Mixed 原生依赖必须在打开绑定撤销事务前加载')
        raw.loadPlugin(str(plugin), quiet=True)


def native_node_cast(host, source, destination, *, swap_names=True):
    host._require_transaction()
    raw = getattr(host._cmds, 'raw', host._cmds)
    host._transaction_changed = True
    raw.advPyNativeNodeCast(host.scene_address(source), host.scene_address(destination), int(swap_names))
