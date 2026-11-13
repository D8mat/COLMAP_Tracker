# COLMAP Tracker

Experimental Windows desktop application for video and image-sequence camera tracking with COLMAP.
The application has its own PySide6 interface and embedded OpenGL viewport.
Blender runs in the background only when exporting a `.blend` file.

## Features

- Video preview, reconstructed image sequence and synchronized camera timeline.
- Folder-based PNG, JPG/JPEG, EXR and TIFF input, source FPS, native playback and tracking.
- Clock-based playback with background frame prefetch and GPU lens correction.
- Colored sparse point cloud, camera trajectory and Z-up orbit navigation.
- Clickable ±X/±Y/±Z orientation gizmo with orthographic views.
- Click-to-select cubes and cones, XYZ move arrows and rotation rings.
- Global/local gizmo axes, whole-scene transforms, numeric editing and JSON layouts.
- Downward-facing cones with their origin at the tip.
- Camera-calibrated object overlay in the image/video pane, with adjustable opacity.
- COLMAP/GLOMAP pipeline controls, static masks, progress, logs and cancellation.
- Blender export with camera animation, points, primitives and a shared scene root.

## Requirements

- Windows, Python **3.10 or 3.11**, and an OpenGL 3.3-capable graphics driver.
- COLMAP: this application has been tested with **3.12.3**. CLI option names may
  differ in other versions. Download from [COLMAP releases](https://github.com/colmap/colmap/releases).
- FFmpeg for video-frame extraction and EXR decoding.
- Optional GLOMAP executable for the global solver.
- Optional Blender **5.2** for `.blend` export (the tested version).

Executables, third-party libraries, example videos and reconstructions are not
bundled. GPU reconstruction also requires a compatible COLMAP build and driver.

## Setup

1. Clone this repository.
2. Install Python 3.10 or 3.11 with the Windows `py.exe` launcher.
3. Run `Setup.cmd`. It creates `.venv`, installs the pinned dependencies and
   copies `config.example.json` to `config.json` if no configuration exists.
4. Edit `config.json`: set the paths for `colmap`, `ffmpeg`, and optionally
   `glomap` and `blender`. An executable on `PATH` can use its executable name.
5. Run `Start_Tracker.cmd`.

Paths with spaces are supported. Keep each executable's DLLs and support files
in its original distribution folder. Relative configuration paths resolve against
the application directory. The launcher uses the configured `python` path.

`qt_packages` is normally empty. It is an optional directory containing PySide6
and shiboken6 when reusing an existing compatible Python environment. RGBMoCap is
**not required** by the normal virtual-environment setup.

`config.json` is local and Git-ignored. Do not put machine-specific paths into
the shared example. Setup preserves existing configuration.

## Workflow

1. Choose **Open video**, or **Open sequence** and select an image folder and its FPS.
2. Set the solver, Tracking FPS, maximum image size and GPU use. Set **First
   seconds** to a short duration for testing, or `0` for the full clip.
3. Click **Start tracking**. Each run gets its own project folder.
4. On completion, inspect **Solved frames**, the camera path and point cloud.
5. Open **Scene & objects** to add primitives and edit transforms.
6. Export `.blend`, or save the scene layout as JSON.

**Stop** terminates the current subprocess and keeps partial output. Consult
`tracking.log` for failures. A failed run is not marked complete. The viewer
loads the largest disconnected reconstruction, rather than merging components.

### Image sequences

Use **File → Open image sequence…** (`Ctrl+Alt+O`) or **Open sequence** in the
header. Choose a folder containing PNG, JPG/JPEG, EXR or TIFF (`.tif`/`.tiff`) files, then enter its
source FPS (for example 24 or 29.97). All supported files directly in that folder
are included, regardless of extension case; subfolders are ignored. Natural
filename ordering places `frame_2` before `frame_10`. Gaps in filenames are played
consecutively, starting at timeline frame 1. Keep one sequence in each folder.

**Source** plays the original sequence with background prefetch. Frame stepping,
Space play/pause/replay, In/Out, loop, playback speed, Fit/100% and image overlays
use the same controls as video. Decoding is asynchronous; large EXRs may play
below the requested FPS. The displayed camera follows the presented frame.

**Tracking FPS** can sample fewer frames than the source rate, but cannot exceed
sequence FPS. The pipeline makes numbered copies of selected PNG/JPG images and
converts selected EXRs and TIFFs into PNGs in the new job folder. Dimensions must match.
TIFF supports 8-bit and 16-bit RGB images; 16-bit precision is retained in the
PNG working copies. Each file is one frame; a multipage TIFF uses its first page.
EXR RGB uses a fixed linear-to-sRGB conversion for both preview and tracking;
this is an 8-bit display/tracking representation, not an HDR grading workflow.
No exposure adjustment, arbitrary EXR layer selection or deep EXR is provided.
Original files are never modified. **Generate 3D mesh** also accepts this source.

Projects save the sequence folder, FPS and exact ordered filename list. Reopening
does not silently include newly added images. A missing image fails reopening
without replacing the current project; a moved folder can be relinked. Older
video-only projects remain supported. `validate_image_sequence.py` checks actual
PNG/JPG/EXR/TIFF decoding, playback, project round trips, overlay association and the
first tracking preparation stage; it does not assess reconstruction quality.

## Viewport and editing

The interface adapts the [Shadow theme by --Shadow--](https://extensions.blender.org/themes/shadow/):
neutral dark panels, light text, blue selection and gently rounded controls.
Scene rows and actions have vector icons, including distinct cube, downward cone,
point cloud, mesh and camera symbols. Show/Lock retain their checkbox controls.

Both preview windows reuse the same prepared primitive geometry. Object or shading
edits rebuild it; camera movement does not. The 3D viewport also retains unchanged
object and surface buffers on the GPU. Video resolution and projection stay unchanged.
On the prepared 2160×3840 / 29.97 fps clip with 16 cubes/cones, a six-second local
profile measured average 3D draw time of 0.62 ms (previously 2.93 ms) and video-canvas
paint time of 4.44 ms (previously 6.39 ms). Both runs presented about 30 fps; this
reduces rendering overhead, not the source frame interval. The roughly 13 ms video
frame conversion/presentation cost remains and depends on the machine and codec.

**Scene & objects** contains a tree of the scene, reconstruction components
and cubes/cones. Selection follows clicks in either the tree or 3D view.
**Show** toggles a primitive in both views; **Lock** prevents picking/editing its
transform (it still follows Whole scene). Double-click or **Rename** changes its
name; **Duplicate** creates an unlocked copy. Visibility and locks are saved in
projects/layouts and carried into Blender export. `F` frames the selection,
`Ctrl+D` duplicates, `Delete` removes and `F2` renames it.

**Edit → Undo/Redo** (`Ctrl+Z` / `Ctrl+Shift+Z`) shares one history for object
operations, transforms, floor settings/alignment and camera corrections. One
gizmo drag is one step; `Esc` cancels it. History resets on project/model replacement
and is not stored on disk. Text fields keep native text undo.

| Action | Control |
| --- | --- |
| Select primitive | Click its surface in the 3D viewport |
| Move | `E` (`G` also works) or **Move**, then drag an axis arrow |
| Rotate | `R` or **Rotate**, then drag a rotation ring |
| Uniform scale | `T` or **Scale**, then drag the square outward/inward |
| Cancel current transform | `Esc` while dragging |
| Change transform axes | **Scene & objects → Gizmo axes → Global/Local** |
| Select whole scene | Click empty space, or choose **Whole scene** in the panel |
| Orbit | Drag empty space with the left mouse button |
| Pan / zoom | Right or middle drag / mouse wheel |
| Axis-aligned view | Click the corner orientation gizmo |
| Reset view | **Fit scene** |

Transform shortcuts work across the window except in text/numeric inputs,
combo boxes and dialogs, and during floor picking or an active drag. Scale is
uniform across XYZ, keeping the selected origin fixed. The cone's downward tip
is its local origin. Whole-scene transforms include the camera, trajectory,
points and added objects. As a result, these transforms preserve image alignment;
move an individual object to change its placement in the overlay.

The image overlay uses the solved camera calibration. It does not occlude virtual
objects behind real-world objects; sparse points are not a scene depth mesh.

## Existing models

**Import TXT model** accepts a folder with `cameras.txt`, `images.txt` and
`points3D.txt`. Image filenames must end with a frame number, such as
`frame_000001.jpg`. Choose the corresponding image directory if it is not found.
Set **Import FPS** before loading an external model. App-generated project folders
recover their tracking rate from `settings.json`.

The optional **Prepared scene** button uses a locally configured `sample_project`
with `04 SCENES/IMG_2284_nonHDR/sparse`, its sibling `images`, and
`02 VIDEOS/IMG_2284_nonHDR.mov`. This developer fixture is not distributed.
The application always starts with an empty project. The configured fixture is
loaded only when you click **Prepared scene**.

## Camera keyframe graph and floor grid

### Projects and the File menu

The application window is named **ALIEN TRACKER**. The source folder and
repository remain COLMAP_Tracker.

**File** provides **New project** (`Ctrl+N`), **Open video** (`Ctrl+O`),
**Open project** (`Ctrl+Shift+O`), **Save project** (`Ctrl+S`), **Save project as**
(`Ctrl+Shift+S`) and **Exit** (`Alt+F4`). Opening a different video starts a fresh
project after offering to save existing edits. New project clears the scene,
camera corrections, model, mesh and video, without deleting files on disk.

A `.tracker.json` project stores tracking settings, source/model/image/mesh
references, frame rate, camera corrections, scene transforms, cubes/cones,
floor settings, shading and the current view/timeline. Media and reconstruction
files are referenced, not embedded. Keep them with the project when moving it;
relative paths are used where possible. Missing assets can be located again
before replacing the current project; Save preserves the new paths. Cancelled
relinking and invalid files leave the current project intact. Saves are atomic.

**File → Recent projects** lists ten recent files. Unsaved work autosaves every
30 seconds to `projects/.recovery`, separately from the manual save. After an
interrupted session, startup reports available snapshots under **File → Recover
autosave** while still opening an empty project. Save the recovered project to
keep it. Referenced assets must remain available. Active sessions are excluded
from recovery lists. Autosave waits during loading, solving, meshing or a drag.

**Generate 3D mesh** in the left panel uses the current reconstruction when it
belongs to the selected video. Otherwise it runs tracking using the current
settings, loads the solve and starts surface generation automatically. **Stop**
cancels tracking and its queued mesh step, or the running mesh job. Surface
detail and trimming are available in **Shading…**. This uses the sparse surface
workflow described below, not dense stereo.

### Aligning a floor from points

Click **Align floor… → Pick floor points**, then click at least three points
spread across the same floor in the 3D viewport. Numbered markers show the
selection; clicking one again removes it. Drag to orbit, use the axis gizmo for
side/top views, and press Escape to leave selection mode. The mesh is temporarily
hidden and points are shown while picking.

**Align floor to Z = 0** fits a plane and rotates/translates the whole scene so
the selected floor is horizontal. Camera, cloud, mesh and objects move together,
preserving their image alignment. Scale is preserved. Collinear or markedly
non-planar selections are rejected. **Edit → Undo** / **Undo last edit** restores
the latest project edit, including floor alignment. Project saving includes the resulting
alignment. This is manual point-based alignment, not automatic floor detection.

Press **Space** to play/pause either source video or solved-frame playback,
including while the 3D viewport or timeline has focus. Text/numeric inputs,
combo boxes and dialogs keep their usual keyboard behavior. Holding Space
does not repeatedly toggle playback.
At the end, pressing **Space** or **Play** starts again from the beginning in
both modes. Pausing in the middle and playing again resumes at that position.

**Left/Right** step a frame, **Home/End** jump to clip ends and **Frame** jumps
to a number. **In/Out** (`I` / `O`) set the playback range; **Clear** resets it.
**Loop** repeats the range; speed supports 0.25×–2×. Source/solved ranges are
separate and saved with the project. Source indexing uses `ffprobe.exe` beside
FFmpeg and actual presentation timestamps, including variable frame spacing.
Stepping is enabled after indexing. If ffprobe is unavailable, ordinary video
playback remains available and the toolbar explains the missing indexer.

In the image pane, wheel zooms around the pointer, middle/right drag pans,
**Fit** resets the view and **100%** shows one image pixel per screen pixel.
**Loupe** magnifies under the pointer and **Hide overlays** shows the clean image.
Video, grid and geometry use the same image transform. Full-resolution images
decode as needed; geometry-overlay raster resolution is capped at 1600 pixels
on the long edge to bound lens-warp memory. **Help → Keyboard & mouse controls**
lists the shortcuts.

Playback follows elapsed video time, skipping overdue frames instead of building
up delay. Solved images decode on a background thread with a bounded 96 MiB cache
(up to 48 images; one unusually large image may exceed that budget). A paused
seek loads the exact selected frame, and camera overlays follow the displayed
image. Source video keeps the newest pending frame. The camera graph reuses its
curves until edited or resized, and lens distortion is applied on the GPU.
This keeps the existing preview resolution and original media unchanged; the
achievable frame rate still depends on the video, overlays and hardware.

Enable **Keyframe graph** below the views to inspect camera motion. Choose
**Position XYZ**, **Translation XYZ** (signed displacement per frame),
**Rotation jump** (degrees per frame), or **Translation total** (displacement magnitude).
Translation XYZ shows ΔX in red, ΔY in green and ΔZ in blue, in Z-up reconstruction
units per frame. Use **XYZ / X only / Y only / Z only** to isolate a component;
the vertical scale follows the visible axes. Negative values show the opposite
direction, and a dashed zero line separates the signs. The first camera uses a
zero baseline; across missing cameras, deltas are divided by the frame gap and
the plotted line remains broken. Dashed curves show the original solve;
solid curves show the current result. Amber ticks mark corrected frames.
Click the graph to select a solved frame, or choose **Around frame ±50** to
inspect a smaller section. Missing cameras appear as gaps. A large jump may
also be real camera movement; the graph does not automatically classify errors.

For a selected frame, edit **X/Y/Z** and **RX/RY/RZ**, then click **Apply pose**.
Enable **Only this frame** to pin manual camera editing to that solved frame.
The editor shows its frame number. Browsing other frames makes the pose fields,
axis drags, Apply, Reset and Interpolate read-only. **Go to edit frame** returns
to the pinned frame; **Use current frame** explicitly chooses a new target.
Turning the lock off follows the selected frame, still editing only that one
camera at a time. The lock is a session editing aid and resets on model/project
replacement. It applies to solved camera frames: at lower tracking FPS, several
source-video frames may share the same solved pose. Enabling the lock switches
to the selected Solved frame so its target is unambiguous.
These are absolute camera coordinates in the Z-up reconstruction, before the
whole-scene transform. Focusing a numeric field pauses playback.
Alternatively, drag the **X ↔ / Y ↔ / Z ↔ / RX° ↔ / RY° ↔ / RZ° ↔** labels
horizontally: changes apply live to the image, reprojection overlay and 3D view.
Hold **Shift** for 10× finer movement; **Drag speed** offers 0.1× / 1× / 10×.
Position sensitivity adapts to the solved camera-path scale; rotation uses
0.1° per pixel at 1×. Releasing commits one Undo step; **Esc**, focus loss or
a frame change cancels the in-progress drag. A simple click makes no correction.
Playback pauses on press. Save/autosave cannot capture a partially completed drag.
Typed values still use Apply pose. These controls adjust the selected camera pose;
they do not move measured 2D markers or run a new solve.
**Interpolate ±5** preserves the selected camera exactly, including its manual
correction, and blends five neighbouring frames on each side towards it. The
range control allows ±5 to ±100 frames. Unchanged cameras just outside the range
are anchors (normally ±6 for the default range); inspect these first. Position
is linear and rotation follows the shortest quaternion arc, weighted by frame
distance. Missing solved frames are skipped. At clip edges the range is shortened
and endpoints remain anchors; one-sided interpolation is supported. Existing
corrections inside the neighbour range are replaced. This explicit range action
also works at the pinned centre with **Only this frame** enabled; pose fields and
drags still edit only that centre. The entire range is one Undo/Redo step.
**Reset frame** restores the solve; **Undo** reverses the last project edit.
Corrections update image overlays, the 3D camera/path and Blender export.
They change camera poses, not lens calibration, points or the source model files.
`validate_camera_drag.py` exercises all six drag axes, live preview, grouped
Undo/Redo, Shift/speed, release-position capture, cancellation and save guards.
`validate_translation_graph.py` verifies rendered XYZ curves, axis isolation,
the total-magnitude fallback, frame selection and plot-cache invalidation.
`validate_interpolation_range.py` checks ±5/±6 ranges, exact centre preservation,
unchanged exterior cameras, shared Undo/Redo and the frame-lock guard.

Use **Save corrections…** / **Load corrections…** for a separate JSON file.
The file is tied to the exact reconstruction; another model is rejected.
The app offers to save unsaved corrections before closing or replacing a model.
Scene layout files and camera correction files are separate.

**Floor grid** overlays the world XY plane in both **Solved frames** and the
matching source video. **Step** sets grid spacing; **Z** sets its height, also
in the 3D viewport. The grid spans 10 steps on each side of the origin. It follows
the calibrated camera, including supported lens distortion. Align the scene
using **Scene & objects**; the floor is not automatically inferred from the video.
The grid is a visual guide and is not exported as geometry or occluded by filmed
objects. It can be toggled independently of the primitive overlay.

## Point cloud and reconstructed mesh overlays

In the video toolbar, **Points**, **Mesh** and **Objects** toggle independent
geometry layers. The opacity slider controls their combined overlay. These work
in solved frames and in the matching original video, including manual camera
corrections. Geometry is depth-tested against the other enabled geometry layers;
filmed objects alone do not provide an occlusion mask.

Open **Shading…** for **Solid**, **Vertex color**, **Wireframe**, **Solid + wire**
and **Normals**, plus **Smooth normals** / flat shading. These modes affect the
surface mesh and primitives in both views. Point overlays have **RGB**, **Solid**
and **Depth** coloring and a pixel-size control. Depth colors run from blue
(near) to orange (far), normalized to the visible cloud for each frame.
Vertex colors are interpolated point-cloud colors, not a photographic texture.

**Build surface mesh** creates an approximate continuous triangle surface using
the configured COLMAP `poisson_mesher`. It runs as a separate process; **Cancel
mesh** stops the worker and COLMAP child while preserving the previous mesh.
**Mesh detail** controls octree depth, **Max input points** controls spatial
sampling, and **Density trim** removes weakly supported surface. Increase trim
to remove speculative geometry; decrease it if too much surface disappears.

The worker uses points observed in at least four cameras with reprojection error
at most two pixels, rejects distant outliers, estimates local normals, orients
them toward observing cameras, then removes unsupported output triangles.
This deliberately favors supported geometry: holes, disconnected pieces and
smoothed details remain possible with a sparse solve. It does not run COLMAP's
dense stereo pipeline. Poisson reconstruction can extrapolate into empty areas;
see the [surface reconstruction explanation](https://www.open3d.org/docs/release/tutorial/geometry/surface_reconstruction.html).
Open3D itself is not required; meshing uses COLMAP and SciPy.

Generated meshes and logs live in `projects/meshes/`. The last completed mesh
reloads with its matching reconstruction. **Load saved mesh…** accepts these
model-bound `.npz` files. **Export mesh .ply…** exports vertex colors and bakes
the whole-scene transform into Z-up world coordinates. **Export .blend** includes
the loaded mesh under the scene root with its vertex-color material. The mesh
belongs to the whole scene; it is not an independently selectable primitive.

The video overlay renders on the GPU with depth and near-plane clipping, then
applies inverse radial/OpenCV lens mapping to the raster. This keeps distorted
triangle interiors aligned, rather than only distorting projected vertices.

## Limitations

- Tracking FPS resamples video to an integer rate; it need not equal source FPS.
- Missing registered poses are not solved cameras. Interpolation in exported
  animation is not a new camera solve.
- The point preview is capped at 200,000 points. Original model files are retained.
- Z-up is a coordinate conversion, not gravity estimation or automatic ground alignment.
- Only static image masks are supported: black excludes, white retains pixels.
- Manual 2D track editing, moving-object tracking and dense reconstruction are not implemented.
- Blender exports link to image sequences; the `.blend` alone is not a self-contained media bundle.
- GLOMAP is wired into the pipeline but its reconstruction run has not been validated here.
- This is a source prototype, not a packaged portable executable.

## Validation

Run the portable core tests with:

```powershell
.venv\Scripts\python.exe -m unittest test_core test_camera_track test_mesh test_project_floor test_preview_cache
```

The cancellation test requires configured FFmpeg and COLMAP; otherwise it skips.
Run real interactive OpenGL picking/gizmo tests with:

```powershell
.venv\Scripts\python.exe validate_manipulators.py
.venv\Scripts\python.exe validate_camera_tools.py
.venv\Scripts\python.exe validate_projection.py
.venv\Scripts\python.exe validate_projects_floor.py
```

Other `validate_*.py` scripts are developer integration checks using the optional
local `IMG_2284_nonHDR` fixture. They require an interactive Windows desktop;
some run reconstruction or Blender and write output into `validation/`.
`validate_mesh_overlay.py` builds a real surface, exercises video/mesh shading,
tests process-tree cancellation, and checks PLY and Blender export.
`validate_video_mesh_flow.py` tests the one-button video-to-mesh sequence on an
8-second fixture clip, project saving, and cancellation of the queued mesh step.
`validate_realtime_preview.py` checks the playback clock, frame/camera pairing,
rapid seeks, graph invalidation, last-frame pause, source-frame coalescing and
cache shutdown. `validate_projection.py` also compares GPU lens correction with
the calibrated CPU reference, including transparent edges.

Verified during development: source-video playback, a 1,349-pose reconstruction,
a new 8-second COLMAP run with 24 registered cameras, calibrated primitive overlay,
XYZ gizmo drags/rotations, cancellation, and Blender export preserving scene-root
transforms and cone-tip origins. Fresh-install setup is separate from those tests.

## Source layout

**Track data…** below the reconstruction statistics opens a read-only table of
registered frames. Double-click a row or choose **Go to selected frame** to inspect
that solved image. It lists measured 2D features, valid 2D-to-3D associations,
untriangulated features and invalid references. These counts are not pixel error
or a quality score. Only registered images are present; missing-camera detection,
aggregate error graphs and marker editing are subsequent roadmap steps.

Enable **Track error** above the image in **Solved frames** to see measured points
as circles, projected points as crosses and a line joining each pair. Green means
error ≤1 px, yellow ≤3 px, and red >3 px, in the imported model's image pixels;
zoom, pan, preview resolution and whole-scene/floor transforms do not change it.
**Current camera** includes manual pose corrections; **Original solve** compares
the same measurements with the original imported camera. Undo updates the overlay.
**Options…** opens minimum-error and maximum-marker controls in Track data.
The default displays at most 1,000 markers, prioritising the largest errors, so
the visible colors are not an unbiased sample of all tracks. Untriangulated or
invalid links are excluded; points behind the camera/non-finite projections are
reported as not projectable, never assigned zero error. Unsupported lenses show
an explicit unavailable message. Supported lenses are SIMPLE_PINHOLE, PINHOLE,
SIMPLE_RADIAL, RADIAL and OPENCV.

Measured diagnostics use the imported camera and its associated solved image,
including either original distorted or undistorted models. **Source video** asks
you to switch to Solved frames: no approximate pairing of measured features with
intermediate video frames or mixing of raw/undistorted coordinates. Ordinary 3D
video overlays continue working. Display options persist in projects; older
projects default to diagnostics off. On the prepared clip, 1,000 markers painted
at about 17 ms per frame in a four-second run, with about 30 paints/second.

The importer preserves original image/point IDs, zero-based observation indices,
XY measurements, XYZ positions and both directions of each reconstructed track.
A reconstructed track is identified by its point ID; an untriangulated observation
by its image ID and observation index. The full arrays are separate from the sampled
Z-up viewport and unchanged by scene/camera corrections. XY belongs to the imported
model's image domain; source-video and undistorted coordinates must not be mixed.
Table time is `(numbered frame - 1) / tracking FPS`, not a source-video frame index.
See the [COLMAP format specification](https://colmap.github.io/format.html).

Text files are streamed and the app loads them in its existing background worker.
The prepared 1,349-image fixture contains 343,352 points and 13,836,119 observations;
full import took about 16 seconds locally, with about 414 MiB in the principal
diagnostic arrays (additional Python/display data uses more memory). Export and
mesh workers use the lightweight geometry-only mode. Projects keep external model
references; reopening reconstructs the diagnostic data from those model files.
Malformed records/duplicate IDs are rejected. Inconsistent track references and
non-finite XY are retained and flagged instead of silently becoming valid tracks.

`test_track_data.py` covers non-contiguous/large IDs, empty observations, invalid
links, precision, malformed input and geometry-only compatibility.
`validate_track_data.py` checks the inspector, frame navigation, viewport ID mapping,
project reopening/reset and the full prepared fixture.
`test_reprojection.py` checks residuals against independent analytic projection,
including a deliberately damaged measurement, supported distortion models and
corrected poses. `validate_reprojection.py` checks pixel placement through zoom/pan,
toggle/Undo behavior, source/frame guards, settings persistence and real playback.

`validate_p0.py` creates a 29.97 fps fixture to verify stepping, ranges/loop/rate,
object-list operations, grouped undo, recovery isolation and relinking. It uses
isolated recovery state under `validation/` and captures the themed interface.

- `transport.py`: indexed source timestamps, stepping, ranges, looping and speed.
- `edit_history.py`, `project_recovery.py`: shared undo, recovery and recent files.
- `ui_theme.py`: Qt adaptation of the Shadow palette; `scene_icons.py`: vector inspector icons.

See [ROADMAP.md](ROADMAP.md) for the feature audit, comparison with other tracking
tools, priorities and acceptance criteria for planned work.

- `desktop.py`: application UI, video and processing controls.
- `preview_cache.py`: background solved-frame decoding and bounded prefetch cache.
- `desktop_viewport.py`, `manipulation.py`: OpenGL rendering, picking and gizmos.
- `scene_editor.py`, `scene_geometry.py`, `image_overlay.py`: primitives and calibration.
- `camera_track.py`, `camera_editor.py`: camera corrections, graph and interpolation.
- `floor_grid.py`: calibrated ground-grid projection and clipping.
- `mesh_worker.py`, `mesh_data.py`, `mesh_panel.py`: surface generation, persistence and shading controls.
- `overlay_renderer.py`, `lens_warp.py`: GPU geometry overlays and calibrated raster distortion.
- `pipeline.py`: subprocess pipeline and COLMAP text-model reader.
- `track_data.py`, `track_data_panel.py`: full observations, track associations and import inspector.
- `reprojection.py`, `reprojection_overlay.py`: per-frame pixel residuals and bounded diagnostic marker drawing.
- `export_desktop.py`, `tracker.py`: background Blender export and the earlier native Blender prototype.

The importer is implemented independently from the
[COLMAP output format](https://colmap.github.io/format.html).
The optional [Blender Photogrammetry Importer](https://github.com/SBCV/Blender-Addon-Photogrammetry-Importer)
is not bundled or installed. External tools and dependencies retain their own licenses.

## Repository layout

- `app/`: application modules and workers.
- `tests/`: unit tests and interactive validation scripts.
- `docs/`: help and roadmap.
- `projects/`: user projects and reconstruction output (paths preserved).
- `validation/`: generated test artifacts.
- `temp/`: older loose previews and logs.

Launch with `Start_Tracker.cmd`; configuration and setup remain at the root.
Run unit tests with `python -m unittest discover -s tests -p "test_*.py"`.
Run interactive checks with `python tests/validate_image_sequence.py`.
