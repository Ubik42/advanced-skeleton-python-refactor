"""Original Corrective popup catalogue, graph, delete, batch edit and bake."""
from adv_py.core.corrective_shapes import CorrectiveTarget,corrective_round,corrective_object_name
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaCorrectiveCatalogMixin:
    def original_corrective_targets(self, *, edit=False):
        c=self._cmds
        result=[]
        for bs in c.ls("*Corrective",recursive=True,type="blendShape") or []:
            deform=self._original_restore_leaf(bs).removesuffix("Corrective")
            for alias in sorted(self.original_face_bs_aliases(bs)):
                parts=alias.split("__")
                if len(parts)!=3:
                    continue
                driver,attribute,_=parts
                if edit and driver.endswith("_L"):
                    continue
                inputs=c.listConnections(bs+"."+alias,source=True,destination=False) or []
                if not inputs:
                    continue
                sdk=inputs[0]
                xs=c.keyframe(sdk,query=True,floatChange=True) or []
                ys=c.keyframe(sdk,query=True,valueChange=True) or []
                if not xs:
                    continue
                minimum=min(99,min(abs(x) for x in xs))
                for x,y in zip(xs,ys):
                    if abs(x)==minimum:
                        continue
                    result.append(CorrectiveTarget(deform,driver,attribute,corrective_round(x),float(y),y!=1,
                        not (y==1 and len(xs)>2),bs,sdk))
        return tuple(result)

    def delete_original_corrective_target(self, target, options):
        self._require_transaction()
        if not target.deletable:
            raise FitSkeletonValidationError("请先删除过渡目标，才能删除完整 Corrective 目标")
        self._cmds.createNode("transform",name="DeleteCorrectiveShape")
        self.edit_original_corrective_shape(target)
        return self.connect_original_corrective_shape(options)

    def graph_original_corrective_target(self, target=None):
        c=self._cmds
        if target:
            group="CorrectiveSoftMods_"+corrective_object_name(target.deform_object,target.driver_object,target.driver_attribute,target.value)
            nodes=c.listRelatives(group,allDescendents=True,type="transform") or [] if c.objExists(group) else []
        else:
            nodes=[]
            if c.objExists("CorrectiveSoftMods"):
                nodes=c.listRelatives("CorrectiveSoftMods",allDescendents=True,type="transform") or []
        c.select(nodes,replace=True)
        from maya import mel
        mel.eval("GraphEditor;")
        return tuple(nodes)

    def batch_edit_original_correctives(self, options):
        self._require_transaction()
        targets=self.original_corrective_targets(edit=True)
        results=[]
        for target in targets:
            self.edit_original_corrective_shape(target)
            self._corrective_raw().refresh()
            results.append(self.connect_original_corrective_shape(options))
        self.go_to_original_corrective_build_pose()
        self._cmds.select(clear=True)
        return tuple(results)

    def bake_into_original_correctives(self, source, destination, axes, options):
        self._require_transaction()
        c=self._cmds;raw=self._corrective_raw()
        if any(not name or "." in name or not raw.objExists(name) for name in (source,destination)):
            raise FitSkeletonValidationError("Corrective 烘焙的来源和目标须为网格对象")
        shape=self._corrective_shape(source)
        self._corrective_shape(destination)
        selected=c.ls(selection=True,long=True) or []
        pose=self.capture_original_control_pose()
        self.go_to_original_corrective_build_pose()
        self.set_original_corrective_all_fk()
        baked=[]
        rotations=(("x",90),("x",-90),("y",90),("y",-90),("z",90),("z",-90))
        try:
            for control in selected:
                leaf=self._original_restore_leaf(control)
                if not self.original_corrective_primary_fk(control):
                    continue
                for enabled,(axis,amount) in zip(axes,rotations):
                    if not enabled:
                        continue
                    c.setAttr(control+".r"+axis,amount)
                    raw.refresh()
                    raw.dgdirty(allPlugs=True)
                    raw.select(destination,replace=True)
                    source_plan=self.capture_original_corrective_create(options)
                    result=self.create_original_corrective_shape(source_plan)
                    target=result["target"]
                    target_shape=c.listRelatives(target,shapes=True,noIntermediate=True,fullPath=True)[0]
                    raw.connectAttr(shape+".outMesh",self.scene_address(target_shape+".inMesh"),force=True)
                    raw.dgdirty(allPlugs=True)
                    raw.pointPosition(self.scene_address(target)+".vtx[0]",local=True)
                    baked.append(self.connect_original_corrective_shape(options))
                    c.setAttr(control+".r"+axis,0)
        finally:
            self.restore_original_control_pose(pose)
            c.select(selected,replace=True)
        return tuple(baked)
