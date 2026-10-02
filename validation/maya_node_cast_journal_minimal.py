"""Check native nodeCast's effect on an enclosing Maya undo chunk."""
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds as c
import json
import sys
from pathlib import Path
plugin = Path(__file__).resolve().parents[1] / 'src/adv_py/maya_plugins/native_node_cast.py'
if '--owned' in sys.argv: c.loadPlugin(str(plugin), quiet=True)
c.file(new=True, force=True); c.undoInfo(state=True)
source = c.createNode('transform', name='CastInput')
destination = c.createNode('transform', name='CastOutput')
c.addAttr(source, longName='authored', attributeType='double', keyable=True, defaultValue=.37)
c.undoInfo(openChunk=True, chunkName='Native cast ownership')
c.createNode('transform', name='BeforeCast')
if '--owned' in sys.argv: c.advPyNativeNodeCast(source, destination, 1)
else: c.nodeCast(source, destination, swapNames=True)
c.createNode('transform', name='AfterCast')
c.undoInfo(closeChunk=True)
report = {'before': {'source_has_attr': c.objExists(source + '.authored'),
                     'destination_has_attr': c.objExists(destination + '.authored')},
          'undo_name': c.undoInfo(query=True, undoName=True)}
c.undo()
report['undone'] = {'before_marker': c.objExists('BeforeCast'), 'after_marker': c.objExists('AfterCast'),
    'source_has_attr': c.objExists(source + '.authored'), 'destination_has_attr': c.objExists(destination + '.authored')}
c.redo()
report['redone'] = {'before_marker': c.objExists('BeforeCast'), 'after_marker': c.objExists('AfterCast'),
    'source_has_attr': c.objExists(source + '.authored'), 'destination_has_attr': c.objExists(destination + '.authored')}
print(json.dumps(report))
maya.standalone.uninitialize()
