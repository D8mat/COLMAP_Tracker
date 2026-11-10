import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,tracker
settings=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
tracker.register()
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
cam,cloud=tracker.import_model(settings['model'],settings['images'],settings['fps'])
cloud.hide_set(False)
from scene_geometry import mesh_geometry,transform_matrix
from mathutils import Matrix
layout=settings.get('layout')
if layout:
    root=bpy.data.objects.new('Tracker Scene Root',None);bpy.context.scene.collection.objects.link(root)
    for obj in list(cam.users_collection[0].objects):obj.parent=root
    root.matrix_world=Matrix(transform_matrix(layout['scene']).tolist())
    for item in layout['objects']:
        vertices,faces=mesh_geometry(item['kind']);mesh=bpy.data.meshes.new(item['name']);mesh.from_pydata(vertices.tolist(),[],faces)
        obj=bpy.data.objects.new(item['name'],mesh);bpy.context.scene.collection.objects.link(obj);obj.parent=root;obj.matrix_basis=Matrix(transform_matrix(item).tolist())
        mat=bpy.data.materials.new(item['name']);mat.diffuse_color=(*item['color'],1);mat.use_nodes=True
        node=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');node.inputs['Base Color'].default_value=(*item['color'],1);obj.data.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath=settings['output'])
