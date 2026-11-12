# COLMAP Tracker

Experimental Windows desktop application for video camera tracking with COLMAP.
The application has its own PySide6 interface and embedded OpenGL viewport.
Blender runs in the background only when exporting a `.blend` file.

## Features

- Video preview, reconstructed image sequence and synchronized camera timeline.
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
- FFmpeg for video-frame extraction.
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

1. Choose **Open video**.
2. Set the solver, Tracking FPS, maximum image size and GPU use. Set **First
   seconds** to a short duration for testing, or `0` for the full clip.
3. Click **Start tracking**. Each run gets its own project folder.
4. On completion, inspect **Solved frames**, the camera path and point cloud.
5. Open **Scene & objects** to add primitives and edit transforms.
6. Export `.blend`, or save the scene layout as JSON.

**Stop** terminates the current subprocess and keeps partial output. Consult
`tracking.log` for failures. A failed run is not marked complete. The viewer
loads the largest disconnected reconstruction, rather than merging components.

## Viewport and editing

| Action | Control |
| --- | --- |
| Select primitive | Click its surface in the 3D viewport |
| Move | `G` or **Move**, then drag an axis arrow |
| Rotate | `R` or **Rotate**, then drag a rotation ring |
| Cancel current transform | `Esc` while dragging |
| Change transform axes | **Scene & objects → Gizmo axes → Global/Local** |
| Select whole scene | Click empty space, or choose **Whole scene** in the panel |
| Orbit | Drag empty space with the left mouse button |
| Pan / zoom | Right or middle drag / mouse wheel |
| Axis-aligned view | Click the corner orientation gizmo |
| Reset view | **Fit scene** |

Keyboard shortcuts apply while the viewport has focus. The cone's downward tip
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
relative paths are used where possible. Missing assets or invalid project files
leave the current project intact. Saves replace the document atomically.

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
non-planar selections are rejected. **Undo floor alignment** restores the prior
scene transform and floor height. Project saving includes the resulting
alignment. This is manual point-based alignment, not automatic floor detection.

Press **Space** to play/pause either source video or solved-frame playback,
including while the 3D viewport or timeline has focus. Text/numeric inputs,
combo boxes and dialogs keep their usual keyboard behavior. Holding Space
does not repeatedly toggle playback.

Playback follows elapsed video time, skipping overdue frames instead of building
up delay. Solved images decode on a background thread with a bounded 96 MiB cache
(up to 48 images; one unusually large image may exceed that budget). A paused
seek loads the exact selected frame, and camera overlays follow the displayed
image. Source video keeps the newest pending frame. The camera graph reuses its
curves until edited or resized, and lens distortion is applied on the GPU.
This keeps the existing preview resolution and original media unchanged; the
achievable frame rate still depends on the video, overlays and hardware.

Enable **Keyframe graph** below the views to inspect camera motion. Choose
**Position XYZ**, **Translation jump** (reconstruction units per frame), or
**Rotation jump** (degrees per frame). Dashed curves show the original solve;
solid curves show the current result. Amber ticks mark corrected frames.
Click the graph to select a solved frame, or choose **Around frame ±50** to
inspect a smaller section. Missing cameras appear as gaps. A large jump may
also be real camera movement; the graph does not automatically classify errors.

For a selected frame, edit **X/Y/Z** and **RX/RY/RZ**, then click **Apply pose**.
These are absolute camera coordinates in the Z-up reconstruction, before the
whole-scene transform. Focusing a numeric field pauses playback.
**Interpolate neighbours** repairs one frame using the previous and next solved
cameras, weighted by frame distance, with shortest-arc quaternion interpolation
for rotation. Check that both neighbours are good first. Endpoints cannot use
this repair. **Reset frame** restores the solve; **Undo** reverses a correction.
Corrections update image overlays, the 3D camera/path and Blender export.
They change camera poses, not lens calibration, points or the source model files.

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

- `desktop.py`: application UI, video and processing controls.
- `preview_cache.py`: background solved-frame decoding and bounded prefetch cache.
- `desktop_viewport.py`, `manipulation.py`: OpenGL rendering, picking and gizmos.
- `scene_editor.py`, `scene_geometry.py`, `image_overlay.py`: primitives and calibration.
- `camera_track.py`, `camera_editor.py`: camera corrections, graph and interpolation.
- `floor_grid.py`: calibrated ground-grid projection and clipping.
- `mesh_worker.py`, `mesh_data.py`, `mesh_panel.py`: surface generation, persistence and shading controls.
- `overlay_renderer.py`, `lens_warp.py`: GPU geometry overlays and calibrated raster distortion.
- `pipeline.py`: subprocess pipeline and COLMAP text-model reader.
- `export_desktop.py`, `tracker.py`: background Blender export and the earlier native Blender prototype.

The importer is implemented independently from the
[COLMAP output format](https://colmap.github.io/format.html).
The optional [Blender Photogrammetry Importer](https://github.com/SBCV/Blender-Addon-Photogrammetry-Importer)
is not bundled or installed. External tools and dependencies retain their own licenses.
