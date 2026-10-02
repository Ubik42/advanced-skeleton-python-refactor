"""Native selection flow of asBindSkinLoops (ADV 6.925, 54981–55390).

Selection conversions are Maya operations: replacing them with a graph flood
fill changes both the seed order and the weighting decisions in the source.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from math import dist


from .maya_original_transform_channels import lock_original_transform_channels

class MayaSkinLoopsSourceMixin:
    @staticmethod
    def _loop_leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _loop_command(self, command: str) -> None:
        from maya import mel
        mel.eval(command + ";")

    def _loop_selection(self, *, flattened: bool = False) -> list[str]:
        return self.cmds.ls(selection=True, flatten=flattened) or []

    def _loop_select(self, items, **flags) -> None:
        if items:
            self.cmds.select(items, **flags)
        elif not flags.get("deselect") and not flags.get("add"):
            self.cmds.select(clear=True)

    def _loop_on_mesh(self, loop_set: str, mesh: str) -> bool:
        members = self.cmds.sets(loop_set, query=True) or []
        return bool(members and self._mesh_transform(members[0])
                    == self._unique(mesh, "transform"))

    def _loop_vertices(self, loop_set: str, *, flattened=False) -> list[str]:
        self.cmds.select(loop_set, replace=True)
        self._loop_command("ConvertSelectionToVertices")
        return self._loop_selection(flattened=flattened)

    def _loop_remove_intermediates(self, mesh: str) -> None:
        c = self.cmds
        for shape in c.listRelatives(mesh, shapes=True, fullPath=True) or []:
            if c.getAttr(shape + ".intermediateObject"):
                c.delete(shape)

    def _loop_cut_copy(self, mesh: str, loop_sets: list[str]) -> str:
        c = self.cmds
        duplicate = c.duplicate(mesh, name=self._name(
            self._loop_leaf(mesh) + "CutUp"))[0]
        self._loop_remove_intermediates(duplicate)
        for loop in loop_sets:
            copied = c.duplicate(loop)[0]
            copied = c.rename(copied, loop + "CutUp")
            c.select(loop, replace=True)
            for member in self._loop_selection(flattened=True):
                if self._mesh_transform(member) == self._unique(
                        duplicate, "transform"):
                    c.sets(member, add=copied)
                    c.sets(member, remove=loop)
        for loop in loop_sets:
            c.rename(loop, loop + "Temp")
            c.rename(loop + "CutUp", loop)
        return duplicate

    def _loop_cut_piece(self, mesh: str, joint: str, cut_name: str,
                        loop_sets: list[str], faces: list[str]) -> str:
        c = self.cmds
        if c.objExists(cut_name):
            c.delete(cut_name)
        world = c.duplicate(mesh, name=cut_name + "WS")[0]
        lock_original_transform_channels(c, world)
        self._loop_remove_intermediates(world)
        piece = c.duplicate(world, name=cut_name)[0]
        piece = c.parent(piece, joint, relative=True)[0]
        piece = c.parent(piece, world=True)[0]
        c.select([world, piece], replace=True)
        c.blendShape(frontOfChain=True, origin="world", weight=(0, 1))
        c.delete(piece, constructionHistory=True)
        c.delete(world)
        piece = c.parent(piece, self._name("CutUpGeometry"))[0]
        c.editDisplayLayerMembers(self._name("CutUp"), piece, noRecurse=True)
        mapped = [piece + face[face.index("."):] for face in faces]
        self._loop_select(mapped, replace=True)
        # asInvertSelection explicitly bypasses Maya's InvertSelection for
        # components (the source documents its Maya 2018 failure).
        objects = c.ls(selection=True, objectsOnly=True) or []
        c.select(objects[0] + ".f[0:999999]", replace=True)
        self._loop_select(mapped, deselect=True)
        c.delete()
        c.select(piece, replace=True)
        c.xform(piece, centerPivots=True)
        for loop in loop_sets:
            c.select(loop, replace=True)
            objects = c.ls(selection=True, objectsOnly=True) or []
            affects = any(self._mesh_transform(obj) == self._unique(
                piece, "transform") for obj in objects)
            if not affects:
                continue
            c.select(mesh + ".e[0:99999]", deselect=True)
            circumference = 0.0
            for edge in self._loop_selection(flattened=True):
                c.select(edge, replace=True)
                self._loop_command("ConvertSelectionToVertices")
                vertices = self._loop_selection(flattened=True)
                a = c.xform(vertices[0], query=True, worldSpace=True,
                            translation=True)
                b = c.xform(vertices[1], query=True, worldSpace=True,
                            translation=True)
                circumference += dist(a, b)
            radius = circumference / 3.14 / 2.0
            c.select(loop, replace=True)
            c.select(mesh + ".e[0:99999]", deselect=True)
            c.polyExtrudeEdge(constructionHistory=True, keepFacesTogether=True,
                              pvx=1.927402496, pvy=3.865962148, pvz=.184265554,
                              divisions=1, twist=0, taper=1, offset=0,
                              thickness=0, smoothingAngle=30)
            extruded = self._loop_selection()
            from maya import mel
            c.setToolTo(mel.eval("global string $gMove; $gMove;"))
            position = c.manipMoveContext("Move", query=True, position=True)
            c.scale(.25, .25, .25, relative=True, pivot=position)
            pivot = c.xform(piece, query=True, worldSpace=True, pivots=True)
            loc1 = c.spaceLocator(name=self._name("tempLoc1"))[0]
            loc2 = c.spaceLocator(name=self._name("tempLoc2"))[0]
            # The source uses Y for Z in both locator placements.
            c.xform(loc1, worldSpace=True,
                    translation=(pivot[0], pivot[1], pivot[1]))
            c.xform(loc2, worldSpace=True,
                    translation=(position[0], position[1], position[1]))
            c.aimConstraint(loc2, loc1, offset=(0, 0, 0), weight=1,
                            aimVector=(1, 0, 0), upVector=(0, 1, 0),
                            worldUpType="vector", worldUpVector=(0, 1, 0))
            piece = c.parent(piece, loc1)[0]
            # Component names obtained before parenting are resolved by short
            # mesh name, as in MEL; do not retain an obsolete full DAG path.
            self._loop_select(extruded, replace=True)
            c.move(radius * .5, 0, 0, relative=True, localSpace=True,
                   worldSpaceDistance=True)
            piece = c.parent(piece, self._name("CutUpGeometry"))[0]
            c.parentConstraint(joint, piece, maintainOffset=True)
            c.scaleConstraint(joint, piece)
            c.delete(loc1, loc2)
            c.select(piece, replace=True)
            c.delete(piece, constructionHistory=True)
            c.sets(piece + ".e[0:99999]", remove=loop)
        return self._unique(piece, "transform")

    def _run_original_skin_loops(self, specs, *, cut_up=False) -> tuple[str, ...]:
        if not self._in_transaction:
            raise RuntimeError("SkinLoops 必须位于事务中")
        c = self.cmds
        loops = sorted(c.sets(self._name("SkinLoops"), query=True) or [])
        wip = c.createNode("transform", name=self._name("CutUpWIP"))
        weighted = c.sets(empty=True, name=self._name("SkinLoopWeighted"))
        if cut_up and not c.objExists(self._name("CutUp")):
            layer = c.createDisplayLayer(empty=True, name=self._name("CutUp"))
            c.setAttr(layer + ".color", 29)
            c.setAttr(layer + ".displayType", 2)
        if not c.objExists(self._name("CutUpGeometry")):
            c.createNode("transform", name=self._name("CutUpGeometry"),
                         parent=self._name("Geometry"))
        pieces = []
        cut_name = ""
        for spec in specs:
            mesh = self._loop_cut_copy(spec.mesh, loops) if cut_up else spec.mesh
            skin = None if cut_up else self._skin(mesh)
            if skin:
                c.skinPercent(skin, mesh,
                              transformValue=(spec.root_joint, 1.0))
            else:
                c.select([spec.root_joint, mesh], replace=True)
                from .maya_original_skin_history import new_original_skin_clusters
                skin = new_original_skin_clusters(commands=c, namespace=self.namespace)[0]
            deform = {}
            for loop in loops:
                if not self._loop_on_mesh(loop, mesh):
                    continue
                joint = self._unique(self._name(
                    self._loop_leaf(loop).replace("SkinLoops_", "", 1)), "joint")
                deform[loop] = joint
                parents = c.listRelatives(joint, parent=True, type="joint") or []
                influences = c.listConnections(skin + ".matrix") or []
                resolved = {self._unique(item, "joint") for item in influences}
                for influence in [joint] + parents[:1]:
                    influence = self._unique(influence, "joint")
                    if influence not in resolved:
                        c.skinCluster(skin, edit=True, lockWeights=False,
                                      weight=0, addInfluence=influence)
                        resolved.add(influence)
                vertices = self._loop_vertices(loop)
                c.refresh()
                c.skinPercent(skin, vertices, transformValue=(joint, 1.0))
                c.sets(vertices, add=weighted)
            c.select(clear=True)
            for loop in loops:
                c.select(loop, add=True)
            self._loop_command("ConvertSelectionToVertices")
            loop_vertices = self._loop_selection()
            count = int(c.polyEvaluate(mesh, vertex=True))
            c.select(f"{mesh}.vtx[0:{count}]", replace=True)
            self._loop_select(loop_vertices, deselect=True)
            c.refresh()
            self._loop_command("weightHammerVerts")
            self._loop_select(loop_vertices, replace=True)
            self._loop_command("GrowPolygonSelectionRegion")
            self._loop_select(loop_vertices, deselect=True)
            self._loop_command("weightHammerVerts")
            all_loop_vertices = self._loop_vertices(self._name("SkinLoops"))
            c.select(clear=True)
            for loop in loops:
                if not fnmatchcase(loop, "*Part[0-9]_*"):
                    c.select(loop, add=True)
            self._loop_command("ConvertSelectionToVertices")
            for loop in loops:
                if not self._loop_on_mesh(loop, mesh):
                    continue
                joint = deform[loop]
                vertices = self._loop_vertices(loop, flattened=True)
                c.select(vertices[0], replace=True)
                self._loop_command("ConvertSelectionToEdges")
                self._loop_command("ConvertSelectionToVertices")
                self._loop_select(all_loop_vertices, deselect=True)
                neighbors = self._loop_selection(flattened=True)
                descendants = {self._unique(item, "joint") for item in (
                    c.listRelatives(joint, allDescendents=True, type="joint") or [])}
                neighbor_index = 0
                while neighbor_index < len(neighbors):
                    neighbor = neighbors[neighbor_index]
                    neighbor_index += 1
                    if c.sets(neighbor, isMember=weighted):
                        continue
                    c.select(neighbor, replace=True)
                    influences = c.skinPercent(skin, neighbor, ignoreBelow=1e-7,
                                               query=True, transform=None) or []
                    downstream = next((item for item in influences
                                       if len(influences) == 1 or self._unique(
                                           item, "joint") in descendants), None)
                    if downstream is not None:
                        cut_name = self._name(self._loop_leaf(joint) + "_" +
                                              self._loop_leaf(downstream) + "_Cut")
                    reverse = (self._name(self._loop_leaf(downstream) + "_" +
                                          self._loop_leaf(joint) + "_CutWIP")
                               if downstream else "")
                    if c.objExists(cut_name + "WIP") or (reverse and c.objExists(reverse)):
                        continue
                    if downstream is None:
                        continue
                    previous_count = -1
                    stop_neighbors = False
                    for _ in range(100):
                        self._loop_command("ConvertSelectionToEdges")
                        self._loop_command("ConvertSelectionToVertices")
                        self._loop_select(all_loop_vertices, deselect=True)
                        current_count = len(self._loop_selection(flattened=True))
                        if current_count == previous_count:
                            break
                        previous_count = current_count
                        if self._loop_leaf(loop) != "SkinLoops_Root_M":
                            stop_neighbors = True
                    c.refresh()
                    region = self._loop_selection(flattened=True)
                    c.createNode("transform", name=cut_name + "WIP", parent=wip)
                    self._loop_select(region, replace=True)
                    if cut_up:
                        self._loop_command("ConvertSelectionToFaces")
                        pieces.append(self._loop_cut_piece(
                            mesh, joint, cut_name, loops, self._loop_selection()))
                    else:
                        c.skinPercent(skin, self._loop_selection(),
                                      transformValue=(joint, 1.0))
                        self._loop_select(region, replace=True)
                        c.sets(self._loop_selection(), add=weighted)
                    if stop_neighbors:
                        # MEL assigns z=99 inside the growth loop; the outer
                        # increment resumes at neighbor 100 if there are more.
                        neighbor_index = 100
            if cut_up:
                c.delete(mesh)
                for loop in loops:
                    if c.objExists(loop):
                        c.delete(loop)
                    c.rename(loop + "Temp", loop)
            else:
                for loop in loops:
                    if not self._loop_on_mesh(loop, mesh):
                        continue
                    joint = deform[loop]
                    if fnmatchcase(joint, "*Part[0-9]_*"):
                        continue
                    vertices = self._loop_vertices(loop)
                    parent = c.listRelatives(joint, parent=True, type="joint") or []
                    if parent:
                        c.skinPercent(skin, vertices,
                                      transformValue=[(joint, .5), (parent[0], .5)])
                    self._loop_command("GrowPolygonSelectionRegion")
                    self._loop_select(loop_vertices, deselect=True)
                    if self._loop_selection():
                        self._loop_command("weightHammerVerts")
                c.select(mesh, replace=True)
                self._loop_command("removeUnusedInfluences")
        c.delete(wip, weighted)
        # Later source cuts may replace a previous mesh with the same name.
        # Return the surviving scene objects, rather than stale duplicate paths.
        surviving = dict.fromkeys(self._loop_leaf(piece) for piece in pieces)
        return tuple(self._unique(self._name(leaf), "transform")
                     for leaf in surviving)

    def bind_skin_loop_batch(self, specs) -> None:
        self._run_original_skin_loops(specs)
