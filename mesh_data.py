"""Triangle mesh storage, PLY interchange and preview shading (no Qt)."""
from pathlib import Path
import numpy as np


def normals(vertices, faces):
    triangles = vertices[faces]
    flat = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    smooth = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(smooth, faces[:, corner], flat)
    flat /= np.maximum(np.linalg.norm(flat, axis=1, keepdims=True), 1e-12)
    smooth /= np.maximum(np.linalg.norm(smooth, axis=1, keepdims=True), 1e-12)
    return flat, smooth


def validate_mesh(vertices, faces, colors):
    vertices, faces, colors = np.asarray(vertices, float), np.asarray(faces), np.asarray(colors, float)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices) or
            faces.ndim != 2 or faces.shape[1] != 3 or not len(faces) or
            not np.issubdtype(faces.dtype, np.integer) or faces.min() < 0 or faces.max() >= len(vertices) or
            colors.shape != vertices.shape or not np.isfinite(vertices).all() or not np.isfinite(colors).all()):
        raise ValueError('Invalid triangle mesh.')
    return dict(vertices=np.ascontiguousarray(vertices, np.float32), faces=np.ascontiguousarray(faces, np.int32),
                colors=np.ascontiguousarray(np.clip(colors, 0, 1), np.float32))


def save_mesh(path, mesh, model):
    np.savez_compressed(path, version=1, model=model, **{k: mesh[k] for k in ('vertices', 'faces', 'colors')})


def load_mesh(path, model=None):
    with np.load(path, allow_pickle=False) as data:
        if int(data['version']) != 1 or (model is not None and str(data['model']) != model):
            raise ValueError('Mesh belongs to a different reconstruction.')
        result = validate_mesh(data['vertices'], data['faces'], data['colors'])
    result['path'] = str(Path(path).resolve())
    return result


def triangle_buffer(mesh, shading='Solid', smooth=True):
    v, f = mesh['vertices'], mesh['faces']
    if '_normals' not in mesh:
        mesh['_normals'] = normals(v, f)
    flat, vertex = mesh['_normals']
    n = vertex[f] if smooth else np.repeat(flat[:, None], 3, axis=1)
    light = np.array([.25, -.35, .9]); light /= np.linalg.norm(light)
    intensity = .3 + .7*np.abs(n @ light)
    if shading == 'Normals':
        colors = n*.5+.5
    else:
        base = mesh['colors'][f] if shading == 'Vertex color' else np.full((len(f), 3, 3), [.65, .72, .8])
        colors = base*intensity[:, :, None]
    return np.ascontiguousarray(np.concatenate((v[f], colors), axis=2).reshape(-1, 6), np.float32)


def write_ply(path, vertices, colors, faces=None, point_normals=None):
    vertices = np.asarray(vertices)
    header = ['ply', 'format binary_little_endian 1.0', f'element vertex {len(vertices)}',
              'property float x', 'property float y', 'property float z']
    fields = [('x', '<f4'), ('y', '<f4'), ('z', '<f4')]
    if point_normals is not None:
        header += ['property float nx', 'property float ny', 'property float nz']
        fields += [('nx', '<f4'), ('ny', '<f4'), ('nz', '<f4')]
    header += ['property uchar red', 'property uchar green', 'property uchar blue']
    fields += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    if faces is not None:
        header += [f'element face {len(faces)}', 'property list uchar int vertex_indices']
    data = np.empty(len(vertices), dtype=fields)
    for i, name in enumerate(('x', 'y', 'z')): data[name] = vertices[:, i]
    if point_normals is not None:
        for i, name in enumerate(('nx', 'ny', 'nz')): data[name] = point_normals[:, i]
    for i, name in enumerate(('red', 'green', 'blue')): data[name] = np.rint(np.clip(colors[:, i], 0, 1)*255)
    with Path(path).open('wb') as stream:
        stream.write(('\n'.join(header+['end_header'])+'\n').encode('ascii'))
        stream.write(data.tobytes())
        if faces is not None:
            triangles = np.empty(len(faces), dtype=[('n', 'u1'), ('indices', '<i4', (3,))])
            triangles['n'] = 3; triangles['indices'] = faces
            stream.write(triangles.tobytes())


def read_ply(path):
    """Read COLMAP's binary/ASCII mesh output; triangulate polygon faces."""
    types = {'char': 'i1', 'uchar': 'u1', 'short': 'i2', 'ushort': 'u2', 'int': 'i4',
             'uint': 'u4', 'float': 'f4', 'double': 'f8', 'float32': 'f4', 'float64': 'f8',
             'int32': 'i4', 'uint32': 'u4', 'uint8': 'u1'}
    with Path(path).open('rb') as stream:
        if stream.readline().strip() != b'ply': raise ValueError('Not a PLY file.')
        elements = []; encoding = None
        for _ in range(1000):
            words = stream.readline().decode('ascii').split()
            if not words: raise ValueError('Incomplete PLY header.')
            if words[0] == 'end_header': break
            if words[0] == 'format': encoding = words[1]
            if words[0] == 'element': elements.append([words[1], int(words[2]), []])
            if words[0] == 'property': elements[-1][2].append(words[1:])
        else: raise ValueError('PLY header too long.')
        if encoding not in ('ascii', 'binary_little_endian', 'binary_big_endian'): raise ValueError('Unsupported PLY format.')
        endian = '>' if encoding == 'binary_big_endian' else '<'
        vertices = colors = None; faces = []
        for name, count, props in elements:
            if count < 0 or count > 10000000: raise ValueError('PLY is too large.')
            if name == 'vertex' and all(p[0] != 'list' for p in props):
                dtype = np.dtype([(p[1], endian+types[p[0]]) for p in props])
                if encoding == 'ascii':
                    values = np.array([list(map(float, stream.readline().split())) for _ in range(count)])
                    data = {p[1]: values[:, i] for i, p in enumerate(props)}
                else:
                    raw = stream.read(dtype.itemsize*count)
                    if len(raw) != dtype.itemsize*count: raise ValueError('Truncated PLY vertices.')
                    data = np.frombuffer(raw, dtype=dtype)
                vertices = np.column_stack([data[k] for k in ('x', 'y', 'z')])
                if all(k in [p[1] for p in props] for k in ('red', 'green', 'blue')):
                    colors = np.column_stack([data[k] for k in ('red', 'green', 'blue')])/255.
                else: colors = np.full(vertices.shape, .7)
            elif name == 'face':
                for _ in range(count):
                    words = iter(stream.readline().split()) if encoding == 'ascii' else None
                    for prop in props:
                        if prop[0] == 'list':
                            n = int(next(words)) if words is not None else int(np.frombuffer(stream.read(np.dtype(types[prop[1]]).itemsize), dtype=endian+types[prop[1]])[0])
                            if n < 0 or n > 10000: raise ValueError('Invalid PLY polygon.')
                            indices = [int(next(words)) for _ in range(n)] if words is not None else np.frombuffer(stream.read(n*np.dtype(types[prop[2]]).itemsize), dtype=endian+types[prop[2]])
                            if prop[-1] in ('vertex_indices', 'vertex_index'):
                                faces.extend((indices[0], indices[i], indices[i+1]) for i in range(1, n-1))
                        elif words is not None: next(words)
                        else: stream.read(np.dtype(types[prop[0]]).itemsize)
            else: raise ValueError('Unsupported PLY element: '+name)
    if vertices is None or not faces: raise ValueError('Mesher produced no surface; try less trimming or more points.')
    return validate_mesh(vertices, np.array(faces), colors)
