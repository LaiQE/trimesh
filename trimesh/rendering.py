"""
rendering.py
--------------

Functions to convert trimesh objects to pyglet/opengl objects.
"""

import numpy as np

try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from pyglet import gl
    # bring in mode enum
    GL_LINES, GL_POINTS, GL_TRIANGLES = (
        gl.GL_LINES,
        gl.GL_POINTS,
        gl.GL_TRIANGLES)
except BaseException:
    # otherwise provide mode flags
    # this is so we can unit test without pyglet
    GL_POINTS, GL_LINES, GL_TRIANGLES = (0, 1, 4)

from . import util


def convert_to_vertexlist(geometry, **kwargs):
    """
    Try to convert various geometry objects to the constructor
    args for a pyglet indexed vertex list.

    Parameters
    ------------
    obj : Trimesh, Path2D, Path3D, (n,2) float, (n,3) float
      Object to render

    Returns
    ------------
    args : tuple
      Args to be passed to pyglet indexed vertex list
      constructor.
    """
    if util.is_instance_named(geometry, 'Trimesh'):
        return mesh_to_vertexlist(geometry, **kwargs)
    elif util.is_instance_named(geometry, 'Path'):
        # works for Path3D and Path2D
        # both of which inherit from Path
        return path_to_vertexlist(geometry, **kwargs)
    elif util.is_instance_named(geometry, 'PointCloud'):
        # pointcloud objects contain colors
        return points_to_vertexlist(geometry.vertices,
                                    colors=geometry.colors,
                                    **kwargs)
    elif util.is_instance_named(geometry, 'ndarray'):
        # (n,2) or (n,3) points
        return points_to_vertexlist(geometry, **kwargs)
    else:
        raise ValueError('Geometry passed is not a viewable type!')


def mesh_to_vertexlist(mesh,
                       group=None,
                       smooth=True,
                       smooth_threshold=60000):
    """
    Convert a Trimesh object to arguments for an
    indexed vertex list constructor.

    Parameters
    -------------
    mesh : trimesh.Trimesh
      Mesh to be rendered
    group : str
      Rendering group for the vertex list
    smooth : bool
      Should we try to smooth shade the mesh
    smooth_threshold : int
      Maximum number of faces to smooth shade

    Returns
    --------------
    args : (7,) tuple
      Args for vertex list constructor
    """

    if hasattr(mesh.visual, 'uv') and mesh.visual.uv is not None:
        # if the mesh has texture defined pass it to pyglet
        vertex_count = len(mesh.vertices)
        normals = mesh.vertex_normals.reshape(-1).tolist()
        faces = mesh.faces.reshape(-1).tolist()
        vertices = mesh.vertices.reshape(-1).tolist()

        # get the per- vertex UV coordinates
        uv = mesh.visual.uv
        # if someone passed (n, 3) UVR cut it off here
        if uv.shape[1] > 2:
            uv = uv[:, :2]
        # texcoord as (2,) float
        color_gl = ('t2f/static',
                    uv.astype(np.float64).reshape(-1).tolist())

    elif smooth and len(mesh.faces) < smooth_threshold:
        # if we have a small number of faces and colors defined
        # smooth the  mesh by merging vertices of faces below
        # the threshold angle
        mesh = mesh.smoothed()
        vertex_count = len(mesh.vertices)
        normals = mesh.vertex_normals.reshape(-1).tolist()
        faces = mesh.faces.reshape(-1).tolist()
        vertices = mesh.vertices.reshape(-1).tolist()
        color_gl = colors_to_gl(mesh.visual.vertex_colors,
                                vertex_count)
    else:
        # we don't have textures or want to smooth so
        # send a polygon soup of disconnected triangles to opengl
        vertex_count = len(mesh.triangles) * 3
        normals = np.tile(mesh.face_normals,
                          (1, 3)).reshape(-1).tolist()
        vertices = mesh.triangles.reshape(-1).tolist()
        faces = np.arange(vertex_count).tolist()
        colors = np.tile(mesh.visual.face_colors,
                         (1, 3)).reshape((-1, 4))
        color_gl = colors_to_gl(colors, vertex_count)

    # create the ordered tuple for pyglet, use like:
    # `batch.add_indexed(*args)`
    args = (vertex_count,    # number of vertices
            GL_TRIANGLES,    # mode
            group,           # group
            faces,           # indices
            ('v3f/static', vertices),
            ('n3f/static', normals),
            color_gl)
    return args


def path_to_vertexlist(path, group=None, colors=None, **kwargs):
    """
    Convert a Path3D object to arguments for an
    indexed vertex list constructor.

    Parameters
    -------------
    path : trimesh.path.Path3D object
      Mesh to be rendered
    group : str
      Rendering group for the vertex list

    Returns
    --------------
    args : (7,) tuple
      Args for vertex list constructor
    """
    # avoid cache check inside tight loop
    vertices = path.vertices

    # get (n, 2, (2|3)) lines
    lines = np.vstack([util.stack_lines(e.discrete(vertices))
                       for e in path.entities])
    count = len(lines)

    # stack zeros for 2D lines
    if util.is_shape(vertices, (-1, 2)):
        lines = lines.reshape((-1, 2))
        lines = np.column_stack((lines, np.zeros(len(lines))))

    # index for GL is one per point
    index = np.arange(count).tolist()

    args = (count,    # number of lines
            GL_LINES,  # mode
            group,    # group
            index,    # indices
            ('v3f/static', lines.reshape(-1)),
            colors_to_gl(colors, count=count))  # default colors
    return args


