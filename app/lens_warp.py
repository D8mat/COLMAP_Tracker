"""Inverse calibrated distortion for raster overlays (avoids warped triangle edges)."""
import numpy as np


def lens_parameters(camera):
    model, width, height, p = camera
    if model in ('SIMPLE_PINHOLE', 'SIMPLE_RADIAL', 'RADIAL'):
        return (p[0], p[0], p[1], p[2]), (p[3] if len(p)>3 else 0, p[4] if len(p)>4 else 0, 0, 0)
    if model in ('PINHOLE', 'OPENCV'):
        return tuple(p[:4]), tuple(p[4:8]) if model == 'OPENCV' else (0, 0, 0, 0)
    raise ValueError('Unsupported overlay camera: '+model)


def distortion_map(camera, output_width, output_height):
    intrinsics, distortion = lens_parameters(camera)
    if not any(distortion): return None
    fx, fy, cx, cy = intrinsics; k1, k2, p1, p2 = distortion
    yy, xx = np.mgrid[:output_height, :output_width]
    xd = ((xx+.5)*camera[1]/output_width-cx)/fx
    yd = ((yy+.5)*camera[2]/output_height-cy)/fy
    x, y = xd.copy(), yd.copy()
    for _ in range(15):
        r2 = x*x+y*y; radial = 1+k1*r2+k2*r2*r2
        ex = x*radial+2*p1*x*y+p2*(r2+2*x*x)-xd
        ey = y*radial+p1*(r2+2*y*y)+2*p2*x*y-yd
        dx, dy = 2*x*(k1+2*k2*r2), 2*y*(k1+2*k2*r2)
        a = radial+x*dx+2*p1*y+6*p2*x
        b = x*dy+2*p1*x+2*p2*y
        c = y*dx+2*p1*x+2*p2*y
        d = radial+y*dy+6*p1*y+2*p2*x
        det = a*d-b*c; det = np.where(abs(det)>1e-10, det, 1.)
        x -= np.clip((d*ex-b*ey)/det, -.25, .25)
        y -= np.clip((a*ey-c*ex)/det, -.25, .25)
    r2 = x*x+y*y; radial = 1+k1*r2+k2*r2*r2
    residual = np.hypot(x*radial+2*p1*x*y+p2*(r2+2*x*x)-xd, y*radial+p1*(r2+2*y*y)+2*p2*x*y-yd)
    valid = np.isfinite(x) & np.isfinite(y) & (residual < 1e-5)
    u, v = x*fx+cx, y*fy+cy
    # Bound unusual calibrations rather than allocate an unbounded offscreen image.
    valid &= (abs(u-cx)<camera[1]*2) & (abs(v-cy)<camera[2]*2)
    if not valid.any(): raise ValueError('Lens distortion cannot be inverted in the image.')
    left, top = np.floor(u[valid].min())-2, np.floor(v[valid].min())-2
    right, bottom = np.ceil(u[valid].max())+2, np.ceil(v[valid].max())+2
    rw = max(2, int(np.ceil((right-left)*output_width/camera[1])))
    rh = max(2, int(np.ceil((bottom-top)*output_height/camera[2])))
    sx = np.where(valid, (u-left)*rw/(right-left)-.5, 0)
    sy = np.where(valid, (v-top)*rh/(bottom-top)-.5, 0)
    ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
    valid &= (ix>=0)&(iy>=0)&(ix<rw-1)&(iy<rh-1)
    ix, iy = np.clip(ix,0,rw-2), np.clip(iy,0,rh-2)
    return dict(camera=('PINHOLE',right-left,bottom-top,[fx,fy,cx-left,cy-top]),size=(rw,rh),
                x=ix,y=iy,wx=(sx-ix).astype(np.float32),wy=(sy-iy).astype(np.float32),valid=valid)


def warp_rgba(source, mapping):
    x,y=mapping['x'],mapping['y'];wx,wy=mapping['wx'][...,None],mapping['wy'][...,None]
    output=(source[y,x]*(1-wx)+source[y,x+1]*wx)*(1-wy)+(source[y+1,x]*(1-wx)+source[y+1,x+1]*wx)*wy
    output[~mapping['valid']]=0
    return np.ascontiguousarray(np.clip(output,0,255),np.uint8)
