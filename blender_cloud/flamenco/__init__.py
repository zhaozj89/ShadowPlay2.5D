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

"""Flamenco interface.

The preferences are managed blender.py, the rest of the Flamenco-specific stuff is here.
"""
import functools
import logging
from pathlib import Path, PurePath
import typing

import bpy
from bpy.types import AddonPreferences, Operator, WindowManager, Scene, PropertyGroup
from bpy.props import StringProperty, EnumProperty, PointerProperty, BoolProperty, IntProperty

from .. import async_loop, pillar
from ..utils import pyside_cache, redraw

log = logging.getLogger(__name__)


@pyside_cache('manager')
def available_managers(self, context):
    """Returns the list of items used by a manager-selector EnumProperty."""

    from ..blender import preferences

    mngrs = preferences().flamenco_manager.available_managers
    if not mngrs:
        return [('', 'No managers available in your Blender Cloud', '')]
    return [(p['_id'], p['name'], '') for p in mngrs]


class FlamencoManagerGroup(PropertyGroup):
    manager = EnumProperty(
        items=available_managers,
        name='Flamenco Manager',
        description='Which Flamenco Manager to use for jobs')

    status = EnumProperty(
        items=[
            ('NONE', 'NONE', 'We have done nothing at all yet'),
            ('IDLE', 'IDLE', 'User requested something, which is done, and we are now idle'),
            ('FETCHING', 'FETCHING', 'Fetching available Flamenco managers from Blender Cloud'),
        ],
        name='status',
        update=redraw)

    # List of managers is stored in 'available_managers' ID property,
    # because I don't know how to store a variable list of strings in a proper RNA property.
    @property
    def available_managers(self) -> list:
        return self.get('available_managers', [])

    @available_managers.setter
    def available_managers(self, new_managers):
        self['available_managers'] = new_managers


class FLAMENCO_OT_fmanagers(async_loop.AsyncModalOperatorMixin,
                            pillar.AuthenticatedPillarOperatorMixin,
                            Operator):
    """Fetches the Flamenco Managers available to the user"""
    bl_idname = 'flamenco.managers'
    bl_label = 'Fetch available Flamenco Managers'

    stop_upon_exception = True
    log = logging.getLogger('%s.FLAMENCO_OT_fmanagers' % __name__)

    @property
    def mypref(self) -> FlamencoManagerGroup:
        from ..blender import preferences

        return preferences().flamenco_manager

    async def async_execute(self, context):
        if not await self.authenticate(context):
            return

        from .sdk import Manager
        from ..pillar import pillar_call

        self.log.info('Going to fetch managers for user %s', self.user_id)

        self.mypref.status = 'FETCHING'
        managers = await pillar_call(Manager.all)

        # We need to convert to regular dicts before storing in ID properties.
        # Also don't store more properties than we need.
        as_list = [{'_id': p['_id'], 'name': p['name']} for p in managers['_items']]

        self.mypref.available_managers = as_list
        self.quit()

    def quit(self):
        self.mypref.status = 'IDLE'
        super().quit()


