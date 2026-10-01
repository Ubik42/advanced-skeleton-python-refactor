"""Persistent corrective SoftMod chains and cancel/exit behavior."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaCorrectiveSoftModsMixin:
    def prepare_original_corrective_softmods(self, enabled):
        c=self._cmds
        if enabled and not c.objExists("CorrectiveSoftModsSystem"):
            c.createNode("transform",name="CorrectiveSoftModsSystem",parent="MotionSystem")
            c.createNode("transform",name="CorrectiveSoftMods",parent="CorrectiveSoftModsSystem")
            c.setAttr("CorrectiveSoftMods.v",0,lock=True)
        elif not enabled and c.objExists("CorrectiveSoftModsSystem"):
            c.delete("CorrectiveSoftModsSystem")

    def restore_original_corrective_softmod_chain(self, target):
        c=self._cmds
        group="CorrectiveSoftMods_"+target
        if not c.objExists(group):
            c.select(clear=True)
            return
        handles=c.listRelatives(group,children=True) or []
        first=last=None
        for handle in handles:
            softmod=handle.replace("Handle","",1)
            if not c.listConnections(softmod+".input[0].inputGeometry",source=True,destination=False):
                first=softmod
            if not c.listConnections(softmod+".outputGeometry[0]",source=False,destination=True):
                last=softmod
            c.parent(handle,world=True)
        if first is not None:
            created=c.softMod(target,falloffMode=1,falloffAroundSelection=False)
            upstream=c.listConnections(created[0]+".input[0].inputGeometry",source=True,destination=False,shapes=True)[0]
            c.connectAttr(upstream+".worldMesh[0]",first+".input[0].inputGeometry")
            c.connectAttr(last+".outputGeometry[0]",target+".inMesh",force=True)
            c.delete(created[0])
        c.select(clear=True)

    def store_original_corrective_softmod_chain(self, target):
        c=self._cmds;raw=self._corrective_raw()
        if not c.objExists("CorrectiveSoftModsSystem"):
            return
        for node in c.listHistory(target,pruneDagObjects=True,interestLevel=1) or []:
            if c.nodeType(node)!="softMod":
                continue
            handle=c.listConnections(node+".matrix",source=True,destination=False)[0]
            group="CorrectiveSoftMods_"+target
            if not c.objExists(group):
                c.createNode("transform",name=group,parent="CorrectiveSoftMods")
            c.parent(handle,group)
        shape=c.listRelatives(target,shapes=True,noIntermediate=True,fullPath=True)[0]
        incoming=c.listConnections(shape+".inMesh",source=True,destination=False,plugs=True) or []
        if incoming:
            c.disconnectAttr(incoming[0],shape+".inMesh")
        raw.delete(self.scene_address(target),constructionHistory=True)

    def original_corrective_sculpt_tool(self, *, soft_mod=False):
        self._require_transaction()
        raw=self._corrective_raw()
        from maya import mel
        if soft_mod:
            raw.optionVar(intValue=("softModPreserveHistory",1))
            mel.eval("SoftModTool;")
        else:
            mel.eval("SculptGeometryTool;")

    def match_original_corrective_softmod_settings(self, source, destination):
        """asMatchSoftModSettings accepts either deformers or their handles."""
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        def resolve(node):
            if c.nodeType(node)=="transform":
                connected=c.listConnections(node+".worldMatrix[0]",source=False,destination=True,type="softMod") or []
                if not connected:raise ValueError("所选 Handle 没有 SoftMod："+node)
                return connected[0]
            return node
        source=resolve(source);destination=resolve(destination)
        for attribute in ("falloffRadius","falloffMode"):
            c.setAttr(destination+"."+attribute,c.getAttr(source+"."+attribute))
        indices=c.getAttr(source+".falloffCurve",multiIndices=True) or []
        for index in indices:
            prefix=".falloffCurve["+str(index)+"].falloffCurve_"
            for attribute in ("Position","FloatValue","Interp"):
                c.setAttr(destination+prefix+attribute,c.getAttr(source+prefix+attribute))
        return len(indices)

    def exit_original_corrective_mode(self):
        c=self._cmds;raw=self._corrective_raw()
        group="Group" if c.objExists("Group") else "FaceGroup"
        hidden=""
        if c.objExists(group+".advPyCorrectiveHiddenSource"):
            nodes=raw.listConnections(self.scene_address(group)+".advPyCorrectiveHiddenSource",
                                     source=True,destination=False) or []
            if len(nodes)==1:
                hidden=nodes[0]
        if not hidden and c.objExists(group+".correctiveShapeModeHidden"):
            hidden=c.getAttr(group+".correctiveShapeModeHidden")
        if hidden and self._original_restore_leaf(hidden)!="FaceCorrective" and raw.objExists(hidden):
            raw.setAttr(hidden+".v",1)
        if raw.headsUpDisplay("HUDCSMMode",query=True,exists=True):
            raw.headsUpDisplay("HUDCSMMode",remove=True)
        if c.objExists("perspCorrective"):
            if raw.objExists(":persp.focalLength") and raw.getAttr(":persp.filmFit")==1:
                raw.setAttr(":persp.focalLength",raw.getAttr(":persp.focalLength")/2)
            c.delete("perspCorrective")
            from maya import mel
            mel.eval("switchPanes single 0;")
            pane=mel.eval("global string $gMainPane; $gMainPane;")
            panel=raw.paneLayout(pane,query=True,pane1=True)
            raw.modelEditor(panel,edit=True,camera=":persp")
        test=c.ls("asDSDriverEdit_*",type="animCurve") or []
        if test:c.delete(test)
        self.remove_original_driving_test_animation()
        raw.dgdirty(allPlugs=True)

    def cancel_original_corrective_shape(self):
        self._require_transaction()
        c=self._cmds;raw=self._corrective_raw()
        self._transaction_changed=True
        roots=c.ls(assemblies=True) or []
        for node in roots:
            leaf=self._original_restore_leaf(node)
            if leaf.startswith("softMod") and leaf.endswith("Handle"):
                c.delete(node)
        raw.refresh()
        for node in roots:
            if c.objExists(node+".driverValue"):
                c.delete(node)
        if c.objExists("CorrectiveSoftModsWipBlendShape"):
            c.delete("CorrectiveSoftModsWipBlendShape")
        if c.objExists("CorrectiveSoftMods"):
            for group in c.listRelatives("CorrectiveSoftMods",children=True) or []:
                if group.endswith("WIP"):
                    name=c.rename(group,group.removesuffix("WIP"))
                    for handle in c.listRelatives(name,children=True,type="transform") or []:
                        skins=c.listConnections(handle+".worldMatrix[0]",type="skinCluster") or []
                        if skins:
                            c.setAttr(skins[0]+".envelope",1)
        if c.objExists("Group"):
            c.setAttr("Group.v",1)
        elif c.objExists("FaceGroup"):
            c.setAttr("FaceGroup.v",1)
        self.exit_original_corrective_mode()
        self.go_to_original_corrective_build_pose()
        c.select(clear=True)
        raw.setToolTo("selectSuperContext")
        return {"cancelled":True}
