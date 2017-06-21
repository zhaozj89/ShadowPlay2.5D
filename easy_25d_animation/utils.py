def get_boundingbox_of_verts(verts):
    import sys
    bbx_min = sys.maxsize
    bbx_max = -sys.maxsize
    bbz_min = sys.maxsize
    bbz_max = -sys.maxsize
    for i in range(len(verts)):
        if verts[i].x < bbx_min:
            bbx_min = verts[i].x
        if verts[i].x > bbx_max:
            bbx_max = verts[i].x
        if verts[i].z < bbz_min:
            bbz_min = verts[i].z
        if verts[i].z > bbz_max:
            bbz_max = verts[i].z

    return (bbx_min, bbx_max, bbz_min, bbz_max)
