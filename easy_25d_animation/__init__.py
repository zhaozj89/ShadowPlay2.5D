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
    "name": "Play2.5D",
    "author": "Zhenjie Zhao",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View",
    "description": "Sketch-based 2.5D Animation Tools",
    "wiki_url": "http://hci.cse.ust.hk/index.html",
    "support": "TESTING",
    "category": "Animation",
}


if "bpy" in locals():
    import importlib
    importlib.reload(opengl_utils)
#     importlib.reload(utils)
#     importlib.reload(ui_utils)
#     importlib.reload(ops_utils)
#     importlib.reload(mesh)
#     importlib.reload(brushes)
else:
    from . import opengl_utils
#     from . import utils, ui_utils, ops_utils, mesh, brushes

import os
import sys
import math
import mathutils
from mathutils import Vector, Matrix
import bpy
from bgl import *
import bpy.utils.previews
import bmesh
from rna_prop_ui import PropertyPanel
from bpy.app.handlers import persistent
from bpy.types import (Panel, Operator, PropertyGroup, UIList, Menu)
from bpy.props import (StringProperty, BoolProperty, IntProperty, FloatProperty, EnumProperty, PointerProperty)
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d

# depends on sklean
import numpy as np
import random
import copy
from numpy import linalg as LA
from sklearn.decomposition import PCA

################################################################################
# Global
################################################################################

class MySettingsProperty(PropertyGroup):
    enum_mode = EnumProperty(name='Mode',
                             description='Different drawing mode',
                             items=[('LIGHTING_MODE','Lighting',''),
                                    ('ANIMATION_MODE','Animation',''),
                                    ('CONSTRUCTING_MODE','Construction',''),
                                    ('IMPORT_MODE','Import','')],
                             default='IMPORT_MODE')

class MySettingsOperatorReset(bpy.types.Operator):
    bl_idname = 'mysettings.reset'
    bl_label = 'MySettings Reset'
    bl_options = {'REGISTER','UNDO'}

    def invoke(self, context, event):
        bpy.ops.wm.read_homefile()
        bpy.ops.wm.addon_refresh()
        return {'FINISHED'}

class MySettingsOperatorRender(bpy.types.Operator):
    bl_idname = 'mysettings.render'
    bl_label = 'MySettings Render'
    bl_options = {'REGISTER','UNDO'}

    def invoke(self, context, event):
        scene = context.scene
        scene.frame_start = 1
        scene.frame_end = context.scene.current_frame+context.scene.frame_block_nb-1

        bpy.ops.render.render(animation=True)
        return {'FINISHED'}

################################################################################
# Construction
################################################################################

# Operator
class ConstructionOperatorInterpreteContour(bpy.types.Operator):
    bl_idname = "construction.interpret_contour"
    bl_label = "Interprete contour stroke"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil!=None)

    def invoke(self, context, event):
        gp = context.scene.grease_pencil

        obj = context.active_object
        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes
        if (strokes==None) or (len(strokes)<1):
            return {'FINISHED'}

        contour_stroke = strokes[-1]

        camera = context.scene.camera
        if camera==None:
            return {'FINISHED'}

        render = context.scene.render
        modelview_matrix = camera.matrix_world.inverted()
        projection_matrix = camera.calc_matrix_camera(render.resolution_x,render.resolution_y,render.pixel_aspect_x,render.pixel_aspect_y)

        M = projection_matrix*modelview_matrix

        points_image = []
        np_M = np.array(M)
        for point in contour_stroke.points:
            co = list(point.co)
            co.append(1.0)
            co = np.array(co)
            res = np.dot(np_M, co)
            res /= res[3]
            points_image.append(res)

        if gp.palettes:
            gp_palette = gp.palettes.active
        else:
            gp_palette = gp.palettes.new('mypalette')

        if 'black' in gp_palette.colors:
            black_col = gp_palette.colors['black']
        else:
            black_col = gp_palette.colors.new()
            black_col.name = 'black'
            black_col.color = (0.0,0.0,0.0)

        M.invert()
        np_M = np.array(M)
        res_points = []
        for i, point in enumerate(points_image):
            first = np.dot(np_M[:,0:2], point[0:2]) + np_M[:,3]
            second = np_M[:,2]
            d = -first[2]/second[2]
            res = first + d*second
            res /= res[3]
            res_points.append(res[0:3])

        points_nb = min(10, len(res_points))

        strokes.remove(contour_stroke)
        stroke = af.strokes.new(colorname=black_col.name)
        stroke.draw_mode = '3DSPACE'
        stroke.line_width = 6
        stroke.points.add(count = points_nb)

        if len(res_points)<points_nb:
            for idx in range(points_nb):
                stroke.points[idx].co = res_points[idx]
        else:
            for idx in range(points_nb):
                stroke.points[idx].co = res_points[idx*int(len(res_points)/points_nb)]

        return {'FINISHED'}

class ConstructionOperatorGenerateSurface(bpy.types.Operator):
    bl_idname = "construction.generate_surface"
    bl_label = "Generate Surface"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil!=None)

    def invoke(self, context, event):
        gp = context.scene.grease_pencil

        obj = context.active_object
        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes
        if (strokes==None) or (len(strokes)<1):
            return {'FINISHED'}

        contour_stroke = strokes[-1]
        contour_stroke.select = True
        bpy.ops.gpencil.convert(type='PATH')
        strokes.remove(contour_stroke)
        objs = bpy.data.objects

        select_obj = None
        for obj in objs:
            if obj.name[0:8]=='GP_Layer':
                select_obj = obj
                break

        if select_obj==None:
            return {'FINISHED'}

        bpy.context.scene.objects.active = select_obj
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.convert(target='MESH')

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='TOGGLE')

        bpy.ops.view3d.edit_mesh_extrude_move_normal()

        return {'FINISHED'}

