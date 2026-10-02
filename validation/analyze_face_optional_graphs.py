"""Compact offline differences from captured Maya graphs (no Maya runtime)."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]


def maximum(a, b):
    if isinstance(a, (list, tuple)):
        if len(a) != len(b): return float('inf')
        return max((maximum(x, y) for x, y in zip(a, b)), default=0.)
    return abs(a - b)


def mixed():
    root = ROOT / 'validation/results/face-mixed-graph'
    a = json.loads((root / 'native.json').read_text(encoding='utf8'))
    b = json.loads((root / 'python.json').read_text(encoding='utf8'))
    transforms = [(maximum(row['matrix'], b['transforms'][node]['matrix']), node) for node, row in a['transforms'].items() if node in b['transforms']]
    print('MIXED_TRANSFORMS', sorted(transforms, reverse=True)[:20])
    print('MISSING_TRANSFORMS', sorted(a['transforms'].keys() - b['transforms'].keys()))
    for node, row in a['skins'].items():
        if node not in b['skins']:
            print('MISSING_SKIN', node); continue
        other = b['skins'][node]
        names, other_names = row['influences'], other['influences']
        shared = set(names) & set(other_names)
        weight_error = max((abs(row['weights'][v * len(names) + names.index(n)] - other['weights'][v * len(other_names) + other_names.index(n)]) for v in range(len(row['weights']) // len(names)) for n in shared), default=0.)
        print('MIXED_SKIN', node, 'points', maximum(row['world_points'], other['world_points']),
              'weights', weight_error, 'missing', set(names) - set(other_names), 'extra', set(other_names) - set(names),
              'bind_pre', max((maximum(row['bind_pre'][n], other['bind_pre'][n]) for n in shared), default=0.))
    for node, row in a['blendshapes'].items():
        other = b['blendshapes'][node]
        names, other_names = row['aliases'][::2], other['aliases'][::2]
        values, other_values = row['weights'], other['weights']
        if values and isinstance(values[0], (tuple, list)): values = values[0]
        if other_values and isinstance(other_values[0], (tuple, list)): other_values = other_values[0]
        errors = [(abs(values[i] - other_values[other_names.index(n)]), n, values[i], other_values[other_names.index(n)]) for i, n in enumerate(names)]
        print('MIXED_BS', node, sorted(errors, reverse=True)[:3])


def journal():
    report = json.loads((ROOT / 'validation/results/face-sdk-journal/report.json').read_text(encoding='utf8'))
    for case, row in report['cases'].items():
        print('JOURNAL', case, row['undo_name'])
        for stage in ('before', 'built', 'undone', 'redone', 'redone_pose'):
            print('VALUES', stage, row[stage]['values'])
        built, redone = row['built']['nodes'], row['redone']['nodes']
        print('MISSING_REDO', built.keys() - redone.keys())
        print('EXTRA_REDO', redone.keys() - built.keys())
        print('SURVIVED_UNDO', len(row['undone']['nodes'].keys() - row['before']['nodes'].keys()))
        changes = [(n, v, redone[n]) for n, v in built.items() if n in redone and (v['connections'] != redone[n]['connections'] or v.get('keys') != redone[n].get('keys'))]
        print('REPLAY_CHANGES', changes[:12])


if __name__ == '__main__':
    import sys
    if '--journal' in sys.argv: journal()
    else: mixed(); journal()
