"""Source asDsGetDrivingSystems/asDsGetAttrs/asDsGetAnimCurves, MEL 65466–65615.

Shared by SDK operations and Fit handoff so rebuild sees the same catalogue.
"""
from fnmatch import fnmatchcase
from .maya_original_control_identity import source_fk_joint


class MayaDrivingCatalogMixin:
    @staticmethod
    def _driving_catalog_leaf(path):
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def original_driving_attributes(self, control):
        c=self._cmds
        face=c.objExists("FaceControlSet") and c.sets(control,isMember="FaceControlSet")
        path=(c.ls(control,long=True) or [control])[0]
        metahuman=face and "|GRP_faceGUI|" in path
        ordinary=not face and "|DrivingSystem|" not in path.replace((self.namespace+":") if self.namespace else "","")
        if face or metahuman:
            attrs=list(c.listAttr(control,keyable=True) or []) if metahuman else ([] if c.getAttr(control+".tx",lock=True) else ["translateX","translateY"])
            attrs.extend(attr for attr in c.listAttr(control,userDefined=True) or [] if not c.getAttr(control+"."+attr,lock=True)
                and (c.getAttr(control+"."+attr,keyable=True) or c.getAttr(control+"."+attr,channelBox=True)))
            if self._driving_catalog_leaf(control)=="ctrlPhonemes_M":attrs=[a for a in attrs if a not in ("multipliers","jaw","lip")]
        elif ordinary:
            attrs=[]
            destinations=c.listConnections(control,source=False,destination=True,skipConversionNodes=True,plugs=True,type="blendWeighted") or []
            for destination in destinations:
                sources=c.listConnections(destination,source=True,destination=False,skipConversionNodes=True,plugs=True) or []
                if sources:attrs.append(sources[0].rsplit(".",1)[1])
        else:attrs=c.listAttr(control,userDefined=True) or []
        return tuple(a for a in attrs if a!="optimizedDS")

    def original_driving_curves(self, control, attribute):
        c=self._cmds
        control=self._driving_catalog_leaf(control)
        deform=source_fk_joint(self,control)
        if deform!=control and c.objExists(deform+"."+attribute):control=deform
        # asDsGetAnimCurves preserves the caller's attribute spelling. Expanding
        # arbitrary short names/aliases here changes the BW lookup in the MEL.
        bw="bw"+control+"_"+attribute
        plug=bw+".output" if c.objExists(bw) else control+"."+attribute
        return tuple(curve for curve in c.listConnections(plug,source=False,destination=True,skipConversionNodes=True,type="animCurve") or []
                     if self._driving_catalog_leaf(curve).startswith(("SDK","bw")))

    def original_driving_systems(self):
        c=self._cmds
        controls=list(c.listRelatives("DrivingSystem",children=True) or []) if c.objExists("DrivingSystem") else []
        if c.objExists("ctrlBox") and not c.objExists("asFaceBS"):
            for control in c.listRelatives("ctrlBox",allDescendents=True,type="transform") or []:
                if any(c.objExists("bw"+control+"_"+attr) for attr in self.original_driving_attributes(control)):controls.append(control)
        for bw in c.ls("bw*",type="blendWeighted") or []:
            output=c.listConnections(bw+".output",skipConversionNodes=True) or []
            if not output or c.nodeType(output[0]).startswith("animCurve"):continue
            curves=c.listConnections(bw+".input",skipConversionNodes=True,type="animCurve") or []
            if not curves:continue
            driver_bw=c.listConnections(curves[0]+".input",skipConversionNodes=True,type="blendWeighted") or []
            if not driver_bw:continue
            sources=c.listConnections(driver_bw[0]+".input",skipConversionNodes=True,type="transform") or []
            if not sources:continue
            control=sources[0];leaf=self._driving_catalog_leaf(control)
            parents=c.listRelatives(control,parent=True) or []
            if parents and self._driving_catalog_leaf(parents[0])=="DrivingSystem":continue
            if fnmatchcase(leaf,"SmilePull_[A-Z]") or fnmatchcase(leaf,"Lip_[A-Z]") or fnmatchcase(leaf,"CTRL_*_*"):continue
            if control not in controls:controls.append(control)
        if c.objExists("MetaHumanControlPanelToggle.MetaHumanControlPanelVis") and c.getAttr("MetaHumanControlPanelToggle.MetaHumanControlPanelVis"):
            for control in c.listRelatives("FRM_faceGUI",allDescendents=True,type="transform") or []:
                leaf=self._driving_catalog_leaf(control)
                if not leaf.startswith("CTRL_") or fnmatchcase(leaf,"*[fF]ollowHead*") or leaf in ("CTRL_expressions","CTRL_faceTweakersGUI","CTRL_GUIswitch"):continue
                shapes=c.listRelatives(control,shapes=True) or []
                materials=c.listConnections(shapes[0]+".instObjGroups",source=False,destination=True) or [] if shapes else []
                if materials and self._driving_catalog_leaf(materials[0])=="asBlackSG":continue
                controls.append(control)
        return tuple(controls)
