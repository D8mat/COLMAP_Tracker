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


if __name__ == '__main__': unittest.main()
