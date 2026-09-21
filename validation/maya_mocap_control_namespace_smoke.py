"""Retarget one of two registered characters without changing its neighbor."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import CharacterExampleHost,build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RegisterBodyCharacter,RetargetMocapRootToCharacter
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        characters=[]
        for namespace in ('hero','partner'):
            cmds.namespace(addNamespace=namespace)
            built=build_character(with_hand=False,host=CharacterExampleHost(namespace=namespace))
            characters.append((MayaMocapControlHost(namespace=namespace),RegisterBodyCharacter(built.host).apply(built.rig)))
        hero,registration=characters[0]
        partner,other=characters[1]
        cmds.namespace(addNamespace='TakeA')
        source=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        for frame,value in ((1,0.),(5,5.),(10,11.)):
            cmds.setKeyframe(source,attribute='translateX',time=frame,value=value)
        before_hero=hero.capture_character_key_state(registration)
        before_other=partner.capture_character_key_state(other)
        samples=RetargetMocapRootToCharacter(hero).apply('|TakeA:Hips',start_frame=1,end_frame=10)
        after_hero=hero.capture_character_key_state(registration)
        checks={
            'target_has_ten_control_samples':len(samples)==10,
            'target_changed':after_hero!=before_hero,
            'other_character_unchanged':partner.capture_character_key_state(other)==before_other,
        }
        cmds.undo()
        checks['target_undo']=hero.capture_character_key_state(registration)==before_hero
        checks['other_undo_unchanged']=partner.capture_character_key_state(other)==before_other
        cmds.redo()
        checks['target_redo']=hero.capture_character_key_state(registration)==after_hero
        checks['other_redo_unchanged']=partner.capture_character_key_state(other)==before_other
        payload={**checks,'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
