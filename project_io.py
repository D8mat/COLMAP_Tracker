"""Versioned project documents; source media and reconstruction assets stay external."""
import copy
import json
import os
from pathlib import Path
from camera_track import CameraTrack
from mesh_data import load_mesh
from pipeline import read_model


def validate_layout(data):
    if data.get('version')!=1 or not isinstance(data.get('objects'),list) or len(data['objects'])>1000:
        raise ValueError('Invalid scene layout.')
    for item in [data['scene']]+data['objects']:
        for key in ('position','rotation'):
            if len(item[key])!=3 or any(not isinstance(v,(int,float)) or abs(v)>1e9 for v in item[key]):raise ValueError('Invalid scene transform.')
        if not .0001<=item['scale']<=1e6:raise ValueError('Invalid scene scale.')
    for item in data['objects']:
        if item['kind'] not in ('Cube','Cone') or not isinstance(item['name'],str) or len(item['color'])!=3 or any(not 0<=v<=1 for v in item['color']):raise ValueError('Invalid scene object.')


def validate_document(data):
    json.dumps(data,allow_nan=False)
    if data.get('format')!='colmap-tracker-project' or data.get('version')!=1:raise ValueError('Unsupported tracker project format.')
    for key in ('video','model_video','model','images','mesh'):
        if not isinstance(data['assets'][key],str):raise ValueError('Invalid project asset path.')
    if not .1<=data['model_fps']<=240:raise ValueError('Invalid project FPS.')
    validate_layout(data['layout'])
    for section in ('tracking','view','meshing','orbit'):
        if not isinstance(data[section],dict):raise ValueError('Invalid project settings.')
    if data.get('camera_corrections') and not data['assets']['model']:raise ValueError('Camera corrections require a reconstruction.')


def map_paths(data,base,encode):
    data=copy.deepcopy(data)
    for section,key in [('assets',k) for k in data['assets']]+[('tracking','mask'),('tracking','output')]:
        value=data[section].get(key,'')
        if not value:continue
        if encode:
            try:value=os.path.relpath(Path(value).resolve(),base)
            except ValueError:value=str(Path(value).resolve())
        else:value=str((base/Path(value)).resolve())
        data[section][key]=value
    return data


def write_project(path,data):
    validate_document(data);path=Path(path).resolve()
    text=json.dumps(map_paths(data,path.parent,True),indent=2,ensure_ascii=False,allow_nan=False)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(text,encoding='utf-8');temporary.replace(path)


def read_project(path):
    path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8-sig'));validate_document(data)
    data=map_paths(data,path.parent,False);assets=data['assets']
    for key in ('video','model_video','mesh'):
        if assets[key] and not Path(assets[key]).is_file():raise ValueError(f'Missing {key}: {assets[key]}')
    if assets['images'] and not Path(assets['images']).is_dir():raise ValueError('Missing frame images folder: '+assets['images'])
    model=read_model(assets['model']) if assets['model'] else None
    if model:
        if not model[1]:raise ValueError('The project reconstruction has no solved cameras.')
        track=CameraTrack(model[1])
        if data.get('camera_corrections'):track.load_document(data['camera_corrections'])
        if assets['mesh']:load_mesh(assets['mesh'],track.fingerprint)
    elif assets['mesh']:raise ValueError('A mesh requires a reconstruction.')
    return data,model
