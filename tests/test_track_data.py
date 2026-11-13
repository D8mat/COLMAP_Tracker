import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Import identity, data validity and compatibility with existing consumers."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from pipeline import ROOT,read_model
from track_data import VALID,UNTRIANGULATED,MISSING_LINK,MISSING_POINT,INVALID_XY


class TrackDataTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir=ROOT);self.folder=Path(self.directory.name)
        (self.folder/'cameras.txt').write_text('17 PINHOLE 100 80 90 90 50 40\n')

    def tearDown(self):self.directory.cleanup()

    def load(self,images,points):
        (self.folder/'images.txt').write_text(images,encoding='utf-8');(self.folder/'points3D.txt').write_text(points,encoding='utf-8')
        return read_model(self.folder)

    def test_sparse_ids_and_empty_observations(self):
        big=2**53+7
        model=self.load(f'44 1 0 0 0 0 0 0 17 take name_000010.jpg\n10.25 20.5 {big} 15 30 -1\n'
                        '3 1 0 0 0 1 2 3 17 frame_000002.jpg\n\n'
                        f'8 1 0 0 0 0 0 0 17 frame_000006.jpg\n8 9 {big}\n',
                        f'{big} 1 2 3 255 128 0 0.5 44 0 8 0\n99 4 5 6 0 0 0 0\n')
        cameras,poses,points=model;data=model.tracks
        self.assertEqual(len(model),3);self.assertEqual([p['image_id'] for p in poses],[3,8,44])
        self.assertEqual(data.image_by_frame,{10:44,2:3,6:8});self.assertEqual(data.images[44].name,'take name_000010.jpg')
        self.assertEqual(int(data.images[44].point_ids[0]),big);self.assertEqual(data.point_rows[big],0)
        np.testing.assert_array_equal(data.point_track(big),[[44,0],[8,0]])
        np.testing.assert_array_equal(data.images[44].states,[VALID,UNTRIANGULATED])
        self.assertEqual(data.images[3].xy.shape,(0,2));self.assertEqual(data.track_lengths.tolist(),[2,0])
        self.assertAlmostEqual(data.images[44].time_seconds(30000/1001),9/(30000/1001))
        self.assertEqual(points[0][0],(1.,2.,3.));self.assertEqual(data.invalid_links,0)
        self.assertEqual(data.counts.tolist(),[1,2,0,0,0])
        with self.assertRaises(ValueError):data.images[44].xy[0,0]=100
        poses[-1]['q'][0]=.5;self.assertEqual(data.images[44].quaternion,(1.,0.,0.,0.))

    def test_geometry_only_import_matches_full_model(self):
        model=self.load('44 1 0 0 0 0 0 0 17 frame_000001.jpg\n10 20 90\n',
                        '90 1 2 3 255 128 0 0.5 44 0\n')
        geometry=read_model(self.folder,with_tracks=False)
        self.assertEqual(tuple(model),tuple(geometry));self.assertIsNone(geometry.tracks)

    def test_broken_references_retained_and_classified(self):
        model=self.load('4 1 0 0 0 0 0 0 17 frame_000001.jpg\n'
                        '10 20 90 11 21 91 12 22 999 nan 23 90 14 24 -1\n',
                        '90 1 2 3 255 0 0 1 4 0 4 0 4 1 4 3 404 0 4 99\n'
                        '91 3 2 1 255 0 0 1\n')
        data=model.tracks
        self.assertEqual(data.images[4].states.tolist(),[VALID,MISSING_LINK,MISSING_POINT,INVALID_XY,UNTRIANGULATED])
        self.assertEqual(data.invalid_links,5);self.assertEqual(len(data.point_track(90)),6)
        self.assertEqual(data.point_track(90,valid_only=True).tolist(),[[4,0]])
        self.assertEqual(data.track_lengths.tolist(),[1,0]);self.assertEqual(len(data.issue_examples),5)

    def test_comments_and_empty_model(self):
        model=self.load(' # comment\n',' # comment\n')
        self.assertEqual(model.tracks.xyz.shape,(0,3));self.assertEqual(model.tracks.track_links.shape,(0,2))
        self.assertEqual(model.tracks.counts.sum(),0)

    def test_malformed_data_fails_before_replacing_model(self):
        pose='4 1 0 0 0 0 0 0 17 frame_000001.jpg\n'
        for images,points in [(pose,''),(pose+'10 20\n',''),(pose+'1 2 -2\n',''),
                              (pose+'\n'+pose+'\n',''),
                              (pose+'\n'+pose.replace('4 1 ','5 1 ')+'\n',''),
                              (pose.replace(' 17 ',' 18 ')+'\n',''),
                              (pose+'\n','90 1 2 3 255 0 0 1 4\n'),
                              (pose+'\n','90 1 2 3 255 0 0 1\n90 1 2 3 255 0 0 1\n')]:
            with self.subTest(images=images,points=points):
                with self.assertRaises(ValueError):self.load(images,points)


if __name__=='__main__':unittest.main()
