"""The original published command strings survive Python callbacks and files."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_py.core.original_poser_file import OriginalPoserButton,OriginalPoserFile,encode,decode
from adv_py.adapters.maya_original_selector_binding import _tokens
from adv_py.adapters.maya_original_ui_commands import bind,command


class OriginalPoserFileTests(unittest.TestCase):
    def fixture(self):
        return OriginalPoserFile('walk',4,2,110,90,'ControlSet FaceControlSet ',(
            OriginalPoserButton(2,2,'asSetAttrs asPoserwalk "FKRoot_M.tx 1;FKRoot_M.ty 2;"',
                '坐姿 "A"\n转身',False,True,'FKRoot_M.tx',-10.,10.),
            OriginalPoserButton(6,6,'asLoadAttrs asPoserwalk 6','走路',True,red_label=True)))

    def test_original_native_data_roundtrip_ignores_embedded_helpers(self):
        value=self.fixture()
        text=encode(value)+'\nglobal proc helper(){ iconTextButton -c "delete AllSet" unrelated; }\n'
        self.assertEqual(decode(text),value)

    def test_legacy_adjacent_quote_popup_is_a_separate_mel_argument(self):
        self.assertEqual(_tokens('asPoseObjects asPoserDefault asPoserDefaultIconTextButton1" select -add"'),
            ('asPoseObjects','asPoserDefault','asPoserDefaultIconTextButton1',' select -add'))

    def test_missing_image_or_grid_is_rejected_without_executing_any_commands(self):
        text=encode(self.fixture())
        for damaged in (text.replace('gridLayout -cw 110','unknown -cw 110'),
            text.replace('walk_2.png','wrong.png')):
            with self.assertRaises(ValueError):decode(damaged)

    def test_callback_source_is_available_for_save_and_rebinding(self):
        class Widgets:
            value='asSetAttrs asPoserDefault "FK.tx 1;"'
            def iconTextButton(self,name,**flags):
                if flags.get('query'):return self.value
                self.value=flags['command']
        c=Widgets()
        original=c.value
        callback=lambda *_:None
        bind(c,'iconTextButton','|window|button',original,callback)
        self.assertEqual(command(c,'iconTextButton','button'),original)
        self.assertIs(c.value,callback)

    def test_standalone_publish_copies_real_marker_lines_not_quoted_marker_literals(self):
        from adv_py.adapters.maya_original_poser_files import _helpers
        with TemporaryDirectory() as folder:
            source=Path(folder)/'AdvancedSkeleton.mel'
            source.write_text('if ($line=="//-- ASTools Procedures Starts Here --//") bad;\n'
                'if ($line=="//-- ASTools Procedures Ends Here --//") bad;\n'
                '//-- ASTools Procedures Starts Here --//\n'
                'global proc kept(){}\n// ******** source comment ********\n'
                '//-- ASTools Procedures Ends Here --//\n',encoding='utf-8')
            text=_helpers(source)
            self.assertIn('global proc kept(){}',text)
            self.assertNotIn('bad',text)
            self.assertNotIn('********',text)
