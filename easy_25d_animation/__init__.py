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


# if "bpy" in locals():
#     import importlib
#     importlib.reload(utils)
#     importlib.reload(ui_utils)
#     importlib.reload(ops_utils)
#     importlib.reload(mesh)
#     importlib.reload(brushes)
# else:
#     from . import utils, ui_utils, ops_utils, mesh, brushes

import os
import sys
import math
import mathutils
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
from numpy import linalg as LA
from sklearn.decomposition import PCA

################################################################################
# Global
################################################################################

class MySettingsProperty(PropertyGroup):
    enum_mode = EnumProperty(name='Mode',
                             description='Different drawing mode',
                             items=[('LIGHTING_MODE','Lighting',''),
                                    ('IMPORT_MODE','Import',''),
                                    ('CONSTRUCTING_MODE','Construction',''),
                                    ('ANIMATION_MODE','Animation','')],
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
class ConstructionOperatorInstancing(bpy.types.Operator):
    bl_idname = "construction.instancing"
    bl_label = "Instancing based on strokes"
    bl_options = {"UNDO"}

    small_depth = 0

    @classmethod
    def poll(cls, context):
        return (context.scene.grease_pencil != None) and (context.active_object!=None)

    def invoke(self, context, event):
        # import pdb; pdb.set_trace()
        gp = context.scene.grease_pencil
        strokes = gp.layers.active.active_frame.strokes

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

            # instancing (including animation data)
            model_obj = context.active_object

            # make some flags
            is_copy_animation = (model_obj.animation_data!=None)
            is_projection = context.scene.is_projection

            if is_copy_animation:
                model_fcurve_x = model_obj.animation_data.action.fcurves[0]
                model_fcurve_z = model_obj.animation_data.action.fcurves[1]
                N = len(model_fcurve_x.keyframe_points)

            for i in range(sampling_nb):
                new_obj = model_obj.copy()
                new_obj.data = model_obj.data.copy()

                if is_projection:
                    new_obj.location[1] = model_obj.location[1] + i*shift[i][2] # z denotes depth
                else:
                    new_obj.location[1] = model_obj.location[1] + ConstructionOperatorInstancing.small_depth

                if is_copy_animation:
                    new_obj.animation_data_create()
                    new_obj.animation_data.action = bpy.data.actions.new(name="LocationAnimation")

                    fcurve_x = new_obj.animation_data.action.fcurves.new(data_path='location', index=0)
                    fcurve_z = new_obj.animation_data.action.fcurves.new(data_path='location', index=2)

                    x_pre = 0
                    z_pre = 0

                    for k in range(N):
                        frame_idx = model_fcurve_x.keyframe_points[k].co[0] # (frame index, real f-value)
                        if k==0:
                            x_cur = shift[i][0]
                            z_cur = shift[i][2]
                        else:
                            x_cur = model_fcurve_x.keyframe_points[k].co[1]+x_pre2-x_pre
                            z_cur = model_fcurve_z.keyframe_points[k].co[1]+z_pre2-z_pre
                        fcurve_x.keyframe_points.insert(frame_idx, x_cur+random.gauss(0, 0.05), {'FAST'})
                        fcurve_z.keyframe_points.insert(frame_idx, z_cur+random.gauss(0, 0.05), {'FAST'})

                        x_pre = model_fcurve_x.keyframe_points[k].co[1]
                        z_pre = model_fcurve_z.keyframe_points[k].co[1]

                        x_pre2 = x_cur
                        z_pre2 = z_cur
                else:
                    if is_projection:
                        new_obj.location[0] = shift[0][0]
                        new_obj.location[2] = shift[0][2]
                    else:
                        new_obj.location[0] = shift[i][0]
                        new_obj.location[2] = shift[i][2]


                context.scene.objects.link(new_obj)
                ConstructionOperatorInstancing.small_depth += 0.001 # prevent z shadowing

            bpy.ops.object.select_all(action='DESELECT')
        return {'FINISHED'}

class CleanStrokes(bpy.types.Operator):
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
class AnimationARAPOperator(bpy.types.Operator):
    bl_idname = 'animation.animation_arap'
    bl_label = 'Animation ARAP'
    bl_options = {'REGISTER','UNDO'}

    def __init__(self):
        print("Start Invoke")
        self.cp_before = []
        self.cp_after = []
        self.seleted_cp = [None]

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
                print('I am pressed')
                if len(self.cp_before)<=0:
                    return {'FINISHED'}
                min_dist = sys.float_info.max
                for co in self.cp_before:
                    dist = LA.norm(np.array((loc-co)))
                    if dist<=min_dist:
                        self.seleted_cp[0] = co
                    # print(co[0])
                    # print(co[1])
                    # print(co[2])


                # print(x)
                # print(y)
                # print("******************")
                # print(loc)
                # print(loc[0])
                # print(loc[1])
                # print(loc[2])
                # print("******************")
                # print(event.mouse_x)
                # print(event.mouse_y)

                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE':
                print('I am released')
                return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            self.delta_x = event.mouse_region_x - self.curr_mouse_x
            self.delta_y = event.mouse_region_y - self.curr_mouse_y

            self.curr_mouse_x = event.mouse_region_x
            self.curr_mouse_y = event.mouse_region_y

            if self.seleted_cp[0]==None:
                return {'RUNNING_MODAL'}

            x, y = self.curr_mouse_x, self.curr_mouse_y
            loc = region_2d_to_location_3d(context.region, context.space_data.region_3d, (x, y), bpy.context.scene.cursor_location)

            self.seleted_cp[0][0] = loc[0]
            self.seleted_cp[0][1] = loc[1]
            self.seleted_cp[0][2] = loc[2]

            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        gp = context.scene.grease_pencil

        self.curr_mouse_x = event.mouse_region_x
        self.curr_mouse_y = event.mouse_region_y

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

        cp_before = []
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

            cp_before.append(cp)

        for stroke in strokes:
            strokes.remove(stroke)

        for cp in cp_before:
            stroke = af.strokes.new()
            stroke.draw_mode = '3DSPACE'
            stroke.points.add(count = 1)
            stroke.points[0].co = cp
            self.cp_before.append(stroke.points[0].co)

        ly.line_change = 10

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
                fcurve_z = obj.animation_data.action.fcurves.new(data_path='location', index=2)

                i = 0
                while int(i*2) < N:
                    idx = int(i*2)
                    position = stroke.points[idx].co
                    fcurve_x.keyframe_points.insert(context.scene.current_frame+idx, position[0], {'FAST'})
                    fcurve_z.keyframe_points.insert(context.scene.current_frame+idx, position[2], {'FAST'})
                    i+=1

        elif context.scene.enum_brushes=='HPOINT':
            mesh = obj.data
            mesh.animation_data_create()
            action = bpy.data.actions.new(name='MeshAnimation')
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

################################################################################
# Recording
################################################################################

class RecordingProperty:
    camera_position_recording = [(0,0)]
    start_frame = []
    end_frame = []
    camera_fcurve_x = None
    camera_fcurve_y = None

# Property
class RecordingPropertyItem(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty(name='Name', default='')
    index = bpy.props.IntProperty(name='Index', default=0)
    start_frame = bpy.props.IntProperty(name='Startframe', default=0)
    end_frame = bpy.props.IntProperty(name='Endframe', default=0)

# UI
class RecordingUIListItem(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(0.3)
        split.prop(item, "name", text="", emboss=False, icon='CLIP')
        split.label('Start: %d' % RecordingProperty.start_frame[index])
        split.label('End: %d' % RecordingProperty.end_frame[index])

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
            RecordingProperty.camera_fcurve_x = obj.animation_data.action.fcurves.new(data_path='location', index=0)
            RecordingProperty.camera_fcurve_y = obj.animation_data.action.fcurves.new(data_path='location', index=1)

        position = obj.location

        RecordingProperty.camera_position_recording.append((position[0],position[1]))

        RecordingProperty.camera_fcurve_x.keyframe_points.insert(context.scene.current_frame, position[0], {'FAST'})
        RecordingProperty.camera_fcurve_y.keyframe_points.insert(context.scene.current_frame, position[1], {'FAST'})

        RecordingProperty.start_frame.append(context.scene.current_frame)
        RecordingProperty.end_frame.append(context.scene.current_frame+context.scene.frame_block_nb-1)
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
        ncamera = len(RecordingProperty.camera_position_recording)
        camera_pos = RecordingProperty.camera_position_recording
        self._opengl_draw(context, self._texture, aspect_ratio, 0.1, ncamera, camera_pos)

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
    def _opengl_draw(context, texture, aspect_ratio, scale, ncamera, camera_pos):
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

        # back_step = 30
        for i in range(ncamera):
            glBegin(GL_TRIANGLES)
            glColor3f(1.0, 0.5, 0.5)
            glVertex3f(camera_pos[i][0]/40.0, camera_pos[i][1]/40.0, 0)
            glVertex3f(camera_pos[i][0]/40.0-0.1, camera_pos[i][1]/40.0+0.1, 0)
            glVertex3f(camera_pos[i][0]/40.0+0.1, camera_pos[i][1]/40.0+0.1, 0)
            glEnd()

        if ncamera>1:
            for i in range(ncamera-1):
                glBegin(GL_LINES);
                glColor3f(0.6, 0.5, 0.5);
                glLineWidth(0.2);
                glVertex2f(camera_pos[i][0]/40.0, camera_pos[i][1]/40.0);
                glVertex2f(camera_pos[i+1][0]/40.0, camera_pos[i+1][1]/40.0);
                glEnd();


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
            row.prop(context.scene, 'is_projection')
            row.prop(context.scene, 'add_noise')
            column.prop(context.scene, 'instance_nb')
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
                row.operator('gpencil.draw', text='Add CP', icon='EDIT').mode='DRAW'
                row.operator('animation.animation_arap', text='Deform', icon='OUTLINER_DATA_MESH')
            column.separator()
            column.operator('layout.cleanstrokes', text='Clean Strokes', icon='MESH_CAPSULE')

        elif my_settings.enum_mode == 'LIGHTING_MODE':
            view = context.space_data
            world = context.scene.world
            row = box.row()
            row.prop(view, "show_floor", text="Show Floor")
            row.prop(view, 'show_world', text='Show World')
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
        row.operator('gpencil.draw', text='Draw', icon='BRUSH_DATA').mode='DRAW'
        row.operator('transform.resize', text='Scale', icon='VIEWZOOM')
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

def register():
    bpy.utils.register_module(__name__)

    bpy.types.Scene.my_settings = PointerProperty(type=MySettingsProperty)

    # Construction
    bpy.types.Scene.add_noise = bpy.props.BoolProperty(name='Add Noise', default=False)
    bpy.types.Scene.is_projection = bpy.props.BoolProperty(name='Projection')
    bpy.types.Scene.instance_nb = bpy.props.IntProperty(name='#', default=6)

    # Animation
    bpy.types.Scene.enum_brushes = EnumProperty(name='Brushes',
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

    # Recording
    del bpy.types.Scene.recording_array
    del bpy.types.Scene.recording_index

if __name__ == "__main__" :
    register()
