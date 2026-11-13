"""Measured/model pixel residuals; no scene-root or display scaling in the error."""
from dataclasses import dataclass
import numpy as np
from camera_track import WORLD,quaternion_matrix
from scene_geometry import project_camera
from track_data import VALID


@dataclass
class Residuals:
    observation_indices: np.ndarray
    point_ids: np.ndarray
    measured: np.ndarray
    projected: np.ndarray
    errors: np.ndarray
    unprojectable: int


def calculate_residuals(tracks,frame,camera,current_pose=None):
    image=tracks.images[tracks.image_by_frame[frame]]
    indices=np.flatnonzero(image.states==VALID)
    rows=np.fromiter((tracks.point_rows[int(point_id)] for point_id in image.point_ids[indices]),dtype=np.int64,count=len(indices))
    xyz=tracks.xyz[rows]
    if current_pose is None:
        camera_xyz=xyz@quaternion_matrix(image.quaternion).T+image.translation
    else:
        # Current camera is camera-to-world in the app's Z-up/OpenGL coordinates.
        inverse=np.diag([1.,-1.,-1.,1.])@np.linalg.inv(current_pose)
        camera_xyz=(xyz@WORLD.T)@inverse[:3,:3].T+inverse[:3,3]
    front=np.isfinite(camera_xyz).all(axis=1)&(camera_xyz[:,2]>1e-8)
    projected=np.full((len(indices),2),np.nan,dtype=np.float64)
    with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
        projected[front]=project_camera(camera_xyz[front],camera)
    good=front&np.isfinite(projected).all(axis=1)
    measured=image.xy[indices[good]];projected=projected[good]
    delta=projected-measured;errors=np.hypot(delta[:,0],delta[:,1])
    finite=np.isfinite(errors)
    return Residuals(indices[good][finite],image.point_ids[indices[good]][finite],measured[finite],
                     projected[finite],errors[finite],int(len(indices)-np.count_nonzero(finite)))


class ResidualCache:
    """A single frame, invalidated by model/lens/frame/pose changes (including Undo)."""
    def __init__(self):self.key=None;self.result=None
    def clear(self):self.key=None;self.result=None
    def get(self,tracks,frame,camera,pose,original):
        key=(id(tracks),frame,repr(camera),None if original else np.asarray(pose).tobytes())
        if key!=self.key:
            self.result=calculate_residuals(tracks,frame,camera,None if original else pose);self.key=key
        return self.result


def display_indices(result,minimum,limit):
    indices=np.flatnonzero(result.errors>=minimum)
    # Show the worst residuals first, with deterministic ordering for equal errors.
    return indices[np.argsort(-result.errors[indices],kind='stable')[:limit]]
