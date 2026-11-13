import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import tempfile
import unittest
from pathlib import Path
from pipeline import read_model, Job, CONFIG, ROOT,load_config


class CoreTests(unittest.TestCase):
    def test_empty_observations_and_frame_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory)
            (p/'cameras.txt').write_text('1 PINHOLE 100 80 90 90 50 40\n')
            (p/'images.txt').write_text('# header\n7 1 0 0 0 0 0 0 1 frame_000010.jpg\n\n3 1 0 0 0 1 2 3 1 frame_000002.jpg\n5 6 -1\n')
            (p/'points3D.txt').write_text('99 1 2 3 255 128 0 0.5 7 0\n')
            cameras, poses, points = read_model(p)
            self.assertEqual([p['frame'] for p in poses], [2, 10])
            self.assertEqual(poses[0]['t'], [1., 2., 3.])
            self.assertEqual(points[0][0], (1., 2., 3.))

    def test_config_without_private_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p=Path(directory)
            (p/'config.example.json').write_text('{"colmap":"missing-colmap.exe","sample_project":"","qt_packages":""}')
            self.assertEqual(load_config(p)['sample_project'],'')
            self.assertEqual(load_config(p)['colmap'],'missing-colmap.exe')

    @unittest.skipUnless(Path(CONFIG['ffmpeg']).is_file() and Path(CONFIG['colmap']).is_file(), 'Requires configured FFmpeg and COLMAP')
    def test_cancel_retains_files_and_no_completion_marker(self):
        settings = dict(CONFIG, video=str(ROOT/'app/pipeline.py'), output=str(ROOT/'validation'),
                        fps=3, duration=1, size=1280, overlap=5, gpu=True, solver='COLMAP', mask='')
        job = Job(settings)
        # Use the installed FFmpeg's continuous synthetic source to test process termination.
        job.steps = [('cancel test', [CONFIG['ffmpeg'], '-nostdin', '-re', '-f', 'lavfi',
                     '-i', 'color=c=black:s=64x64:r=1', '-f', 'null', '-'])]
        job.tick()
        child = job.process
        job.cancel()
        self.assertIsNotNone(child.poll())
        self.assertTrue((job.folder/'settings.json').is_file())
        self.assertFalse((job.folder/'complete.json').exists())
        self.assertEqual(job.state, 'cancelled')


if __name__ == '__main__':
    unittest.main()