class ConstructionOperatorOnSurface(bpy.types.Operator):
    bl_idname = "construction.on_surface"
    bl_label = "Grease pencil on surface or 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        bpy.ops.object.mode_set(mode='OBJECT')
        if context.scene.on_surface==True:
            context.scene.tool_settings.gpencil_stroke_placement_view3d='CURSOR'
        else:
            context.scene.tool_settings.gpencil_stroke_placement_view3d='SURFACE'

        context.scene.on_surface = not context.scene.on_surface
        return {'FINISHED'}

class ConstructionOperatorInstancing(bpy.types.Operator):
    bl_idname = "construction.instancing"
    bl_label = "Instancing"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil!=None) and (context.active_object!=None)

    def invoke(self, context, event):
        gp = context.scene.grease_pencil

        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes

        try:
            stroke = strokes[-1]
        except IndexError:
            pass
        else:
            verts = []
            points = stroke.points
            for i in range(len(stroke.points)):
                verts.append(points[i].co)

            sampling_nb = min(context.scene.instance_nb, len(verts))
            sampling_step = len(verts)/sampling_nb

            shift = []
            for i in range(sampling_nb):
                idx = int(i*sampling_step)
                if idx<len(verts):
                    x = verts[idx].x
                    y = verts[idx].y
                    z = verts[idx].z
                    shift.append((x,y,z))

            model_obj = context.active_object

            for i in range(sampling_nb):
                new_obj = model_obj.copy()
                if (model_obj.animation_data!=None) and (model_obj.animation_data.action!=None):
                    model_fcurve_x = model_obj.animation_data.action.fcurves[0]
                    model_fcurve_y = model_obj.animation_data.action.fcurves[1]
                    model_fcurve_z = model_obj.animation_data.action.fcurves[2]
                    N = len(model_fcurve_x.keyframe_points)

                    new_obj.animation_data_create()
                    new_obj.animation_data.action = bpy.data.actions.new(name="LocationAnimation")

                    fcurve_x = new_obj.animation_data.action.fcurves.new(data_path='location', index=0)
                    fcurve_y = new_obj.animation_data.action.fcurves.new(data_path='location', index=1)
                    fcurve_z = new_obj.animation_data.action.fcurves.new(data_path='location', index=2)

                    x_pre = 0
                    z_pre = 0

                    for k in range(N):
                        frame_idx = model_fcurve_x.keyframe_points[k].co[0]
                        if k==0:
                            x_cur = shift[i][0]
                            y_cur = shift[i][1]
                            z_cur = shift[i][2]
                        else:
                            x_cur = model_fcurve_x.keyframe_points[k].co[1]+x_pre2-x_pre
                            y_cur = model_fcurve_y.keyframe_points[k].co[1]+y_pre2-y_pre
                            z_cur = model_fcurve_z.keyframe_points[k].co[1]+z_pre2-z_pre

                        fcurve_x.keyframe_points.insert(frame_idx, x_cur+random.gauss(0, 0.05), {'FAST'})
                        fcurve_y.keyframe_points.insert(frame_idx, y_cur+random.gauss(0, 0.05), {'FAST'})
                        fcurve_z.keyframe_points.insert(frame_idx, z_cur+random.gauss(0, 0.05), {'FAST'})

                        x_pre = model_fcurve_x.keyframe_points[k].co[1]
                        y_pre = model_fcurve_y.keyframe_points[k].co[1]
                        z_pre = model_fcurve_z.keyframe_points[k].co[1]

                        x_pre2 = x_cur
                        y_pre2 = y_cur
                        z_pre2 = z_cur
                else:
                    new_obj.location[0] = shift[i][0]
                    new_obj.location[1] = shift[i][1]
                    new_obj.location[2] = shift[i][2]
                context.scene.objects.link(new_obj)

            bpy.ops.object.select_all(action='DESELECT')
        return {'FINISHED'}

class ConstructionOperatorCleanStrokes(bpy.types.Operator):
    bl_idname = 'layout.cleanstrokes'
    bl_label = 'Cleaning strokes'
    bl_options = {'REGISTER','UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil != None)

    def invoke(self, context, event):
        g = context.scene.grease_pencil
        for l in g.layers:
            if l.active_frame!=None:
                for s in l.active_frame.strokes:
                    l.active_frame.strokes.remove(s)
        return {'FINISHED'}

################################################################################
# Animation
################################################################################

# Operator
# https://wiki.blender.org/index.php/Dev:IT/2.5/Py/Scripts/Cookbook/Code_snippets/Armatures
class AnimationOperatorBone(bpy.types.Operator):
    bl_idname = 'animation.animation_bone'
    bl_label = 'Animation Bone'
    bl_options = {'REGISTER','UNDO'}

    def _createRig(self, name, origin, boneTable):
        bpy.ops.object.add(type='ARMATURE', enter_editmode=True, location=Vector((0,0,0)))
        ob = bpy.context.object
        ob.show_x_ray = True
        ob.name = name
        amt = ob.data
        amt.draw_type = 'STICK'
        amt.name = name+'Amt'
        amt.show_axes = True

        # Create bones
        bpy.ops.object.mode_set(mode='EDIT')
        for (bname, pname, head, tail) in boneTable:
            bone = amt.edit_bones.new(bname)
            if pname:
                parent = amt.edit_bones[pname]
                bone.use_connect = False

            bone.head = head
            bone.tail = tail
        bpy.ops.object.mode_set(mode='OBJECT')
        return ob

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None) and (context.scene.grease_pencil!=None)

    def invoke(self, context, event):
        self.obj = context.active_object
        gp = context.scene.grease_pencil

        if gp.layers==None:
            return {'FINISHED'}
        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes

        if (strokes==None):
            return {'FINISHED'}

        pre_name = None
        boneTable = []
        for idx, stroke in enumerate(strokes):
            points = stroke.points
            if len(points)==0:
                continue
            else:
                tail = points[-1].co
                head = points[0].co

            current_name = 'bone' + str(idx)
            item = (current_name, pre_name, head, tail)
            boneTable.append(item)
            pre_name = current_name

        bent = self._createRig(self.obj.name, self.obj.location, boneTable)

        self.obj.select = True
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")

        for stroke in strokes:
            strokes.remove(stroke)
        return {'FINISHED'}

