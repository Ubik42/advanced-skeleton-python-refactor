"""AdvancedSkeleton 6.925 curve-based corrective deformation (asCBD/asCB)."""
import json
from dataclasses import asdict
from adv_py.core.corrective_shapes import CorrectiveShapeOptions
from adv_py.core.skin_cage import plan_skin_cage_build, plan_skin_cage_width
from adv_py.core.skin_cage_sliders import SkinCageSlider, plan_skin_cage_sliders
from .maya_skin_cage_sliders import MayaSkinCageSliderHost
from .maya_face_deformer_sets import original_face_deformer_sets
from .maya_original_skin_history import bind_original_skin
from .maya_original_transform_channels import lock_original_transform_channels


class MayaCorrectiveCurvesMixin:
    def hide_original_corrective_curve_source(self, mesh):
        self._require_transaction();self._transaction_changed=True
        raw=self._corrective_raw()
        mesh=self._original_bs_physical_address(mesh)
        if raw.objExists(mesh):raw.setAttr(mesh+".v",0)

    def _cbd_data(self, attribute):
        c=self._cmds;raw=self._corrective_raw()
        link={"mesh":"advPySourceMesh","fkControl":"advPySourceFKControl"}.get(attribute)
        if link and c.objExists("curveDeformationSetup."+link):
            nodes=raw.listConnections(self.scene_address("curveDeformationSetup."+link),
                                     source=True,destination=False) or []
            if len(nodes)==1:
                paths=raw.ls(nodes[0],long=True) or []
                if len(paths)==1:
                    return paths[0] if attribute=="mesh" else self._original_restore_leaf(paths[0])
        value=c.getAttr("curveDeformationSetup."+attribute)
        if attribute=="mesh":
            return self._original_bs_physical_address(value)
        return value

    def _cbd_store(self, attribute, value, *, locked=False):
        c=self._cmds
        if isinstance(value,str):
            c.addAttr("curveDeformationSetup",longName=attribute,dataType="string")
            c.setAttr("curveDeformationSetup."+attribute,value,type="string",lock=locked)
            link={"mesh":"advPySourceMesh","fkControl":"advPySourceFKControl"}.get(attribute)
            if link:
                c.addAttr("curveDeformationSetup",longName=link,attributeType="message")
                self._corrective_raw().connectAttr(self.scene_address(value)+".message",
                    self.scene_address("curveDeformationSetup."+link))
        else:
            c.addAttr("curveDeformationSetup",longName=attribute,attributeType="bool",defaultValue=bool(value),keyable=True)

    def _cbd_slider_host(self):
        return MayaSkinCageSliderHost(self.namespace or "")

    def create_original_corrective_curves(self, mesh, fk_control):
        self._require_transaction()
        c=self._cmds;raw=self._corrective_raw()
        fk_control=self._original_restore_leaf(fk_control)
        if not self.original_corrective_primary_fk(fk_control):
            raise ValueError("请选择 FK 控制器")
        mesh=self._original_bs_physical_address(mesh)
        self._corrective_shape(mesh)
        joint=self.original_corrective_joint_for_fk(fk_control)
        parents=c.listRelatives(joint,parent=True,type="joint") or []
        if not parents or "Part" not in parents[0] or "Part1_" in parents[0]:
            raise ValueError("曲线变形要求至少两个 Twist 关节")
        self._transaction_changed=True
        stem,side=joint.rsplit("_",1)
        slider_host=self._cbd_slider_host()
        had_cage=c.objExists("SkinCage")
        if not had_cage:
            plan=plan_skin_cage_build(*slider_host.capture_build_input())
            slider_host.preflight_build(plan)
            slider_host.create_cage(plan)
            # Width uses all middle profiles, as asSkinCurvesToWidth.
            profiles=slider_host.capture_mirror_input()
            if profiles:
                raw.select(profiles,replace=True)
                for spec in plan_skin_cage_width(slider_host.capture_width_input()):
                    slider_host.set_width(spec)
            for node in ("SkinCage","SkinCurves1","SkinCurves2"):
                c.setAttr(node+".v",0)
        if c.objExists("tempLoc"):
            c.delete("tempLoc")
        if c.objExists("curveDeformationObjects"):
            members=c.sets("curveDeformationObjects",query=True) or []
            if members:c.delete(members)
            c.sets(clear="curveDeformationObjects")
        else:
            c.sets(empty=True,name="curveDeformationObjects")
        c.createNode("transform",name="curveDeformationSetup")
        c.setAttr("curveDeformationSetup.overrideEnabled",1)
        c.setAttr("curveDeformationSetup.overrideColor",13)
        c.sets("curveDeformationSetup",add="curveDeformationObjects")
        self._cbd_store("mesh",mesh,locked=True)
        self._cbd_store("fkControl",fk_control,locked=True)
        parent=parents[0]
        while "Part" in self._original_restore_leaf(parent):
            parent=c.listRelatives(parent,parent=True,type="joint")[0]
        child=c.listRelatives(joint,children=True,type="joint")[0]
        while "Part" in self._original_restore_leaf(child):
            child=c.listRelatives(child,children=True,type="joint")[0]
        fat=lambda node:c.getAttr(node+".fat")*c.getAttr(node+".fatWidth")
        widths=(fat(parent),fat(joint),fat(child))
        start=joint+"_startProfile" if c.objExists(joint+"_startProfile") else next(
            (parent+"_twistProfile"+str(i) for i in range(20,0,-1) if c.objExists(parent+"_twistProfile"+str(i))),"")
        end=joint+"_endProfile" if c.objExists(joint+"_endProfile") else (
            joint+"_twistProfile1" if c.objExists(joint+"_twistProfile1") else "")
        slider_name=lambda segment,index:stem+segment+"Slider"+str(index)+"_"+side
        created_specs=[];duplicate_sliders=[]
        for segment,profile in (("middle",joint+"_middleProfile"),("start",start),("end",end)):
            if c.objExists(slider_name(segment,0)):
                continue
            if profile and c.objExists(profile):
                raw.select(self.scene_address(profile),replace=True)
                specs=plan_skin_cage_sliders(slider_host.capture_slider_rows())
                slider_host.preflight_sliders(specs,creating=True,include_controller=False)
                self._cbd_ensure_partial_joints(specs)
                with slider_host.slider_sampling_scope():
                    for spec in specs:
                        if slider_host.create_slider(spec,include_controller=False):
                            created_specs.append(asdict(spec))
            elif segment!="middle":
                for index in range(5):
                    original=slider_name("middle",index)
                    if c.objExists(original):
                        target=slider_name(segment,index)
                        c.duplicate(original,name=target)
                        c.parent(target,joint)
                        c.setAttr(target+".tx",c.getAttr((joint if segment=="start" else child)+".tx"))
                        duplicate_sliders.append(target)
        y_only=not c.objExists(slider_name("middle",0))
        z_only=not c.objExists(slider_name("middle",1))
        orient=c.getAttr(joint+".jointOrient")[0]
        if self.original_driver_uses_opm():
            from maya.api import OpenMaya as om
            rotation=om.MTransformationMatrix(om.MMatrix(c.getAttr(joint+".offsetParentMatrix"))).rotation()
            orient=(rotation.x,rotation.y,rotation.z)
        positive=(y_only and orient[1]>0) or (z_only and orient[2]>0)
        for attr,value in (("rotYonly",y_only),("rotZonly",z_only),("singleAxisPositive",positive),("haveSkinCage",had_cage),("curvesBound",False)):
            self._cbd_store(attr,value)
        c.spaceLocator(name="tempLoc")
        pc=c.pointConstraint(parent,joint,child,"tempLoc")[0]
        aliases=c.pointConstraint(pc,query=True,weightAliasList=True)
        c.parent("tempLoc",joint)
        c.setAttr("tempLoc.r",0,0,0,type="float3")
        bindings=[]
        samples={0:((1,0,0),widths[0]),1:((3,1,0),widths[0]),2:((1,1,0),(widths[0]+widths[1])/2),
                 6:((0,1,1),(widths[1]+widths[2])/2),7:((0,1,3),(widths[1]+widths[2])/2),8:((0,0,1),widths[2])}
        for axis in "YZ":
            if (y_only and axis=="Y") or (z_only and axis=="Z"):continue
            for sign in (1,-1):
                index={("Y",1):2,("Y",-1):0,("Z",1):3,("Z",-1):1}[axis,sign]
                name="deformationCurve"+axis+str(1 if sign==1 else 2)
                points=[]
                c.setAttr(pc+".offset",0,0,0,type="float3")
                for ordinal in range(9):
                    if ordinal in (3,4,5):
                        pos=c.xform(slider_name(("start","middle","end")[ordinal-3],index),query=True,worldSpace=True,translation=True)
                    else:
                        weights,width=samples[ordinal]
                        for alias,weight in zip(aliases,weights):c.setAttr(pc+"."+alias,weight)
                        c.setAttr(pc+".offset"+axis,width*sign)
                        pos=c.xform("tempLoc",query=True,worldSpace=True,translation=True)
                        if ordinal<3 and side=="R":
                            if parent.endswith("_M") and name!="deformationCurveZ1":
                                c.setAttr(pc+"."+aliases[0],0);c.setAttr(pc+"."+aliases[1],1)
                                pos[0]=c.xform("tempLoc",query=True,worldSpace=True,translation=True)[0]
                            pos[0]=min(pos[0],0)
                    points.append(pos)
                c.curve(name=name,degree=3,point=points,knot=(0,0,0,1,2,3,4,5,6,6,6))
                c.setAttr(name+".dispCV",1)
                c.parent(name,"curveDeformationSetup")
                sliders=[slider_name(segment,index) for segment in ("start","middle","end")]
                bindings.append({"curve":name,"influences":[child,parent,*sliders],"weights":[parent]*3+sliders+[child]*3})
        self._cbd_store("advPyCurveBindings",json.dumps(bindings))
        self._cbd_store("advPyCreatedSliders",json.dumps(created_specs))
        self._cbd_store("advPyDuplicateSliders",json.dumps(duplicate_sliders))
        bind_commands=[]
        for row in bindings:
            skin=row["curve"]+"SC"
            bind_commands.append("skinCluster -toSelectedBones -mi 3 -dr 4 -rui false -n "+skin+" "+" ".join(row["influences"]+[row["curve"]])+";")
            bind_commands.extend("skinPercent -tv "+joint+" 1 "+skin+" "+row["curve"]+".cv["+str(index)+"];" for index,joint in enumerate(row["weights"]))
        self._cbd_store("bindCmd","".join(bind_commands))
        self._cbd_store("deleteSlidersCmd",";".join("select "+row["profile"]+";asDeleteSliders" for row in created_specs))
        if c.objExists("deformationCurveZ1") and c.objExists("deformationCurveY2"):
            c.reorder("deformationCurveZ1",relative=-1)
        c.delete("tempLoc")
        self.rebind_original_corrective_curves()
        c.select(clear=True)
        return {"curves":len(bindings),"single_axis":bool(y_only or z_only)}

    def _cbd_ensure_partial_joints(self, specs):
        # Primitive calls share this corrective transaction; do not open another undo chunk.
        from .maya_partial_joints import MayaPartialJointsHost
        from adv_py.core.partial_joints import plan_create_partial_joints
        c=self._cmds
        for joint in dict.fromkeys(row.deform_joint for row in specs):
            stem,side=self._original_restore_leaf(joint).rsplit("_",1)
            if c.objExists(stem+"Partial_"+side):continue
            c.select(joint,replace=True)
            host=MayaPartialJointsHost(namespace=self.namespace)
            plan=plan_create_partial_joints(host.capture_partial_candidates(),host.resolve_partial_selection(),
                count=1,include_controller=False,auto_bind=False,use_opm=host.partial_uses_opm())
            host.preflight_partial_scene(include_controller=False,multi=False,auto_bind=False)
            host._transaction_active=True
            try:
                for row in plan.specs:host.create_partial_joint(row)
            finally:host._transaction_active=False

    def unbind_original_corrective_curves(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        nodes=c.ls("deformationCurve*SC",type="skinCluster") or []
        if nodes:c.delete(nodes)
        c.setAttr("curveDeformationSetup.curvesBound",0)
        return len(nodes)

    def rebind_original_corrective_curves(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        if self._cbd_data("curvesBound"):
            raise ValueError("曲线已蒙皮，请先解除绑定")
        bindings=json.loads(self._cbd_data("advPyCurveBindings"))
        for row in bindings:
            skin=row["curve"]+"SC"
            bind_original_skin(c, (row["curve"],*row["influences"]), skin,
                               namespace=self.namespace)
            for ordinal,joint in enumerate(row["weights"]):
                c.skinPercent(skin,row["curve"]+".cv["+str(ordinal)+"]",transformValue=[(joint,1.)])
        c.setAttr("curveDeformationSetup.curvesBound",1)
        c.select(clear=True)
        return len(bindings)

    def animate_original_corrective_curves(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        if not self._cbd_data("curvesBound"):
            raise ValueError("请先重新绑定曲线")
        control=self._cbd_data("fkControl")
        self.set_original_corrective_fk(control)
        y_only=self._cbd_data("rotYonly");z_only=self._cbd_data("rotZonly")
        raw.currentTime(0)
        end=10 if y_only or z_only else 80
        raw.playbackOptions(minTime=0,animationStartTime=0,animationEndTime=end,maxTime=end)
        if y_only or z_only:
            axes=[axis for axis,enabled in (("y",y_only),("z",z_only)) if enabled]
            for axis in axes:c.setKeyframe(control+".r"+axis)
            raw.currentTime(10)
            for axis in axes:
                c.setAttr(control+".r"+axis,90 if self._cbd_data("singleAxisPositive") else -90)
                c.setKeyframe(control+".r"+axis)
        else:
            c.setKeyframe(control+".r")
            for frame,axis,value in ((10,"y",90),(20,"y",0),(30,"y",-90),(40,"y",0),(50,"z",90),(60,"z",0),(70,"z",-90),(80,"z",0)):
                raw.currentTime(frame);c.setAttr(control+".r"+axis,value);c.setKeyframe(control+".r")
        raw.refresh();raw.currentTime(5)
        return end

    def show_original_corrective_curve_mesh(self, *, original):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        raw.setAttr(self._cbd_data("mesh")+".v",int(original))
        if c.objExists("Corrective"):c.setAttr("Corrective.v",int(not original))

    def create_original_corrective_curve_mesh(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        mesh=self._cbd_data("mesh");control=self._cbd_data("fkControl")
        skins=raw.ls(raw.listHistory(mesh,pruneDagObjects=True) or [],type="skinCluster") or []
        if not skins:raise ValueError("来源网格没有 SkinCluster")
        current=raw.currentTime(query=True)
        raw.currentTime(0)
        try:
            for node in ("Corrective","deformationLoft","deformationMesh"):
                if c.objExists(node):c.delete(node)
            curves=[node for node in c.listRelatives("curveDeformationSetup",children=True) or []
                    if c.listRelatives(node,shapes=True,type="nurbsCurve")]
            c.loft(*curves,name="deformationLoft",ch=True,u=True,c=True,ar=True,d=3,ss=2,rn=False,po=0,rsn=True)
            loft_shape=c.listRelatives("deformationLoft",shapes=True)[0]
            c.setAttr(loft_shape+".curvePrecisionShaded",4)
            c.setAttr("deformationLoft.v",0);c.parent("deformationLoft","curveDeformationSetup")
            c.duplicate(mesh,name="Corrective")
            lock_original_transform_channels(c,"Corrective")
            c.setAttr("Corrective.v",1)
            c.parent("Corrective","curveDeformationSetup")
            for shape in c.listRelatives("Corrective",shapes=True,fullPath=True) or []:
                if c.getAttr(shape+".intermediateObject"):c.delete(shape)
            influences=raw.listConnections(skins[0]+".matrix",source=True,destination=False) or []
            with original_face_deformer_sets(c):
                skin=bind_original_skin(raw, (self.scene_address("Corrective"),*influences),
                    self.scene_address("CorrectiveSC"), namespace=self.namespace)
            self._cbd_rename_deformer_set(skin,"CorrectiveSCSet")
            raw.copySkinWeights(sourceSkin=skins[0],destinationSkin=skin,noMirror=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            c.nurbsToPoly("deformationLoft",name="deformationMesh",mnd=1,ch=1,f=3,pt=0,pc=200,chr=.9,ft=.01,mel=.001,d=.1,ut=1,un=3,vt=1,vn=3,uch=0,ucr=0,cht=0,es=0,ntr=0,mrt=0,uss=1)
            # curveDeformationObjects is an objectSet, so its DAG members live in Setup.
            c.parent("deformationMesh","curveDeformationSetup");c.setAttr("deformationMesh.v",0)
            with self._corrective_creation_context():
                raw.polySmooth(self.scene_address("deformationMesh"),mth=0,dv=2,bnr=1,c=1,kb=0,ksb=1,khe=0,kt=1,kmb=1,suv=1,peh=0,sl=1,dpe=1,ps=.1,ro=1,ch=1)
            c.sets([*curves,"deformationLoft","deformationMesh","Corrective"],add="curveDeformationObjects")
            with original_face_deformer_sets(c):
                wrap=self._original_bs_native_wrap("Corrective","deformationMesh",exclusive=False,name="CorrectiveWrap")
            if not wrap:raise RuntimeError("局部变形网格没有生成 Wrap")
            self._cbd_rename_deformer_set(self.scene_address("CorrectiveWrap"),"CorrectiveWrapSet")
            joint=self.original_corrective_joint_for_fk(control)
            raw.select(self.scene_address("Corrective"),replace=True)
            if joint.endswith("_R"):
                raw.polySelectConstraint(m=3,t=1,d=3,db=(0,999),da=(1,0,0),dp=(999,0,0))
                selected=raw.ls(selection=True,flatten=True) or []
                if selected:raw.sets(selected,remove=self.scene_address("CorrectiveWrapSet"))
            raw.select(self.scene_address("Corrective"),replace=True)
            radius=c.getAttr(joint+".fat")*c.getAttr(joint+".fatWidth")*6
            position=c.xform(control,query=True,worldSpace=True,translation=True)
            raw.polySelectConstraint(m=3,t=1,d=1,db=(0,radius),dp=position)
            near=raw.ls(selection=True,flatten=True) or []
            raw.polySelectConstraint(m=0)
            if near:raw.sets(near,remove=self.scene_address("CorrectiveSCSet"))
            all_vertices=set(raw.ls(self.scene_address("Corrective")+".vtx[*]",flatten=True) or [])
            outside=sorted(all_vertices-set(near))
            if outside:
                raw.sets(outside,remove=self.scene_address("CorrectiveWrapSet"))
                faces=raw.polyListComponentConversion(outside,toFace=True)
                deleted=c.polyDelFacet(faces,ch=True) or []
                if deleted:c.rename(deleted[0],"CorrectiveDeleteComponent")
            return {"mesh":"Corrective","radius":radius}
        finally:
            raw.polySelectConstraint(m=0)
            raw.currentTime(current)

    def _cbd_rename_deformer_set(self, deformer, name):
        raw=self._corrective_raw()
        sets=raw.listConnections(deformer+".message",source=False,destination=True,type="objectSet") or []
        if not sets:
            raise RuntimeError("原版变形器成员集合未创建："+deformer)
        self._cmds.rename(sets[0],name)

    def bake_original_corrective_curve_mesh(self, options):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        mesh=self._cbd_data("mesh");control=self._cbd_data("fkControl")
        raw.setAttr(mesh+".v",1)
        if c.objExists("CorrectiveDeleteComponent"):c.delete("CorrectiveDeleteComponent")
        y_only=self._cbd_data("rotYonly");z_only=self._cbd_data("rotZonly")
        positive=self._cbd_data("singleAxisPositive")
        axes=(False,False,True,True,True,True)
        if y_only or z_only:axes=(False,False,bool(y_only and positive),bool(y_only and not positive),bool(z_only and positive),bool(z_only and not positive))
        c.select(control,replace=True)
        result=self.bake_into_original_correctives(self.scene_address("Corrective"),mesh,axes,
            CorrectiveShapeOptions(not bool(y_only or z_only),options.use_soft_mods,options.mirror))
        self.cleanup_original_corrective_curves()
        return result

    def cleanup_original_corrective_curves(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        mesh=self._cbd_data("mesh");control=self._cbd_data("fkControl")
        slider_host=self._cbd_slider_host()
        for row in json.loads(self._cbd_data("advPyCreatedSliders")):
            row["indices"]=tuple(row["indices"])
            with slider_host.slider_delete_time_scope(), slider_host.slider_sampling_scope():
                slider_host.delete_slider(SkinCageSlider(**row))
            slider_host.finish_slider_delete()
        for node in json.loads(self._cbd_data("advPyDuplicateSliders")):
            if c.objExists(node):c.delete(node)
        if not self._cbd_data("haveSkinCage"):slider_host.delete_cage()
        members=c.sets("curveDeformationObjects",query=True) or []
        if members:c.delete(members)
        raw.setAttr(mesh+".v",1)
        animation=c.listConnections(control,source=True,destination=False,type="animCurveTA") or []
        if animation:c.delete(animation)
        c.setAttr(control+".r",0,0,0,type="float3")
        return {"cleaned":True}
