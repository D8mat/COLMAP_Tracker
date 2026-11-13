import copy
import unittest
import numpy as np
from camera_track import (CameraTrack, camera_matrix, interpolate_matrix,
    quaternion_matrix, rotation_quaternion, WORLD)
from scene_geometry import transform_matrix
from floor_grid import project_floor


def pose_from_matrix(frame, matrix):
    r = (WORLD.T @ matrix[:3, :3] @ np.diag([1, -1, -1])).T
    return dict(frame=frame, name=f'frame_{frame:06d}.jpg', camera=1,
                q=rotation_quaternion(r).tolist(), t=(-r @ WORLD.T @ matrix[:3, 3]).tolist())


def matrix(position=(0, 0, 0), rotation=(0, 0, 0)):
    return transform_matrix(dict(position=position, rotation=rotation, scale=1))


class CameraTests(unittest.TestCase):
    def test_conversion_and_shortest_rotation(self):
        for angles in ([180, 0, 0], [23, 89, -134], [0, 0, 179], [0, 0, -179]):
            m = matrix([1, 2, 3], angles)
            np.testing.assert_allclose(quaternion_matrix(rotation_quaternion(m[:3, :3])), m[:3, :3], atol=1e-12)
            np.testing.assert_allclose(camera_matrix(pose_from_matrix(8, m)), m, atol=1e-12)
        mid = interpolate_matrix(matrix(rotation=[0, 0, 179]), matrix(rotation=[0, 0, -179]), .5)
        np.testing.assert_allclose(mid[:3, :3], matrix(rotation=[0, 0, 180])[:3, :3], atol=1e-10)

    def test_weighted_repair_undo_persistence_and_validation(self):
        poses = [pose_from_matrix(f, matrix([x, 0, 0], [0, 0, angle]))
                 for f, x, angle in [(1, 0, 0), (2, 20, 90), (5, 4, 40)]]
        raw = copy.deepcopy(poses)
        track = CameraTrack(poses)
        self.assertGreater(track.values(1)[1, 0], 19)
        track.interpolate(2)
        np.testing.assert_allclose(camera_matrix(poses[1]), matrix([1, 0, 0], [0, 0, 10]), atol=1e-10)
        np.testing.assert_allclose(track.values(1)[1:, 0], [1, 1], atol=1e-10)
        np.testing.assert_allclose(track.values(2)[1:, 0], [10, 10], atol=1e-10)
        self.assertEqual(poses[1]['q'], raw[1]['q'])
        self.assertTrue(track.dirty)
        doc = track.document()
        restored = CameraTrack(copy.deepcopy(raw)); restored.load_document(doc)
        self.assertFalse(restored.dirty)
        self.assertEqual(restored.edits(), track.edits())
        for invalid in (dict(doc, model='wrong'), dict(doc, cameras={'3': np.eye(4).tolist()}),
                        dict(doc, cameras={'2': np.zeros((4, 4)).tolist()})):
            before = restored.edits()
            with self.assertRaises(ValueError): restored.load_document(invalid)
            self.assertEqual(restored.edits(), before)
        track.reset(2); self.assertEqual(track.edits(), {})
        track.undo(); self.assertEqual(track.document(), doc)
        track.undo(); self.assertEqual(track.edits(), {})
        with self.assertRaises(ValueError): track.interpolate(1)

    def test_floor_visibility_clipping_and_transform(self):
        camera = ('PINHOLE', 640, 480, [500, 500, 320, 240])
        downward = matrix([0, 0, 3])
        uv, axes = project_floor(downward, camera)
        self.assertGreater(len(uv), 0)
        self.assertTrue(np.isfinite(uv).all())
        self.assertTrue((uv >= -1e-10).all() and (uv <= 1+1e-10).all())
        self.assertTrue({1, 2}.issubset(set(axes)))
        self.assertEqual(len(project_floor(matrix([0, 0, 3], [180, 0, 0]), camera)[0]), 0)
        # Camera crosses horizon; distorted endpoints must still be clipped safely.
        tilted = matrix([0, -3, .2], [89, 0, 0])
        uv, _ = project_floor(tilted, ('SIMPLE_RADIAL', 640, 480, [500, 320, 240, .15]))
        self.assertGreater(len(uv), 0)
        self.assertTrue(np.isfinite(uv).all())
        self.assertTrue((uv >= -1e-6).all() and (uv <= 1+1e-6).all())
        moved, _ = project_floor(matrix([0, 0, 6]), camera)
        self.assertNotEqual(len(moved), len(project_floor(downward, camera)[0]))

    def test_neighbour_range_preserves_center_anchors_and_atomic_undo(self):
        poses=[pose_from_matrix(f,matrix([f*f, f%3, 0])) for f in range(1,18)]
        raw=copy.deepcopy(poses);track=CameraTrack(poses)
        track.set_matrix(3,matrix([0,0,0],[0,0,179]))
        track.set_matrix(9,matrix([6,12,18],[0,0,-179]))
        track.set_matrix(15,matrix([12,0,6],[0,0,-167]))
        track.set_matrix(6,matrix([999,0,0]))
        before=copy.deepcopy(poses);edits=copy.deepcopy(track.edits());history=len(track.history)
        targets=track.interpolate_neighbours(9)
        self.assertEqual(targets,list(range(4,9))+list(range(10,15)))
        for f in set(range(1,18))-set(targets):self.assertEqual(poses[f-1],before[f-1])
        np.testing.assert_allclose(camera_matrix(poses[5]),matrix([3,6,9],[0,0,180]),atol=1e-7)
        np.testing.assert_allclose(camera_matrix(poses[11]),matrix([9,6,12],[0,0,-173]),atol=1e-7)
        self.assertEqual(len(track.history),history+1)
        restored=CameraTrack(raw);restored.load_document(track.document())
        self.assertEqual(restored.edits(),track.edits())
        track.undo();self.assertEqual(track.edits(),edits);self.assertEqual(poses,before)

    def test_neighbour_range_edges_gaps_and_invalid_input(self):
        for center,expected in ((1,[2,3,4,5,6]),(9,[4,5,6,7,8]),(5,[2,3,4,6,7,8])):
            track=CameraTrack([pose_from_matrix(f,matrix([f*f,0,0])) for f in range(1,10)])
            before=copy.deepcopy(track.poses)
            self.assertEqual(track.interpolate_neighbours(center),expected)
            for f in (1,center,9):self.assertEqual(track.by_frame[f],before[f-1])
        track=CameraTrack([pose_from_matrix(f,matrix([f*f,0,0])) for f in (1,4,9,11,17)])
        self.assertEqual(track.interpolate_neighbours(9),[4,11])
        np.testing.assert_allclose(camera_matrix(track.by_frame[4])[:3,3],[31,0,0],atol=1e-10)
        np.testing.assert_allclose(camera_matrix(track.by_frame[11])[:3,3],[133,0,0],atol=1e-10)
        self.assertNotIn('matrix',track.by_frame[9])
        before=copy.deepcopy(track.edits());history=len(track.history)
        for frame,radius in ((8,5),(9,0),(9,-1),(9,5.5),(9,True)):
            with self.assertRaises(ValueError):track.interpolate_neighbours(frame,radius)
        self.assertEqual(track.edits(),before);self.assertEqual(len(track.history),history)
        for frames,center in (((1,),1),((1,2),1),((1,2,3),2)):
            track=CameraTrack([pose_from_matrix(f,matrix()) for f in frames])
            self.assertEqual(track.interpolate_neighbours(center),[])
            self.assertEqual(track.history,[]);self.assertEqual(track.edits(),{})

    def test_matrix_cache_matches_poses_and_invalidates_on_undo(self):
        poses=[pose_from_matrix(i,matrix([i,2,3],[i*3,12,20])) for i in range(1,8)]
        track=CameraTrack(poses);first=track.matrices()
        np.testing.assert_allclose(first,[camera_matrix(p) for p in poses]);self.assertIs(first,track.matrices())
        changed=matrix([10,11,12],[20,30,40]);track.set_matrix(4,changed)
        self.assertIsNot(first,track.matrices());np.testing.assert_allclose(track.matrices(),[camera_matrix(p) for p in poses])
        np.testing.assert_allclose(track.values(0),track.matrices()[:,:3,3])
        track.undo();np.testing.assert_allclose(track.matrices(),first)

    def test_signed_translation_axes_and_frame_gaps(self):
        track=CameraTrack([pose_from_matrix(f,matrix(p)) for f,p in
                           [(1,[10,10,10]),(2,[11,8,13]),(5,[14,2,4])]])
        expected=np.array([[0,0,0],[1,-2,3],[1,-2,-3]],float)
        np.testing.assert_allclose(track.values(3),expected,atol=1e-10)
        np.testing.assert_allclose(track.values(1)[:,0],np.linalg.norm(expected,axis=1),atol=1e-10)
        track.set_matrix(2,matrix([11,20,13]))
        updated=track.values(3);np.testing.assert_allclose(updated[:,[0,2]],expected[:,[0,2]],atol=1e-10)
        np.testing.assert_allclose(updated[:,1],[0,10,-6],atol=1e-10)
        np.testing.assert_allclose(track.values(3,original=True),expected,atol=1e-10)
        track.undo();np.testing.assert_allclose(track.values(3),expected,atol=1e-10)


if __name__ == '__main__': unittest.main()
