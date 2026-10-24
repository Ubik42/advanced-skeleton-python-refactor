"""Template-import external skeleton scan and source preparation."""
from adv_py.core.source_import_matcher import SourceImportMatcherDetection,source_import_matcher_joint
from adv_py.core.fbx_rig_import import detect_fbx_source_application


class MayaSourceImportMatcherMixin:
    def detect_source_import_matcher(self):
        c = self._cmds
        raw = getattr(c,'raw',c)
        template = c.getAttr('FitSkeleton.fitSkeletonTemplate') if c.objExists('FitSkeleton.fitSkeletonTemplate') else ''
        excluded = {self.scene_address(path) for path in c.listRelatives(
            'FitSkeleton',allDescendents=True,fullPath=True) or ()} if c.objExists('FitSkeleton') else set()
        joints = tuple(path for path in raw.ls(type='joint',long=True) or () if path not in excluded)
        joint = source_import_matcher_joint(template,joints,
            importing=bool(c.objExists('FitSkeletonNameMatcherImporting')))
        if joint is None:return None
        root = joint
        while True:
            parent = raw.listRelatives(root,parent=True,type='joint',fullPath=True) or ()
            if not parent:break
            root = parent[0]
        template = detect_fbx_source_application(tuple(raw.ls(long=True) or ()))
        return SourceImportMatcherDetection(joint,root,template)

    def prepare_source_import_matcher(self, detection):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c,'raw',c)
        self._transaction_changed = True
        raw.select(raw.ls(assemblies=True) or (),replace=True)
        times = tuple(raw.keyframe(query=True,timeChange=True) or ())
        raw.select(clear=True)
        if times:
            last = int(max(times))
            raw.playbackOptions(minTime=-1,animationStartTime=-1,maxTime=last,animationEndTime=last)
            raw.currentTime(-1)
            raw.autoKeyframe(state=True)
        eyes = tuple(raw.ls('CC_Base_Eye',recursive=True) or ())
        faces = tuple(raw.ls('CC_Base_Eye.f[0]',recursive=True) or ())
        if eyes and not faces:
            choice = raw.confirmDialog(title='Straighten ?',
                message='"CC AutoSetup for Maya" detected, some updates needed:\n\n-Reset TopNodePivot\n-Rename Eye Geo\n\nProceed ?',
                button=('Yes','No'),defaultButton='Yes',dismissString='No')
            if choice!='Yes':return False
            # Native uses the first namespace token and first DAG component.
            tokens = eyes[0].split(':')
            namespace = tokens[0] if len(tokens)>1 else ''
            paths = raw.ls(eyes[0],long=True) or ()
            top = next(part for part in paths[0].split('|') if part)
            raw.xform(top,pivots=(0,0,0))
            if raw.objExists(namespace+':Eye_R') and raw.objExists('polySeparate1'):
                eye = namespace+':CC_Base_Eye'
                raw.select(raw.listRelatives(eye,children=True) or (),replace=True)
                parents = raw.listRelatives(eye,parent=True) or ()
                combined = raw.polyUnite(name=eye,constructionHistory=False)[0]
                if parents:raw.parent(combined,parents[0])
                raw.select((namespace+':CC_Base_Head',combined),replace=True)
                raw.skinCluster(toSelectedBones=True,maximumInfluences=3,dropoffRate=4,
                                removeUnusedInfluence=False)
        raw.select(detection.source_root,replace=True)
        return True

    def mark_source_import_matcher_alignment(self, detected_joint):
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        for name,kind in (('alignedWithExternalSkeleton','bool'),('externalSkelDetectedJoint','string')):
            if not c.attributeQuery(name,node='FitSkeleton',exists=True):
                if kind=='bool':c.addAttr('FitSkeleton',longName=name,attributeType='bool',defaultValue=True,keyable=False)
                else:c.addAttr('FitSkeleton',longName=name,dataType='string',keyable=False)
        c.setAttr('FitSkeleton.alignedWithExternalSkeleton',True)
        c.setAttr('FitSkeleton.externalSkelDetectedJoint',detected_joint,type='string')
        getattr(c,'raw',c).refresh()
