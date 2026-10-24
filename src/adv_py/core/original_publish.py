"""ADV 6.925 Publish filename and ordered optionVar policy (76597–76878)."""
from dataclasses import dataclass
import ntpath


PUBLISH_OPTION = 'asPublishFileNames'
BODY_ONLY_SCRIPT = 'asDeleteAdvancedFace;\ndelete FaceGroup;'
LO_ONLY_SCRIPT = 'layerEditorSelectObjects Hi;\ndoDelete;\ndelete Hi;'


@dataclass(frozen=True, slots=True)
class OriginalPublishEntry:
    name: str
    script: str


@dataclass(frozen=True, slots=True)
class OriginalPublishPlan:
    scene: str
    destination: str
    variants: tuple[tuple[OriginalPublishEntry, str], ...]
    default_script: str


def original_publish_entries(values):
    # The source stores a single name=script string per array slot. Script
    # contents may themselves contain '=', newlines, quotes, and semicolons.
    if isinstance(values, str):
        values = (values,)
    return tuple(OriginalPublishEntry(*value.partition('=')[::2]) for value in values)


def replace_original_publish_entry(values, name, script):
    """Replace the first matching slot without jumbling the native UI order."""
    if not name:
        raise ValueError('No Name given')
    values = tuple(values) if not isinstance(values, str) else (values,)
    for index, entry in enumerate(original_publish_entries(values)):
        if entry.name == name:
            return (*values[:index], name + '=' + script, *values[index + 1:])
    return (*values, name + '=' + script)


def original_publish_template(template):
    return OriginalPublishEntry('' if template == '*new' else template,
        BODY_ONLY_SCRIPT if template == 'BodyOnly' else LO_ONLY_SCRIPT if template == 'LoOnly' else '')


def plan_original_publish(scene, entries=()):
    if not scene:
        raise ValueError('File not saved, can not publish')
    directory, filename = ntpath.split(scene)
    basename = ntpath.splitext(filename)[0]
    # Original gmatch is case sensitive: only .mb appends _Published.
    destination = ntpath.join(directory, basename + ('_Published' if scene.endswith('.mb') else '') + '.mb')
    variants, default = [], ''
    for entry in entries:
        if entry.name == 'Default':
            default = entry.script
        else:
            variants.append((entry, ntpath.join(directory, basename + '_' + entry.name + '.mb')))
    return OriginalPublishPlan(scene, destination, tuple(variants), default)
