import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Independent analytic pixel checks for measured/model residuals."""
from array import array
import unittest
import numpy as np
from camera_track import camera_matrix,WORLD
from track_data import TrackData,ImageObservations
from reprojection import calculate_residuals,ResidualCache,display_indices


def fixture(xyz,xy,q=(1.,0.,0.,0.),t=(0.,0.,0.)):
    ids=np.arange(len(xyz),dtype=np.int64)*100+101
    image=ImageObservations(37,9,17,'frame_000017.jpg',q,t,np.array(xy,dtype=float),ids,np.zeros(len(ids),np.uint8))
    links=array('q',[v for i in range(len(ids)) for v in (37,i)])
    return TrackData({37:image},ids,[(tuple(p),(1.,1.,1.),0.) for p in xyz],list(range(len(ids)+1)),links)


class ReprojectionTests(unittest.TestCase):
    def test_corrupt_measurement_identifies_right_point(self):
        camera=('PINHOLE',200,200,[100,110,100,100]);tracks=fixture([[0,0,5],[1,1,5]],[[103,104],[120,122]])
        result=calculate_residuals(tracks,17,camera)
        np.testing.assert_allclose(result.errors,[5,0]);np.testing.assert_allclose(result.projected,[[100,100],[120,122]])
        self.assertEqual(result.point_ids[display_indices(result,1,10)].tolist(),[101])
        self.assertEqual(result.observation_indices[display_indices(result,1,10)].tolist(),[0])

    def test_supported_distortion_models_against_explicit_formula(self):
        x,y=.4,.2;r2=x*x+y*y;k1=.2;k2=-.03;t1=.01;t2=-.02
        models=[('SIMPLE_PINHOLE',[100,90,80],(100*x+90,100*y+80)),
                ('SIMPLE_RADIAL',[100,90,80,k1],(100*x*(1+k1*r2)+90,100*y*(1+k1*r2)+80)),
                ('RADIAL',[100,90,80,k1,k2],(100*x*(1+k1*r2+k2*r2*r2)+90,100*y*(1+k1*r2+k2*r2*r2)+80)),
                ('OPENCV',[100,110,90,80,k1,k2,t1,t2],
                 (100*(x*(1+k1*r2+k2*r2*r2)+2*t1*x*y+t2*(r2+2*x*x))+90,
                  110*(y*(1+k1*r2+k2*r2*r2)+t1*(r2+2*y*y)+2*t2*x*y)+80))]
        for model,params,xy in models:
            with self.subTest(model=model):
                result=calculate_residuals(fixture([[2,1,5]],[xy]),17,(model,200,200,params))
                np.testing.assert_allclose(result.errors,[0],atol=1e-12)

    def test_world_to_camera_rotation_translation_and_z_up(self):
        q=(2**-.5,0.,0.,2**-.5);t=(1.,2.,3.);tracks=fixture([[1,0,2]],[[120,166]],q,t)
        camera=('PINHOLE',200,200,[100,110,100,100]);pose=camera_matrix(dict(q=q,t=t))
        np.testing.assert_allclose(calculate_residuals(tracks,17,camera).projected,[[120,166]],atol=1e-10)
        np.testing.assert_allclose(calculate_residuals(tracks,17,camera,pose).projected,[[120,166]],atol=1e-10)

    def test_current_pose_and_undo_invalidate_cache(self):
        tracks=fixture([[0,0,5]],[[100,100]]);camera=('PINHOLE',200,200,[100,100,100,100])
        pose=camera_matrix(dict(q=[1,0,0,0],t=[0,0,0]));cache=ResidualCache()
        first=cache.get(tracks,17,camera,pose,False);self.assertIs(cache.get(tracks,17,camera,pose,False),first)
        moved=pose.copy();moved[:3,3]+=WORLD@np.array([1,0,0])
        result=cache.get(tracks,17,camera,moved,False);np.testing.assert_allclose(result.errors,[20])
        np.testing.assert_allclose(cache.get(tracks,17,camera,moved,True).errors,[0])
        np.testing.assert_allclose(cache.get(tracks,17,camera,pose,False).errors,[0])
        np.testing.assert_allclose(cache.get(tracks,17,('PINHOLE',200,200,[100,100,110,100]),pose,False).errors,[10])

    def test_behind_camera_and_invalid_observations_are_not_zero_error(self):
        tracks=fixture([[0,0,-5],[0,0,0],[0,0,5],[0,0,5]],[[100,100],[100,100],[100,100],[float('nan'),100]])
        result=calculate_residuals(tracks,17,('PINHOLE',200,200,[100,100,100,100]))
        self.assertEqual(result.unprojectable,2);self.assertEqual(result.point_ids.tolist(),[301])
        self.assertEqual(len(result.errors),1)

    def test_display_limit_keeps_worst_residuals(self):
        tracks=fixture([[0,0,5]]*4,[[100,100],[101,100],[110,100],[105,100]])
        result=calculate_residuals(tracks,17,('PINHOLE',200,200,[100,100,100,100]))
        self.assertEqual(display_indices(result,1,2).tolist(),[2,3]);self.assertEqual(display_indices(result,20,10).tolist(),[])


if __name__=='__main__':unittest.main()
