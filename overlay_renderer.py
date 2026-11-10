"""Depth-tested offscreen OpenGL geometry overlay using the solved lens model."""
import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat, QMatrix4x4, QImage
from PySide6.QtOpenGL import (QOpenGLFunctions_3_3_Core, QOpenGLShader, QOpenGLShaderProgram,
    QOpenGLBuffer, QOpenGLVertexArrayObject, QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat)
from scene_geometry import mesh_geometry, transform_matrix
from mesh_data import triangle_buffer
from lens_warp import distortion_map,warp_rgba,lens_parameters


def primitive_mesh(item):
    vertices, polygons = mesh_geometry(item['kind'])
    m = transform_matrix(item)
    vertices = vertices @ m[:3, :3].T + m[:3, 3]
    faces = np.array([(f[0], f[i], f[i+1]) for f in polygons for i in range(1, len(f)-1)])
    return dict(vertices=vertices, faces=faces, colors=np.tile(item['color'], (len(vertices), 1)))


class CalibratedRenderer:
    def __init__(self):
        self.context = None
        self.framebuffer = None
        self.buffers = {}
        self.cache_key = None
        self.cached_image = None
        self.mapping_key = None
        self.mapping = None

    def initialize(self):
        fmt = QSurfaceFormat(); fmt.setVersion(3, 3); fmt.setProfile(QSurfaceFormat.CoreProfile); fmt.setDepthBufferSize(24)
        self.surface = QOffscreenSurface(); self.surface.setFormat(fmt); self.surface.create()
        self.context = QOpenGLContext(); self.context.setFormat(fmt)
        if not self.context.create() or not self.context.makeCurrent(self.surface):
            self.context = None
            raise RuntimeError('OpenGL 3.3 overlay context is unavailable.')
        self.gl = QOpenGLFunctions_3_3_Core(); self.gl.initializeOpenGLFunctions()
        self.program = QOpenGLShaderProgram()
        vertex = '''#version 330 core
layout(location=0) in vec3 position; layout(location=1) in vec3 color;
uniform mat4 worldToCamera;
uniform vec4 intrinsics;
uniform vec2 imageSize; uniform float pointSize;
out vec3 rgb; out float cameraDepth;
void main(){
    vec3 c=(worldToCamera*vec4(position,1)).xyz;
    vec2 px=c.xy*intrinsics.xy+intrinsics.zw*c.z;
    vec2 clipXY=vec2(2*px.x/imageSize.x-c.z,c.z-2*px.y/imageSize.y);
    float nearPlane=.001; float farPlane=100000.;
    gl_Position=vec4(clipXY,((farPlane+nearPlane)*c.z-2*farPlane*nearPlane)/(farPlane-nearPlane),c.z);
    gl_PointSize=pointSize; rgb=color; cameraDepth=c.z;
}'''
        fragment = '''#version 330 core
in vec3 rgb; in float cameraDepth;
uniform int pointsMode; uniform int colorMode; uniform vec3 tint; uniform vec2 depthRange;
out vec4 frag;
void main(){
    if(pointsMode==1 && length(gl_PointCoord-vec2(.5))>.5)discard;
    vec3 color=rgb;
    if(colorMode==1)color=tint;
    if(colorMode==2){float t=clamp((cameraDepth-depthRange.x)/max(.0001,depthRange.y-depthRange.x),0,1);
        color=mix(vec3(.16,.65,1.),vec3(1.,.35,.12),t);}
    frag=vec4(color,1);
}'''
        if not self.program.addShaderFromSourceCode(QOpenGLShader.Vertex, vertex) or not self.program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment) or not self.program.link():
            raise RuntimeError(self.program.log())
        self.vao = QOpenGLVertexArrayObject(); self.vao.create()

    def uniform(self, name, *values):
        location = self.program.uniformLocation(name)
        if len(values) == 1 and isinstance(values[0], int): self.gl.glUniform1i(location, values[0])
        else: getattr(self.gl, f'glUniform{len(values)}f')(location, *map(float, values))

    def draw(self, key, data, mode):
        if not len(data): return
        if key not in self.buffers:
            buffer = QOpenGLBuffer(); buffer.create(); self.buffers[key] = [buffer, None]
        buffer, previous = self.buffers[key]
        buffer.bind(); self.vao.bind()
        if previous is not data:
            raw = np.ascontiguousarray(data, np.float32).tobytes(); buffer.allocate(raw, len(raw))
            self.buffers[key][1] = data
        self.program.enableAttributeArray(0); self.program.enableAttributeArray(1)
        self.program.setAttributeBuffer(0, 0x1406, 0, 3, 24)
        self.program.setAttributeBuffer(1, 0x1406, 12, 3, 24)
        self.gl.glDrawArrays(mode, 0, len(data))
        self.vao.release(); buffer.release()

    def render(self, view, camera, size, points=False, mesh=False, objects=True, point_size=3., point_color='RGB'):
        key = (id(view.points), id(view.mesh), view.pose.tobytes(), repr(camera), size.width(), size.height(),
               points, mesh, objects, point_size, point_color, view.shading, view.smooth_mesh, view.selected, repr(view.objects) if objects else '')
        if key == self.cache_key: return self.cached_image
        mapping_key=(repr(camera),size.width(),size.height())
        if mapping_key!=self.mapping_key:
            self.mapping=distortion_map(camera,size.width(),size.height());self.mapping_key=mapping_key
        mapping=self.mapping
        render_camera=mapping['camera'] if mapping else camera
        render_size=QSize(*mapping['size']) if mapping else size
        if self.context is None: self.initialize()
        if not self.context.makeCurrent(self.surface): raise RuntimeError('Cannot activate overlay context.')
        try:
            if self.framebuffer is None or self.framebuffer.size() != render_size:
                self.framebuffer = None
                fmt = QOpenGLFramebufferObjectFormat(); fmt.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
                self.framebuffer = QOpenGLFramebufferObject(render_size, fmt)
            if not self.framebuffer.isValid(): raise RuntimeError('Overlay framebuffer allocation failed.')
            self.framebuffer.bind()
            gl = self.gl
            gl.glViewport(0, 0, render_size.width(), render_size.height()); gl.glClearColor(0, 0, 0, 0); gl.glClear(0x4000|0x0100)
            gl.glEnable(0x0B71); gl.glDepthFunc(0x0203); gl.glEnable(0x8642)
            self.program.bind()
            # Camera and reconstructed geometry share the scene root, which cancels.
            inv = np.diag([1, -1, -1, 1]) @ np.linalg.inv(view.pose)
            self.program.setUniformValue(self.program.uniformLocation('worldToCamera'), QMatrix4x4(*inv.reshape(-1).tolist()))
            self.uniform('intrinsics', *lens_parameters(render_camera)[0]);self.uniform('imageSize',render_camera[1],render_camera[2])
            self.uniform('pointSize', float(point_size)); self.uniform('pointsMode', 0); self.uniform('colorMode', 0)
            geometry = []
            if mesh and view.mesh is not None: geometry.append(('surface', view.mesh_preview()))
            if objects and view.objects:
                parts=[]
                for index,item in enumerate(view.objects):
                    part=triangle_buffer(primitive_mesh(item), view.shading, view.smooth_mesh)
                    if index==view.selected:part[:,3:]=np.minimum(1,part[:,3:]+.12)
                    parts.append(part)
                data = np.concatenate(parts)
                geometry.append(('objects', data))
            if view.shading != 'Wireframe':
                gl.glEnable(0x8037); gl.glPolygonOffset(1., 1.)
                for name, data in geometry: self.draw(name, data, 0x0004)
                gl.glDisable(0x8037)
            if view.shading in ('Wireframe', 'Solid + wire'):
                gl.glPolygonMode(0x0408, 0x1B01)
                self.uniform('colorMode', 1); self.uniform('tint', .1, .85, .95)
                for name, data in geometry: self.draw(name, data, 0x0004)
                gl.glPolygonMode(0x0408, 0x1B02)
            if points:
                self.uniform('pointsMode', 1); self.uniform('colorMode', {'RGB': 0, 'Solid': 1, 'Depth': 2}[point_color])
                self.uniform('tint', .2, .85, 1.)
                if point_color == 'Depth' and len(view.points):
                    z = view.points[:, :3] @ inv[2, :3] + inv[2, 3]; z = z[z > .001]
                    self.uniform('depthRange', *(np.percentile(z, [5, 95]) if len(z) else [0, 1]))
                self.draw('points', view.points, 0x0000)
            self.program.release()
            result = self.framebuffer.toImage()
            self.framebuffer.release()
            if mapping:
                rgba=result.convertToFormat(QImage.Format_RGBA8888)
                source=np.frombuffer(rgba.bits(),np.uint8).reshape(rgba.height(),rgba.bytesPerLine()//4,4)[:,:rgba.width()]
                warped=warp_rgba(source,mapping)
                result=QImage(warped.data,size.width(),size.height(),int(warped.strides[0]),QImage.Format_RGBA8888_Premultiplied).copy()
            self.cache_key, self.cached_image = key, result
            return result
        finally:
            self.context.doneCurrent()

    def close(self):
        if self.context and self.context.makeCurrent(self.surface):
            self.framebuffer = None
            for buffer, _ in self.buffers.values(): buffer.destroy()
            self.buffers.clear()
            if hasattr(self,'vao'):self.vao.destroy()
            if hasattr(self,'program'):self.program.removeAllShaders()
            self.context.doneCurrent()
        self.context = None
