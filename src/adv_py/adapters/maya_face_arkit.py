"""Python asConnectARKit/asDisconnectARKit graph, source 14523–14821."""
from adv_py.core.face_arkit import (ARKIT_SHAPES, SNAPCHAT_SHAPES,
    SNAPCHAT_ARKIT_SHAPES, original_arkit_driver_rows)
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFaceARKitMixin:
    def connect_original_face_arkit(self, blendshape=None, *, mouth_close_includes_open=False):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        if not c.objExists("FaceControlSet"):
            raise FitSkeletonValidationError("没有 FaceControlSet，请先建立 Face 绑定")
        snap = bool(c.objExists(fit + ".SnapChat") and c.getAttr(fit + ".SnapChat"))
        control = "ctrlSnapChat_M" if snap else "ctrlARKit_M"
        create = bool(c.objExists(control) and not c.objExists(control + ".eyeBlinkLeft")) or snap
        connect = bool(c.objExists(control) and c.objExists(control + ".eyeBlinkLeft"))
        before = self.capture_face_build_node_ids()
        self._transaction_changed = True
        if create:
            source = control
            c.addAttr(control, longName="createCtrlMode", attributeType="bool", keyable=False)
        else:
            source = blendshape
            if source:
                matches = raw.ls(source, long=True) or []
                if len(matches) != 1:
                    raise FitSkeletonValidationError("ARKit 来源节点缺失或不唯一")
                source = matches[0]
                if ":" not in source:
                    source = ":" + source
            if not connect and c.objExists(fit + ".RigType") and c.getAttr(fit + ".RigType") == 1:
                raise FitSkeletonValidationError("Connect ARKit 需要 Joints 或 Mixed Face 绑定")
            if not source or not c.objExists(source):
                raise FitSkeletonValidationError("请选择有效的 ARKit BlendShape 来源")
        semantic_names = SNAPCHAT_ARKIT_SHAPES if snap else ARKIT_SHAPES
        names = SNAPCHAT_SHAPES[:len(semantic_names)] if snap else ARKIT_SHAPES
        driver_value = 10 if create else 1
        if create:
            for name in names:
                c.addAttr(source, longName=name, attributeType="double", keyable=True,
                          softMinValue=0, softMaxValue=10)
                self.original_face_output_bw(source + "." + name)
        quick = not create and not connect
        if quick and not c.objExists("ARKitQuickConnecting"):
            c.createNode("transform", name="ARKitQuickConnecting")
        # The source requests frame zero. Avoid journaling a no-op time change:
        # Maya 2024 can crash undoing that command after Quick Connect tears
        # down/reconnects the existing animation graph. The requested time and
        # every driven value remain identical when already at frame zero.
        if c.currentTime(query=True) != 0:
            c.currentTime(0)
        auto = bool(raw.autoKeyframe(query=True, state=True))
        if auto:
            raw.autoKeyframe(state=False)
        connected, missing = [], []
        try:
            for semantic, name in zip(semantic_names, names):
                alt = name.replace("Right", "_R", 1).replace("Left", "_L", 1)
                attr = name if c.objExists(source + "." + name) else alt
                if not c.objExists(source + "." + attr):
                    missing.append(source + "." + alt)
                    continue
                plug = source + "." + attr
                if connect:
                    targets = [control + "." + name]
                    if semantic == "mouthClose" and mouth_close_includes_open:
                        targets.append(control + ".jawOpen")
                    for target in targets:
                        for dv, value in ((0, 0), (1, 10)):
                            try:
                                c.setDrivenKeyframe(target, currentDriver=plug, driverValue=dv, value=value,
                                                    inTangentType="linear", outTangentType="linear")
                            except RuntimeError as error:
                                raw.warning(str(error))  # Original catch, then continue.
                    connected.append(name)
                    continue
                for target, override, value in original_arkit_driver_rows(semantic,
                        jaw_forward=c.objExists("ctrlMouth_M.jawForward")):
                    self.add_original_face_sdk(plug, target, driver_value if override is None else override, value)
                if semantic == "mouthClose":
                    c.setAttr("ctrlMouth_M.ty", 0)
                    closed = c.xform("lowerLip_M", query=True, worldSpace=True, translation=True)
                    c.setAttr("ctrlMouth_M.ty", -1)
                    opened = c.xform("lowerLip_M", query=True, worldSpace=True, translation=True)
                    c.xform("lowerLip_M", worldSpace=True, translation=(opened[0], closed[1], opened[2]))
                    offset = c.getAttr("lowerLip_M.t")[0]
                    c.setAttr("ctrlMouth_M.ty", 0)
                    c.setAttr("lowerLip_M.t", 0, 0, 0, type="float3")
                    self.add_original_face_sdk(plug, "SDKlowerLip_M.ty", driver_value, offset[1] / 2)
                    self.add_original_face_sdk(plug, "SDKupperLip_M.ty", driver_value, offset[1] / -2)
                    if mouth_close_includes_open:
                        self.add_original_face_sdk(plug, "ctrlMouth_M.ty", driver_value, -1)
                connected.append(name)
        finally:
            if auto:
                raw.autoKeyframe(state=True)
            if c.objExists("ARKitQuickConnecting"):
                c.delete("ARKitQuickConnecting")
        raw.dgdirty(allPlugs=True)
        c.select(clear=True)
        generated = [node for node in c.ls(objectsOnly=True) or []
                     if c.nodeType(node) not in ("objectSet", "partition")
                     and not before.intersection(c.ls(node, uuid=True) or [])]
        if generated and c.objExists("FaceAllSet"):
            c.sets(generated, add="FaceAllSet")
        self._transaction_changed = True
        return {"controller": control, "source": source, "channels": tuple(connected),
                "missing_channels": tuple(missing), "snapchat": snap}

    def disconnect_original_face_arkit(self):
        self._require_transaction()
        c = self._cmds
        if not c.objExists("FaceControlSet"):
            raise FitSkeletonValidationError("没有 FaceControlSet")
        self._transaction_changed = True
        disconnected = set()
        for control in c.sets("FaceControlSet", query=True) or []:
            for kind in ("animCurve", "blendWeighted"):
                nodes = c.listConnections(control, source=True, destination=False, type=kind) or []
                if nodes:
                    identifiers = set(c.ls(nodes, uuid=True) or [])
                    pairs = c.listConnections(control, source=True, destination=False,
                                               plugs=True, connections=True) or []
                    for destination, source in zip(pairs[::2], pairs[1::2]):
                        if identifiers.intersection(c.ls(source.split('.', 1)[0], uuid=True) or []):
                            disconnected.add(destination)
                    c.delete(nodes)
        self.apply_face_build_pose(self.read_face_build_pose())
        # Maya's delete undo records the input graph, but redo can restore a
        # stale cached driven value when that graph is removed again. Journal
        # exactly the source's already-computed disconnected scalar values.
        # This neither invents defaults nor resets unrecorded ARKit channels.
        for plug in sorted(disconnected):
            if c.objExists(plug) and c.getAttr(plug, settable=True):
                value = c.getAttr(plug)
                if isinstance(value, (bool, int, float)):
                    c.setAttr(plug, value)
        self._transaction_changed = True
