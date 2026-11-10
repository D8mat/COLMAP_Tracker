"""Picking and transform math shared by viewport interaction tests."""
import math
import numpy as np


def ray_triangle(origin,direction,triangle):
    a,b,c=triangle;e1=b-a;e2=c-a;p=np.cross(direction,e2);det=e1@p
    if abs(det)<1e-10:return None
    t=origin-a;u=(t@p)/det
    if u<0 or u>1:return None
    q=np.cross(t,e1);v=(direction@q)/det
    if v<0 or u+v>1:return None
    distance=(e2@q)/det
    return float(distance) if distance>=0 else None


def axis_parameter(origin,direction,pivot,axis):
    dot=float(direction@axis);denom=1-dot*dot
    if denom<1e-5:return None
    w=origin-pivot
    return float((axis@w-dot*(direction@w))/denom)


def plane_vector(origin,direction,pivot,axis):
    denom=float(direction@axis)
    if abs(denom)<1e-5:return None
    distance=float((pivot-origin)@axis)/denom
    if distance<0:return None
    v=origin+distance*direction-pivot;n=np.linalg.norm(v)
    return v/n if n>1e-8 else None


def axis_rotation(axis,angle):
    x,y,z=axis;c=math.cos(angle);s=math.sin(angle)
    cross=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return c*np.eye(3)+(1-c)*np.outer(axis,axis)+s*cross


def euler_xyz(rotation):
    y=math.asin(float(np.clip(-rotation[2,0],-1,1)))
    if abs(math.cos(y))>1e-7:x=math.atan2(rotation[2,1],rotation[2,2]);z=math.atan2(rotation[1,0],rotation[0,0])
    else:x=math.atan2(-rotation[1,2],rotation[1,1]);z=0.
    return np.degrees([x,y,z]).tolist()


def segment_distance(point,a,b):
    ab=b-a;t=float(np.clip((point-a)@ab/max(float(ab@ab),1e-12),0,1))
    return float(np.linalg.norm(point-(a+t*ab))),t
