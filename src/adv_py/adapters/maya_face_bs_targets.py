"""Original BlendShape target reset, wizard, extract and new target."""
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFaceBSTargetsMixin:
    def _original_bs_target_driver(self, target):
        c = self._cmds
        curves = c.listConnections("asFaceBS." + target, source=True, destination=False,
                                   type="animCurve", skipConversionNodes=True) or []
        if not curves:
            raise FitSkeletonValidationError("目标没有 SDK 驱动：" + target)
        curve = curves[0]
        sources = c.listConnections(curve + ".input", source=True, destination=False,
                                   plugs=True, skipConversionNodes=True) or []
        if not sources:
            raise FitSkeletonValidationError("SDK 没有控制器来源：" + target)
        driver = sources[0]
        # Converted mouth-corner SDK uses its output BW. Its sole retained
        # input is the same controller attribute that the source wizard edits.
        if c.nodeType(driver.split(".", 1)[0]) == "blendWeighted":
            sources = c.listConnections(driver.split(".", 1)[0] + ".input[0]", source=True,
                                       destination=False, plugs=True, skipConversionNodes=True) or []
            if sources:
                driver = sources[0]
        return curve, driver.replace("Layered", "", 1)

    def adjust_original_face_bs_named_target(self, target, *, auto_mirror=True):
        self._require_transaction()
        self._transaction_changed = True
        self.apply_face_build_pose(self.read_face_build_pose())
        curve, driver = self._original_bs_target_driver(target)
        changes = self._cmds.keyframe(curve, query=True, floatChange=True) or []
        if len(changes) < 2:
            raise FitSkeletonValidationError("SDK 缺少目标驱动关键帧：" + target)
        value = changes[0] if changes[0] < 0 else changes[1]
        self._cmds.setAttr(driver, value)
        getattr(self._cmds, "raw", self._cmds).refresh()
        return self.adjust_original_face_bs_target(auto_mirror=auto_mirror)

    def stop_original_face_bs_wizard(self):
        self._require_transaction()
        self.original_face_bs_editable_targets()
        self._transaction_changed = True
        if self._cmds.objExists("deleteThis"):
            self._cmds.delete("deleteThis")
        self.apply_face_build_pose(self.read_face_build_pose())
        return {"step": 0, "total": len(self.original_face_bs_editable_targets()), "finished": True}

    def start_original_face_bs_wizard(self, *, auto_mirror=True, multiplier=1):
        self.stop_original_face_bs_wizard()
        raw = getattr(self._cmds, "raw", self._cmds)
        raw.playbackOptions(minTime=1, maxTime=10, animationStartTime=1, animationEndTime=10)
        return self.next_original_face_bs_wizard(0, auto_mirror=auto_mirror, multiplier=multiplier)

    def next_original_face_bs_wizard(self, previous_step, *, auto_mirror=True, multiplier=1):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        targets = self.original_face_bs_editable_targets()
        limits = bool(c.getAttr("ctrlBox.limits"))
        self._transaction_changed = True
        if c.objExists("deleteThis"):
            c.delete("deleteThis")
        self.apply_face_build_pose(self.read_face_build_pose())
        if limits:
            c.setAttr("ctrlBox.limits", 0)
        try:
            for index in range(previous_step, len(targets)):
                target = targets[index]
                curve, driver = self._original_bs_target_driver(target)
                xs = c.keyframe(curve, query=True, floatChange=True) or []
                ys = c.keyframe(curve, query=True, valueChange=True) or []
                values = [x for x, y in zip(xs, ys) if y == 1]
                if not values:
                    raise FitSkeletonValidationError("SDK 缺少权重为 1 的关键帧：" + target)
                if "tx" in driver and "_ty" in driver:
                    continue
                raw.refresh()
                c.setAttr(driver, values[-1])
                edited = self.adjust_original_face_bs_target(auto_mirror=auto_mirror, multiplier=multiplier)
                return {"step": index + 1, "total": len(targets), "target": target,
                        "driver": driver, "value": values[-1], "edited": edited, "finished": False}
            return self.stop_original_face_bs_wizard()
        finally:
            if limits:
                c.setAttr("ctrlBox.limits", 1)

    def reset_original_face_bs_target(self):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        if not c.objExists("deleteThis"):
            raise FitSkeletonValidationError("请先创建用于编辑的目标网格")
        source = self.capture_original_face_bs_edit()
        selection = c.ls(selection=True, long=True) or []
        self._transaction_changed = True
        reset = []
        for target in c.listRelatives("deleteThis", children=True, type="transform") or []:
            if not c.objExists(target + ".sourceObject"):
                continue
            geometry = c.getAttr(target + ".sourceObject")
            bs = "asFaceBS" if geometry == source["geometry"] else "asFaceBS_" + self._original_bs_geo_tag(geometry)
            c.setAttr(bs + ".envelope", 0)
            with self._original_bs_creation_context():
                raw.blendShape(geometry, self.scene_address(target), name=self.scene_address("tempBS"),
                               frontOfChain=True, weight=(0, 1))
            raw.refresh()
            raw.delete(self.scene_address(target), constructionHistory=True)
            c.setAttr(bs + ".envelope", 1)
            reset.append(target)
        if c.objExists("faceCombinedDefaultShape"):
            c.connectAttr("faceCombinedDefaultShape.outMesh", "faceCombinedMirrorDriverShape.inMesh", force=True)
            raw.refresh()
            c.disconnectAttr("faceCombinedDefaultShape.outMesh", "faceCombinedMirrorDriverShape.inMesh")
        c.select(selection, replace=True) if selection else c.select(clear=True)
        return tuple(reset)

    def _original_bs_creation_context(self):
        from contextlib import nullcontext
        return self._cmds._creation_namespace() if hasattr(self._cmds, "_creation_namespace") else nullcontext()

    def extract_all_original_face_bs_targets(self, *, auto_mirror=True):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        self._transaction_changed = True
        if c.objExists("asBlendShapes"):
            c.delete("asBlendShapes")
        c.createNode("transform", name="asBlendShapes")
        result = self.start_original_face_bs_wizard(auto_mirror=auto_mirror)
        extracted = []
        for row in range(999):
            if result["finished"] or not c.objExists("deleteThis"):
                break
            for wrap in c.ls("asFaceMirroWrap*", type="wrap") or []:
                outputs = c.listConnections(wrap + ".outputGeometry", source=False, destination=True) or []
                if outputs:
                    raw.delete(tuple(self.scene_address(node) for node in outputs), constructionHistory=True)
            targets = c.listRelatives("deleteThis", children=True, type="transform") or []
            for target in targets:
                raw.delete(self.scene_address(target), constructionHistory=True)
            for target in targets:
                leaf = self._original_restore_leaf(target)
                if leaf.endswith("_L"):
                    c.setAttr(target + ".v", 1)
                if c.getAttr(target + ".v"):
                    c.parent(target, "asBlendShapes")
                    target = leaf
                    extracted.append(target)
                if "_M" in leaf:
                    c.setAttr(target + ".tx", 0)
                c.setAttr(target + ".ty", (row + 1) * c.getAttr(self._fit(required=True) + ".faceScale"))
            result = self.next_original_face_bs_wizard(result["step"], auto_mirror=auto_mirror)
        if c.objExists("deleteThis"):
            c.delete("deleteThis")
        self.apply_face_build_pose(self.read_face_build_pose())
        return tuple(extracted)

    def create_new_original_face_bs_target(self, attribute="", control="", *, mirror=True):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        source = self.capture_original_face_bs_edit()
        attribute, control = attribute or "Untitled", control or "ctrlUntitled"
        if c.objExists(attribute):
            raise FitSkeletonValidationError("目标名称已被对象占用：" + attribute)
        side = ("_R" if control.endswith("_R") else "_M") if c.objExists(control) else ("_R" if mirror else "_M")
        stem = control[:-2] if control.endswith(("_R", "_M")) else control
        sides = ("_R", "_L") if side == "_R" else ("_M",)
        self._transaction_changed = True
        self.apply_face_build_pose(self.read_face_build_pose())
        if c.objExists("deleteThis"):
            c.delete("deleteThis")
        c.createNode("transform", name="deleteThis")
        controls = []
        for ordinal, geometry in enumerate(source["geos"]):
            bs = "asFaceBS" if ordinal == 0 else "asFaceBS_" + self._original_bs_geo_tag(geometry)
            if not c.objExists(bs):
                continue
            name = attribute if ordinal == 0 else attribute + "_" + self._original_bs_geo_tag(geometry)
            self._original_bs_mesh_sample(geometry, name + side)
            c.move(source["cheek"][0] * 2.5, 0, 0, name + side, relative=True)
            if side == "_R":
                c.duplicate(name + side, name=name + "_L")
                c.move(source["cheek"][0] * -5, 0, 0, name + "_L", relative=True)
                c.duplicate(name + "_L", name=name + "_LMirrorDriver")
                c.setAttr(name + "_LMirrorDriver.sx", -1)
                c.setAttr(name + "_LMirrorDriver.v", 0)
                self._original_bs_native_wrap(name + "_L", name + "_LMirrorDriver")
                c.connectAttr(self._original_bs_mesh_shape(name + side) + ".outMesh",
                              self._original_bs_mesh_shape(name + "_LMirrorDriver") + ".inMesh", force=True)
            for ctrl_side in sides:
                driver = stem + ctrl_side
                if ordinal == 0:
                    if not c.objExists(driver):
                        created = c.circle(center=(0,0,0), normal=(0,0,1), sweep=360, radius=.1,
                            degree=3, useTolerance=False, tolerance=.000393701, sections=8, constructionHistory=False)[0]
                        c.rename(created, driver)
                        c.parent(driver, "ctrlBox")
                        shape = c.listRelatives(driver, shapes=True)[0]
                        c.setAttr(shape + ".overrideEnabled", 1)
                        c.setAttr(shape + ".overrideColor", 13)
                        c.xform(driver, objectSpace=True, translation=(0,0,0), rotation=(0,0,0), scale=(1,1,1))
                        if ctrl_side != "_M":
                            c.setAttr(driver + ".tx", source["cheek"][0] * .2 * (1 if ctrl_side == "_R" else -1))
                        c.sets(driver, add="FaceControlSet")
                    if not c.objExists(driver + "." + attribute):
                        c.addAttr(driver, longName=attribute, attributeType="double", keyable=True,
                                  softMinValue=0, softMaxValue=10, defaultValue=10)
                    controls.append(driver)
                target = name + ctrl_side
                index = self._original_face_bs_add_target(geometry, bs, target)
                alias = attribute + ctrl_side
                c.aliasAttr(alias, bs + ".weight[" + str(index) + "]")
                for dv, value in ((0,0), (10,1)):
                    c.setDrivenKeyframe(bs + "." + alias, currentDriver=driver + "." + attribute,
                        driverValue=dv, value=value, inTangentType="linear", outTangentType="spline")
                c.setAttr(bs + "_" + alias + ".preInfinity", 4)
                c.setAttr(bs + "_" + alias + ".postInfinity", 4)
        rows = list(self._face_pose_numeric_rows())
        for driver in controls:
            paths = c.ls(driver, long=True)
            row = (paths[0], attribute, 0.)
            rows = [r for r in rows if tuple(r[:2]) != row[:2]]
            rows.append(row)
        self._write_face_pose_numeric_rows(rows)
        c.delete("deleteThis")
        self.apply_face_build_pose(self.read_face_build_pose())
        c.setAttr(stem + side + "." + attribute, 10)
        raw.dgdirty(allPlugs=True)
        return self.adjust_original_face_bs_target(auto_mirror=mirror)

    def finish_original_face_bs_edit(self):
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        if c.objExists("deleteThis"):
            c.delete("deleteThis")
        return True

    def delta_mush_all_original_face_bs_targets(self, *, auto_mirror=True, multiplier=1.3):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        source = self.capture_original_face_bs_edit()
        self._transaction_changed = True
        self.apply_face_build_pose(self.read_face_build_pose())
        with self._original_bs_creation_context():
            deformer = raw.deltaMush(source["geometry"], smoothingIterations=10,
                                    smoothingStep=.5, pinBorderVertices=True, envelope=1)[0]
        if c.objExists("Main") and c.objExists("MainScaleMultiplyDivide"):
            for axis in "XYZ":
                raw.connectAttr(self.scene_address("MainScaleMultiplyDivide") + ".output" + axis,
                                deformer + ".s" + axis.lower())
        raw.refresh()
        if c.objExists("eyeLidArea") and c.objExists("lipArea"):
            raw.select((self.scene_address("eyeLidArea"), self.scene_address("lipArea")), replace=True)
            raw.percent(deformer, value=0)
        c.createNode("transform", name="runningDeltaMushAllTargets")
        result = self.start_original_face_bs_wizard(auto_mirror=auto_mirror, multiplier=multiplier)
        processed = []
        # Keep the batch inside the application's undo chunk. The source's
        # temporary undo-disable was only a speed optimization for its UI loop.
        if not result["finished"]:
            processed.append(result["target"])
        for _ in range(999):
            if result["finished"] or not c.objExists("deleteThis"):
                break
            result = self.next_original_face_bs_wizard(result["step"], auto_mirror=auto_mirror, multiplier=multiplier)
            if not result["finished"]:
                processed.append(result["target"])
        for node in raw.listHistory(source["geometry"]) or []:
            if raw.nodeType(node) == "deltaMush":
                raw.delete(node)
        self._original_bs_delete_existing(("runningDeltaMushAllTargets", "deleteThis"))
        self.apply_face_build_pose(self.read_face_build_pose())
        return tuple(processed)
