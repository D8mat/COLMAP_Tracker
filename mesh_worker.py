"""Cancellable external job: estimate oriented normals, then COLMAP Poisson mesh."""
import argparse
import json
import subprocess
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from pipeline import read_model
from camera_track import WORLD, camera_matrix, CameraTrack
from mesh_data import write_ply, read_ply, save_mesh


def observing_centers(model, poses, points):
    centers_by_name={p['name']:camera_matrix(p)[:3,3] for p in poses}
    centers={};lines=iter((Path(model)/'images.txt').read_text().splitlines())
    for line in lines:
        if not line or line.startswith('#'):continue
        values=line.split(maxsplit=9);centers[int(values[0])]=centers_by_name[values[9]];next(lines,None)
    hints=[];good=[]
    for line in (Path(model)/'points3D.txt').read_text().splitlines():
        if not line or line.startswith('#'):continue
        values=line.split();observations=[centers[int(i)] for i in values[8::2] if int(i) in centers]
        good.append(len(observations)>=4 and float(values[7])<=2.)
        hints.append(np.mean(observations,axis=0) if observations else points[len(hints)])
    return np.asarray(hints),np.asarray(good)


def build(model, output, colmap, depth=8, limit=80000, trim=6.):
    folder = Path(output); folder.mkdir(parents=True, exist_ok=True)
    print('Reading sparse reconstruction…', flush=True)
    _, poses, source = read_model(model,with_tracks=False)
    points = np.array([p[0] for p in source]) @ WORLD.T
    colors = np.array([p[1] for p in source])
    hints, reliable = observing_centers(model,poses,points)
    keep = np.isfinite(points).all(axis=1) & reliable
    points, colors, hints = points[keep], colors[keep], hints[keep]
    if len(points) < 100: raise ValueError('At least 100 reliable points (4 observations, reprojection error <= 2 pixels) are required.')
    # A few distant triangulation errors must not determine Poisson's octree scale.
    lower,upper=np.percentile(points,[.5,99.5],axis=0)
    margin=np.maximum((upper-lower)*.05,1e-6)
    bounded=((points>=lower-margin)&(points<=upper+margin)).all(axis=1)
    points,colors,hints=points[bounded],colors[bounded],hints[bounded]
    # Spatial voxel sampling retains geometry across the entire scene.
    extent = np.linalg.norm(np.percentile(points, 99, axis=0)-np.percentile(points, 1, axis=0))
    voxel = max(extent/500, 1e-8)
    while len(points) > limit:
        _, indices = np.unique(np.floor(points/voxel).astype(np.int64), axis=0, return_index=True)
        if len(indices) <= limit:
            points, colors, hints = points[indices], colors[indices], hints[indices]; break
        voxel *= 1.3
    tree = cKDTree(points)
    distance, _ = tree.query(points, k=8, workers=4)
    spacing = distance[:, -1]
    valid = spacing < np.percentile(spacing, 98)
    points, colors, hints = points[valid], colors[valid], hints[valid]
    if len(points) < 100: raise ValueError('Too few reliable points after filtering.')
    tree = cKDTree(points)
    print(f'Estimating normals for {len(points):,} points…', flush=True)
    normals = np.empty_like(points)
    for start in range(0, len(points), 4000):
        part = points[start:start+4000]
        _, neighbours = tree.query(part, k=min(24, len(points)), workers=4)
        local = points[neighbours]
        local -= local.mean(axis=1, keepdims=True)
        covariance = np.einsum('nki,nkj->nij', local, local)
        normals[start:start+len(part)] = np.linalg.eigh(covariance)[1][:, :, 0]
    # Use only cameras which actually observed each point, not an unrelated nearby view.
    facing = np.sum(normals*(hints-points), axis=1)
    normals[facing < 0] *= -1
    oriented = folder/'oriented_points.ply'
    write_ply(oriented, points, colors, point_normals=normals)
    print(f'COLMAP Poisson surface reconstruction · depth {depth}…', flush=True)
    output_ply = folder/'surface.ply'
    subprocess.run([colmap, 'poisson_mesher', '--input_path', str(oriented), '--output_path', str(output_ply),
                    '--PoissonMeshing.depth', str(depth), '--PoissonMeshing.trim', str(trim),
                    '--PoissonMeshing.num_threads', '4'], check=True)
    mesh = read_ply(output_ply)
    print('Removing extrapolated surface and transferring point colors…', flush=True)
    distance, nearest = tree.query(mesh['vertices'], workers=4)
    local_spacing = tree.query(points, k=8, workers=4)[0][:, -1]
    support = distance < np.maximum(local_spacing[nearest]*2, np.median(local_spacing)*.5)
    keep_faces = support[mesh['faces']].all(axis=1)
    centers=mesh['vertices'][mesh['faces']].mean(axis=1)
    center_distance,center_nearest=tree.query(centers,workers=4)
    keep_faces &= center_distance < np.maximum(local_spacing[center_nearest]*1.5,np.median(local_spacing)*.5)
    mesh['faces'] = mesh['faces'][keep_faces]
    if not len(mesh['faces']): raise ValueError('No supported surface. Try a lower trim value.')
    mesh['colors'] = colors[nearest].astype(np.float32)
    used, inverse = np.unique(mesh['faces'], return_inverse=True)
    mesh['vertices'] = mesh['vertices'][used]; mesh['colors'] = mesh['colors'][used]
    mesh['faces'] = inverse.reshape(-1, 3).astype(np.int32)
    fingerprint = CameraTrack(poses).fingerprint
    save_mesh(folder/'surface.npz', mesh, fingerprint)
    write_ply(output_ply, mesh['vertices'], mesh['colors'], mesh['faces'])
    (folder/'settings.json').write_text(json.dumps(dict(model=str(model), fingerprint=fingerprint, depth=depth, limit=limit, trim=trim)), encoding='utf-8')
    print(f'Done: {len(mesh["vertices"]):,} vertices / {len(mesh["faces"]):,} triangles. Sparse approximation, not dense photogrammetry.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True); parser.add_argument('--output', required=True); parser.add_argument('--colmap', required=True)
    parser.add_argument('--depth', type=int, default=8); parser.add_argument('--limit', type=int, default=80000); parser.add_argument('--trim', type=float, default=6.)
    args = parser.parse_args()
    build(args.model, args.output, args.colmap, args.depth, args.limit, args.trim)
