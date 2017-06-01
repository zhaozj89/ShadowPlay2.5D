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
else:
    from . import utils

import os
import math
import mathutils
import bpy
import bpy.utils.previews
from rna_prop_ui import PropertyPanel
from bpy.types import Panel, UIList

# this function sets all needed default settings
def default_settings():
    bpy.context.scene.world.use_sky_paper = True
    bpy.context.scene.world.use_sky_blend = True
    bpy.context.space_data.show_world = True


class InstanceGPencilStrokes(bpy.types.Operator):
    bl_idname = "gpencil.instance_gpencil_strokes"
    bl_label = "Instance Selected GPencil Strokes"
    bl_options = {"UNDO"}

    def invoke(self, context, event):
        gp = context.scene.grease_pencil
        if gp==None:
            return {"FINISHED"}


        # nlayer = len(gp.layers)
        # print('num of layers: ' + str(nlayer))
        # nframe = {}
        # for i in nlayer:
        #     nframe[i] = len(gp.layers[i].frames)
        #     print('num of frames: ' + str(nframe[i]))

        # https://blender.stackexchange.com/questions/48992/how-to-add-points-to-a-grease-pencil-stroke-or-make-new-one-with-python-script
        # https://blender.stackexchange.com/questions/24694/query-grease-pencil-strokes-from-python
        # omit all setups
        counter = 0
        active_strokes = gp.layers.active.active_frame.strokes
        for i in range(len(active_strokes)): # MUST use this pattern!
            old_stroke = active_strokes[i]
            if old_stroke.select==True:
                counter += 1
                # API: https://docs.blender.org/api/current/bpy.types.GPencilStrokes.html#bpy.types.GPencilStrokes.new
                new_stroke = active_strokes.new(old_stroke.colorname)

                new_stroke.draw_mode = '3DSPACE'
                #new_stroke.color = old_stroke.color
                new_stroke.points.add(count=len(old_stroke.points))

                points = old_stroke.points
                for i, point in enumerate(points):
                    points[i].co = old_stroke.points[i].co + mathutils.Vector((1, 1, 1))

        print('num of selected strokes: ' + str(counter))
        return {"FINISHED"}

# class My_GPENCIL_UL_palettecolor(UIList):
#     def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
#         # assert(isinstance(item, bpy.types.PaletteColor)
#         palcolor = item
#
#         if self.layout_type in {'DEFAULT', 'COMPACT'}:
#             if palcolor.lock:
#                 layout.active = False
#
#             split = layout.split(percentage=0.25)
#             row = split.row(align=True)
#             row.enabled = not palcolor.lock
#             row.prop(palcolor, "color", text="", emboss=palcolor.is_stroke_visible)
#             row.prop(palcolor, "fill_color", text="", emboss=palcolor.is_fill_visible)
#             split.prop(palcolor, "name", text="", emboss=False)
#
#             row = layout.row(align=True)
#             row.prop(palcolor, "lock", text="", emboss=False)
#             row.prop(palcolor, "hide", text="", emboss=False)
#
#         elif self.layout_type == 'GRID':
#             layout.alignment = 'CENTER'
#             layout.label(text="", icon_value=icon)

class EasyAnimationPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_easy_anime'
    bl_label = 'Easy Animation Panel'
    bl_context = 'objectmode'
    bl_category = 'Easy Animation'

    def draw(self, context):
        layout = self.layout
        view = context.space_data
        world = context.scene.world

        box = layout.box()
        box.label('Drawing')
        row = box.row()
        row.operator('gpencil.draw', text='Pencil', icon='GREASEPENCIL').mode = 'DRAW'
        row.operator('gpencil.draw', text='Eraser', icon='FORCE_CURVE').mode = 'ERASER'

        # box = layout.box()
        # box.label('Color Palette')
        # palette = context.active_gpencil_palette
        # if palette:
        #     # Palette colors
        #     row = box.row()
        #     col = row.column()
        #     if len(palette.colors) >= 2:
        #         color_rows = 2
        #     else:
        #         color_rows = 2
        #     col.template_list("My_GPENCIL_UL_palettecolor", "", palette, "colors", palette.colors, "active_index",
        #                       rows=color_rows)
        #
        #     col = row.column()
        #     sub = col.column(align=True)
        #     sub.operator("gpencil.palettecolor_add", icon='ZOOMIN', text="")
        #     sub.operator("gpencil.palettecolor_remove", icon='ZOOMOUT', text="")
        #
        # pcolor = palette.colors.active
        # if pcolor:
        #     self.draw_palettecolors(box, pcolor)

        box = layout.box()
        box.label('Constructing Scene')
        row = box.row()
        split = row.split(percentage=0.55)
        split.prop(view, "show_floor", text="Show Floor")
        split.prop(view, "show_axis_x", text="X", toggle=True)
        split.prop(view, "show_axis_y", text="Y", toggle=True)
        split.prop(view, "show_axis_z", text="Z", toggle=True)

        box.column().prop(view, 'show_world', text='Show World')
        box.column().prop(world, 'use_sky_paper', text='Use Skey Color')
        box.column().prop(world, 'use_sky_blend', text='Use Ground Color')
        row = box.row()
        row.column().prop(world, "horizon_color", text="Ground Color")
        row.column().prop(world, "zenith_color", text='Sky Color')

        column = box.column()
        column.operator('gpencil.editmode_toggle', text='Start Animation Mode', icon='POSE_DATA')
        column.operator('gpencil.select_border', text='Border Select', icon='BORDER_RECT')
        column.operator('gpencil.select_all', text='Deselect All', icon='CANCEL')
        column.operator('gpencil.instance_gpencil_strokes', text='Instance', icon='COPYDOWN')

        box = layout.box()
        box.label('Animating')
        column = box.column()
        column.operator('screen.animation_play', text='Play', icon='RIGHTARROW')


    # Draw palette colors
    # def draw_palettecolors(self, layout, pcolor):
    #     # color settings
    #     split = layout.split(percentage=0.5)
    #     split.active = not pcolor.lock
    #
    #     # Column 1 - Stroke
    #     col = split.column(align=True)
    #     col.enabled = not pcolor.lock
    #     col.prop(pcolor, "color", text="Stroke Color")
    #     col.prop(pcolor, "alpha", slider=True)
    #
    #     # Column 2 - Fill
    #     col = split.column(align=True)
    #     col.enabled = not pcolor.lock
    #     col.prop(pcolor, "fill_color", text="Filling Color")
    #     col.prop(pcolor, "fill_alpha", text="Opacity", slider=True)
    #
    #     # Options
    #     split = layout.split(percentage=0.5)
    #     split.active = not pcolor.lock

classes = (
InstanceGPencilStrokes,
EasyAnimationPanel,
)

def register():
    default_settings()
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    # bpy.utils.register_module(__name__)


def unregister():
    from bpy.utils import unregister_class
    for cls in classes:
        unregister_class(cls)
    # bpy.utils.unregister_module(__name__)


if __name__ == "__main__" :
    register()
