import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,tracker
settings=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
tracker.register()
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
cam,cloud=tracker.import_model(settings['model'],settings['images'],settings['fps'],settings.get('camera_corrections'))
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
        obj.hide_render=not item.get('visible',True);obj.hide_set(not item.get('visible',True));obj.hide_select=item.get('locked',False)
        mat=bpy.data.materials.new(item['name']);mat.diffuse_color=(*item['color'],1);mat.use_nodes=True
        node=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');node.inputs['Base Color'].default_value=(*item['color'],1);obj.data.materials.append(mat)
if settings.get('mesh'):
    from mesh_data import load_mesh
    surface=load_mesh(settings['mesh'],settings['camera_corrections']['model'] if settings.get('camera_corrections') else None)
    mesh=bpy.data.meshes.new('Reconstructed surface');mesh.from_pydata(surface['vertices'].tolist(),[],surface['faces'].tolist());mesh.update()
    obj=bpy.data.objects.new('Reconstructed surface',mesh);bpy.context.scene.collection.objects.link(obj)
    if layout:obj.parent=root
    colors=mesh.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
    for dest,rgb in zip(colors.data,surface['colors']):dest.color=(*rgb,1)
    for face in mesh.polygons:face.use_smooth=settings.get('mesh_smooth',True)
    material=bpy.data.materials.new('Reconstructed vertex colors');material.use_nodes=True
    nodes=material.node_tree.nodes;attribute=nodes.new('ShaderNodeVertexColor');attribute.layer_name='Color'
    material.node_tree.links.new(attribute.outputs['Color'],nodes.get('Principled BSDF').inputs['Base Color']);obj.data.materials.append(material)
bpy.ops.wm.save_as_mainfile(filepath=settings['output'])
