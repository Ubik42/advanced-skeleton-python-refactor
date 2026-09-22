"""Compare FK keys at original, new-key, and between-key times."""
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(folder, source_count, target_count):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        stem = f'spine-{source_count}-to-{target_count}'
        original = folder / f'{stem}-before.ma'
        original_digest = sha256(original.read_bytes()).hexdigest()
        frames = tuple(1 + index * .125 for index in range(73))

        def run(substeps):
            cmds.file(str(original), open=True, force=True)
            cmds.undoInfo(state=True)
            host = MayaOriginalSkinSpineMigrationHost(namespace='target')
            source = host.read_source_character_registration('source')
            target = host.read_character_registration()
            short = lambda path: path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            internal = {short(path) for path in source.spine.body_joints[1:-1]}
            names = tuple(sorted(short(row.path) for row in source.body
                                 if short(row.path) not in internal))
            expected = host.capture_source_registered_spine_body_take(
                'source', source, names, frames)
            result = ReplaceRegisteredSpineCharacter(host).apply(
                'source', 'target', 'source:SourceSkin', '|source:SourceMesh',
                start_frame=1, end_frame=10, fk_substeps=substeps,
                max_mesh_error=1, max_body_error=1)
            promoted = MayaOriginalSkinSpineMigrationHost(namespace='source')

            def error():
                actual = promoted.capture_registered_spine_body_take(
                    target, names, frames)
                return max(abs(a-b)
                    for expected_frame, actual_frame in zip(expected, actual)
                    for (_, left), (_, right) in zip(expected_frame, actual_frame)
                    for old_point, new_point in zip(left, right)
                    for a, b in zip(old_point, new_point))

            measured = error()
            if substeps == 1:
                return result.frames, measured, None
            cmds.undo()
            undone = cmds.namespace(exists='target')
            cmds.redo()
            redo_error = error()
            output = folder / f'{stem}-fk-substeps.ma'
            cmds.file(rename=str(output))
            cmds.file(save=True, type='mayaAscii', force=True)
            cmds.file(str(output), open=True, force=True)
            reopen_error = error()
            return result.frames, measured, (undone, redo_error, reopen_error)

        baseline_frames, baseline_error, _ = run(1)
        dense_frames, dense_error, persistence = run(4)
        undone, redo_error, reopen_error = persistence
        checks = dict(frame_counts=(baseline_frames, dense_frames) == (10, 37),
                      improved=dense_error < baseline_error,
                      undo=undone,
                      redo=abs(redo_error-dense_error) < 1e-6,
                      reopened=abs(reopen_error-dense_error) < 1e-6,
                      input_unchanged=sha256(original.read_bytes()).hexdigest()
                          == original_digest)
        report = dict(source=source_count, target=target_count,
                      baseline_body_error_cm=baseline_error,
                      dense_body_error_cm=dense_error, checks=checks)
        (folder / f'{stem}-fk-substeps.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3])))
