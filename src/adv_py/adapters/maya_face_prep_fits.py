"""Original symmetric/non-symmetric Fit preparation from asFacePrep."""

class MayaFacePrepFitsMixin:
    def prepare_original_face_fit_sides(self):
        self._require_transaction()
        c=self._cmds; fit=self._fit(required=True)
        non_sym=bool(c.objExists(fit+".NonSym") and c.getAttr(fit+".NonSym"))
        if non_sym:
            for node in c.listRelatives(fit,children=True,type="transform") or []:
                if c.getAttr(node+".visibility",lock=True): c.setAttr(node+".visibility",lock=False)
                c.setAttr(node+".visibility",True)
            return ()
        center={"FaceFitNose","FaceFitNoseUnder","FaceFitNoseBridge","FaceFitJaw","FaceFitChinCrease","FaceFitThroat"}
        created=[]
        for node in c.listRelatives(fit,children=True,type="transform") or []:
            leaf=node.rsplit("|",1)[-1].rsplit(":",1)[-1]
            if leaf.endswith("Center") or leaf in center or leaf.endswith("Left"): continue
            left=leaf+"Left"
            if c.objExists(left): c.delete(left)
            original_children=c.listRelatives(node,allDescendents=True,type="transform",fullPath=True) or []
            root=c.duplicate(node,name=left,returnRootsOnly=True)[0]
            c.setAttr(root+".sx",-c.getAttr(node+".sx"))
            copies=c.listRelatives(root,allDescendents=True,type="transform",fullPath=True) or []
            # Descendant order is leaves first, matching the original rename walk.
            for original,copy in zip(original_children,copies):
                name=original.rsplit("|",1)[-1].rsplit(":",1)[-1]+"Left"
                c.rename(copy,name)
            created.append(left)
        return tuple(created)
