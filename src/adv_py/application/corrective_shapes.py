"""Source Corrective create/edit/apply/cancel/bake commands with one undo chunk."""
from adv_py.core.corrective_shapes import CorrectiveShapeOptions

class EditOriginalCorrectiveShapes:
    def __init__(self,host):
        self.host=host

    def targets(self, *, edit=False):
        return self.host.original_corrective_targets(edit=edit)

    def apply(self, action, *, target=None, q_rotations=True, use_soft_mods=False, mirror=True,
              source="", destination="", fk_control="", axes=(True,True,True,True,True,True)):
        allowed=("create","edit","delete","graph","apply","cancel","batch","bake","sculpt","softmod","curve_create","curve_unbind","curve_rebind","curve_animate",
                 "curve_mesh","curve_original","curve_new","curve_bake","curve_cleanup","curve_hide")
        if action not in allowed:
            raise ValueError("Corrective Shapes 操作无效")
        if action in ("edit","delete") and target is None:
            raise ValueError("请从 Corrective 目标菜单选择具体目标")
        if len(axes)!=6:
            raise ValueError("Corrective 烘焙须指定六个旋转方向")
        options=CorrectiveShapeOptions(bool(q_rotations),bool(use_soft_mods),bool(mirror))
        plan=self.host.capture_original_corrective_create(options) if action=="create" else None
        with self.host.transaction("原版 Corrective Shapes："+action):
            before=self.host.capture_face_build_node_ids()
            if action=="create":result=self.host.create_original_corrective_shape(plan)
            elif action=="edit":result=self.host.edit_original_corrective_shape(target)
            elif action=="delete":result=self.host.delete_original_corrective_target(target,options)
            elif action=="graph":result=self.host.graph_original_corrective_target(target)
            elif action=="apply":result=self.host.connect_original_corrective_shape(options)
            elif action=="cancel":result=self.host.cancel_original_corrective_shape()
            elif action=="batch":result=self.host.batch_edit_original_correctives(options)
            elif action=="bake":result=self.host.bake_into_original_correctives(source,destination,axes,options)
            elif action=="curve_create":result=self.host.create_original_corrective_curves(source,fk_control)
            elif action=="curve_unbind":result=self.host.unbind_original_corrective_curves()
            elif action=="curve_rebind":result=self.host.rebind_original_corrective_curves()
            elif action=="curve_animate":result=self.host.animate_original_corrective_curves()
            elif action=="curve_mesh":result=self.host.create_original_corrective_curve_mesh()
            elif action=="curve_original":result=self.host.show_original_corrective_curve_mesh(original=True)
            elif action=="curve_new":result=self.host.show_original_corrective_curve_mesh(original=False)
            elif action=="curve_bake":result=self.host.bake_original_corrective_curve_mesh(options)
            elif action=="curve_cleanup":result=self.host.cleanup_original_corrective_curves()
            elif action=="curve_hide":result=self.host.hide_original_corrective_curve_source(source)
            else:result=self.host.original_corrective_sculpt_tool(soft_mod=action=="softmod")
            c=self.host._cmds
            generated=[node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition")
                       and not before.intersection(c.ls(node,uuid=True) or [])]
            if generated:
                if not c.objExists("CorrectiveShapesSet"):
                    c.sets(empty=True,name="CorrectiveShapesSet")
                c.sets(generated,add="CorrectiveShapesSet")
                if c.objExists("AllSet"):
                    c.sets("CorrectiveShapesSet",add="AllSet")
                elif c.objExists("FaceAllSet"):
                    c.sets("CorrectiveShapesSet",add="FaceAllSet")
            return result
