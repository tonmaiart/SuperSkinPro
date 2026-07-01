"""Weight Transfer operators — moved from operators/ops_tools.py."""

import bpy
import mathutils


class OBJECT_OT_mw_copy_skin_weight_maya(bpy.types.Operator):
    """Copy skin weights with perfect axial Linear Interpolation based on group centers"""
    bl_idname = "object.mw_copy_skin_weight_maya"
    bl_label = "Copy Skin Weight (Maya Style)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2 and all(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        non_active_objs = [obj for obj in selected_objs if obj != context.active_object]
        source_obj = next((obj for obj in non_active_objs if any(m.type == 'ARMATURE' and m.object for m in obj.modifiers)), None)
        if not source_obj:
            source_obj = next((obj for obj in non_active_objs if len(obj.vertex_groups) >= 2), None)
        if not source_obj and non_active_objs:
            source_obj = non_active_objs[0]

        if not source_obj:
            self.report({'ERROR'}, "ไม่สามารถระบุวัตถุ Source (Proxy Mesh) ได้!")
            return {'CANCELLED'}

        target_objs = [obj for obj in selected_objs if obj != source_obj]
        source_vg_names = [vg.name for vg in source_obj.vertex_groups]

        if len(source_vg_names) < 2:
            self.report({'ERROR'}, "Proxy Mesh ต้องมี Vertex Group อย่างน้อย 2 กลุ่มขึ้นไป")
            return {'CANCELLED'}

        source_armature = next((m.object for m in source_obj.modifiers if m.type == 'ARMATURE' and m.object), None)
        if not source_armature:
            self.report({'ERROR'}, f"Source '{source_obj.name}' ไม่มีกระดูกผูกอยู่!")
            return {'CANCELLED'}

        src_mesh = source_obj.data
        matrix_world_src = source_obj.matrix_world

        vg_start_idx = source_obj.vertex_groups[source_vg_names[0]].index
        vg_end_idx = source_obj.vertex_groups[source_vg_names[-1]].index

        start_coords = []
        end_coords = []

        for v in src_mesh.vertices:
            world_co = matrix_world_src @ v.co
            for g in v.groups:
                if g.group == vg_start_idx and g.weight > 0.1:
                    start_coords.append(world_co)
                if g.group == vg_end_idx and g.weight > 0.1:
                    end_coords.append(world_co)

        if start_coords:
            A = sum(start_coords, mathutils.Vector((0, 0, 0))) / len(start_coords)
        else:
            A = matrix_world_src @ src_mesh.vertices[0].co

        if end_coords:
            B = sum(end_coords, mathutils.Vector((0, 0, 0))) / len(end_coords)
        else:
            B = matrix_world_src @ src_mesh.vertices[-1].co

        AB = B - A
        ab_length_sq = AB.length_squared

        if ab_length_sq == 0:
            self.report({'ERROR'}, "ระยะแกนหน้าตัดเป็น 0 คำนวณไม่ได้!")
            return {'CANCELLED'}

        for target in target_objs:
            target.vertex_groups.clear()
            for name in source_vg_names:
                target.vertex_groups.new(name=name)

            arm_mod = next((m for m in target.modifiers if m.type == 'ARMATURE'), None)
            if not arm_mod:
                arm_mod = target.modifiers.new(name="Armature", type='ARMATURE')
            arm_mod.object = source_armature

            arm_mod.use_deform_preserve_volume = True

            target_vg_start = target.vertex_groups[source_vg_names[0]]
            target_vg_end = target.vertex_groups[source_vg_names[-1]]

            matrix_world_tgt = target.matrix_world

            context.view_layer.objects.active = target

            for v in target.data.vertices:
                P = matrix_world_tgt @ v.co

                AP = P - A
                t = AP.dot(AB) / ab_length_sq
                t = max(0.0, min(1.0, t))

                weight_end = t
                weight_start = 1.0 - t

                target_vg_start.add([v.index], weight_start, 'REPLACE')
                target_vg_end.add([v.index], weight_end, 'REPLACE')

            target.data.update()

        context.view_layer.objects.active = source_obj

        self.report({'INFO'}, "Successfully applied accurate center-aligned linear weights!")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_mw_copy_skin_weight_maya)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_mw_copy_skin_weight_maya)
