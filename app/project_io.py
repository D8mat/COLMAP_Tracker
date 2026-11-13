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
        if any(not isinstance(item.get(key,default),bool) for key,default in [('visible',True),('locked',False)]):raise ValueError('Invalid object visibility/lock.')
        if item['kind'] not in ('Cube','Cone') or not isinstance(item['name'],str) or len(item['color'])!=3 or any(not 0<=v<=1 for v in item['color']):raise ValueError('Invalid scene object.')


def validate_document(data):
    json.dumps(data,allow_nan=False)
    if data.get('format')!='colmap-tracker-project' or data.get('version')!=1:raise ValueError('Unsupported tracker project format.')
    for key in ('video','model_video','model','images','mesh'):
        if not isinstance(data['assets'][key],str):raise ValueError('Invalid project asset path.')
    for key in ('sequence','model_sequence'):
        if key in data['assets'] and not isinstance(data['assets'][key],str):raise ValueError('Invalid sequence folder.')
    if data.get('sequence') is not None:
        from image_sequence import validate_sequence
        validate_sequence(data['sequence'])
        if not data['assets'].get('sequence') or data['assets']['video']:raise ValueError('Sequence projects require one source folder.')
    elif data['assets'].get('sequence') or data['assets'].get('model_sequence'):raise ValueError('Missing sequence information.')
    if not .1<=data['model_fps']<=240:raise ValueError('Invalid project FPS.')
    validate_layout(data['layout'])
    for section in ('tracking','view','meshing','orbit'):
        if not isinstance(data[section],dict):raise ValueError('Invalid project settings.')
    if data.get('camera_corrections') and not data['assets']['model']:raise ValueError('Camera corrections require a reconstruction.')
    if 'diagnostics' in data:
        d=data['diagnostics']
        if (not isinstance(d,dict) or type(d.get('enabled')) is not bool or type(d.get('original')) is not bool
                or type(d.get('minimum')) not in (int,float) or not 0<=d['minimum']<=1000
                or type(d.get('limit')) is not int or not 10<=d['limit']<=5000):raise ValueError('Invalid track-error display settings.')
    if 'transport' in data:
        transport=data['transport']
        if not isinstance(transport,dict) or not isinstance(transport.get('loop'),bool) or transport.get('rate') not in (.25,.5,1,1.5,2):raise ValueError('Invalid playback controls.')
        ranges=transport.get('ranges')
        if not isinstance(ranges,dict):raise ValueError('Invalid playback ranges.')
        for key,value in ranges.items():
            if key not in ('source','solved') or not isinstance(value,list) or len(value)!=2 or any(type(v) is not int or v<1 for v in value) or value[1]<value[0]:raise ValueError('Invalid playback range.')


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


def project_document(path):
    path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8-sig'));validate_document(data)
    return map_paths(data,path.parent,False)


def read_project(path,data=None):
    data=project_document(path) if data is None else copy.deepcopy(data);validate_document(data);assets=data['assets']
    for key in ('video','model_video','mesh'):
        if assets[key] and not Path(assets[key]).is_file():raise ValueError(f'Missing {key}: {assets[key]}')
    if data.get('sequence'):
        from image_sequence import validate_sequence
        validate_sequence(data['sequence'],assets['sequence'])
        if assets.get('model_sequence') and not Path(assets['model_sequence']).is_dir():raise ValueError('Missing model sequence folder.')
    if assets['images'] and not Path(assets['images']).is_dir():raise ValueError('Missing frame images folder: '+assets['images'])
    model=read_model(assets['model']) if assets['model'] else None
    if model:
        if not model[1]:raise ValueError('The project reconstruction has no solved cameras.')
        track=CameraTrack(model[1])
        if data.get('camera_corrections'):track.load_document(data['camera_corrections'])
        if assets['mesh']:load_mesh(assets['mesh'],track.fingerprint)
    elif assets['mesh']:raise ValueError('A mesh requires a reconstruction.')
    return data,model