class FLAMENCO_OT_render(async_loop.AsyncModalOperatorMixin,
                         pillar.AuthenticatedPillarOperatorMixin,
                         Operator):
    """Performs a Blender render on Flamenco."""
    bl_idname = 'flamenco.render'
    bl_label = 'Render on Flamenco'
    bl_description = __doc__.rstrip('.')

    stop_upon_exception = True
    log = logging.getLogger('%s.FLAMENCO_OT_render' % __name__)

    async def async_execute(self, context):
        if not await self.authenticate(context):
            return

        from ..blender import preferences

        scene = context.scene

        # Save to a different file, specifically for Flamenco.
        context.window_manager.flamenco_status = 'PACKING'
        filepath = await self._save_blendfile(context)

        # Determine where the render output will be stored.
        render_output = render_output_path(context, filepath)
        if render_output is None:
            self.report({'ERROR'}, 'Current file is outside of project path.')
            self.quit()
            return
        self.log.info('Will output render files to %s', render_output)

        # BAM-pack the files to the destination directory.
        outfile, missing_sources = await self.bam_pack(filepath)
        if not outfile:
            return

        # Create the job at Flamenco Server.
        prefs = preferences()

        context.window_manager.flamenco_status = 'COMMUNICATING'
        settings = {'blender_cmd': '{blender}',
                    'chunk_size': scene.flamenco_render_fchunk_size,
                    'filepath': str(outfile),
                    'frames': scene.flamenco_render_frame_range,
                    'render_output': str(render_output),
                    }

        # Add extra settings specific to the job type
        if scene.flamenco_render_job_type == 'blender-render-progressive':
            samples = scene.cycles.samples
            if scene.cycles.use_square_samples:
                samples **= 2

            settings['cycles_num_chunks'] = scene.flamenco_render_schunk_count
            settings['cycles_sample_count'] = samples
            settings['format'] = 'EXR'

        try:
            job_info = await create_job(self.user_id,
                                        prefs.attract_project.project,
                                        prefs.flamenco_manager.manager,
                                        scene.flamenco_render_job_type,
                                        settings,
                                        'Render %s' % filepath.name,
                                        priority=scene.flamenco_render_job_priority)
        except Exception as ex:
            self.report({'ERROR'}, 'Error creating Flamenco job: %s' % ex)
            self.quit()
            return

        # Store the job ID in a file in the output dir.
        with open(str(outfile.parent / 'jobinfo.json'), 'w', encoding='utf8') as outfile:
            import json

            job_info['missing_files'] = [str(mf) for mf in missing_sources]
            json.dump(job_info, outfile, sort_keys=True, indent=4)

        # We can now remove the local copy we made with bpy.ops.wm.save_as_mainfile().
        # Strictly speaking we can already remove it after the BAM-pack, but it may come in
        # handy in case of failures.
        try:
            self.log.info('Removing temporary file %s', filepath)
            filepath.unlink()
        except Exception as ex:
            self.report({'ERROR'}, 'Unable to remove file: %s' % ex)
            self.quit()
            return

        if prefs.flamenco_open_browser_after_submit:
            import webbrowser
            from urllib.parse import urljoin
            from ..blender import PILLAR_WEB_SERVER_URL

            url = urljoin(PILLAR_WEB_SERVER_URL, '/flamenco/jobs/%s/redir' % job_info['_id'])
            webbrowser.open_new_tab(url)

        # Do a final report.
        if missing_sources:
            names = (ms.name for ms in missing_sources)
            self.report({'WARNING'}, 'Flamenco job created with missing files: %s' %
                        '; '.join(names))
        else:
            self.report({'INFO'}, 'Flamenco job created.')

        self.quit()

    async def _save_blendfile(self, context):
        """Save to a different file, specifically for Flamenco.

        We shouldn't overwrite the artist's file.
        We can compress, since this file won't be managed by SVN and doesn't need diffability.
        """

        render = context.scene.render

        # Remember settings we need to restore after saving.
        old_use_file_extension = render.use_file_extension
        old_use_overwrite = render.use_overwrite
        old_use_placeholder = render.use_placeholder

        try:

            # The file extension should be determined by the render settings, not necessarily
            # by the setttings in the output panel.
            render.use_file_extension = True

            # Rescheduling should not overwrite existing frames.
            render.use_overwrite = False
            render.use_placeholder = False

            filepath = Path(context.blend_data.filepath).with_suffix('.flamenco.blend')
            self.log.info('Saving copy to temporary file %s', filepath)
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath),
                                        compress=True,
                                        copy=True)
        finally:
            # Restore the settings we changed, even after an exception.
            render.use_file_extension = old_use_file_extension
            render.use_overwrite = old_use_overwrite
            render.use_placeholder = old_use_placeholder

        return filepath

    def quit(self):
        super().quit()
        bpy.context.window_manager.flamenco_status = 'IDLE'

    async def bam_pack(self, filepath: Path) -> (typing.Optional[Path], typing.List[Path]):
        """BAM-packs the blendfile to the destination directory.

        Returns the path of the destination blend file.

        :param filepath: the blend file to pack (i.e. the current blend file)
        :returns: the destination blend file, or None if there were errors BAM-packing,
            and a list of missing paths.
        """

        from datetime import datetime
        from ..blender import preferences
        from . import bam_interface

        prefs = preferences()

        # Create a unique directory that is still more or less identifyable.
        # This should work better than a random ID.
        # BAM doesn't like output directories that end in '.blend'.
        unique_dir = '%s-%s-%s' % (datetime.now().isoformat('-').replace(':', ''),
                                   self.db_user['username'],
                                   filepath.stem)
        outdir = Path(prefs.flamenco_job_file_path) / unique_dir
        outfile = outdir / filepath.name

        try:
            outdir.mkdir(parents=True)
        except Exception as ex:
            self.log.exception('Unable to create output path %s', outdir)
            self.report({'ERROR'}, 'Unable to create output path: %s' % ex)
            self.quit()
            return None, []

        try:
            missing_sources = await bam_interface.bam_copy(filepath, outfile)
        except bam_interface.CommandExecutionError as ex:
            self.log.exception('Unable to execute BAM pack')
            self.report({'ERROR'}, 'Unable to execute BAM pack: %s' % ex)
            self.quit()
            return None, []

        return outfile, missing_sources


