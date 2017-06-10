# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    "name": "Easy 2.5D Animation",
    "author": "Zhenjie Zhao",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View",
    "description": "Sketch-based 2.5D Animation Tools",
    "wiki_url": "http://hci.cse.ust.hk/index.html",
    "support": "TESTING", # must be capital
    "category": "Animation",
}


if "bpy" in locals():
    import importlib
    importlib.reload(utils)
    importlib.reload(ui_utils)
    importlib.reload(ops_utils)
    importlib.reload(mesh)
else:
    from . import utils, ui_utils, ops_utils, mesh

import os
import sys
import math
import mathutils
import bpy
import bpy.utils.previews
from rna_prop_ui import PropertyPanel

# from bpy.app.handlers import persistent
from bpy.types import (Panel, Operator, PropertyGroup, UIList, Menu)
from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       EnumProperty,
                       PointerProperty)


################################################################################
# Animation Part
################################################################################

class FollowingPath(bpy.types.Operator):
    bl_idname = 'animation.following_path'
    bl_label = 'Rigid Body Transformation'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None) and (context.scene.grease_pencil!=None)

    def invoke(self, context, event):
        strokes = context.scene.grease_pencil.layers.active.active_frame.strokes
        if strokes==None:
            return {'FINISHED'}

        anim_all_option_check = bpy.data.window_managers['WinMan'].key_points
        bpy.data.window_managers['WinMan'].key_points = True

        stroke = strokes[-1]
        sample_nb = len(stroke.points)
        step = 1

        context.scene.frame_start = 0
        for i in range(sample_nb):
            context.scene.frame_current = i
            context.active_object.location[0] = stroke.points[i].co[0]
            context.active_object.location[2] = stroke.points[i].co[2]
            bpy.ops.anim.keyframe_insert_menu(type='LocRotScale')

        context.scene.frame_end = sample_nb
        bpy.ops.screen.animation_play()

        bpy.data.window_managers['WinMan'].key_points = anim_all_option_check
        return {'FINISHED'}








################################################################################
# hairy stuff below for instance-based layout
################################################################################

class ObjectStore:
    current_object = None
    current_control = None
    current_object_array = []

# this is a good example to illustrate the usage of execute, invoke, and modal
# class Instancing(bpy.types.Operator):
#     bl_idname = "gpencil.instancing"
#     bl_label = "Instancing based on strokes"
#     bl_options = {"UNDO"}
#
#     @classmethod
#     def poll(cls, context):
#         return (context.area.type == "VIEW_3D")
#
#     def __init__(self):
#         print("Start Invoke")
#         # bpy.ops.gpencil.draw(mode='DRAW')
#
#     def __del__(self):
#         print("End Invoke")
#
#     # def execute(self, context):
#     #     print('I am execute')
#     #     return {'FINISHED'}
#     #
#     def modal(self, context, event):
#         if event.type == 'MOUSEMOVE':
#             # bpy.ops.gpencil.draw('INVOKE_DEFAULT',mode='DRAW')
#             # self.execute(context)
#             return {'RUNNING_MODAL'}
#         if event.type == 'LEFTMOUSE':
#             if event.value == 'RELEASE':
#         #     print('rightmouse')
#                 return {'FINISHED'}
#             elif event.type == 'PRESS':
#                 # bpy.ops.gpencil.draw('INVOKE_DEFAULT',mode='DRAW')
#                 return {'RUNNING_MODAL'}
#         return {'PASS_THROUGH'}
#
#     def invoke(self, context, event):
#         bpy.ops.gpencil.draw('INVOKE_DEFAULT',mode='DRAW')
#         print('I am invoke')
#         # self.execute(context)
#         context.window_manager.modal_handler_add(self)
#         return {'RUNNING_MODAL'}
#

