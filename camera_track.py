"""Non-destructive camera corrections in the Z-up reconstruction coordinate system."""
import hashlib
import json
import numpy as np

WORLD = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)


def quaternion_matrix(q):
    w, x, y, z = np.asarray(q) / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def camera_matrix(pose):
    if 'matrix' in pose:
        return np.array(pose['matrix'], dtype=float)
    r = quaternion_matrix(pose['q'])
    m = np.eye(4)
    m[:3, :3] = WORLD @ r.T @ np.diag([1, -1, -1])
    m[:3, 3] = WORLD @ (-r.T @ np.asarray(pose['t']))
    return m


def rotation_quaternion(r):
    # Symmetric eigensystem also handles rotations close to 180 degrees.
    x, y, z = r[0, 0], r[1, 1], r[2, 2]
    k = np.array([[x-y-z, r[0,1]+r[1,0], r[0,2]+r[2,0], r[2,1]-r[1,2]],
                  [r[0,1]+r[1,0], y-x-z, r[1,2]+r[2,1], r[0,2]-r[2,0]],
                  [r[0,2]+r[2,0], r[1,2]+r[2,1], z-x-y, r[1,0]-r[0,1]],
                  [r[2,1]-r[1,2], r[0,2]-r[2,0], r[1,0]-r[0,1], x+y+z]]) / 3
    q = np.linalg.eigh(k)[1][:, -1]
    return q[[3, 0, 1, 2]]


def interpolate_matrix(a, b, weight):
    qa, qb = rotation_quaternion(a[:3, :3]), rotation_quaternion(b[:3, :3])
    dot = float(qa @ qb)
    if dot < 0:
        qb = -qb
        dot = -dot
    if dot > .9995:
        q = (1-weight)*qa + weight*qb
    else:
        angle = np.arccos(np.clip(dot, -1, 1))
        q = (np.sin((1-weight)*angle)*qa + np.sin(weight*angle)*qb)/np.sin(angle)
    result = np.eye(4)
    result[:3, :3] = quaternion_matrix(q)
    result[:3, 3] = (1-weight)*a[:3, 3] + weight*b[:3, 3]
    return result


def validate_matrix(value):
    m = np.asarray(value, dtype=float)
    if (m.shape != (4, 4) or not np.isfinite(m).all() or
            not np.allclose(m[3], [0, 0, 0, 1], atol=1e-7) or
            not np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3), atol=1e-6) or
            not np.isclose(np.linalg.det(m[:3, :3]), 1, atol=1e-6)):
        raise ValueError('Camera correction must be a finite rigid transform (no scale or reflection).')
    return m.tolist()


class CameraTrack:
    def __init__(self, poses):
        self.poses = poses
        self.frames = np.array([p['frame'] for p in poses], dtype=int)
        self.by_frame = {p['frame']: p for p in poses}
        source = [{k: p[k] for k in ('frame', 'name', 'camera', 'q', 't')} for p in poses]
        self.fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        self.original = np.array([camera_matrix(p) for p in source])
        self.history = []
        self.saved = {}
        self.cache = {}
        self.revision = 0

    def edits(self):
        return {str(p['frame']): p['matrix'] for p in self.poses if 'matrix' in p}

    @property
    def dirty(self):
        return self.edits() != self.saved

    def replace(self, edits, remember=True):
        checked = {}
        for frame, value in edits.items():
            if str(int(frame)) != str(frame) or int(frame) not in self.by_frame:
                raise ValueError('Correction refers to an unregistered frame.')
            checked[str(frame)] = validate_matrix(value)
        if remember:
            self.history.append(self.edits())
            self.history = self.history[-100:]
        for p in self.poses:
            p.pop('matrix', None)
            if str(p['frame']) in checked:
                p['matrix'] = checked[str(p['frame'])]
        self.cache.clear()
        self.revision += 1

    def set_matrix(self, frame, matrix):
        edits = self.edits()
        edits[str(frame)] = validate_matrix(matrix)
        self.replace(edits)

    def reset(self, frame):
        edits = self.edits()
        edits.pop(str(frame), None)
        self.replace(edits)

    def undo(self):
        if self.history:
            self.replace(self.history.pop(), remember=False)

    def interpolate(self, frame):
        i = list(self.frames).index(frame)
        if i == 0 or i == len(self.frames)-1:
            raise ValueError('Interpolation needs a solved frame on both sides.')
        a, b = self.poses[i-1], self.poses[i+1]
        weight = (frame-a['frame'])/(b['frame']-a['frame'])
        self.set_matrix(frame, interpolate_matrix(camera_matrix(a), camera_matrix(b), weight))

    def values(self, channel, original=False):
        key = (channel, original)
        if key in self.cache:
            return self.cache[key]
        matrices = self.original if original else np.array([camera_matrix(p) for p in self.poses])
        if channel == 0:
            self.cache[key] = matrices[:, :3, 3]
            return self.cache[key]
        values = np.zeros(len(matrices))
        if len(matrices) > 1:
            gaps = np.diff(self.frames)
            if channel == 1:
                values[1:] = np.linalg.norm(np.diff(matrices[:, :3, 3], axis=0), axis=1)/gaps
            else:
                r = matrices[:, :3, :3]
                relative = np.einsum('nji,njk->nik', r[:-1], r[1:])
                values[1:] = np.degrees(np.arccos(np.clip((np.trace(relative, axis1=1, axis2=2)-1)/2, -1, 1)))/gaps
        self.cache[key] = values[:, None]
        return self.cache[key]

    def document(self):
        return dict(version=1, model=self.fingerprint, cameras=self.edits())

    def load_document(self, document):
        if document.get('version') != 1 or document.get('model') != self.fingerprint:
            raise ValueError('Corrections belong to a different reconstruction.')
        self.replace(document['cameras'])
        self.saved = self.edits()
