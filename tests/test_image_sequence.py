import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import copy
import tempfile
import unittest
from pathlib import Path
from image_sequence import scan_sequence,validate_sequence,sampled_indices
from project_io import write_project,read_project
from scene_geometry import identity_transform


class SequenceTests(unittest.TestCase):
    def test_order_extensions_gaps_and_manifest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('shot_10.EXR','shot_2.jpg','shot_1.PNG','shot_30.JPEG','shot_40.tif','shot_50.TIFF','ignore.txt'):(root/name).write_bytes(b'fixture')
            (root/'nested').mkdir();(root/'nested/hidden.png').write_bytes(b'fixture')
            data=scan_sequence(root,23.976)
            self.assertEqual(data['files'],['shot_1.PNG','shot_2.jpg','shot_10.EXR','shot_30.JPEG','shot_40.tif','shot_50.TIFF'])
            for names in ([],['../bad.png'],['a/b.png'],['a\\b.png'],['C:bad.png'],['x.png','X.PNG'],['file.txt']):
                with self.assertRaises(ValueError):validate_sequence(dict(fps=24,files=names))
            for fps in (0,float('nan'),float('inf'),True,241):
                with self.assertRaises(ValueError):scan_sequence(root,fps)
            for size in ([0,120],[160],['160',120],None):
                with self.assertRaises(ValueError):validate_sequence(dict(data,size=size))
            (root/'shot_2.jpg').unlink()
            with self.assertRaisesRegex(ValueError,'Missing sequence image'):validate_sequence(data,root)

    def test_time_sampling(self):
        self.assertEqual(sampled_indices(12,24,6),[0,4,8])
        self.assertEqual(sampled_indices(12,24,24),list(range(12)))
        self.assertEqual(sampled_indices(120,24,6,.5),[0,4,8])
        self.assertEqual(sampled_indices(3,23.976,23.976),[0,1,2])
        self.assertEqual(sampled_indices(3,.5,.5),[0,1,2])
        with self.assertRaises(ValueError):sampled_indices(12,24,30)

    def test_sequence_project_roundtrip_and_missing_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'images';source.mkdir();(source/'001.png').write_bytes(b'fixture')
            doc=dict(format='colmap-tracker-project',version=1,assets=dict(video='',model_video='',model='',images='',mesh='',sequence=str(source)),
                sequence=scan_sequence(source,24),model_fps=6,layout=dict(version=1,scene=identity_transform(),objects=[]),camera_corrections=None,
                tracking=dict(mask='',output=str(root)),view={},meshing={},orbit={})
            target=root/'project.tracker.json';write_project(target,doc);data,model=read_project(target)
            self.assertIsNone(model);self.assertEqual(data['sequence'],doc['sequence']);self.assertEqual(data['assets']['sequence'],str(source))
            # A later addition must not silently change the stored frame mapping.
            (source/'002.png').write_bytes(b'fixture');self.assertEqual(len(read_project(target)[0]['sequence']['files']),1)
            invalid=copy.deepcopy(doc);invalid['assets']['video']='other.mov'
            with self.assertRaises(ValueError):write_project(target,invalid)
            (source/'001.png').unlink()
            with self.assertRaisesRegex(ValueError,'Missing sequence image'):read_project(target)


if __name__=='__main__':unittest.main()