class SelectObject(bpy.types.Operator):
    bl_idname = "instance.selectobject"
    bl_label = "Select Object"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.area.type == "VIEW_3D")

    # def __init__(self):
    #     # print("Start Invoke")
    #     # bpy.ops.gpencil.draw(mode='DRAW')
    #
    # def __del__(self):
        # print("End Invoke")

    # def execute(self, context):
    #     print('I am execute')
    #     return {'FINISHED'}
    #
    def modal(self, context, event):
        if event.type == 'LEFTMOUSE':
            if event.value == 'RELEASE':
                ObjectStore.current_object = context.active_object
                print(ObjectStore.current_object)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        bpy.ops.object.mode_set(mode='OBJECT')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class Instancing(bpy.types.Operator):
    bl_idname = "instance.instancing"
    bl_label = "Instancing based on strokes"
    bl_options = {"UNDO", 'REGISTER'}

    small_depth = 0

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil != None) and ((context.active_object!=None) or (ObjectStore.current_object!=None)) and (context.scene.grease_pencil.layers.active.active_frame.strokes[0]!=None)

    def invoke(self, context, event):
        gp = context.scene.grease_pencil
        strokes = gp.layers.active.active_frame.strokes

        if gp==None:
            return {'FINISHED'}
        if len(strokes)==0:
            return {'FINISHED'}
        stroke = strokes[-1]

        verts = []
        points = stroke.points
        for j in range(len(stroke.points)):
            verts.append(points[j].co)
            # print(points[j].co)

        sampling_nb = min(MySettings.instance_nb, len(verts))
        sampling_step = len(verts)/sampling_nb

        # bbx_min = sys.maxsize
        # bbx_max = -sys.maxsize
        # bbz_min = sys.maxsize
        # bbz_max = -sys.maxsize
        # for i in range(len(verts)):
        #     if verts[i].x < bbx_min:
        #         bbx_min = verts[i].x
        #     if verts[i].x > bbx_max:
        #         bbx_max = verts[i].x
        #     if verts[i].z < bbz_min:
        #         bbz_min = verts[i].z
        #     if verts[i].z > bbz_max:
        #         bbz_max = verts[i].z

        shift = []
        for i in range(sampling_nb):
            idx = int(i*sampling_step)
            if idx<len(verts):
                x = verts[idx].x# - verts[0].x
                z = verts[idx].z# - verts[0].z
                shift.append((x,z))

        # [obj, curve] = mesh.create_curve('test', verts)
        # curve.fill_mode = 'FULL'
        # curve.bevel_depth = 0.005
        # material = bpy.data.materials.new(name="Material")
        # material.diffuse_color[0] = 0.0
        # material.diffuse_color[1] = 0.0
        # material.diffuse_color[2] = 0.0
        # curve.materials.append(material)

        # for l in gp.layers:
        #     gp.layers.remove(l)
        #
        # ObjectStore.current_control = obj
        # print(ObjectStore.current_control)
        #
        # # the real algorithm goes here
        #
        instance_array = []
        for i in range(sampling_nb):
            model_obj = None
            if ObjectStore.current_object != None:
                model_obj = ObjectStore.current_object
            else:
                model_obj = context.active_object

            new_obj = model_obj.copy()
            new_obj.data = model_obj.data.copy()

            new_obj.location[0] = shift[i][0] #+ model_obj.location[0]
            new_obj.location[1] = model_obj.location[1] + Instancing.small_depth
            new_obj.location[2] = shift[i][1] #+ model_obj.location[2]
            new_obj.animation_data_clear()
            context.scene.objects.link(new_obj)
            instance_array.append(new_obj)

            Instancing.small_depth += 0.001 # prevent z shadowing

        ObjectStore.current_object_array = instance_array
        bpy.ops.object.select_all(action='DESELECT')

        return {'FINISHED'}

