"""COLMAP Tracker: a dedicated Blender workspace, no global addon installation."""
import atexit
import json
from pathlib import Path
import sys
import os
import math

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import bpy
from mathutils import Matrix, Quaternion, Vector
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty, PointerProperty
from pipeline import CONFIG, Job, read_model

SAMPLE = Path(CONFIG['sample_project']) if CONFIG.get('sample_project') else ROOT/'sample_project'
JOB = None
DRAW = None
CLOUD = None
# COLMAP's reference camera has +Y down and +Z forward. Map -Y to
# Blender's +Z up, and +Z to +Y forward with a proper (non-mirrored) rotation.
WORLD_FROM_COLMAP = Matrix(((1, 0, 0, 0), (0, 0, 1, 0),
                            (0, -1, 0, 0), (0, 0, 0, 1)))


def draw_cloud():
    if CLOUD is None:
        return
    if bpy.context.region_data and bpy.context.region_data.view_perspective == 'CAMERA':
        if not bpy.context.scene.tracker.overlay_points:
            return
    import gpu
    shader, batch = CLOUD
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.point_size_set(2.0)
    shader.bind()
    batch.draw(shader)
    gpu.state.depth_test_set('NONE')
    gpu.state.point_size_set(1.0)


def load_cloud(mesh):
    global CLOUD, DRAW
    if bpy.app.background:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    color = mesh.color_attributes.get('Color')
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    CLOUD = shader, batch_for_shader(shader, 'POINTS', {
        'pos': [v.co[:] for v in mesh.vertices],
        'color': [c.color[:] for c in color.data]})
    if DRAW is None:
        DRAW = bpy.types.SpaceView3D.draw_handler_add(draw_cloud, (), 'WINDOW', 'POST_VIEW')


def import_model(folder, images, fps):
    cameras, poses, points = read_model(folder)
    if not poses:
        raise ValueError('This model has no registered cameras.')
    supported = {'SIMPLE_PINHOLE', 'SIMPLE_RADIAL', 'RADIAL', 'PINHOLE', 'OPENCV'}
    for model, w, h, p in cameras.values():
        if model not in supported:
            raise ValueError('Unsupported camera model: ' + model)
    scene = bpy.context.scene
    collection = bpy.data.collections.new('COLMAP Result')
    scene.collection.children.link(collection)
    # Keep native geometry in the .blend, even without this viewer's GPU handler.
    selected = points[::max(1, math.ceil(len(points) / 150000))]
    mesh = bpy.data.meshes.new('Reconstructed points')
    mesh.from_pydata([WORLD_FROM_COLMAP @ Vector(p[0]) for p in selected], [], [])
    cloud = bpy.data.objects.new('Sparse point cloud', mesh)
    collection.objects.link(cloud)
    colors = mesh.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
    for c, p in zip(colors.data, selected):
        c.color = (*p[1], 1)
    load_cloud(mesh)
    data = bpy.data.cameras.new('Solved camera')
    cam = bpy.data.objects.new('Solved camera', data)
    collection.objects.link(cam)
    cam.rotation_mode = 'QUATERNION'
    cam.data.display_size = 0.3
    scene.camera = cam
    # COLMAP world -> camera (+Z forward, +Y down) to Blender camera (-Z, +Y).
    flip = Matrix.Diagonal((1, -1, -1, 1))
    previous = None
    positions = []
    for pose in poses:
        rotation = Quaternion(pose['q']).to_matrix()
        world_to_camera = rotation.to_4x4()
        world_to_camera.translation = Vector(pose['t'])
        matrix = WORLD_FROM_COLMAP @ world_to_camera.inverted() @ flip
        cam.location = matrix.translation
        quat = matrix.to_quaternion()
        if previous is not None and previous.dot(quat) < 0:
            quat.negate()
        previous = quat.copy()
        cam.rotation_quaternion = quat
        cam.keyframe_insert('location', frame=pose['frame'])
        cam.keyframe_insert('rotation_quaternion', frame=pose['frame'])
        positions.append(tuple(matrix.translation))
    action = cam.animation_data.action
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(cam.animation_data.action_slot)
            if bag:
                for fc in bag.fcurves:
                    for key in fc.keyframe_points:
                        key.interpolation = 'LINEAR'
    model, width, height, p = cameras[poses[0]['camera']]
    if model in {'PINHOLE', 'OPENCV'}:
        fx, fy, cx, cy = p[:4]
    else:
        fx, cx, cy = p[:3]
        fy = fx
    data.sensor_fit = 'HORIZONTAL'
    data.sensor_width = 36
    data.lens = fx * 36 / width
    data.shift_x = (width / 2 - cx) / width
    data.shift_y = (cy - height / 2) * (fx / fy) / width
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1
    scene.render.pixel_aspect_y = fx / fy
    scene.render.fps = round(fps)
    scene.render.fps_base = round(fps) / fps
    scene.frame_start, scene.frame_end = poses[0]['frame'], poses[-1]['frame']
    scene.frame_set(scene.frame_start)
    curve = bpy.data.curves.new('Camera trajectory', 'CURVE')
    curve.dimensions = '3D'
    spline = curve.splines.new('POLY')
    spline.points.add(len(positions) - 1)
    for dest, xyz in zip(spline.points, positions):
        dest.co = (*xyz, 1)
    trajectory = bpy.data.objects.new('Camera trajectory', curve)
    collection.objects.link(trajectory)
    trajectory.color = (0.1, 0.8, 1, 1)
    if images:
        first = Path(images) / poses[0]['name']
        if first.is_file():
            image = bpy.data.images.load(str(first), check_existing=True)
            image.source = 'SEQUENCE'
            data.show_background_images = True
            bg = data.background_images.new()
            bg.image = image
            bg.alpha = 1
            bg.display_depth = 'BACK'
            bg.image_user.frame_start = poses[0]['frame']
            bg.image_user.frame_duration = scene.frame_end - scene.frame_start + 1
            bg.image_user.use_auto_refresh = True
    bpy.ops.object.select_all(action='DESELECT')
    cloud.select_set(True)
    bpy.context.view_layer.objects.active = cloud
    scene.tracker.status = '%d cameras | %d points | %.3f fps' % (len(poses), len(points), fps)
    scene.tracker.result = str(folder)
    scene['colmap_source'] = str(folder)
    scene['colmap_world_up'] = 'Z'
    collection['colmap_world_up'] = 'Z'
    scene['colmap_registered_frames'] = len(poses)
    scene['colmap_total_points'] = len(points)
    if model not in {'PINHOLE', 'SIMPLE_PINHOLE'}:
        scene.tracker.status += ' | Original distorted images'
    # Mark unsolved gaps honestly; Blender interpolates between solved samples.
    scene['colmap_missing_frames'] = scene.frame_end - scene.frame_start + 1 - len(poses)
    focus_views()
    cloud.select_set(False)
    cloud.hide_set(True)  # GPU colors replace Blender's black loose-vertex overlay.
    return cam, cloud


