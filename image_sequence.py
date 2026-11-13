"""Ordered image sources and consistent EXR display/tracking conversion."""
import math
import re
import subprocess
from pathlib import Path

EXTENSIONS={'.png','.jpg','.jpeg','.exr','.tif','.tiff'}


def natural_key(name):
    return tuple((1,int(part)) if part.isdigit() else (0,part.casefold()) for part in re.split(r'(\d+)',name))


def scan_sequence(folder,fps=30.):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError('Select an existing image folder.')
    files=sorted((p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS),key=lambda n:(natural_key(n),n))
    data=dict(fps=fps,files=files)
    validate_sequence(data,folder)
    return data


def validate_sequence(data,folder=None):
    if not isinstance(data,dict) or type(data.get('fps')) not in (int,float) or not .1<=data['fps']<=240:
        raise ValueError('Sequence FPS must be between 0.1 and 240.')
    names=data.get('files')
    if not isinstance(names,list) or not names:raise ValueError('No PNG, JPG, EXR or TIFF images found in this folder.')
    if any(not isinstance(n,str) or not n or '/' in n or '\\' in n or ':' in n or Path(n).suffix.lower() not in EXTENSIONS for n in names):
        raise ValueError('Invalid sequence filename.')
    if len({n.casefold() for n in names})!=len(names):raise ValueError('Duplicate sequence filenames.')
    if 'size' in data and (not isinstance(data['size'],(list,tuple)) or len(data['size'])!=2 or any(type(v) is not int or v<1 for v in data['size'])):
        raise ValueError('Invalid sequence dimensions.')
    if folder is not None:
        for name in names:
            if not (Path(folder)/name).is_file():raise ValueError('Missing sequence image: '+name)


def exr_png(path,ffmpeg,size=None):
    # Use the same linear-to-sRGB display transform for preview and tracking copies.
    command=[str(ffmpeg),'-v','error','-nostdin','-threads','2','-apply_trc','iec61966_2_1','-i',str(path),'-frames:v','1']
    if size:command+=['-vf',f'scale={max(1,size[0])}:{max(1,size[1])}:force_original_aspect_ratio=decrease']
    command+=['-pix_fmt','rgb24','-threads','1','-f','image2pipe','-c:v','png','pipe:1']
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Cannot decode EXR '+Path(path).name+': '+result.stderr.decode(errors='replace')[-1200:])
    return result.stdout


def sampled_indices(count,source_fps,target_fps,duration=0):
    if not 0<target_fps<=source_fps:raise ValueError('Tracking FPS cannot exceed sequence FPS.')
    length=min(count/source_fps,duration) if duration>0 else count/source_fps
    return [min(count-1,int(i*source_fps/target_fps+1e-8)) for i in range(math.ceil(length*target_fps-1e-8))]


def prepare_frames(settings,folder):
    """Subprocess entry: originals are read only, numbered copies feed COLMAP."""
    import shutil
    data=settings['sequence'];source=Path(settings['video']);validate_sequence(data,source)
    indices=sampled_indices(len(data['files']),data['fps'],settings['fps'],settings['duration'])
    expected=None
    # Qt reads image headers; it is available in the desktop runtime or qt_packages.
    import sys
    if settings.get('qt_packages'):sys.path.insert(0,settings['qt_packages'])
    from PySide6.QtGui import QImageReader,QImage
    for frame,index in enumerate(indices,1):
        path=source/data['files'][index];extension=path.suffix.lower()
        if extension=='.exr':
            payload=exr_png(path,settings['ffmpeg']);image=QImage.fromData(payload,'PNG');size=image.size()
        else:
            reader=QImageReader(str(path));image=reader.read();size=image.size()
        if image.isNull():raise ValueError('Cannot read sequence image: '+path.name)
        dimensions=(size.width(),size.height())
        if expected is None:expected=dimensions
        if dimensions!=expected:raise ValueError('Sequence images must have matching dimensions: '+path.name)
        target=Path(folder)/f'frame_{frame:06d}{".png" if extension in (".exr",".tif",".tiff") else extension}'
        if extension=='.exr':target.write_bytes(payload)
        elif extension in ('.tif','.tiff'):
            if not image.save(str(target),'PNG'):raise ValueError('Cannot prepare TIFF image: '+path.name)
        else:shutil.copyfile(path,target)
        if frame==1 or frame%25==0 or frame==len(indices):print(f'Prepared {frame}/{len(indices)} images',flush=True)


if __name__=='__main__':
    import json,sys
    prepare_frames(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')),sys.argv[2])
