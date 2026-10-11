"""Save and restore actual render-camera framing, independent of viewport size."""
FIELDS=('lens','ortho_scale','shift_x','shift_y','sensor_width','sensor_height','sensor_fit','clip_start','clip_end')

def snapshot(camera):
    return {'matrix_world':[list(row) for row in camera.matrix_world],**{k:getattr(camera.data,k) for k in FIELDS}}

def restore(camera,pose):
    from mathutils import Matrix
    camera.matrix_world=Matrix(pose['matrix_world'])
    for key in FIELDS:
        if key in pose:setattr(camera.data,key,pose[key])
