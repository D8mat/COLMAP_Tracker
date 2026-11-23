import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from colmap_compat import feature_options,select_option

class CompatibilityTests(unittest.TestCase):
    def test_old_and_new_commands(self):
        for extraction,matching in [('SiftExtraction','SiftMatching'),('FeatureExtraction','FeatureMatching')]:
            with patch('colmap_compat.subprocess.run',side_effect=[
                SimpleNamespace(returncode=0,stdout=f'--{extraction}.use_gpu arg\n--{extraction}.max_image_size arg'),
                SimpleNamespace(returncode=0,stdout=f'--{matching}.use_gpu arg')]):
                self.assertEqual(feature_options('colmap'),(f'--{extraction}.use_gpu',f'--{extraction}.max_image_size',f'--{matching}.use_gpu'))
    def test_unknown_options_fail_clearly(self):
        with self.assertRaises(ValueError):select_option('--Other.option','FeatureExtraction.use_gpu','SiftExtraction.use_gpu')
        with patch('colmap_compat.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='failed')):
            with self.assertRaises(ValueError):feature_options('colmap')
