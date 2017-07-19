# class AnimationBrushes:
#     gp = [None]
#     brush_dict = {}


# def AnimationHandlerUpdateBrushes(self, context):
#     if brushes.AnimationBrushes.gp[0] == None:
#         brushes.AnimationBrushes.gp[0] = bpy.data.grease_pencil.new('AnimationPencil')
#
#     gp = brushes.AnimationBrushes.gp[0]
#     context.scene.grease_pencil = gp
#
#     if 'FOLLOWPATH' not in brushes.AnimationBrushes.brush_dict:
#         layer = gp.layers.new('FOLLOWPATH')
#         layer.tint_color = (1.0, 0.0, 0.0)
#         layer.tint_factor = 1.0
#         brushes.AnimationBrushes.brush_dict['FOLLOWPATH'] = layer
#     if 'HPOINT' not in brushes.AnimationBrushes.brush_dict:
#         layer = gp.layers.new('HPOINT')
#         layer.tint_color = (0.5, 0.5, 0.5)
#         layer.tint_factor = 1.0
#         brushes.AnimationBrushes.brush_dict['HPOINT'] = layer
#     if 'ARAP' not in brushes.AnimationBrushes.brush_dict:
#         layer = gp.layers.new('ARAP')
#         layer.tint_color = (0.5, 1.0, 0.0)
#         layer.tint_factor = 1.0
#         brushes.AnimationBrushes.brush_dict['ARAP'] = layer
#
#     if context.scene.enum_brushes!=None:
#         gp.layers.active = brushes.AnimationBrushes.brush_dict[context.scene.enum_brushes]
#
#     return None
