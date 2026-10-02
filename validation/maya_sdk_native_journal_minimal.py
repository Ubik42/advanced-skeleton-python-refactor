"""Native SDK insertion ownership on existing drivers, independent of ADV."""
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds as c
import json


def graph():
    enabled = c.undoInfo(query=True, state=True)
    c.undoInfo(stateWithoutFlush=False)
    try:
        return {n: {'type': c.nodeType(n), 'links': c.listConnections(n, plugs=True, connections=True) or [],
                    'keys': c.keyframe(n, query=True, valueChange=True) if c.nodeType(n).startswith('animCurve') else None}
                for n in c.ls(type=('animCurve', 'blendWeighted', 'unitConversion'))}
    finally:
        c.undoInfo(stateWithoutFlush=enabled)


report = {}
for mode in ('unconnected', 'two-drivers', 'three-drivers', 'preexisting-two'):
    c.file(new=True, force=True); c.undoInfo(state=True)
    for name in ('driverA', 'driverB', 'driverC', 'target'):
        c.createNode('transform', name=name)
    if mode == 'preexisting-two':
        for v in (0, 1): c.setDrivenKeyframe('target.tx', currentDriver='driverA.tx', driverValue=v, value=v)
    c.undoInfo(openChunk=True, chunkName='SDK insertion')
    drivers = ('driverB', 'driverC') if mode == 'preexisting-two' else ('driverA', 'driverB', 'driverC')[:{'unconnected': 1, 'two-drivers': 2, 'three-drivers': 3}.get(mode, 1)]
    for driver in drivers:
        for v in (0, 1): c.setDrivenKeyframe('target.tx', currentDriver=driver + '.tx', driverValue=v, value=v)
    c.undoInfo(closeChunk=True)
    row = {'before': graph(), 'undo_name': c.undoInfo(query=True, undoName=True)}
    c.undo(); row['undo'] = graph(); row['redo_name'] = c.undoInfo(query=True, redoName=True)
    c.redo(); row['redo'] = graph()
    report[mode] = row
c.file(new=True, force=True)
c.createNode('animCurveUL', name='curve')
c.createNode('blendWeighted', name='bw')
c.createNode('transform', name='target')
c.connectAttr('curve.output', 'bw.input[0]'); c.connectAttr('bw.output', 'target.tx')
report['direct_units'] = graph()
print(json.dumps(report))
maya.standalone.uninitialize()
