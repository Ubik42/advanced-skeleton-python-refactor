"""Source Selector/Picker feedback preserves selection and undo semantics."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters import maya_original_selection_feedback as feedback


class Commands:
    def __init__(self):
        self.options={'asShowSelection':1,'asShowKeyed':1,'asShowExtra':0}
        self.selected=['hero:FKWrist_R']
        self.nodes={'hero:FKWrist_R','hero:FKExtraWrist_R','picker_biped:FKWrist_R'}
        self.menus={'asSelectorbipedOptionMenu':'hero:','asPickerOptionMenu':'hero:'}
        self.checkbox={}
        self.buttons={'wrist':dict(annotation='FKWrist_R',image1='',overlayLabelColor=(.1,.2,.3)),
            'all':dict(annotation='FaceAllSet',image1='custom_project_1_2_OnK1.png')}
        self.events=[]
        self.undo=True
        self.jobs={}
        self.inputs={'hero:FKWrist_R':['key'], 'hero:FKExtraWrist_R':['driven']}
        self.kinds={'key':'animCurveTA','driven':'animCurveUU'}
        self.picker=False
    def optionVar(self,**flags):
        if 'exists' in flags:return flags['exists'] in self.options
        if 'query' in flags:return self.options[flags['query']]
        name,value=flags['intValue'];self.options[name]=value
    def objExists(self,name):return name in self.nodes
    def optionMenu(self,name,**flags):
        if flags.get('exists'):return name in self.menus and (self.picker or name!='asPickerOptionMenu')
        return self.menus[name]
    def checkBox(self,name,**flags):
        if flags.get('exists'):return name in self.checkbox
        return self.checkbox[name]
    def lsUI(self,**flags):return ['asSelectorbiped'] if flags.get('windows') else []
    def ls(self,*args,**flags):
        from fnmatch import fnmatchcase
        nodes=self.selected if flags.get('selection') else sorted(self.nodes)
        if not args:return list(nodes)
        return [node for node in nodes if fnmatchcase(node,args[0])]
    def formLayout(self,name,**flags):
        if flags.get('exists'):return name=='asSelectorbipedFormLayout'
        return list(self.buttons)
    def iconTextButton(self,name,**flags):
        if flags.get('exists'):return name in self.buttons
        if flags.get('edit'):
            self.events.append(('button',name,flags));self.buttons[name].update(flags);return
        return next(self.buttons[name][key] for key,value in flags.items() if value and key!='query')
    def listConnections(self,name,**flags):return self.inputs.get(name,[])
    def objectType(self,name):return self.kinds[name]
    def tabLayout(self,name,**flags):
        if flags.get('exists'):return self.picker
        return ['biped'] if flags.get('tabLabel') else 1
    def text(self,name,**flags):return False
    def undoInfo(self,**flags):
        if flags.get('query'):return self.undo
        self.undo=flags['stateWithoutFlush'];self.events.append(('undo',self.undo))
    def setAttr(self,plug,value):self.events.append(('attr',plug,value))
    def select(self,*nodes,**flags):
        self.events.append(('select',nodes,flags))
        if flags.get('clear'):self.selected=[];return
        values=list(nodes[0]) if len(nodes)==1 and isinstance(nodes[0],(tuple,list)) else list(nodes)
        if flags.get('replace'):self.selected=values;return
        for node in values:
            if flags.get('deselect') or node in self.selected:
                if node in self.selected:self.selected.remove(node)
            else:self.selected.append(node)
    def scriptJob(self,**flags):
        if 'exists' in flags:return flags['exists'] in self.jobs
        if flags.get('listJobs'):
            return [str(number)+': '+event+' '+callback
                    for number,(event,callback) in self.jobs.items()
                    if isinstance(callback,str)]
        if 'kill' in flags:
            del self.jobs[flags['kill']]
            return
        number=len(self.jobs)+1;self.jobs[number]=flags['event'];return number


class SelectionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.c=Commands();self.host=SimpleNamespace(_cmds=self.c)
        self.job=feedback._JOB
        feedback._JOB=None
    def tearDown(self):feedback._JOB=self.job

    def test_selected_keyed_color_and_all_set_icon_follow_source(self):
        feedback.refresh(self.host)
        self.assertEqual(self.c.buttons['wrist']['backgroundColor'],(1.,.5,.5))
        self.assertEqual(self.c.buttons['all']['image'],'custom_project_1_2_OffK0.png')
        self.assertEqual(self.c.selected,['hero:FKWrist_R'])
        self.assertTrue(self.c.undo)

    def test_plain_button_restores_authored_color_when_toggles_clear(self):
        feedback.refresh(self.host)
        self.c.options.update(asShowSelection=0,asShowKeyed=0)
        feedback.toggle(self.host)
        self.assertEqual(self.c.buttons['wrist']['backgroundColor'],(.1,.2,.3))
        self.assertEqual(self.c.selected,['hero:FKWrist_R'])

    def test_selector_extra_fallback_and_picker_menu_namespace(self):
        self.c.checkbox['asSelectorbipedExtraCheckBox']=True
        self.assertEqual(feedback.resolve(self.c,'biped','FKWrist_R'),'hero:FKExtraWrist_R')
        self.assertEqual(feedback.resolve(self.c,'biped','RootX_M'),'hero:RootX_M')
        self.c.picker=True
        self.assertEqual(feedback.resolve(self.c,'missing','FKWrist_R'),'hero:FKWrist_R')
        self.c.picker=False
        self.assertEqual(feedback.resolve(self.c,'outer:inner:Rig','FKWrist_R'),'outer:inner:FKWrist_R')

    def test_picker_click_toggles_actual_character_without_undo_flush(self):
        self.c.picker=True
        self.c.selected=['picker_biped:FKWrist_R']
        feedback.refresh(self.host)
        self.assertEqual(self.c.selected,['hero:FKWrist_R'])
        self.assertIn(('attr','picker_biped:FKWrist_R.overrideColor',14),self.c.events)
        self.assertEqual([event for event in self.c.events if event[0]=='undo'],[('undo',False),('undo',True)])

    def test_picker_second_click_deselects_and_restores_keyed_color(self):
        self.c.picker=True
        self.c.selected=['picker_biped:FKWrist_R','hero:FKWrist_R']
        feedback.refresh(self.host)
        self.assertEqual(self.c.selected,[])
        self.assertIn(('attr','picker_biped:FKWrist_R.overrideColor',13),self.c.events)

    def test_picker_failure_restores_undo_and_reentrant_guard(self):
        self.c.picker=True
        with patch.object(self.c,'setAttr',side_effect=RuntimeError('native failure')):
            with self.assertRaisesRegex(RuntimeError,'native failure'):feedback.refresh(self.host)
        self.assertTrue(self.c.undo)
        self.assertFalse(feedback._RUNNING)

    def test_file_loading_suppresses_callbacks_and_restores_after_exception(self):
        with self.assertRaisesRegex(ValueError,'load'):
            with feedback.file_loading():
                self.assertEqual(feedback.refresh(self.host),())
                raise ValueError('load')
        self.assertEqual(feedback._LOADING,0)
        self.assertEqual(self.c.events,[])
        self.assertTrue(feedback.refresh(self.host))

    def test_one_job_for_live_session_reinstalls_only_when_job_is_gone(self):
        first=feedback.install(self.host)
        self.assertEqual(feedback.install(self.host),first)
        self.assertEqual(len(self.c.jobs),1)
        self.c.jobs.clear()
        feedback.install(self.host)
        self.assertEqual(len(self.c.jobs),1)

    def test_binding_replaces_only_exact_original_observer_and_preserves_other_jobs(self):
        self.c.jobs={10:('SelectionChanged','asSelChange'),
                     11:('SelectionChanged','asSelChange;'),
                     12:('SelectionChanged','myTool; asSelChange;'),
                     13:('SceneOpened','asSelChange'),
                     14:('SelectionChanged','otherTool')}
        job=feedback.install(self.host)
        self.assertNotIn(10,self.c.jobs)
        self.assertNotIn(11,self.c.jobs)
        self.assertTrue({12,13,14,job}<=self.c.jobs.keys())
        # A newly loaded standalone Selector can reinstall its old observer.
        self.c.jobs[20]=('SelectionChanged','"asSelChange"')
        self.assertEqual(feedback.install(self.host),job)
        self.assertNotIn(20,self.c.jobs)
        self.assertTrue({12,13,14,job}<=self.c.jobs.keys())


if __name__=='__main__':unittest.main()