def points_to_vertexlist(points,
                         colors=None,
                         group=None,
                         **kwargs):
    """
    Convert a numpy array of 3D points to args for
    a vertex list constructor.

    Parameters
    -------------
    points : (n, 3) float
      Points to be rendered
    colors : (n, 3) or (n, 4) float
      Colors for each point
    group : str
      Rendering group for the vertex list

    Returns
    --------------
    args : (7,) tuple
      Args for vertex list constructor
    """
    points = np.asanyarray(points, dtype=np.float64)

    if util.is_shape(points, (-1, 2)):
        points = np.column_stack((points, np.zeros(len(points))))
    elif not util.is_shape(points, (-1, 3)):
        raise ValueError('Pointcloud must be (n,3)!')

    index = np.arange(len(points)).tolist()

    args = (len(points),  # number of vertices
            GL_POINTS,   # mode
            group,       # group
            index,       # indices
            ('v3f/static', points.reshape(-1)),
            colors_to_gl(colors, len(points)))
    return args


def colors_to_gl(colors, count):
    """
    Given a list of colors (or None) return a GL- acceptable list of colors

    Parameters
    ------------
    colors: (count, (3 or 4)) float
      Input colors as an array

    Returns
    ---------
    colors_type : str
      Color type
    colors_gl : (count,) list
      Colors to pass to pyglet
    """

    colors = np.asanyarray(colors)
    count = int(count)
    if util.is_shape(colors, (count, (3, 4))):
        # convert the numpy dtype code to an opengl one
        colors_dtype = {'f': 'f',
                        'i': 'B',
                        'u': 'B'}[colors.dtype.kind]
        # create the data type description string pyglet expects
        colors_type = 'c' + str(colors.shape[1]) + colors_dtype + '/static'
        # reshape the 2D array into a 1D one and then convert to a python list
        colors = colors.reshape(-1).tolist()
    else:
        # case where colors are wrong shape, use a default color
        colors = np.tile([.5, .10, .20], (count, 1)).reshape(-1).tolist()
        colors_type = 'c3f/static'

    return colors_type, colors


def material_to_texture(material):
    """
    Convert a trimesh.visual.texture.Material object into
    a pyglet- compatible texture object.

    Parameters
    --------------
    material : trimesh.visual.texture.Material
      Material to be converted

    Returns
    ---------------
    texture : pyglet.image.Texture
      Texture loaded into pyglet form
    """

    # try to extract a PIL image from material
    if hasattr(material, 'image'):
        img = material.image
    else:
        img = material.baseColorTexture

    if img is None:
        return None

    # use a PNG export to exchange into pyglet
    # probably a way to do this with a PIL converter
    with util.BytesIO() as f:
        # export PIL image as PNG
        img.save(f, format='png')
        f.seek(0)
        # filename used for format guess
        gl_image = pyglet.image.load(filename='.png', file=f)

    # turn image into pyglet texture
    texture = gl_image.get_texture()

    return texture


def matrix_to_gl(matrix):
    """
    Convert a numpy row- major homogenous transformation matrix
    to a flat column- major GLfloat transformation.

    Parameters
    -------------
    matrix : (4,4) float
      Row- major homogenous transform

    Returns
    -------------
    glmatrix : (16,) gl.GLfloat
      Transform in pyglet format
    """
    matrix = np.asanyarray(matrix, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError('matrix must be (4,4)!')

    # switch to column major and flatten to (16,)
    column = matrix.T.flatten()
    # convert to GLfloat
    glmatrix = (gl.GLfloat * 16)(*column)

    return glmatrix


def vector_to_gl(array, *args):
    """
    Convert an array and an optional set of args into a
    flat vector of gl.GLfloat
    """
    array = np.array(array)
    if len(args) > 0:
        array = np.append(array, args)
    vector = (gl.GLfloat * len(array))(*array)
    return vector


def light_to_gl(light, transform, lightN):
    """
    Convert trimesh.scene.lighting.Light objects into
    args for gl.glLightFv calls

    Parameters
    --------------
    light : trimesh.scene.lighting.Light
      Light object to be converted to GL
    transform : (4, 4) float
      Transformation matrix of light
    lightN : int
      Result of gl.GL_LIGHT0, gl.GL_LIGHT1, etc

    Returns
    --------------
    multiarg : [tuple]
      List of args to pass to gl.glLightFv eg:
      [gl.glLightfb(*a) for a in multiarg]
    """

    # convert color to opengl
    gl_color = vector_to_gl(light.color.astype(np.float64) / 255.0)
    assert len(gl_color) == 4

    # cartesian translation from matrix
    gl_position = vector_to_gl(transform[:3, 3])

    # create the different position and color arguments
    args = [(lightN, gl.GL_POSITION, gl_position),
            (lightN, gl.GL_SPECULAR, gl_color),
            (lightN, gl.GL_DIFFUSE, gl_color),
            (lightN, gl.GL_AMBIENT, gl_color)]

    return args
