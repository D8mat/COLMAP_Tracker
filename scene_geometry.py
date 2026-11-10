"""Shared geometry, transforms and calibrated projection; no GUI dependencies."""
import math
import numpy as np


def read_raw_cameras(project):
    import struct
    models=list((project/'sparse').glob('*/cameras.bin'))
    def count(path):
        with (path.parent/'images.bin').open('rb') as f:return struct.unpack('<Q',f.read(8))[0]
    path=max(models,key=count)
    specs={0:('SIMPLE_PINHOLE',3),1:('PINHOLE',4),2:('SIMPLE_RADIAL',4),3:('RADIAL',5),4:('OPENCV',8)}
    result={}
    with path.open('rb') as f:
        for _ in range(struct.unpack('<Q',f.read(8))[0]):
            cid,model,width,height=struct.unpack('<iiQQ',f.read(24));name,n=specs[model]
            result[cid]=(name,width,height,list(struct.unpack('<'+'d'*n,f.read(n*8))))
    return result


def identity_transform():
    return dict(position=[0.,0.,0.],rotation=[0.,0.,0.],scale=1.)


def transform_matrix(item):
    x,y,z=np.radians(item['rotation']); cx,sx=np.cos(x),np.sin(x); cy,sy=np.cos(y),np.sin(y); cz,sz=np.cos(z),np.sin(z)
    rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    matrix=np.eye(4);matrix[:3,:3]=(rz@ry@rx)*item['scale'];matrix[:3,3]=item['position']
    return matrix


def mesh_geometry(kind):
    if kind=='Cube':
        vertices=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)
        faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    elif kind=='Cone':
        # Downward tip is exactly the local origin; the circular base is above it.
        vertices=np.array([[0,0,0]]+[[math.cos(a),math.sin(a),2] for a in np.linspace(0,2*math.pi,24,endpoint=False)])
        faces=[(0,(i+1)%24+1,i+1) for i in range(24)]+[tuple(range(1,25))]
    else:raise ValueError('Unknown primitive: '+kind)
    return vertices,faces


def object_triangles(item):
    v,faces=mesh_geometry(item['kind']);m=transform_matrix(item);v=v@m[:3,:3].T+m[:3,3]
    triangles=[]
    for face in faces:
        for i in range(1,len(face)-1):triangles.append(v[[face[0],face[i],face[i+1]]])
    return triangles


def clip_near(triangle,near=1e-4):
    output=[]
    for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
        ina,inb=a[2]>=near,b[2]>=near
        if ina:output.append(a)
        if ina!=inb:output.append(a+(b-a)*((near-a[2])/(b[2]-a[2])))
    return np.array(output)


def project_camera(vertices,camera):
    model,width,height,p=camera
    x,y=vertices[:,0]/vertices[:,2],vertices[:,1]/vertices[:,2]
    if model in ('SIMPLE_PINHOLE','SIMPLE_RADIAL','RADIAL'):
        fx=fy=p[0];cx,cy=p[1:3];r2=x*x+y*y
        radial=1+(p[3]*r2 if len(p)>3 else 0)+(p[4]*r2*r2 if len(p)>4 else 0)
        x,y=x*radial,y*radial
    elif model in ('PINHOLE','OPENCV'):
        fx,fy,cx,cy=p[:4]
        if model=='OPENCV':
            k1,k2,t1,t2=p[4:8];r2=x*x+y*y;radial=1+k1*r2+k2*r2*r2
            x,y=x*radial+2*t1*x*y+t2*(r2+2*x*x),y*radial+t1*(r2+2*y*y)+2*t2*x*y
    else:raise ValueError('Unsupported overlay camera: '+model)
    return np.column_stack((fx*x+cx,fy*y+cy))