class FLAMENCO_OT_scene_to_frame_range(Operator):
    """Sets the scene frame range as the Flamenco render frame range."""
    bl_idname = 'flamenco.scene_to_frame_range'
    bl_label = 'Sets the scene frame range as the Flamenco render frame range'
    bl_description = __doc__.rstrip('.')

    def execute(self, context):
        s = context.scene
        s.flamenco_render_frame_range = '%i-%i' % (s.frame_start, s.frame_end)
        return {'FINISHED'}


class FLAMENCO_OT_copy_files(Operator,
                             async_loop.AsyncModalOperatorMixin):
    """Uses BAM to copy the current blendfile + dependencies to the target directory."""
    bl_idname = 'flamenco.copy_files'
    bl_label = 'Copy files to target'
    bl_description = __doc__.rstrip('.')

    stop_upon_exception = True

    async def async_execute(self, context):
        from pathlib import Path
        from . import bam_interface
        from ..blender import preferences

        context.window_manager.flamenco_status = 'PACKING'

        missing_sources = await bam_interface.bam_copy(
            Path(context.blend_data.filepath),
            Path(preferences().flamenco_job_file_path),
        )

        if missing_sources:
            names = (ms.name for ms in missing_sources)
            self.report({'ERROR'}, 'Missing source files: %s' % '; '.join(names))

        self.quit()

    def quit(self):
        super().quit()
        bpy.context.window_manager.flamenco_status = 'IDLE'


