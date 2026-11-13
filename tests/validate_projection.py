import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Analytical GPU checks independent of the sample reconstruction."""
import numpy as np
import desktop
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from PySide6.QtGui import QSurfaceFormat,QImage,QPixmap
from PySide6.QtCore import QPointF
from image_overlay import OverlayImage
from overlay_renderer import CalibratedRenderer
from mesh_data import validate_mesh
from scene_geometry import project_camera
from lens_warp import warp_rgba

fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);v=desktop.Viewport();v.pose=np.eye(4);r=CalibratedRenderer()

def pixels(image,premultiplied=False):
    image=image.convertToFormat(QImage.Format_RGBA8888_Premultiplied if premultiplied else QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

try:
    camera=('PINHOLE',200,200,[100,100,100,100])
    v.points=np.array([[1,1,-5,1,0,0],[0,0,5,0,1,0]],np.float32)
    data=pixels(r.render(v,camera,QSize(200,200),points=True,objects=False,point_size=5.))
    assert data[80,120,0]>200 and data[80,120,3]==255
    assert data[100,100,3]==0,'Behind-camera point rendered'
    vertices=np.array([[-2,-2,-5],[2,-2,-5],[0,2,-5],[-4,-4,-10],[4,-4,-10],[0,4,-10]],float)
    v.set_mesh(validate_mesh(vertices,np.array([[0,1,2],[3,4,5]]),np.array([[0,1,0]]*3+[[1,0,0]]*3)))
    data=pixels(r.render(v,camera,QSize(200,200),mesh=True,objects=False))
    assert data[100,100,1]>150 and data[100,100,0]<5,'Hidden face leaked through surface'
    v.points=np.array([[0,0,-3,0,0,1]],np.float32)
    data=pixels(r.render(v,camera,QSize(200,200),mesh=True,points=True,objects=False,point_size=5.))
    assert data[100,100,2]>200,'Point in front of mesh is missing'
    v.points=np.array([[0,0,-12,0,0,1]],np.float32)
    data=pixels(r.render(v,camera,QSize(200,200),mesh=True,points=True,objects=False,point_size=5.))
    assert data[100,100,1]>150 and data[100,100,2]<5,'Point behind mesh leaked through'
    for camera in [('SIMPLE_RADIAL',200,200,[100,100,100,.3]),('OPENCV',200,200,[100,110,100,100,.1,.02,.004,-.003])]:
        v.points=np.array([[2,1,-5,1,0,0]],np.float32)
        rendered=r.render(v,camera,QSize(200,200),points=True,objects=False,point_size=7.)
        data=pixels(rendered)
        uv=project_camera(np.array([[2,-1,5]]),camera)[0]
        x,y=np.floor(uv).astype(int)
        assert data[y,x,0]>150 and data[y,x,3]>150,(camera,uv,data[y,x])
        r.context.makeCurrent(r.surface)
        reference=warp_rgba(pixels(r.framebuffer.toImage()),r.mapping)
        r.context.doneCurrent()
        # Compare premultiplied pixels, as used by the old CPU warp for compositing.
        # GPU bilinear sampling may round by a couple of levels at transparent edges.
        assert np.max(abs(pixels(rendered,True).astype(int)-reference.astype(int)))<=3,'GPU lens warp differs from calibrated CPU reference'
    # A triangle crossing the camera plane must be clipped in homogeneous space.
    v.set_mesh(validate_mesh(np.array([[-.5,-.5,-2],[.5,-.5,-2],[0,.5,1]]),np.array([[0,1,2]]),np.array([[0,1,0]]*3)))
    data=pixels(r.render(v,('PINHOLE',200,200,[100,100,100,100]),QSize(200,200),mesh=True,objects=False))
    assert 0<np.count_nonzero(data[:,:,3])<40000
    # Raster output and geometry share the same transform through Fit, 100% and pan.
    canvas=OverlayImage('',v);canvas.resize(400,400);canvas.set_native_size(QSize(200,200));base=QImage(200,200,QImage.Format_RGB32);base.fill(0)
    canvas.setPixmap(QPixmap.fromImage(base));canvas.camera=('PINHOLE',200,200,[100,100,100,100]);canvas.enabled_overlay=False;canvas.enabled_points=True;canvas.opacity=1
    v.points=np.array([[1,1,-5,1,0,0]],np.float32);canvas.show();app.processEvents()
    for zoom,pan in ((None,QPointF()),(1.,QPointF(20,15))):
        canvas.zoom=zoom;canvas.pan=pan;rect=canvas.image_rect();raster=pixels(canvas.grab().toImage())
        x=round((rect.left()+.6*rect.width())*canvas.devicePixelRatioF());y=round((rect.top()+.4*rect.height())*canvas.devicePixelRatioF())
        assert raster[y,x,0]>180,'Zoomed overlay lost image registration'
    canvas.renderer.close();canvas.close()
    # Cached primitives must update after edits, selection and visibility changes.
    import copy
    camera=('PINHOLE',200,200,[100,100,100,100]);v.pose=np.eye(4)
    cube=v.add_primitive('Cube');cube.update(position=[0,0,-5],scale=.5,color=[.4,.2,.1]);v.selected=-1
    def objects_image():return pixels(r.render(v,camera,QSize(200,200)))
    original=copy.deepcopy(cube);first=objects_image();geometry=v.objects_preview()
    assert first[100,100,3]==255
    v.pose[0,3]=.1;objects_image();assert v.objects_preview() is geometry,'Camera movement rebuilt static geometry'
    v.pose=np.eye(4);cube['position'][0]=2;shifted=objects_image()
    assert shifted[100,100,3]==0 and shifted[100,140,3]==255,'Cached overlay ignored translation'
    cube.update(copy.deepcopy(original));assert np.array_equal(objects_image(),first),'Restored transform did not restore pixels'
    cube['rotation'][2]=45;assert not np.array_equal(objects_image(),first),'Cached overlay ignored rotation'
    cube.update(copy.deepcopy(original));cube['scale']=1.;assert np.count_nonzero(objects_image()[:,:,3])>np.count_nonzero(first[:,:,3])
    cube.update(copy.deepcopy(original));v.selected=0;assert not np.array_equal(objects_image(),first),'Selection highlight is stale'
    for shading in ('Wireframe','Solid + wire','Solid','Vertex color'):
        v.shading=shading;assert np.count_nonzero(objects_image()[:,:,3])>0
    cube['visible']=False;assert np.count_nonzero(objects_image()[:,:,3])==0,'All-hidden objects left stale geometry'
    cube['visible']=True;assert np.count_nonzero(objects_image()[:,:,3])>0
    v.objects=[];assert np.count_nonzero(objects_image()[:,:,3])==0,'Deleted object remains in overlay'
    print('PASS cached primitives: camera motion, move/rotate/scale, restore, selection, shading, hide/show and delete',flush=True)
    print('PASS GPU calibrated point locations, radial/OpenCV raster warp, front/back depth occlusion and near-plane clipping',flush=True)
finally:r.close();v.close()
