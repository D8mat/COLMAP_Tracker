"""Calibrated Z-up ground overlay with near-plane and image-rectangle clipping."""
import numpy as np
from functools import lru_cache
from scene_geometry import project_camera


@lru_cache(maxsize=8)
def floor_segments(spacing=1., height=0.):
    coordinates = np.linspace(-10*spacing, 10*spacing, 41)
    segments, axes = [], []
    for i in range(-10, 11):
        for direction in (0, 1):
            points = np.zeros((41, 3))
            points[:, direction] = coordinates
            points[:, 1-direction] = i*spacing
            points[:, 2] = height
            segments.extend(np.stack((points[:-1], points[1:]), axis=1))
            axes.extend([direction+1 if i == 0 else 0]*40)
    return np.asarray(segments), np.asarray(axes)


def project_floor(camera_pose, camera, spacing=1., height=0.):
    segments, axes = floor_segments(spacing, height)
    inv = np.linalg.inv(camera_pose)
    cv = (segments @ inv[:3, :3].T + inv[:3, 3])*[1, -1, -1]
    near = 1e-3
    keep = np.max(cv[:, :, 2], axis=1) >= near
    cv, axes = cv[keep], axes[keep]
    if not len(cv):
        return np.empty((0, 2, 2)), axes
    for end in (0, 1):
        mask = cv[:, end, 2] < near
        a, b = cv[mask, end].copy(), cv[mask, 1-end]
        t = (near-a[:, 2])/(b[:, 2]-a[:, 2])
        cv[mask, end] = a+(b-a)*t[:, None]
    uv = project_camera(cv.reshape(-1, 3), camera).reshape(-1, 2, 2)
    uv /= np.array([camera[1], camera[2]])
    # Liang-Barsky clipping keeps huge near-horizon/distorted coordinates out of Qt.
    a, delta = uv[:, 0], uv[:, 1]-uv[:, 0]
    low, high = np.zeros(len(uv)), np.ones(len(uv))
    valid = np.isfinite(uv).all(axis=(1, 2))
    for axis in (0, 1):
        parallel = abs(delta[:, axis]) < 1e-15
        valid &= ~parallel | ((a[:, axis] >= 0) & (a[:, axis] <= 1))
        denominator = np.where(parallel, 1., delta[:, axis])
        t0, t1 = -a[:, axis]/denominator, (1-a[:, axis])/denominator
        low = np.maximum(low, np.where(parallel, 0, np.minimum(t0, t1)))
        high = np.minimum(high, np.where(parallel, 1, np.maximum(t0, t1)))
    valid &= low <= high
    result = np.stack((a+low[:, None]*delta, a+high[:, None]*delta), axis=1)
    return result[valid], axes[valid]
