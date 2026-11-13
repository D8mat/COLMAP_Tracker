import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from floor_alignment import align_floor
from scene_geometry import transform_matrix,identity_transform
from project_io import write_project,read_project


class ProjectFloorTests(unittest.TestCase):
    def test_alignment_preserves_geometry_and_root_projection(self):
        points=np.array([[-2,-2,-1],[2,-2,-.2],[2,2,.6],[-2,2,-.2]])
        scene=dict(position=[3,-2,7],rotation=[15,5,40],scale=2.3)
        aligned,error=align_floor(points,scene)
        a,b=transform_matrix(scene),transform_matrix(aligned)
        world=points@b[:3,:3].T+b[:3,3]
        np.testing.assert_allclose(world[:,2],0,atol=1e-10)
        self.assertLess(error,1e-10)
        self.assertAlmostEqual(np.linalg.norm(world[1]-world[0]),np.linalg.norm(points[1]-points[0])*2.3)
        camera=np.eye(4);camera[:3,3]=[2,-5,3];point=np.r_[points[0],1]
        np.testing.assert_allclose(np.linalg.inv(a@camera)@(a@point),np.linalg.inv(b@camera)@(b@point),atol=1e-10)
        with self.assertRaises(ValueError):align_floor([[0,0,0],[1,0,0],[2,0,0]],scene)
        with self.assertRaises(ValueError):align_floor([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],scene)

    def test_relative_project_paths_and_invalid_save_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);video=root/'clip.mp4';video.write_bytes(b'fixture')
            path=root/'scene.tracker.json'
            doc=dict(format='colmap-tracker-project',version=1,assets=dict(video=str(video),model_video='',model='',images='',mesh=''),model_fps=30,
                layout=dict(version=1,scene=identity_transform(),objects=[]),camera_corrections=None,tracking=dict(mask='',output=str(root)),view={},meshing={},orbit={})
            write_project(path,doc);text=path.read_text();self.assertIn('clip.mp4',text);self.assertNotIn(str(video).replace('\\','\\\\'),text)
            loaded,model=read_project(path);self.assertIsNone(model);self.assertEqual(loaded['assets']['video'],str(video.resolve()))
            invalid=copy.deepcopy(doc);invalid['layout']['scene']['scale']=0
            with self.assertRaises(ValueError):write_project(path,invalid)
            self.assertEqual(path.read_text(),text)
            video.unlink()
            with self.assertRaisesRegex(ValueError,'Missing video'):read_project(path)


if __name__=='__main__':unittest.main()
