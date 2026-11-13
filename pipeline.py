"""External processes only; Blender's timer polls these without blocking its UI."""
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
def load_config(root=ROOT):
    config=json.loads((root/'config.example.json').read_text(encoding='utf-8-sig'))
    if (root/'config.json').is_file():
        config.update(json.loads((root/'config.json').read_text(encoding='utf-8-sig')))
    for key in ('colmap','glomap','ffmpeg','blender','python','qt_packages','sample_project'):
        value=config.get(key,'')
        if not value:continue
        path=Path(os.path.expandvars(os.path.expanduser(value)))
        if path.is_absolute():config[key]=str(path)
        elif (root/path).exists():config[key]=str((root/path).resolve())
        elif key in ('colmap','glomap','ffmpeg','blender','python'):
            config[key]=shutil.which(str(path)) or str(path)
        else:config[key]=str((root/path).resolve())
    return config


CONFIG = load_config()


def read_model(folder,with_tracks=True):
    from track_data import read_reconstruction
    return read_reconstruction(folder,with_tracks=with_tracks)


class Job:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.log = None
        self.index = 0
        self.state = 'running'
        self.message = 'Preparing'
        video = Path(settings['video'])
        sequence=settings.get('sequence')
        if sequence:
            from image_sequence import validate_sequence,sampled_indices
            validate_sequence(sequence,video)
            sampled_indices(len(sequence['files']),sequence['fps'],settings['fps'],settings['duration'])
        elif not video.is_file():
            raise ValueError('Select an existing video first.')
        for key in ('colmap', 'ffmpeg') + (('glomap',) if settings['solver'] == 'GLOMAP' else ()):
            if not Path(settings[key]).is_file():
                raise ValueError('Executable not found: ' + settings[key])
        self.folder = Path(settings['output']) / (datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6])
        self.folder.mkdir(parents=True, exist_ok=False)
        for directory in ('images', 'sparse', 'model'):
            (self.folder / directory).mkdir()
        (self.folder / 'settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
        self.log = (self.folder / 'tracking.log').open('w', encoding='utf-8')
        c, f = settings['colmap'], settings['ffmpeg']
        db = str(self.folder / 'database.db')
        images = str(self.folder / 'images')
        # Exact regular time sampling: timeline fps equals the extraction fps.
        extract = [f, '-hide_banner', '-nostdin', '-n', '-i', str(video)]
        if settings['duration'] > 0:
            extract += ['-t', str(settings['duration'])]
        extract += ['-vf', 'fps=' + str(settings['fps']), '-q:v', '2', str(self.folder / 'images/frame_%06d.jpg')]
        if sequence:
            import sys
            extract=[sys.executable,str(ROOT/'image_sequence.py'),str(self.folder/'settings.json'),images]
        features = [c, 'feature_extractor', '--database_path', db, '--image_path', images,
                    '--ImageReader.single_camera', '1', '--ImageReader.camera_model', 'SIMPLE_RADIAL',
                    '--SiftExtraction.use_gpu', str(int(settings['gpu'])),
                    '--SiftExtraction.max_image_size', str(settings['size'])]
        if settings.get('mask'):
            if not Path(settings['mask']).is_file():
                self.log.close()
                raise ValueError('Camera mask does not exist.')
            features += ['--ImageReader.camera_mask_path', settings['mask']]
        match = [c, 'sequential_matcher', '--database_path', db,
                 '--SiftMatching.use_gpu', str(int(settings['gpu'])),
                 '--SequentialMatching.overlap', str(settings['overlap'])]
        mapper = [settings['glomap'] if settings['solver'] == 'GLOMAP' else c, 'mapper',
                  '--database_path', db, '--image_path', images, '--output_path', str(self.folder / 'sparse')]
        self.steps = [('1/6 Prepare sequence images' if sequence else '1/6 Extract video frames', extract), ('2/6 Detect image features', features),
                      ('3/6 Match neighbouring frames', match), ('4/6 Solve camera motion', mapper)]

    def tick(self):
        if self.state != 'running':
            return self.state
        if self.process:
            code = self.process.poll()
            if code is None:
                return self.state
            self.process = None
            if code:
                return self.fail('Process failed (exit %s). See tracking.log.' % code)
        if self.index == 4:
            models = list((self.folder / 'sparse').glob('*/images.bin'))
            if not models:
                return self.fail('No camera solution. Try more textured frames and camera translation.')
            # Header is a uint64 registered-image count, not file size.
            import struct
            def count(path):
                with path.open('rb') as stream:
                    return struct.unpack('<Q', stream.read(8))[0]
            model = max(models, key=count).parent
            self.steps.append(('5/6 Undistort images', [self.settings['colmap'], 'image_undistorter',
                '--image_path', str(self.folder / 'images'), '--input_path', str(model),
                '--output_path', str(self.folder / 'undistorted'), '--output_type', 'COLMAP',
                '--max_image_size', str(self.settings['size'])]))
            self.steps.append(('6/6 Export calibrated model', [self.settings['colmap'], 'model_converter',
                '--input_path', str(self.folder / 'undistorted/sparse'),
                '--output_path', str(self.folder / 'model'), '--output_type', 'TXT']))
        if self.index == len(self.steps):
            self.state, self.message = 'done', 'Camera solve complete'
            self.log.close()
            (self.folder / 'complete.json').write_text(json.dumps({'model': 'model'}))
            return self.state
        self.message, command = self.steps[self.index]
        self.log.write('\n' + self.message + '\n' + subprocess.list2cmdline(command) + '\n')
        self.log.flush()
        env = os.environ.copy()
        exe_dir = str(Path(command[0]).parent)
        env['PATH'] = exe_dir + os.pathsep + env.get('PATH', '')
        # Do not inherit Blender/Qt plugin paths into COLMAP's Qt5 runtime.
        env.pop('QT_PLUGIN_PATH', None)
        env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
        try:
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                cwd=exe_dir, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as exc:
            return self.fail(str(exc))
        self.index += 1
        return self.state

    def fail(self, message):
        self.state, self.message = 'error', message
        if self.log:
            self.log.close()
        return self.state

    def cancel(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.state, self.message = 'cancelled', 'Cancelled; partial files retained'
        if self.log:
            self.log.close()
