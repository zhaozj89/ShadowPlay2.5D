import bpy

# TODO, the patterns look similar, refactoring it later

# https://blender.stackexchange.com/questions/23086/add-a-simple-vertex-via-python
def create_triangle(name, verts):
    # create a new mesh
    mesh = bpy.data.meshes.new(name+'_mesh')
    obj = bpy.data.objects.new(name, mesh)

    # link
    bpy.context.scene.objects.link(obj)
    mesh.from_pydata(verts, [], [[0, 1, 2]])
    mesh.update()
    return obj

# https://blender.stackexchange.com/questions/6750/poly-bezier-curve-from-a-list-of-coordinates
def create_curve(name, verts):
    curve = bpy.data.curves.new(name+'_curve', type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 2

    polyline = curve.splines.new('NURBS')
    polyline.points.add(len(verts))
    for i, coord in enumerate(verts):
        x, y, z = coord
        polyline.points[i].co = (x, y, z, 1)

    # link
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.objects.link(obj)
    return [obj, curve]