def focus_views():
    if not bpy.context.screen:
        return
    views = sorted([a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'], key=lambda a: a.x)
    for index, area in enumerate(views):
        space = area.spaces.active
        space.clip_end = 10000
        space.overlay.show_floor = index != 0
        space.show_region_ui = index == len(views) - 1
        space.show_region_toolbar = False
        if index == 0 and len(views) > 1:
            space.region_3d.view_perspective = 'CAMERA'
            space.region_3d.view_camera_zoom = 0
        else:
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region:
                with bpy.context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_selected(use_all_regions=False)
            obj = bpy.context.view_layer.objects.active
            if obj and obj.type == 'MESH' and len(obj.data.vertices):
                import statistics
                vertices = [v.co.copy() for v in obj.data.vertices]
                center = Vector([statistics.median(v[i] for v in vertices) for i in range(3)])
                radii = sorted((v - center).length for v in vertices)
                space.region_3d.view_location = center
                space.region_3d.view_distance = max(1, radii[int(len(radii) * .85)] * 3)
                if bpy.context.scene.camera:
                    # Orbit with world Z upright; never inherit the source camera's roll.
                    back = bpy.context.scene.camera.rotation_quaternion @ Vector((0, 0, 1))
                    horizontal = Vector((back.x, back.y, 0))
                    if horizontal.length < 1e-6:
                        horizontal = Vector((0, -1, 0))
                    horizontal.normalize()
                    offset = Quaternion((0, 0, 1), .45) @ horizontal + Vector((0, 0, .35))
                    space.region_3d.view_rotation = offset.to_track_quat('Z', 'Y')


class TrackerSettings(bpy.types.PropertyGroup):
    video: StringProperty(name='Video', subtype='FILE_PATH')
    output: StringProperty(name='Projects', subtype='DIR_PATH', default=str(ROOT / 'projects'))
    result: StringProperty(name='Model folder', subtype='DIR_PATH')
    job_folder: StringProperty(subtype='DIR_PATH')
    images: StringProperty(name='Image folder', subtype='DIR_PATH')
    fps: IntProperty(name='Tracking FPS', default=6, min=1, max=60)
    import_fps: FloatProperty(name='Model FPS', default=29.97002997, min=1, max=240)
    duration: FloatProperty(name='First seconds (0 = all)', default=0, min=0)
    size: IntProperty(name='Max image size', default=1920, min=640, max=8192)
    overlap: IntProperty(name='Neighbour frames', default=10, min=2, max=100)
    gpu: BoolProperty(name='Use GPU', default=True)
    overlay_points: BoolProperty(name='Show points over camera image', default=False)
    solver: EnumProperty(name='Solver', items=[('COLMAP', 'COLMAP', 'Incremental reconstruction'), ('GLOMAP', 'GLOMAP', 'Global reconstruction')])
    mask: StringProperty(name='Static mask', subtype='FILE_PATH', description='Black excludes pixels; white keeps them. Must match source image dimensions.')
    status: StringProperty(default='Ready — load a video or the prepared scene')
    colmap: StringProperty(name='COLMAP', subtype='FILE_PATH', default=CONFIG['colmap'])
    glomap: StringProperty(name='GLOMAP', subtype='FILE_PATH', default=CONFIG['glomap'])
    ffmpeg: StringProperty(name='FFmpeg', subtype='FILE_PATH', default=CONFIG['ffmpeg'])


def poll_job():
    global JOB
    if JOB is None:
        return None
    s = bpy.context.scene.tracker
    try:
        state = JOB.tick()
        s.status = JOB.message
        if state == 'done':
            s.images = str(JOB.folder / 'undistorted/images')
            s.import_fps = JOB.settings['fps']
            import_model(JOB.folder / 'model', s.images, s.import_fps)
            total = len(list((JOB.folder / 'images').glob('*.jpg')))
            s.status += ' | %d/%d registered' % (bpy.context.scene['colmap_registered_frames'], total)
        if state != 'running':
            JOB = None
            return None
    except Exception as exc:
        s.status = 'Error: ' + str(exc)
        if JOB:
            JOB.cancel()
        JOB = None
        import traceback
        traceback.print_exc()
        return None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return 0.25


class TRACKER_OT_start(bpy.types.Operator):
    bl_idname = 'tracker.start'
    bl_label = 'Start Camera Tracking'
    def execute(self, context):
        global JOB
        if JOB:
            return {'CANCELLED'}
        s = context.scene.tracker
        settings = {key: getattr(s, key) for key in ('fps', 'duration', 'size', 'overlap', 'gpu', 'solver')}
        settings.update({key: bpy.path.abspath(getattr(s, key)) if getattr(s, key) else ''
                         for key in ('video', 'output', 'colmap', 'glomap', 'ffmpeg', 'mask')})
        try:
            JOB = Job(settings)
            s.job_folder = str(JOB.folder)
            bpy.app.timers.register(poll_job, first_interval=0.1)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class TRACKER_OT_stop(bpy.types.Operator):
    bl_idname = 'tracker.stop'
    bl_label = 'Stop'
    def execute(self, context):
        global JOB
        if JOB:
            JOB.cancel()
            context.scene.tracker.status = JOB.message
            JOB = None
        return {'FINISHED'}


class TRACKER_OT_import(bpy.types.Operator):
    bl_idname = 'tracker.import_model'
    bl_label = 'Load Reconstruction'
    sample: BoolProperty(default=False)
    def execute(self, context):
        s = context.scene.tracker
        if self.sample:
            s.result = str(SAMPLE / '04 SCENES/IMG_2284_nonHDR/sparse')
            s.images = str(SAMPLE / '04 SCENES/IMG_2284_nonHDR/images')
            s.video = str(SAMPLE / '02 VIDEOS/IMG_2284_nonHDR.mov')
            s.import_fps = 30000 / 1001
        try:
            import_model(bpy.path.abspath(s.result), bpy.path.abspath(s.images), s.import_fps)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class TRACKER_OT_preview(bpy.types.Operator):
    bl_idname = 'tracker.preview'
    bl_label = 'Preview Source Video'
    def execute(self, context):
        path = bpy.path.abspath(context.scene.tracker.video)
        if not Path(path).is_file():
            self.report({'ERROR'}, 'Choose an existing video')
            return {'CANCELLED'}
        try:
            clip = bpy.data.movieclips.load(path, check_existing=True)
            area = next((a for a in context.screen.areas if a.type == 'VIEW_3D' and a != context.area), None)
            if area:
                area.type = 'CLIP_EDITOR'
                area.spaces.active.clip = clip
                area.spaces.active.show_region_ui = False
                area.spaces.active.show_region_toolbar = False
            context.scene.tracker.status = 'Source preview uses original frames; solve preview uses Tracking FPS'
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class TRACKER_OT_views(bpy.types.Operator):
    bl_idname = 'tracker.views'
    bl_label = 'Camera + 3D View'
    def execute(self, context):
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                area.type = 'VIEW_3D'
        focus_views()
        return {'FINISHED'}


class TRACKER_OT_log(bpy.types.Operator):
    bl_idname = 'tracker.log'
    bl_label = 'Open Job Folder'
    def execute(self, context):
        s = context.scene.tracker
        folder = JOB.folder if JOB else (Path(s.job_folder) if s.job_folder else Path(bpy.path.abspath(s.result)).parent)
        if folder.is_dir():
            os.startfile(str(folder))
        return {'FINISHED'}


class TRACKER_PT_main(bpy.types.Panel):
    bl_label = 'COLMAP / VIDEO TRACKER'
    bl_idname = 'TRACKER_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -100
    def draw(self, context):
        layout = self.layout
        s = context.scene.tracker
        layout.label(text='CAMERA SOLVE WORKSPACE', icon='TRACKER')
        col = layout.column()
        col.enabled = JOB is None
        col.prop(s, 'video')
        col.operator('tracker.preview', icon='PLAY')
        box = col.box()
        box.label(text='Tracking settings')
        for key in ('solver', 'fps', 'duration', 'size', 'overlap', 'gpu', 'mask'):
            box.prop(s, key)
        box.label(text='Mask: black = ignore, white = track', icon='INFO')
        col.prop(s, 'output')
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator('tracker.stop' if JOB else 'tracker.start', icon='CANCEL' if JOB else 'TRACKING_FORWARDS')
        box = layout.box()
        # Wrap status text to keep errors and statistics readable in a narrow sidebar.
        import textwrap
        for line in textwrap.wrap(s.status, width=38):
            box.label(text=line)
        layout.operator('tracker.log', icon='FILE_FOLDER')
        layout.operator('tracker.views', icon='VIEW_CAMERA')
        layout.prop(s, 'overlay_points')
        layout.operator('screen.animation_play', text='Play / Pause', icon='PLAY')
        layout.operator('wm.save_as_mainfile', text='Save Blender Project', icon='FILE_BLEND')


class TRACKER_PT_import(bpy.types.Panel):
    bl_label = 'Existing Reconstruction'
    bl_idname = 'TRACKER_PT_import'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -100
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        col = self.layout.column()
        col.enabled = JOB is None
        s = context.scene.tracker
        col.operator('tracker.import_model', text='Load Prepared SCENES Preview', icon='SCENE_DATA').sample = True
        col.prop(s, 'result')
        col.prop(s, 'images')
        col.prop(s, 'import_fps')
        col.operator('tracker.import_model', icon='IMPORT')
        col.label(text='Folder must contain COLMAP TXT files')


class TRACKER_PT_tools(bpy.types.Panel):
    bl_label = 'Executables'
    bl_idname = 'TRACKER_PT_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -100
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        col = self.layout.column()
        col.enabled = JOB is None
        for key in ('colmap', 'glomap', 'ffmpeg'):
            col.prop(context.scene.tracker, key)


CLASSES = (TrackerSettings, TRACKER_OT_start, TRACKER_OT_stop, TRACKER_OT_import,
           TRACKER_OT_preview, TRACKER_OT_views, TRACKER_OT_log, TRACKER_PT_main,
           TRACKER_PT_import, TRACKER_PT_tools)


def register():
    # The transform controls remain available in the Properties editor.
    transform_panel = getattr(bpy.types, 'VIEW3D_PT_transform', None)
    if transform_panel:
        bpy.utils.unregister_class(transform_panel)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tracker = PointerProperty(type=TrackerSettings)


def setup_workspace():
    # This runs only in the launcher's fresh --factory-startup process.
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if bpy.context.workspace:
        bpy.context.workspace.name = 'COLMAP Tracker'
    if bpy.context.screen:
        area = max((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.area_split(direction='VERTICAL', factor=0.40)
    bpy.context.scene.world.color = (0.045, 0.045, 0.045)
    focus_views()
    if (SAMPLE / '04 SCENES/IMG_2284_nonHDR/sparse/images.txt').is_file():
        bpy.ops.tracker.import_model(sample=True)
    return None


def shutdown():
    if JOB:
        JOB.cancel()


atexit.register(shutdown)
if __name__ == '__main__':
    bpy.context.preferences.view.show_splash = False
    register()
    if not bpy.app.background:
        bpy.app.timers.register(setup_workspace, first_interval=0.5)
