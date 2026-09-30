"""Original WrinkleMap commands under the shared Face undo boundary."""
from pathlib import Path
from adv_py.core.fit_settings import FitSkeletonValidationError


class EditOriginalFaceWrinkles:
    def __init__(self,host):
        self.host=host

    def apply(self,action,*,wrinkle="All",element="Curves",shader=None,image_path=None,
              map_width=1024,map_height=1024,mask_width=512,mask_height=512,format="png",modifier=None):
        actions=("curves","map","uv","apply","cancel","settings","save_settings","view_normal","view_bump","view_masks","view_file","edit")
        if action not in actions:
            raise ValueError("原版 WrinkleMap 操作无效")
        source=self.host.capture_original_face_wrinkle_curves(shader) if action=="curves" else None
        if action=="save_settings":
            if format not in ("png","tga") or min(map_width,map_height,mask_width,mask_height)<=0:
                raise FitSkeletonValidationError("WrinkleMap 尺寸必须为正，格式须为 png 或 tga")
            if image_path is not None and not str(image_path).strip():
                raise FitSkeletonValidationError("WrinkleMap 贴图目录不能为空")
        if modifier is None:
            modifier = self.host.original_face_wrinkle_modifiers() if action in ("map","apply") else 0
        with self.host.transaction("原版 WrinkleMap："+action):
            c=self.host._cmds
            raw=getattr(c,"raw",c)
            before=self.host.capture_face_build_node_ids()
            if action=="curves": result=self.host.create_original_face_wrinkle_curves(source)
            elif action=="map": result=self.host.create_original_face_wrinkle_map(modifier=modifier)
            elif action=="uv": result=self.host.update_original_face_wrinkle_uv()
            elif action=="apply":
                self.host.cancel_original_face_wrinkle_edit()
                raw.refresh()
                c.setAttr("WrinkleMap.modifier",modifier)
                result=self.host.bake_original_face_wrinkle_maps()
            elif action=="cancel": result=self.host.cancel_original_face_wrinkle_edit()
            elif action=="edit": result=self.host.edit_original_face_wrinkle(wrinkle,element)
            elif action in ("settings","save_settings"):
                self.host.ensure_original_face_wrinkle_map()
                if action=="save_settings":
                    self.host._transaction_changed=True
                    for attr,value in (("mapWidth",map_width),("mapHeight",map_height),("maskWidth",mask_width),("maskHeight",mask_height)):
                        c.setAttr("WrinkleMap."+attr,int(value))
                    c.setAttr("WrinkleMap.format",("png","tga").index(format))
                    if image_path is not None:
                        c.setAttr("WrinkleMap.imagePath",str(Path(image_path).expanduser()).replace(chr(92),"/"),type="string")
                result={attr:c.getAttr("WrinkleMap."+attr) for attr in ("imagePath","mapWidth","mapHeight","maskWidth","maskHeight")}
                result["format"]=c.getAttr("WrinkleMap.format",asString=True)
                c.select("WrinkleMap",replace=True)
            else:
                if action=="view_normal":
                    raw.soloMaterial(unsolo=True)
                else:
                    node={"view_bump":"bump2dWrinkle","view_masks":"WrinkleMasksLayeredTexture","view_file":"fileFaceWrinkles"}[action]
                    if not c.objExists(node):
                        raise FitSkeletonValidationError("请先创建 WrinkleMap")
                    self.host.view_original_face_wrinkle_material(node)
                result={"view":action}
            generated=[node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition")
                       and not before.intersection(c.ls(node,uuid=True) or [])]
            if generated and c.objExists("FaceAllSet"):
                c.sets(generated,add="FaceAllSet")
            return result
