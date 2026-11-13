import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import tempfile
import unittest
from pathlib import Path
import numpy as np
from mesh_data import validate_mesh,save_mesh,load_mesh,write_ply,read_ply,normals
from lens_warp import distortion_map
from scene_geometry import project_camera


class MeshTests(unittest.TestCase):
    def test_ply_storage_and_model_binding(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
        faces=np.array([[0,1,2],[0,3,1]])
        colors=np.array([[1,0,0],[0,1,0],[0,0,1],[1,1,1]],float)
        mesh=validate_mesh(vertices,faces,colors)
        flat,smooth=normals(vertices,faces)
        np.testing.assert_allclose(flat,[[0,0,1],[0,1,0]])
        np.testing.assert_allclose(smooth[0],[0,2**-.5,2**-.5])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mesh.ply';write_ply(path,vertices,colors,faces)
            result=read_ply(path)
            for key in ('vertices','faces','colors'):np.testing.assert_allclose(result[key],mesh[key])
            path=Path(folder)/'mesh.npz';save_mesh(path,mesh,'model_a')
            np.testing.assert_array_equal(load_mesh(path,'model_a')['faces'],faces)
            with self.assertRaises(ValueError):load_mesh(path,'model_b')
        with self.assertRaises(ValueError):validate_mesh(vertices,[[0,1,99]],colors)

    def test_inverse_lens_maps_roundtrip(self):
        for model,parameters in [('SIMPLE_RADIAL',[400,320,240,-.08]),('RADIAL',[400,320,240,-.1,.02]),('OPENCV',[400,420,320,240,.07,.01,.004,-.003])]:
            camera=(model,640,480,parameters)
            mapping=distortion_map(camera,160,120)
            self.assertTrue(mapping['valid'].all())
            source=mapping['camera'];rw,rh=mapping['size']
            u=(mapping['x']+mapping['wx']+.5)*source[1]/rw
            v=(mapping['y']+mapping['wy']+.5)*source[2]/rh
            fx,fy,cx,cy=source[3]
            rays=np.column_stack(((u.ravel()-cx)/fx,(v.ravel()-cy)/fy,np.ones(u.size)))
            projected=project_camera(rays,camera).reshape(120,160,2)
            yy,xx=np.mgrid[:120,:160]
            np.testing.assert_allclose(projected[:,:,0],(xx+.5)*4,atol=1e-4)
            np.testing.assert_allclose(projected[:,:,1],(yy+.5)*4,atol=1e-4)
        self.assertIsNone(distortion_map(('PINHOLE',640,480,[400,400,320,240]),160,120))


if __name__=='__main__':unittest.main()