class AnimationOperatorBoneDeform(bpy.types.Operator):
    bl_idname = 'animation.bone_deform'
    bl_label = 'Animation Bone Deform'
    bl_options = {'REGISTER','UNDO'}

    def __init__(self):
        print('start')
        self.counter = 0
        self.left_pressed = False
        bpy.ops.object.mode_set(mode='POSE')

    # potential bug, be careful about it
    def __del__(self):
        print('delete')
        # bpy.ops.object.mode_set(mode='OBJECT')

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None) and (type(context.active_object.data)==bpy.types.Armature)

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                x, y = event.mouse_region_x, event.mouse_region_y
                loc = region_2d_to_location_3d(context.region, context.space_data.region_3d, (x, y), bpy.context.scene.cursor_location)
                self.pre_loc = loc

                bones = context.active_object.pose.bones
                min_dist = sys.float_info.max
                for bone in bones:
                    dist = LA.norm(np.array((loc-bone.center)), 2)
                    if dist<min_dist:
                        min_dist = dist
                        self.bone = bone
                        # bone.select = True
                self.left_pressed = True
                return {'RUNNING_MODAL'}

            if event.value == 'RELEASE':
                return {'FINISHED'}
        if (event.type == 'MOUSEMOVE') and (self.left_pressed==True):
            x, y = event.mouse_region_x, event.mouse_region_y
            loc = region_2d_to_location_3d(context.region, context.space_data.region_3d, (x, y), bpy.context.scene.cursor_location)

            self.bone.rotation_mode = 'XYZ'
            axis = 'Z'
            vec1 = loc - self.bone.head
            vec2 = self.pre_loc - self.bone.head

            angle = vec1.angle(vec2)

            vec3 = self.bone.head - bpy.data.objects['Camera'].location

            v1 = np.cross(np.array(vec1), np.array(vec2))

            sign = np.dot(v1, vec3)
            if sign<0:
                angle = -angle

            self.bone.rotation_euler.rotate_axis(axis, angle)

            self.pre_loc = loc

            self.bone.keyframe_insert(data_path="rotation_euler" ,frame=self.frames[self.counter])

            if self.counter < context.scene.frame_block_nb-1:
                self.counter+=1

            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        self.frames = [context.scene.current_frame+i for i in range(context.scene.frame_block_nb)]
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class AnimationOperatorARAP(bpy.types.Operator):
    bl_idname = 'animation.animation_arap'
    bl_label = 'Animation ARAP'
    bl_options = {'REGISTER','UNDO'}

    def __init__(self):
        print("Start Invoke")
        self.cp_before = []
        self.cp_after = []
        self.seleted_cp = [None]
        self.leftmouse_pressed = False

    def __del__(self):
        print("End Invoke")

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None) and (context.scene.grease_pencil!=None)

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                x, y = event.mouse_region_x, event.mouse_region_y
                loc = region_2d_to_location_3d(context.region, context.space_data.region_3d, (x, y), bpy.context.scene.cursor_location)
                if len(self.cp_after)<=0:
                    return {'FINISHED'}
                min_dist = sys.float_info.max

                matrix_object = self.obj.matrix_world.inverted()
                loc_obj = np.array(matrix_object * loc)

                for co in self.cp_after:
                    cp_obj = np.array(matrix_object * co)
                    dist = LA.norm(np.array((loc_obj[0:2]-cp_obj[0:2])), 2)
                    if dist<=min_dist:
                        self.seleted_cp[0] = co
                        min_dist = dist

                if min_dist<0.05:
                    self.leftmouse_pressed = True
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE':
                return {'FINISHED'}
        if (event.type == 'MOUSEMOVE') and (self.leftmouse_pressed==True):
            if self.seleted_cp[0]==None:
                return {'RUNNING_MODAL'}

            x, y = event.mouse_region_x, event.mouse_region_y
            loc = region_2d_to_location_3d(context.region, context.space_data.region_3d, (x, y), bpy.context.scene.cursor_location)

            self.seleted_cp[0][0] = loc[0]
            self.seleted_cp[0][1] = loc[1]
            self.seleted_cp[0][2] = loc[2]

            # Image Deformation Using Moving Least Squares
            ncp = len(self.cp_before)
            assert(ncp==len(self.cp_after))
            matrix_object = self.obj.matrix_world.inverted()

            # compute q
            q = []
            for i in range(ncp):
                cp_obj = matrix_object * self.cp_after[i]
                q.append(np.array(cp_obj[0:2]))

            # compute q_star
            q_star = {}
            for vert in self.mesh.vertices:
                idx = vert.index
                numerator = np.zeros(2)
                w_sum = 0
                for i in range(ncp):
                    numerator += (self.weight_list[i][idx]*q[i])
                    w_sum += self.weight_list[i][idx]
                q_star[idx] = numerator / w_sum

            # compute new positions
            for vert in self.mesh.vertices:
                idx = vert.index
                f_hat = np.zeros(2)
                for i in range(ncp):
                    q_hat = q[i] - q_star[idx]
                    f_hat += np.dot(q_hat, self.A_list[i][idx])
                f_hat /= self.mu[idx]
                f_hat = f_hat/LA.norm(f_hat, 2)
                vco_new = self.res_length[idx]*f_hat + q_star[idx]
                self.mesh.vertices[idx].co[0] = vco_new[0]
                self.mesh.vertices[idx].co[1] = vco_new[1]

                if self.fcurve_x[vert.index]==None:
                    self.fcurve_x[vert.index] = self.action.fcurves.new('vertices[%d].co'%vert.index, index=0)
                self.fcurve_x[vert.index].keyframe_points.insert(self.frames[self.counter], vco_new[0], {'FAST'})
                if self.fcurve_y[vert.index]==None:
                    self.fcurve_y[vert.index] = self.action.fcurves.new('vertices[%d].co'%vert.index, index=1)
                self.fcurve_y[vert.index].keyframe_points.insert(self.frames[self.counter], vco_new[1], {'FAST'})

            if self.counter < context.scene.frame_block_nb-1:
                self.counter+=1
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        gp = context.scene.grease_pencil

        if gp.layers==None:
            return {'FINISHED'}
        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes

        if (strokes==None):
            return {'FINISHED'}

        cp_after = []
        for stroke in strokes:
            points = stroke.points
            if len(points)==0:
                continue
            cp = [0,0,0]
            for point in points:
                cp[0] += point.co[0]
                cp[1] += point.co[1]
                cp[2] += point.co[2]
            cp[0] /= len(points)
            cp[1] /= len(points)
            cp[2] /= len(points)

            cp_after.append(cp)

        for stroke in strokes:
            strokes.remove(stroke)

        if gp.palettes:
            gp_palette = gp.palettes.active
        else:
            gp_palette = gp.palettes.new('mypalette')

        if 'black' in gp_palette.colors:
            black_col = gp_palette.colors['black']
        else:
            black_col = gp_palette.colors.new()
            black_col.name = 'black'
            black_col.color = (0.0,0.0,0.0)

        for cp in cp_after:
            stroke = af.strokes.new(colorname=black_col.name)
            stroke.draw_mode = '3DSPACE'
            stroke.line_width = 10
            stroke.points.add(count = 1)
            stroke.points[0].co = cp
            self.cp_after.append(stroke.points[0].co)

        self.cp_before = copy.deepcopy(self.cp_after)

        self.obj = context.active_object
        self.mesh = self.obj.data

        # ADD animation data
        self.counter = 0
        self.frames = [context.scene.current_frame+i for i in range(context.scene.frame_block_nb)]
        if self.mesh.animation_data==None:
            self.mesh.animation_data_create()
            action = bpy.data.actions.new(name='ARAP_Animation')
            self.mesh.animation_data.action = action

        self.fcurve_x = {}
        self.fcurve_y = {}
        for i in range(len(self.mesh.vertices)):
            self.fcurve_x[i] = None
            self.fcurve_y[i] = None
        self.action = self.mesh.animation_data.action

        # Image Deformation Using Moving Least Squares
        self.p = []

        ncp = len(self.cp_before)
        assert(ncp==len(self.cp_after))
        matrix_object = self.obj.matrix_world.inverted()

        for i in range(ncp):
            cp_obj = matrix_object * self.cp_before[i]
            self.p.append(np.array(cp_obj[0:2]))

        self.weight_list = []
        for i in range(ncp):
            weight = {}
            for vert in self.mesh.vertices:
                idx = vert.index
                dist = LA.norm(self.p[i]-np.array(vert.co[0:2]), 2)
                weight[idx] = 1/(dist*dist+1e-18)
                weight[idx] = min(weight[idx], 9999.0)
            self.weight_list.append(weight)

        # pre-computing p_star
        self.p_star = {}
        self.res_length = {}
        for vert in self.mesh.vertices:
            idx = vert.index
            numerator = np.zeros(2)
            w_sum = 0
            for i in range(ncp):
                numerator += (self.weight_list[i][idx]*self.p[i])
                w_sum += self.weight_list[i][idx]
            self.p_star[idx] = numerator / w_sum
            self.res_length[idx] = LA.norm(np.array(vert.co[0:2]) - self.p_star[idx], 2)

        # pre-compute mu
        self.mu = {}
        for vert in self.mesh.vertices:
            idx = vert.index
            mu = 0.0
            for i in range(ncp):
                p_hat = self.p[i] - self.p_star[idx]
                mu = mu+(self.weight_list[i][idx]*np.dot(p_hat, p_hat))
            self.mu[idx] = mu

        # pre-computing A
        self.A_list = []
        for i in range(ncp):
            A = {}
            for vert in self.mesh.vertices:
                idx = vert.index
                vo = np.array(vert.co[0:2])
                p_hat = self.p[i] - self.p_star[idx]
                v_pstar = vo - self.p_star[idx]

                m_left = np.zeros((2,2))
                m_left[0,0] = p_hat[0]
                m_left[0,1] = p_hat[1]
                m_left[1,0] = p_hat[1]
                m_left[1,1] = -p_hat[0]

                m_right = np.zeros((2,2))
                m_right[0,0] = v_pstar[0]
                m_right[0,1] = v_pstar[1]
                m_right[1,0] = v_pstar[1]
                m_right[1,1] = -v_pstar[0]

                A[idx] = np.dot(m_left,m_right.transpose())
                A[idx] = self.weight_list[i][idx]*A[idx]
            self.A_list.append(A)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class AnimationOperatorUpdate(bpy.types.Operator):
    bl_idname = 'animation.animation_update'
    bl_label = 'Animation Update'
    bl_options = {'REGISTER','UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object!=None) and (context.scene.grease_pencil!=None)

    def invoke(self, context, event):
        # import pdb; pdb.set_trace()
        gp = context.scene.grease_pencil

        obj = context.active_object
        ly = gp.layers.active
        if ly==None:
            return {'FINISHED'}
        af = ly.active_frame
        if af==None:
            return {'FINISHED'}
        strokes = af.strokes

        if (strokes==None) or (len(strokes)>10):
            return {'FINISHED'}

        self.frames = [context.scene.current_frame+i for i in range(context.scene.frame_block_nb)]

        if context.scene.enum_brushes=='FOLLOWPATH':
            try:
                stroke = strokes[-1]
            except IndexError:
                pass
            else:
                obj.animation_data_create()
                obj.animation_data.action = bpy.data.actions.new(name="LocationAnimation")

                N = len(stroke.points)

                fcurve_x = obj.animation_data.action.fcurves.new(data_path='location', index=0)
                fcurve_y = obj.animation_data.action.fcurves.new(data_path='location', index=1)
                fcurve_z = obj.animation_data.action.fcurves.new(data_path='location', index=2)

                if N<context.scene.frame_block_nb:
                    for i in range(N):
                        position = stroke.points[i].co
                        fcurve_x.keyframe_points.insert(self.frames[i], position[0], {'FAST'})
                        fcurve_y.keyframe_points.insert(self.frames[i], position[1], {'FAST'})
                        fcurve_z.keyframe_points.insert(self.frames[i], position[2], {'FAST'})
                else:
                    float_step = N/context.scene.frame_block_nb
                    for i in range(context.scene.frame_block_nb):
                        idx = int(float_step*i)
                        position = stroke.points[idx].co
                        fcurve_x.keyframe_points.insert(self.frames[i], position[0], {'FAST'})
                        fcurve_y.keyframe_points.insert(self.frames[i], position[1], {'FAST'})
                        fcurve_z.keyframe_points.insert(self.frames[i], position[2], {'FAST'})


        elif context.scene.enum_brushes=='HPOINT':
            mesh = obj.data
            mesh.animation_data_create()
            action = bpy.data.actions.new(name='HPOINT_Animation')
            mesh.animation_data.action = action

            # Point handler
            pca = PCA(n_components=2)

            try:
                stroke = strokes[-1]
            except IndexError:
                pass
            else:
                phandler = stroke.points[0].co.xyz
                ppath = [p.co.xz for p in stroke.points]
                phandler = np.array(phandler)
                ppath = np.array(ppath) # the size is correct, amazing

                #PCA
                res = pca.fit(ppath).transform(ppath)
                res[:,1] = 0.0
                new_ppath = pca.inverse_transform(res)
                new_phandler = phandler

                # proportional based linear blend skinning
                (nframe, ndim) = new_ppath.shape
                delta_list = []
                for i in range(1, nframe):
                    t0 = new_ppath[i, 0] - new_ppath[i-1, 0]
                    t1 = new_ppath[i, 1] - new_ppath[i-1, 1]
                    delta_list.append((t0, t1))

                weight = {}
                matrix_world = obj.matrix_world
                for vert in mesh.vertices:
                    v_co_world = np.array(matrix_world*vert.co)
                    dist = LA.norm(v_co_world-new_phandler, 2)
                    weight[vert.index] = np.exp(-dist)

                normalized_delta_list = []
                for i in range(context.scene.frame_block_nb):
                    normalized_delta_list.append(delta_list[i%len(delta_list)])

                frames = [context.scene.current_frame+i for i in range(context.scene.frame_block_nb)]

                for vert in mesh.vertices:
                    fcurve_x = action.fcurves.new('vertices[%d].co'%vert.index, index=0)
                    fcurve_y = action.fcurves.new('vertices[%d].co'%vert.index, index=1)
                    co_kf_x = vert.co[0]
                    co_kf_y = vert.co[1]
                    for frame, val in zip(frames, normalized_delta_list):
                        co_kf_x += weight[vert.index]*val[0]
                        co_kf_y += weight[vert.index]*val[1]
                        fcurve_x.keyframe_points.insert(frame, co_kf_x, {'FAST'})
                        fcurve_y.keyframe_points.insert(frame, co_kf_y, {'FAST'})

        return {'FINISHED'}

class AnimationOperatorPreview(bpy.types.Operator):
    bl_idname = 'animation.preview'
    bl_label = 'Animation Preview'
    bl_options = {'REGISTER','UNDO'}

    def invoke(self, context, event):
        scene = context.scene
        scene.frame_start = context.scene.current_frame
        scene.frame_end = context.scene.current_frame+context.scene.frame_block_nb-1

        bpy.ops.screen.animation_play()
        if context.screen.is_animation_playing==False:
            scene.frame_current = context.scene.current_frame

        return {'FINISHED'}

class AnimationOperatorAddBone(bpy.types.Operator):
    bl_idname = 'animation.add_bone'
    bl_label = 'Add Bone'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        bpy.ops.object.armature_add()
        ob = bpy.context.scene.objects.active
        ob.data.draw_type = 'STICK'
        ob.show_x_ray = True
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

################################################################################
# Recording
################################################################################

# Property
class RecordingPropertyItem(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty(name='Name', default='')
    index = bpy.props.IntProperty(name='Index', default=0)
    start_frame = bpy.props.IntProperty(name='Startframe', default=0)
    end_frame = bpy.props.IntProperty(name='Endframe', default=0)

    camera_position0 = bpy.props.FloatProperty(name='camera_position0', default=0.0)
    camera_position1 = bpy.props.FloatProperty(name='camera_position1', default=0.0)
    camera_rotation_euler = bpy.props.FloatProperty(name='camera_rotation_euler', default=0.0)

# UI
class RecordingUIListItem(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(0.3)
        split.prop(item, "name", text="", emboss=False, icon='CLIP')
        split.label('Start: %d' % item.start_frame)
        split.label('End: %d' % item.end_frame)

# Operator
class RecordingOperatorListActionEdit(bpy.types.Operator):
    bl_idname = 'recording.edit'
    bl_label = 'List Action Edit'

    def invoke(self, context, event):
        index = context.scene.recording_index
        context.scene.frame_current = index*context.scene.frame_block_nb+1
        return {'FINISHED'}

# https://blender.stackexchange.com/questions/30444/create-an-interface-which-is-similar-to-the-material-list-box
class RecordingOperatorListActionAdd(bpy.types.Operator):
    bl_idname = 'recording.add'
    bl_label = 'List Action Add'

    def invoke(self, context, event):
        scene = context.scene

        item = scene.recording_array.add()
        item.id = len(scene.recording_array)
        item.name = 'Recording-%d'%len(scene.recording_array)
        item.index = len(scene.recording_array)
        scene.recording_index = (len(scene.recording_array)-1)

        # add camera animation
        obj = bpy.data.objects['Camera']
        if obj.animation_data==None:
            obj.animation_data_create()
            obj.animation_data.action = bpy.data.actions.new(name='LocationAnimation')
            camera_fcurve_x = obj.animation_data.action.fcurves.new(data_path='location', index=0)
            camera_fcurve_y = obj.animation_data.action.fcurves.new(data_path='location', index=1)
        else:
            camera_fcurve_x = obj.animation_data.action.fcurves[0]
            camera_fcurve_y = obj.animation_data.action.fcurves[1]

        position = obj.location
        item.camera_position0 = position[0]
        item.camera_position1 = position[1]
        item.camera_rotation_euler = obj.rotation_euler[2]

        camera_fcurve_x.keyframe_points.insert(context.scene.current_frame, position[0], {'FAST'})
        camera_fcurve_y.keyframe_points.insert(context.scene.current_frame, position[1], {'FAST'})

        item.start_frame = context.scene.current_frame
        item.end_frame = context.scene.current_frame+context.scene.frame_block_nb-1
        context.scene.current_frame+=context.scene.frame_block_nb

        return {"FINISHED"}

################################################################################
# OverView Drawing Using OpenGL
# Modified from https://github.com/dfelinto/blender/blob/master/doc/python_api/examples/gpu.offscreen.1.py
################################################################################

class OffScreenDraw(bpy.types.Operator):
    bl_idname = "view3d.offscreen_draw"
    bl_label = "View3D Offscreen Draw"

    _handle_calc = None
    _handle_draw = None
    is_enabled = False

    # manage draw handler
    @staticmethod
    def draw_callback_px(self, context):
        aspect_ratio = 1.0
        self._update_offscreen(context, self._offscreen)
        ncamera = len(context.scene.recording_array)
        camera_pos = []
        objects_pos = []
        for i in range(ncamera):
            camera_pos.append((context.scene.recording_array[i].camera_position0,context.scene.recording_array[i].camera_position1))

        for obj in bpy.data.objects:
            objects_pos.append((obj.location[0], obj.location[1]))

        self._opengl_draw(context, self._texture, aspect_ratio, 0.1, ncamera, camera_pos, objects_pos)

    @staticmethod
    def handle_add(self, context):
        OffScreenDraw._handle_draw = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback_px, (self, context), 'WINDOW', 'POST_PIXEL')

    @staticmethod
    def handle_remove():
        if OffScreenDraw._handle_draw is not None:
            bpy.types.SpaceView3D.draw_handler_remove(OffScreenDraw._handle_draw, 'WINDOW')
        OffScreenDraw._handle_draw = None

    # off-screen buffer
    @staticmethod
    def _setup_offscreen(context):
        import gpu
        try:
            offscreen = gpu.offscreen.new(512, 512)
        except Exception as e:
            print(e)
            offscreen = None
        return offscreen

    @staticmethod
    def _update_offscreen(context, offscreen):
        scene = context.scene
        render = scene.render
        camera = scene.camera

        modelview_matrix = camera.matrix_world.inverted()
        projection_matrix = camera.calc_matrix_camera(
                render.resolution_x,
                render.resolution_y,
                render.pixel_aspect_x,
                render.pixel_aspect_y,
                )

        offscreen.draw_view3d(
                scene,
                context.space_data,
                context.region,
                projection_matrix,
                modelview_matrix,
                )

    @staticmethod
    def _opengl_draw(context, texture, aspect_ratio, scale, ncamera, camera_pos, objects_pos):
        """
        OpenGL code to draw a rectangle in the viewport
        """

        glDisable(GL_DEPTH_TEST)
        glClearColor(1.0, 1.0, 1.0, 1.0);

        # view setup
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glOrtho(-1, 1, -1, 1, -15, 15)
        gluLookAt(0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

        act_tex = Buffer(GL_INT, 1)
        glGetIntegerv(GL_TEXTURE_2D, act_tex)

        viewport = Buffer(GL_INT, 4)
        glGetIntegerv(GL_VIEWPORT, viewport)

        width = int(scale * viewport[2])
        height = int(width / aspect_ratio)

        glViewport(viewport[0], viewport[1], width, height)
        glScissor(viewport[0], viewport[1], width, height)

        # draw routine
        glEnable(GL_TEXTURE_2D)
        glActiveTexture(GL_TEXTURE0)

        # glBindTexture(GL_TEXTURE_2D, texture)

        # texco = [(1, 1), (0, 1), (0, 0), (1, 0)]
        verco = [(1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)]

        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glColor4f(1.0, 1.0, 1.0, 1.0)

        glBegin(GL_QUADS)
        for i in range(4):
            # glTexCoord3f(texco[i][0], texco[i][1], 0.0)
            glVertex2f(verco[i][0], verco[i][1])
        glEnd()

        for i in range(ncamera):
            glBegin(GL_TRIANGLES)
            glColor3f(1.0, 0.5, 0.5)
            glVertex3f(camera_pos[i][0]/20.0, camera_pos[i][1]/20.0, 0)
            glVertex3f(camera_pos[i][0]/20.0-0.1, camera_pos[i][1]/20.0+0.1, 0)
            glVertex3f(camera_pos[i][0]/20.0+0.1, camera_pos[i][1]/20.0+0.1, 0)
            glEnd()

        if ncamera>1:
            for i in range(ncamera-1):
                glBegin(GL_LINES);
                glColor3f(0.6, 0.5, 0.5);
                glLineWidth(0.2);
                glVertex2f(camera_pos[i][0]/20.0, camera_pos[i][1]/20.0);
                glVertex2f(camera_pos[i+1][0]/20.0, camera_pos[i+1][1]/20.0);
                glEnd();

        # OBJECTS DRAWING
        for loc in objects_pos:
            opengl_utils.draw_dot(loc[0]/20.0, loc[1]/20.0)

        # restoring settings
        # glBindTexture(GL_TEXTURE_2D, act_tex[0])

        glDisable(GL_TEXTURE_2D)

        # reset view
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()

        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

        glViewport(viewport[0], viewport[1], viewport[2], viewport[3])
        glScissor(viewport[0], viewport[1], viewport[2], viewport[3])

    # operator functions
    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if OffScreenDraw.is_enabled:
            self.cancel(context)
            return {'FINISHED'}
        else:
            self._offscreen = OffScreenDraw._setup_offscreen(context)
            if self._offscreen:
                self._texture = self._offscreen.color_texture
            else:
                self.report({'ERROR'}, "Error initializing offscreen buffer. More details in the console")
                return {'CANCELLED'}

            OffScreenDraw.handle_add(self, context)
            OffScreenDraw.is_enabled = True

            if context.area:
                context.area.tag_redraw()

            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

    def cancel(self, context):
        OffScreenDraw.handle_remove()
        OffScreenDraw.is_enabled = False

        if context.area:
            context.area.tag_redraw()

################################################################################
# Camera
################################################################################

# UI
class CameraUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_camera_path'
    bl_label = 'Camera Path'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout
        camera = context.scene.objects['Camera']
        assert(camera!=None)

        box = layout.box()
        box.prop(camera, 'location', text='LF/RT', index=0)
        box.prop(camera, 'location', text='FWD/BWD', index=1)
        box.prop(camera, 'rotation_euler', text='Rotation', index=2)
        box.separator()
        box.operator('camera.setting', text='Set', icon='RENDER_STILL')

# Operator
class CameraOperatorSetting(bpy.types.Operator):
    bl_idname = 'camera.setting'
    bl_label = 'Camera Setting'
    bl_options = {'REGISTER','UNDO'}

    def invoke(self, context, event):
        context.scene.cursor_location.x = context.scene.objects['Camera'].location.x
        context.scene.cursor_location.y = context.scene.objects['Camera'].location.y+2.5
        return {'FINISHED'}

################################################################################
# Main UI:
################################################################################

class MainUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_2.5d_animation'
    bl_label = 'Animation'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label('Mode')
        my_settings = scene.my_settings
        box.prop(my_settings, 'enum_mode', text='')

        if my_settings.enum_mode == 'IMPORT_MODE':
            column = box.column()
            column.operator('import_image.to_grid', text='Import', icon='FILE_FOLDER')

        elif my_settings.enum_mode == 'CONSTRUCTING_MODE':
            column = box.column()
            row = column.row(align=True)
            row.prop(context.scene, 'add_noise')
            row.prop(context.scene, 'instance_nb')
            column.separator()
            # column.prop(context.scene, 'construction_mode', text='Mode')
            column.operator('construction.instancing', text='Instancing', icon='BOIDS')
            column.separator()
            column.operator('layout.cleanstrokes', text='Clean Strokes', icon='MESH_CAPSULE')

        elif my_settings.enum_mode == 'ANIMATION_MODE':
            column = box.column()
            column.prop(context.scene, 'enum_brushes', text='Brushes')
            column.separator()
            if (scene.enum_brushes=='FOLLOWPATH') or (scene.enum_brushes=='HPOINT'):
                column.operator('animation.animation_update', text='Update', icon='ANIM')
            elif scene.enum_brushes=='ARAP':
                row = column.row()
                # row.operator('gpencil.draw', text='Add CP', icon='EDIT').mode='DRAW'
                row.operator('animation.animation_arap', text='Point Interprete and Deform', icon='OUTLINER_DATA_MESH')
                row = column.row()
                # row.operator('gpencil.draw', text='Add Bone', icon='BONE_DATA').mode='DRAW'
                row.operator('animation.animation_bone', text='Bone Interprete', icon='BONE_DATA')
                row.operator('animation.bone_deform', text='Bone Deform', icon='OUTLINER_DATA_MESH')
                # row = column.row()
                # row.operator('animation.add_bone', text='Add Bone', icon='BONE_DATA')
                # row.operator('armature.extrude', text='Extrude Bone')
                # row = column.row()
                # row.operator('object.parent_set', text='Bind', icon='CONSTRAINT')
                # row.operator('object.parent_set', text='Bone Deform', icon='OUTLINER_DATA_MESH')
            column.separator()
            column.operator('layout.cleanstrokes', text='Clean Strokes', icon='MESH_CAPSULE')

        elif my_settings.enum_mode == 'LIGHTING_MODE':
            # view = context.space_data
            world = context.scene.world
            # row = box.row()
            # row.prop(view, 'show_world', text='Show World')
            row = box.row()
            row.prop(world, 'use_sky_paper', text='Skey Color')
            row.prop(world, 'use_sky_blend', text='Ground Color')
            row = box.row()
            row.column().prop(world, "horizon_color", text="Ground Color")
            row.column().prop(world, "zenith_color", text='Sky Color')

        for i in range(3):
            layout.split()

        box = layout.box()
        box.label('Tools')
        col = box.column()
        row=col.row(align=True)
        # if bpy.context.active_object.mode=='OBJECT':
        #     context.scene.edit_mode=='Object'
        # elif bpy.context.active_object.mode=='EIDT':
        #     context.scene.edit_mode=='Edit'
        # elif bpy.context.active_object.mode=='POSE':
        #     context.scene.edit_mode=='Pose'
        row.prop(context.scene, "edit_mode", text="Mode")
        row=col.row(align=True)
        row.operator('transform.translate', text='Translate', icon='NDOF_TRANS')
        row.operator('transform.rotate', text='Rotate', icon='NDOF_TURN')
        row.operator('transform.resize', text='Scale', icon='VIEWZOOM')
        row=col.row(align=True)
        row.operator('gpencil.draw', text='Draw', icon='BRUSH_DATA').mode='DRAW'
        row.operator('construction.interpret_contour', text='Interprete', icon='PARTICLE_DATA')
        row=col.row(align=True)
        row.operator('construction.generate_surface', text='Generate Surface')
        if context.scene.on_surface==True:
            row.operator('construction.on_surface', text='Surface', icon='SURFACE_NSURFACE')
        else:
            row.operator('construction.on_surface', text='Cursor', icon='LAYER_ACTIVE')
        row=col.row(align=True)
        row.operator('object.delete', text='Delete', icon='X')
        row.operator('mysettings.reset', text='Reset', icon='HAND')
        row=col.row(align=True)
        row.operator('ed.undo', text='Undo', icon='BACK')
        row.operator('ed.redo', text='Redo', icon='FORWARD')
        if context.screen.is_animation_playing==True:
            col.operator("animation.preview", text="Pause", icon='PAUSE')
        else:
            col.operator('animation.preview', text='Preview', icon='RIGHTARROW')
        col.separator()
        col.prop(context.space_data, "show_floor", text="Show Floor")
        col.prop(context.active_object, "location", text="Depth", index=1)
        col.operator('view3d.offscreen_draw', text='Show OverView', icon='MESH_UVSPHERE')


        for i in range(3):
            layout.split()

        box = layout.box()
        box.label('Record')
        row = box.row()
        col = row.column()
        col.template_list('RecordingUIListItem', '', scene, 'recording_array', scene, 'recording_index', rows=2)

        col = box.column()
        col.operator('recording.add', icon='ZOOMIN', text='Add')
        col.separator()
        col.operator('recording.edit', icon='SEQ_SEQUENCER', text='Edit')

class RenderingUIPanel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    bl_idname = 'OBJECT_PT_rendering'
    bl_label = 'Rendering'
    bl_category = 'Play2.5D'

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        col = box.column()
        col.operator('mysettings.render', text='Rendering', icon='COLORSET_03_VEC')
        col.separator()
        col.prop(context.scene.render, "filepath", text="")

################################################################################
# Logic:
################################################################################
def update_mode_func(self, context):
    mode = context.scene.edit_mode
    if mode=='Object':
        bpy.ops.object.mode_set(mode='OBJECT')
    elif mode=='Edit':
        bpy.ops.object.mode_set(mode='EDIT')
    elif mode=='Pose':
        bpy.ops.object.mode_set(mode='POSE')

def register():
    bpy.utils.register_module(__name__)

    bpy.types.Scene.my_settings = PointerProperty(type=MySettingsProperty)

    bpy.types.Scene.edit_mode = bpy.props.EnumProperty(name='Edit Mode',
                                                    description='Different Modes',
                                                    items=[('','',''),
                                                           ('Object','Object',''),
                                                           ('Edit','Edit',''),
                                                           ('Pose','Pose','')],
                                                    default='', update=update_mode_func)

    # Construction
    bpy.types.Scene.on_surface = bpy.props.BoolProperty(name='on_surface', default=False)
    bpy.types.Scene.add_noise = bpy.props.BoolProperty(name='Add Noise', default=False)
    bpy.types.Scene.instance_nb = bpy.props.IntProperty(name='#', default=6)
    bpy.types.Scene.plane_construction_smalldepth = bpy.props.FloatProperty(name='small_depth', default=0.0)

    # Animation
    bpy.types.Scene.enum_brushes = bpy.props.EnumProperty(name='Brushes',
                                                description='Different Brushes',
                                                items=[('','',''),
                                                       ('FOLLOWPATH','Path Following',''),
                                                       ('HPOINT','Handle Point',''),
                                                       ('ARAP','Rigid Deformation','')],
                                                default='')
    bpy.types.Scene.current_frame = bpy.props.IntProperty(name="current_frame", default=1)
    bpy.types.Scene.frame_block_nb = bpy.props.IntProperty(name='frame_block_nb', default=100)

    # Recording
    bpy.types.Scene.recording_array = bpy.props.CollectionProperty(type=RecordingPropertyItem)
    bpy.types.Scene.recording_index = bpy.props.IntProperty()

def unregister():
    bpy.utils.unregister_module(__name__)

    del bpy.types.Scene.my_settings

    # Construction
    del bpy.types.Scene.on_surface
    del bpy.types.Scene.add_noise
    del bpy.types.Scene.instance_nb
    del bpy.types.Scene.plane_construction_smalldepth

    # Animation
    del bpy.types.Scene.enum_brushes
    del bpy.types.Scene.current_frame
    del bpy.types.Scene.frame_block_nb

    # Recording
    del bpy.types.Scene.recording_array
    del bpy.types.Scene.recording_index

if __name__ == "__main__" :
    register()