class ReArrangeLayout(bpy.types.Operator):
    bl_idname = 'layout.relayout'
    bl_label = 'Update the stroke to relayout the instances'
    bl_options = {'UNDO', 'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.scene.grease_pencil.layers.active.active_frame != None

    def invoke(self, context, event):
        gp = context.scene.grease_pencil
        scene = context.scene

        strokes = gp.layers.active.active_frame.strokes

        if gp==None:
            return {'FINISHED'}
        if len(strokes)==0:
            return {'FINISHED'}

        bpy.ops.object.mode_set(mode='GPENCIL_EDIT')
        scene.tool_settings.proportional_edit = 'CONNECTED'

        # for i in range(len)


        scene.tool_settings.proportional_size = 1

        bpy.ops.transform.translate()


        return {'FINISHED'}

class InstanceFinishing(bpy.types.Operator):
    bl_idname = 'instance.finish'
    bl_label = 'Cleaning Tasks'
    bl_options = {'UNDO'}

    # @classmethod
    # def poll(cls, context):
    #     return (ObjectStore.current_control != None) and ((ObjectStore.current_object!=None) or (context.active_object!=None))

    def invoke(self, context, event):
        # bpy.data.objects.remove(ObjectStore.current_control, do_unlink = True)
        # for i in range(len(bpy.data.curves)):
        #     bpy.data.curves.remove(bpy.data.curves[i], do_unlink=True)
        g = context.scene.grease_pencil
        for l in g.layers:
            g.layers.remove(l)

        # works
        # if ObjectStore.current_object!=None:
        #     ObjectStore.current_object.location[0] = ObjectStore.current_object.location[0]+0.01
        #     ObjectStore.current_object.location[0] = ObjectStore.current_object.location[0]-0.01
        # else:
        #     context.active_object.location[0] = context.active_object.location[0]+0.01
        #     context.active_object.location[0] = context.active_object.location[0]-0.01
        return {'FINISHED'}

class CGenerating(bpy.types.Operator):
    bl_idname = "gpencil.cgenerating"
    bl_label = "Generate Selected GPencil Strokes"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        gp = context.scene.grease_pencil
        return (gp != None) and (len(gp.layers['GP_Layer'].active_frame.strokes)!=0)

    def invoke(self, context, event):
        scene = context.scene
        gp = context.scene.grease_pencil

        sketch_strokes = gp.layers['GP_Layer'].active_frame.strokes
        construct_strokes = gp.layers['gpl_constructing'].active_frame.strokes

        position = []
        for i in range(len(construct_strokes)):
            construct_stroke = construct_strokes[i]
            for i, point in enumerate(construct_stroke.points):
                position.append(point.co)

        for k in range(len(position)):
            for i in range(len(sketch_strokes)):
                sketch_stroke = sketch_strokes[i]
                if sketch_stroke.select==True:
                    new_stroke = sketch_strokes.new(sketch_stroke.colorname)
                    new_stroke.draw_mode = '3DSPACE'
                    new_stroke.points.add(count=len(sketch_stroke.points))

                    points = sketch_stroke.points
                    for i, point in enumerate(points):
                        new_stroke.points[i].co = points[i].co + position[k]


        # nlayer = len(gp.layers)
        # print('num of layers: ' + str(nlayer))
        # nframe = {}
        # for i in nlayer:
        #     nframe[i] = len(gp.layers[i].frames)
        #     print('num of frames: ' + str(nframe[i]))

        # https://blender.stackexchange.com/questions/48992/how-to-add-points-to-a-grease-pencil-stroke-or-make-new-one-with-python-script
        # https://blender.stackexchange.com/questions/24694/query-grease-pencil-strokes-from-python
        # omit all setups
        # counter = 0
        # active_strokes = gp.layers.active.active_frame.strokes
        # for i in range(len(active_strokes)): # MUST use this pattern!
        #     old_stroke = active_strokes[i]
        #     if old_stroke.select==True:
        #         counter += 1
        #         # API: https://docs.blender.org/api/current/bpy.types.GPencilStrokes.html#bpy.types.GPencilStrokes.new
        #         new_stroke = active_strokes.new(old_stroke.colorname)
        #
        #         new_stroke.draw_mode = '3DSPACE'
        #         #new_stroke.color = old_stroke.color
        #         new_stroke.points.add(count=len(old_stroke.points))
        #
        #         points = old_stroke.points
        #         for i, point in enumerate(points):
        #             points[i].co = old_stroke.points[i].co + mathutils.Vector((1, 1, 1))
        return {"FINISHED"}


# for constructing scenes
class CStartRepetition(bpy.types.Operator):
    bl_idname = "gpencil.cstartrepetition"
    bl_label = "Start Repetition for Constructing"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        gp = context.scene.grease_pencil
        return (gp != None) and (gp.layers != None)

    def invoke(self, context, event):
        scene = context.scene
        gp = context.scene.grease_pencil

        gpl_constructing = gp.layers.new('gpl_constructing', set_active = True )
        # if gpl_constructing.frames:
        #     fr = gpl_constructing.active_frame
        # else:
        #     fr = gpl_constructing.frames.new(1)
        #
        # str = fr.strokes.new()
        # str.draw_mode = '3DSPACE'

        return {"FINISHED"}

class MySettings(PropertyGroup):
    instance_nb = 6
    b_use_projection = BoolProperty(name="Use Projection", description="", default=False)
    enum_mode = EnumProperty(name='Mode',
                             description='Different drawing mode',
                             items=[#('SKETCHING_MODE', "Sketching", ""),
                                    ('ANIMATION_MODE', "Animation", ""),
                                    ('CONSTRUCTING_MODE', 'Constructing', '')],
                             default='ANIMATION_MODE')
    # instance_nbr = IntProperty(name="Instancing Number", default=10)
    # instance_direction = EnumProperty(name='Instancing Direction',
    #                                   description='Instancing Direction',
    #                                   items=[('Left', "Left", ""),
    #                                          ('Right', 'Right', ''),
    #                                          ('Forward', 'Forward', ''),
    #                                          ('Backward', 'Backward', '')])


class Stroke2Mesh(bpy.types.Operator):
    bl_idname = 'gpencil.stroke2mesh'
    bl_label = 'Convert Stroke to Mesh'

    @classmethod
    def poll(cls, context):
        gp = context.scene.grease_pencil
        return (gp!=None) and (gp.layers.active.active_frame.strokes!=None)

    def invoke(self, context, event):
        scene = context.scene
        gp = context.scene.grease_pencil

        strokes = gp.layers.active.active_frame.strokes
        for i in range(len(strokes)):
            stroke = strokes[i]
            if stroke.select == True:
                # create a path
                verts = []
                points = stroke.points
                for j in range(len(stroke.points)):
                    verts.append(points[j].co)

                curve = mesh.create_curve('test', verts)
                curve.fill_mode = 'FULL'
                curve.bevel_depth = 0.005
                material = bpy.data.materials.new(name="Material")
                material.diffuse_color[0] = 0.0
                material.diffuse_color[1] = 0.0
                material.diffuse_color[2] = 0.0
                curve.materials.append(material)


                # create all triangles
                # create a new material for triangles
                material = bpy.data.materials.new(name="Material")
                triangles = stroke.triangles
                for j in range(len(triangles)):
                    v1 = triangles[j].v1
                    v2 = triangles[j].v2
                    v3 = triangles[j].v3
                    co1 = stroke.points[v1].co
                    co2 = stroke.points[v2].co
                    co3 = stroke.points[v3].co
                    obj = mesh.create_triangle('test', [co1, co2, co3])
                    obj.data.materials.append(material)
                    obj.show_transparent = True
                    obj.active_material.diffuse_color[0] = stroke.color.fill_color[0]
                    obj.active_material.diffuse_color[1] = stroke.color.fill_color[1]
                    obj.active_material.diffuse_color[2] = stroke.color.fill_color[2]
                    obj.active_material.alpha = stroke.color.fill_alpha
        return {"FINISHED"}

#####################################################################
## Panels
#####################################################################

class My_GPENCIL_UL_palettecolor(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # assert(isinstance(item, bpy.types.PaletteColor)
        palcolor = item

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if palcolor.lock:
                layout.active = False

            split = layout.split(percentage=0.25)
            row = split.row(align=True)
            row.enabled = not palcolor.lock
            row.prop(palcolor, "color", text="", emboss=palcolor.is_stroke_visible)
            row.prop(palcolor, "fill_color", text="", emboss=palcolor.is_fill_visible)
            split.prop(palcolor, "name", text="", emboss=False)

            row = layout.row(align=True)
            row.prop(palcolor, "lock", text="", emboss=False)
            row.prop(palcolor, "hide", text="", emboss=False)

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class My_GPENCIL_UL_layer(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # assert(isinstance(item, bpy.types.GPencilLayer)
        gpl = item

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if gpl.lock:
                layout.active = False

            row = layout.row(align=True)
            if gpl.is_parented:
                icon = 'BONE_DATA'
            else:
                icon = 'BLANK1'

            row.label(text="", icon=icon)
            row.prop(gpl, "info", text="", emboss=False)

            row = layout.row(align=True)
            row.prop(gpl, "lock", text="", emboss=False)
            row.prop(gpl, "hide", text="", emboss=False)
            row.prop(gpl, "unlock_color", text="", emboss=False)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)




class NotInterestingPanel1(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_notinerestingpanel1'
    bl_label = 'Not Interesting Panel 1'
    bl_context = 'objectmode'
    bl_category = 'StayTuned'

    def draw(self, context):
        layout = self.layout
        gp = context.scene.grease_pencil
        view = context.space_data
        world = context.scene.world
        box = layout.box()
        box.label('World Settings')
        row = box.row()
        split = row.split(percentage=0.55)
        split.prop(view, "show_floor", text="Show Floor")
        split.prop(view, "show_axis_x", text="X", toggle=True)
        split.prop(view, "show_axis_y", text="Y", toggle=True)
        split.prop(view, "show_axis_z", text="Z", toggle=True)

        box.column().prop(view, 'show_world', text='Show World')
        # box.column().prop(world, 'use_sky_paper', text='Use Skey Color')
        # box.column().prop(world, 'use_sky_blend', text='Use Ground Color')
        row = box.row()
        row.column().prop(world, "horizon_color", text="Ground Color")
        # row.column().prop(world, "zenith_color", text='Sky Color')

class NotInterestingPanel2(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_notinerestingpanel2'
    bl_label = 'Not Interesting Panel 2'
    bl_context = 'objectmode'
    bl_category = 'StayTuned'

    def draw(self, context):
        layout = self.layout
        gp = context.scene.grease_pencil

        box = layout.box()
        box.label('Color Palette')
        palette = context.active_gpencil_palette
        if palette != None:
            # Palette colors
            row = box.row()
            col = row.column()
            if len(palette.colors) >= 2:
                color_rows = 2
            else:
                color_rows = 2
            col.template_list("My_GPENCIL_UL_palettecolor", "", palette, "colors", palette.colors, "active_index",
                              rows=color_rows)

            col = row.column()
            sub = col.column(align=True)
            sub.operator("gpencil.palettecolor_add", icon='ZOOMIN', text="")
            sub.operator("gpencil.palettecolor_remove", icon='ZOOMOUT', text="")

            pcolor = palette.colors.active
            if pcolor:
                self.draw_palettecolors(box, pcolor)

        box = layout.box()
        box.label('Painting Layers')
        if gp!=None:
            if len(gp.layers) >= 2:
                layer_rows = 2
            else:
                layer_rows = 2
            box.template_list("My_GPENCIL_UL_layer", "", gp, "layers", gp.layers, "active_index", rows=layer_rows)

    # Draw palette colors
    def draw_palettecolors(self, layout, pcolor):
        # color settings
        split = layout.split(percentage=0.5)
        split.active = not pcolor.lock

        # Column 1 - Stroke
        col = split.column(align=True)
        col.enabled = not pcolor.lock
        col.prop(pcolor, "color", text="Stroke Color")
        col.prop(pcolor, "alpha", slider=True)

        # Column 2 - Fill
        col = split.column(align=True)
        col.enabled = not pcolor.lock
        col.prop(pcolor, "fill_color", text="Filling Color")
        col.prop(pcolor, "fill_alpha", text="Opacity", slider=True)

        # Options
        split = layout.split(percentage=0.5)
        split.active = not pcolor.lock


class MyUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_easy_animation'
    bl_label = 'Easy Animation'
    bl_context = 'objectmode'
    bl_category = 'Easy Animation'



    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label('Mode')
        my_settings = scene.my_settings
        box.prop(my_settings, 'enum_mode', text='')

        # if my_settings.enum_mode == 'SKETCHING_MODE':
        #     box = layout.box()
        #     box.label('Drawing')
        #     row = box.row()
        #     row.operator('gpencil.draw', text='Pencil', icon='GREASEPENCIL').mode = 'DRAW'
        #     row.operator('gpencil.draw', text='Eraser', icon='FORCE_CURVE').mode = 'ERASER'

        if my_settings.enum_mode == 'CONSTRUCTING_MODE':
            box = layout.box()
            box.label('Layout')
            box.prop(context.active_object, 'location', text='Object Location')

            box = layout.box()
            box.label('Instancing')
            column = box.column()
            column.operator('instance.selectobject', text='Select', icon='GREASEPENCIL')
            column.separator()
            column.operator('gpencil.draw', text='Drawing', icon='GREASEPENCIL').mode = 'DRAW'
            column.prop(my_settings, 'b_use_projection', text='Projection')
            column.operator('instance.instancing', text='Instancing', icon='GREASEPENCIL')
            # column.separator()
            # column.prop(my_settings, 'instance_nbr', text='Instancing Number')
            # column.prop(my_settings, 'instance_direction', text='Direction')
            # column.operator('instance.instancing', text='Updating', icon='GREASEPENCIL')

            column.separator()
            column.operator('layout.relayout', text='Relayout', icon='GREASEPENCIL')
            column.separator()
            column.operator('instance.finish', text='Clean Strokes', icon='GREASEPENCIL')


            # TODO, this is a rather bad design, replace it later
            # row.operator('gpencil.editmode_toggle', text='Start Constructing Mode', icon='POSE_DATA')
            # row.operator('gpencil.select_border', text='Border Select', icon='BORDER_RECT')
            # row.operator('gpencil.select_all', text='Deselect All', icon='CANCEL')
            #
            # column = box.column()
            # column.operator('gpencil.stroke2mesh', text='Object', icon='COPYDOWN')
            #
            # column = box.column()
            # column.operator('gpencil.cstartrepetition', text='Start', icon='COPYDOWN')
            # column.operator('gpencil.draw', text='Draw', icon='GREASEPENCIL').mode = 'DRAW'
            # column.operator('gpencil.cgenerating', text='Generate', icon='COPYDOWN')

        elif my_settings.enum_mode == 'ANIMATION_MODE':
            box = layout.box()
            box.label('Animating')
            row = box.row()
            if not scene.use_preview_range:
                row.prop(scene, "frame_start", text="Start")
                row.prop(scene, "frame_end", text="End")
            else:
                row.prop(scene, "frame_preview_start", text="Start")
                row.prop(scene, "frame_preview_end", text="End")
            column = box.column()
            column.operator('screen.animation_play', text='Play', icon='RIGHTARROW')
            column.separator()
            column.operator('animation.following_path', text='Following Path', icon='GREASEPENCIL')


# class DirectionPieMenu(Menu):
#     bl_idname = 'OBJECT_MT_direction_pie_menu'
#     bl_label = "Select Direction"
#
#     def draw(self, context):
#         layout = self.layout
#
#         pie = layout.menu_pie()
#         pie.operator_enum("mesh.select_mode", "type")

class CameraUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_camera_path'
    bl_label = 'Camera Path'
    bl_context = 'objectmode'
    bl_category = 'Easy Animation'

    def draw(self, context):
        layout = self.layout
        camera = context.scene.objects['Camera']

        box = layout.box()
        box.prop(camera, 'location', text='')


def register():
    # from bpy.utils import register_class
    # for cls in classes:
    #     register_class(cls)
    # bpy.utils.register_class(DirectionPieMenu)
    # wm = bpy.context.window_manager
    # km = wm.keyconfigs.addon.keymaps.new(name="Object Mode" )
    # kmi = km.keymap_items.new('wm.call_menu_pie', 'SPACE', 'PRESS').properties.name='OBJECT_MT_direction_pie_menu'

    bpy.utils.register_module(__name__)
    # bpy.app.handlers.scene_update_pre.append(setIt)
    # bpy.app.handlers.load_post.append(setIt)
    bpy.types.Scene.my_settings = PointerProperty(type=MySettings)


def unregister():
    # from bpy.utils import unregister_class
    # for cls in classes:
    #     unregister_class(cls)
    # bpy.utils.unregister_class(DirectionPieMenu)
    bpy.utils.unregister_module(__name__)
    # bpy.app.handlers.load_post.remove(setIt)
    del bpy.types.Scene.my_settings

if __name__ == "__main__" :
    register()
