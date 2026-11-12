"""Analytical GPU checks independent of the sample reconstruction."""
import numpy as np
import desktop
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from PySide6.QtGui import QSurfaceFormat,QImage
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
    print('PASS GPU calibrated point locations, radial/OpenCV raster warp, front/back depth occlusion and near-plane clipping',flush=True)
finally:r.close();v.close()