class FLAMENCO_OT_explore_file_path(Operator):
    """Opens the Flamenco job storage path in a file explorer."""
    bl_idname = 'flamenco.explore_file_path'
    bl_label = 'Open in file explorer'
    bl_description = __doc__.rstrip('.')

    path = StringProperty(name='Path', description='Path to explore', subtype='DIR_PATH')

    def execute(self, context):
        import platform
        import subprocess
        import os

        if platform.system() == "Windows":
            os.startfile(self.path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", self.path])
        else:
            subprocess.Popen(["xdg-open", self.path])

        return {'FINISHED'}


async def create_job(user_id: str,
                     project_id: str,
                     manager_id: str,
                     job_type: str,
                     job_settings: dict,
                     job_name: str = None,
                     *,
                     priority: int = 50,
                     job_description: str = None) -> dict:
    """Creates a render job at Flamenco Server, returning the job object as dictionary."""

    import json
    from .sdk import Job
    from ..pillar import pillar_call

    job_attrs = {
        'status': 'queued',
        'priority': priority,
        'name': job_name,
        'settings': job_settings,
        'job_type': job_type,
        'user': user_id,
        'manager': manager_id,
        'project': project_id,
    }
    if job_description:
        job_attrs['description'] = job_description

    log.info('Going to create Flamenco job:\n%s',
             json.dumps(job_attrs, indent=4, sort_keys=True))

    job = Job(job_attrs)
    await pillar_call(job.create)

    log.info('Job created succesfully: %s', job._id)
    return job.to_dict()


def is_image_type(render_output_type: str) -> bool:
    """Determines whether the render output type is an image (True) or video (False)."""

    # This list is taken from rna_scene.c:273, rna_enum_image_type_items.
    video_types = {'AVI_JPEG', 'AVI_RAW', 'FRAMESERVER', 'FFMPEG', 'QUICKTIME'}
    return render_output_type not in video_types


@functools.lru_cache(1)
def _render_output_path(
        local_project_path: str,
        blend_filepath: Path,
        flamenco_job_output_strip_components: int,
        flamenco_job_output_path: str,
        render_image_format: str,
        flamenco_render_frame_range: str,
) -> typing.Optional[PurePath]:
    """Cached version of render_output_path()

    This ensures that redraws of the Flamenco Render and Add-on preferences panels
    is fast.
    """

    try:
        project_path = Path(bpy.path.abspath(local_project_path)).resolve()
    except FileNotFoundError:
        # Path.resolve() will raise a FileNotFoundError if the project path doesn't exist.
        return None

    try:
        proj_rel = blend_filepath.parent.relative_to(project_path)
    except ValueError:
        return None

    rel_parts = proj_rel.parts[flamenco_job_output_strip_components:]
    output_top = Path(flamenco_job_output_path)

    # Strip off '.flamenco' too; we use 'xxx.flamenco.blend' as job file, but
    # don't want to have all the output paths ending in '.flamenco'.
    stem = blend_filepath.stem
    if stem.endswith('.flamenco'):
        stem = stem[:-9]

    dir_components = output_top.joinpath(*rel_parts) / stem

    # Blender will have to append the file extensions by itself.
    if is_image_type(render_image_format):
        return dir_components / '######'
    return dir_components / flamenco_render_frame_range


def render_output_path(context, filepath: Path = None) -> typing.Optional[PurePath]:
    """Returns the render output path to be sent to Flamenco.

    :param context: the Blender context (used to find Flamenco preferences etc.)
    :param filepath: the Path of the blend file to render, or None for the current file.

    Returns None when the current blend file is outside the project path.
    """

    from ..blender import preferences

    scene = context.scene
    prefs = preferences()

    if filepath is None:
        filepath = Path(context.blend_data.filepath)

    return _render_output_path(
        prefs.attract_project_local_path,
        filepath,
        prefs.flamenco_job_output_strip_components,
        prefs.flamenco_job_output_path,
        scene.render.image_settings.file_format,
        scene.flamenco_render_frame_range,
    )


class FLAMENCO_PT_render(bpy.types.Panel):
    bl_label = "Flamenco Render"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        from ..blender import preferences

        prefs = preferences()

        labeled_row = layout.split(0.25, align=True)
        labeled_row.label('Job Type:')
        labeled_row.prop(context.scene, 'flamenco_render_job_type', text='')

        labeled_row = layout.split(0.25, align=True)
        labeled_row.label('Frame Range:')
        prop_btn_row = labeled_row.row(align=True)
        prop_btn_row.prop(context.scene, 'flamenco_render_frame_range', text='')
        prop_btn_row.operator('flamenco.scene_to_frame_range', text='', icon='ARROW_LEFTRIGHT')

        layout.prop(context.scene, 'flamenco_render_job_priority')
        layout.prop(context.scene, 'flamenco_render_fchunk_size')

        if getattr(context.scene, 'flamenco_render_job_type', None) == 'blender-render-progressive':
            layout.prop(context.scene, 'flamenco_render_schunk_count')

        readonly_stuff = layout.column(align=True)
        labeled_row = readonly_stuff.split(0.25, align=True)
        labeled_row.label('Storage:')
        prop_btn_row = labeled_row.row(align=True)
        prop_btn_row.label(prefs.flamenco_job_file_path)
        props = prop_btn_row.operator(FLAMENCO_OT_explore_file_path.bl_idname,
                                      text='', icon='DISK_DRIVE')
        props.path = prefs.flamenco_job_file_path

        labeled_row = readonly_stuff.split(0.25, align=True)
        labeled_row.label('Output:')
        prop_btn_row = labeled_row.row(align=True)
        render_output = render_output_path(context)

        if render_output is None:
            prop_btn_row.label('Unable to render with Flamenco, outside of project directory.')
        else:
            prop_btn_row.label(str(render_output))
            props = prop_btn_row.operator(FLAMENCO_OT_explore_file_path.bl_idname,
                                          text='', icon='DISK_DRIVE')
            props.path = str(render_output.parent)

            flamenco_status = context.window_manager.flamenco_status
            if flamenco_status == 'IDLE':
                layout.operator(FLAMENCO_OT_render.bl_idname,
                                text='Render on Flamenco',
                                icon='RENDER_ANIMATION')
            elif flamenco_status == 'PACKING':
                layout.label('Flamenco is packing your file + dependencies')
            elif flamenco_status == 'COMMUNICATING':
                layout.label('Communicating with Flamenco Server')
            else:
                layout.label('Unknown Flamenco status %s' % flamenco_status)


def register():
    from ..utils import redraw

    bpy.utils.register_class(FlamencoManagerGroup)
    bpy.utils.register_class(FLAMENCO_OT_fmanagers)
    bpy.utils.register_class(FLAMENCO_OT_render)
    bpy.utils.register_class(FLAMENCO_OT_scene_to_frame_range)
    bpy.utils.register_class(FLAMENCO_OT_copy_files)
    bpy.utils.register_class(FLAMENCO_OT_explore_file_path)
    bpy.utils.register_class(FLAMENCO_PT_render)

    scene = bpy.types.Scene
    scene.flamenco_render_fchunk_size = IntProperty(
        name='Frame Chunk Size',
        description='Maximum number of frames to render per task',
        min=1,
        default=1,
    )
    scene.flamenco_render_schunk_count = IntProperty(
        name='Number of Sample Chunks',
        description='Number of Cycles samples chunks to use per frame',
        min=2,
        default=3,
        soft_max=10,
    )
    scene.flamenco_render_frame_range = StringProperty(
        name='Frame Range',
        description='Frames to render, in "printer range" notation'
    )
    scene.flamenco_render_job_type = EnumProperty(
        name='Job Type',
        items=[
            ('blender-render', 'Simple Render', 'Simple frame-by-frame render'),
            ('blender-render-progressive', 'Progressive Render',
             'Each frame is rendered multiple times with different Cycles sample chunks, then combined'),
        ]
    )

    scene.flamenco_render_job_priority = IntProperty(
        name='Job Priority',
        min=0,
        default=50,
        max=100,
        description='Higher numbers mean higher priority'
    )

    bpy.types.WindowManager.flamenco_status = EnumProperty(
        items=[
            ('IDLE', 'IDLE', 'Not doing anything.'),
            ('PACKING', 'PACKING', 'BAM-packing all dependencies.'),
            ('COMMUNICATING', 'COMMUNICATING', 'Communicating with Flamenco Server.'),
        ],
        name='flamenco_status',
        default='IDLE',
        description='Current status of the Flamenco add-on',
        update=redraw)


def unregister():
    bpy.utils.unregister_module(__name__)

    try:
        del bpy.types.Scene.flamenco_render_fchunk_size
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.flamenco_render_schunk_count
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.flamenco_render_frame_range
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.flamenco_render_job_type
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.flamenco_render_job_priority
    except AttributeError:
        pass
    try:
        del bpy.types.WindowManager.flamenco_status
    except AttributeError:
        pass
