"""Full COLMAP observations, independent of the sampled Z-up display geometry.

IDs are identifiers, not array offsets. Observation indices are zero-based.
XY/XYZ and poses remain in the imported model's original coordinate system.
Format reference: https://colmap.github.io/format.html
"""
from array import array
from dataclasses import dataclass
from pathlib import Path
import re
import numpy as np

UNTRIANGULATED, VALID, MISSING_POINT, MISSING_LINK, INVALID_XY = range(5)


@dataclass
class ImageObservations:
    image_id: int
    camera_id: int
    frame: int
    name: str
    quaternion: tuple
    translation: tuple
    xy: np.ndarray
    point_ids: np.ndarray
    states: np.ndarray

    def time_seconds(self, fps):
        """Regular extraction time, not an original-media frame index or PTS."""
        if not np.isfinite(fps) or fps<=0:raise ValueError('FPS must be positive.')
        return (self.frame-1)/fps


class Reconstruction(tuple):
    """Keep the original cameras/poses/points unpacking contract for exporters."""
    def __new__(cls,cameras,poses,points,tracks):
        result=super().__new__(cls,(cameras,poses,points));result.tracks=tracks;return result


class TrackData:
    def __init__(self,images,point_ids,points,offsets,links):
        self.images=images
        self.image_by_frame={image.frame:image.image_id for image in images.values()}
        self.point_ids=np.asarray(point_ids,dtype=np.int64)
        self.point_rows={int(point_id):row for row,point_id in enumerate(point_ids)}
        self.xyz=np.asarray([p[0] for p in points],dtype=np.float64).reshape(-1,3)
        self.colors=np.asarray([p[1] for p in points],dtype=np.float32).reshape(-1,3)
        self.imported_errors=np.asarray([p[2] for p in points],dtype=np.float64)
        self.track_offsets=np.asarray(offsets,dtype=np.int64)
        self.track_links=np.frombuffer(links,dtype=np.int64).reshape(-1,2)
        self.link_valid=np.zeros(len(self.track_links),dtype=bool)
        self.issue_examples=[]
        self._validate_links()
        self.frame_counts={image_id:np.bincount(image.states,minlength=5) for image_id,image in images.items()}
        self.counts=np.sum(list(self.frame_counts.values()),axis=0,dtype=np.int64) if images else np.zeros(5,dtype=np.int64)
        self.invalid_links=int(np.count_nonzero(~self.link_valid))
        cumulative=np.concatenate(([0],np.cumsum(self.link_valid,dtype=np.int64)))
        self.track_lengths=cumulative[self.track_offsets[1:]]-cumulative[self.track_offsets[:-1]]
        # Diagnostic data must not silently change when the viewport is transformed.
        arrays=[self.point_ids,self.xyz,self.colors,self.imported_errors,self.track_offsets,
                self.track_links,self.link_valid,self.track_lengths,self.counts,*self.frame_counts.values()]
        for image in images.values():arrays.extend((image.xy,image.point_ids,image.states))
        for data in arrays:data.setflags(write=False)

    def _validate_links(self):
        sorted_ids=np.sort(self.point_ids)
        for image in self.images.values():
            attached=image.point_ids>=0
            image.states[attached]=MISSING_POINT
            if len(sorted_ids):
                rows=np.searchsorted(sorted_ids,image.point_ids)
                exists=attached & (rows<len(sorted_ids))
                exists &= sorted_ids[np.minimum(rows,len(sorted_ids)-1)]==image.point_ids
                image.states[exists]=MISSING_LINK
            image.states[~np.isfinite(image.xy).all(axis=1)]=INVALID_XY
        for row,point_id in enumerate(self.point_ids):
            seen=set()
            for index in range(self.track_offsets[row],self.track_offsets[row+1]):
                image_id,observation=map(int,self.track_links[index]);image=self.images.get(image_id)
                reason=None
                if (image_id,observation) in seen:reason='duplicate track link'
                elif image is None:reason='missing image'
                elif not 0<=observation<len(image.point_ids):reason='observation index out of range'
                elif image.point_ids[observation]!=point_id:reason='point ID differs between image and track'
                elif image.states[observation]==INVALID_XY:reason='non-finite image coordinates'
                if reason:
                    if len(self.issue_examples)<20:self.issue_examples.append(f'Point {point_id}, image {image_id}, observation {observation}: {reason}')
                else:
                    self.link_valid[index]=True;image.states[observation]=VALID
                seen.add((image_id,observation))

    def point_track(self,point_id,valid_only=False):
        row=self.point_rows[point_id];start,end=self.track_offsets[row:row+2]
        links=self.track_links[start:end]
        return links[self.link_valid[start:end]] if valid_only else links


