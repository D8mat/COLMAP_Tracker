import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import tracker
from mathutils import Vector, Quaternion
tracker.register()
assert (tracker.WORLD_FROM_COLMAP.to_3x3() @ Vector((0, -1, 0)) - Vector((0, 0, 1))).length < 1e-6
assert abs(tracker.WORLD_FROM_COLMAP.to_3x3().determinant() - 1) < 1e-6
s = bpy.context.scene.tracker
s.result = str(tracker.SAMPLE / '04 SCENES/IMG_2284_nonHDR/sparse')
s.images = str(tracker.SAMPLE / '04 SCENES/IMG_2284_nonHDR/images')
cam, cloud = tracker.import_model(s.result, s.images, 30000 / 1001)
assert bpy.context.scene['colmap_registered_frames'] == 1349
assert len(cloud.data.vertices) > 10000
assert cam.data.background_images[0].image.source == 'SEQUENCE'
# Independently verify reprojection of actual observed 3D points against COLMAP.
folder = Path(s.result)
point_lookup = {}
with (folder / 'points3D.txt').open() as stream:
    for line in stream:
        if line.startswith('#') or not line.strip(): continue
        t = line.split()
        point_lookup[int(t[0])] = tracker.WORLD_FROM_COLMAP @ Vector(tuple(map(float, t[1:4])))
with (folder / 'images.txt').open() as stream:
    for line in stream:
        if line.startswith('#') or not line.strip(): continue
        pose = line.split()
        observations = next(stream).split()
        break
from bpy_extras.object_utils import world_to_camera_view
scene = bpy.context.scene
scene.frame_set(1)
bpy.context.view_layer.update()
errors = []
for i in range(0, len(observations), 3):
    x, y, pid = observations[i:i+3]
    if int(pid) < 0 or int(pid) not in point_lookup: continue
    ndc = world_to_camera_view(scene, cam, point_lookup[int(pid)])
    px = ndc.x * scene.render.resolution_x
    py = (1 - ndc.y) * scene.render.resolution_y
    errors.append(((px-float(x))**2 + (py-float(y))**2)**0.5)
errors.sort()
median = errors[len(errors)//2]
assert median < 3, median
initial_location = cam.location.copy()
assert scene['colmap_world_up'] == 'Z'
# Path and camera must agree after the world-coordinate conversion.
trajectory = next(o for o in cam.users_collection[0].objects if o.type == 'CURVE')
assert (Vector(trajectory.data.splines[0].points[0].co[:3]) - cam.location).length < 1e-5
scene.frame_set(600)
bpy.context.view_layer.update()
assert (cam.location - initial_location).length > .01
assert (Vector(trajectory.data.splines[0].points[599].co[:3]) - cam.location).length < 1e-5
bpy.ops.wm.save_as_mainfile(filepath=str(tracker.ROOT / 'prepared_preview.blend'))
print('VALIDATION OK: 1349 cameras, %d displayed points, median reprojection %.4f pixels' % (len(cloud.data.vertices), median))
