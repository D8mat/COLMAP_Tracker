"""Resolve renamed COLMAP options from the installed executable's help."""
import os
import re
import subprocess


def select_option(help_text,modern,legacy):
    options=set(re.findall(r'--([A-Za-z0-9_.]+)',help_text))
    for name in (modern,legacy):
        if name in options:return '--'+name
    raise ValueError(f'COLMAP does not advertise {modern} or {legacy}. Check the configured executable.')


def feature_options(executable):
    env=os.environ.copy()
    for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key,None)
    def help_for(command):
        result=subprocess.run([str(executable),command,'-h'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',timeout=10,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError(f'Cannot inspect COLMAP {command}: {result.stdout[-1200:]}')
        return result.stdout
    extraction=help_for('feature_extractor');matching=help_for('sequential_matcher')
    return (select_option(extraction,'FeatureExtraction.use_gpu','SiftExtraction.use_gpu'),
            select_option(extraction,'FeatureExtraction.max_image_size','SiftExtraction.max_image_size'),
            select_option(matching,'FeatureMatching.use_gpu','SiftMatching.use_gpu'))