def _records(path):
    with path.open(encoding='utf-8-sig') as stream:
        for number,line in enumerate(stream,1):
            if line.strip() and not line.lstrip().startswith('#'):yield number,line


def _finite(values,label):
    if not np.isfinite(values).all():raise ValueError('Non-finite '+label)


def read_reconstruction(folder,with_tracks=True):
    folder=Path(folder);cameras={};poses=[];images={};frames=set();image_ids=set()
    for number,line in _records(folder/'cameras.txt'):
        t=line.split()
        if len(t)<5:raise ValueError(f'Malformed cameras.txt line {number}')
        camera_id=int(t[0]);width,height=map(int,t[2:4]);params=list(map(float,t[4:]))
        if camera_id<0 or camera_id in cameras:raise ValueError(f'Duplicate or invalid camera ID: {camera_id}')
        if width<=0 or height<=0:raise ValueError('Invalid camera dimensions.')
        _finite(params,'camera parameters');cameras[camera_id]=(t[1],width,height,params)
    # Stream the file: a real clip may contain hundreds of MB of observations.
    with (folder/'images.txt').open(encoding='utf-8-sig') as stream:
        lines=enumerate(stream,1)
        for number,line in lines:
            if not line.strip() or line.lstrip().startswith('#'):continue
            t=line.split(maxsplit=9)
            if len(t)!=10:raise ValueError(f'Malformed images.txt pose on line {number}')
            image_id=int(t[0]);camera_id=int(t[8]);name=t[9].strip()
            match=re.search(r'(\d+)$',Path(name).stem)
            if not match:raise ValueError('Expected numbered frame image: '+name)
            frame=int(match[1]);q=tuple(map(float,t[1:5]));translation=tuple(map(float,t[5:8]))
            if image_id<0 or image_id in image_ids:raise ValueError(f'Duplicate or invalid image ID: {image_id}')
            if frame in frames:raise ValueError(f'Multiple images map to frame {frame}; import a single video sequence.')
            if camera_id not in cameras:raise ValueError(f'Image {image_id} references missing camera {camera_id}')
            _finite(q+translation,'camera pose')
            if np.linalg.norm(q)<1e-12:raise ValueError('Zero camera quaternion.')
            record=next(lines,None)
            while record is not None and record[1].lstrip().startswith('#'):record=next(lines,None)
            if record is None:raise ValueError(f'Missing observations line for image {image_id}')
            if with_tracks:
                values=record[1].split()
                if len(values)%3:raise ValueError(f'Malformed observations for image {image_id}')
                # Parse IDs as integers separately: float conversion loses large IDs.
                xy=np.column_stack((np.asarray(values[0::3],dtype=np.float64),np.asarray(values[1::3],dtype=np.float64)))
                ids=np.asarray(values[2::3],dtype=np.int64)
                if np.any(ids < -1):raise ValueError(f'Invalid point ID in image {image_id}')
                images[image_id]=ImageObservations(image_id,camera_id,frame,name,q,translation,xy,ids,np.zeros(len(ids),dtype=np.uint8))
            poses.append(dict(image_id=image_id,frame=frame,q=list(q),t=list(translation),camera=camera_id,name=name));frames.add(frame)
            image_ids.add(image_id)
    points=[];point_ids=[];seen_ids=set();offsets=[0];links=array('q')
    for number,line in _records(folder/'points3D.txt'):
        t=line.split() if with_tracks else line.split(maxsplit=8)
        if len(t)<8 or (with_tracks and (len(t)-8)%2):raise ValueError(f'Malformed points3D.txt line {number}')
        point_id=int(t[0]);xyz=tuple(map(float,t[1:4]));rgb=tuple(map(int,t[4:7]));error=float(t[7])
        if point_id<0 or point_id in seen_ids:raise ValueError(f'Duplicate or invalid point ID: {point_id}')
        _finite(xyz+(error,),'3D point')
        if any(c<0 or c>255 for c in rgb) or error<0:raise ValueError('Invalid point color or error.')
        points.append((xyz,tuple(c/255 for c in rgb),error));point_ids.append(point_id);seen_ids.add(point_id)
        if with_tracks:links.extend(map(int,t[8:]));offsets.append(len(links)//2)
    tracks=TrackData(images,point_ids,points,offsets,links) if with_tracks else None
    return Reconstruction(cameras,sorted(poses,key=lambda p:p['frame']),points,tracks)
