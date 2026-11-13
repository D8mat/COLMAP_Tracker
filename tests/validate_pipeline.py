import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import time
from pathlib import Path
from pipeline import CONFIG, Job, ROOT
sample=Path(CONFIG.get('sample_project') or ROOT/'sample_project')
settings = dict(CONFIG, video=str(sample/'02 VIDEOS/IMG_2284_nonHDR.mov'),
                output=str(ROOT/'validation'), fps=3, duration=8, size=1600,
                overlap=8, gpu=True, solver='COLMAP', mask='')
job = Job(settings)
print('JOB', job.folder, flush=True)
previous = ''
try:
    while job.tick() == 'running':
        if job.message != previous:
            print(job.message, flush=True)
            previous = job.message
        time.sleep(.5)
    print(job.state, job.message, flush=True)
    assert job.state == 'done', job.message
    from pipeline import read_model
    cameras, poses, points = read_model(job.folder/'model')
    assert len(poses) >= 3 and len(points) > 10
    print('PIPELINE OK', len(poses), 'cameras', len(points), 'points', flush=True)
finally:
    if job.state == 'running': job.cancel()
