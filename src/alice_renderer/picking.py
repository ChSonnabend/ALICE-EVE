"""Screen-space picking of displayed polylines, independent of Blender UI state."""
import numpy as np

def inside_viewport(area,region,x,y):
    if not region.x<=x<region.x+region.width or not region.y<=y<region.y+region.height:return False
    space=area.spaces.active
    for overlay in area.regions:
        if overlay.type=='WINDOW':continue
        if overlay.type=='UI' and not getattr(space,'show_region_ui',True):continue
        if overlay.type=='TOOLS' and not getattr(space,'show_region_toolbar',True):continue
        if overlay.width>0 and overlay.height>0 and overlay.x<=x<overlay.x+overlay.width and overlay.y<=y<overlay.y+overlay.height:return False
    return True


def projected_hit(mouse,points,matrix,width,height,tolerance=10.):
    points=np.asarray(points,dtype=float)
    if len(points)<2:return None
    if points.shape[1]==3:points=np.column_stack((points,np.ones(len(points))))
    clip=points@np.asarray(matrix,dtype=float).T
    valid=clip[:,3]>1.e-10
    ndc=np.zeros((len(points),3));np.divide(clip[:,:3],clip[:,3,None],out=ndc,where=valid[:,None])
    screen=(ndc[:,:2]+1)*np.array([width,height])/2
    a=screen[:-1];delta=screen[1:]-a;den=np.sum(delta*delta,axis=1)
    t=np.zeros(len(a));np.divide(np.sum((np.asarray(mouse)-a)*delta,axis=1),den,out=t,where=den>1.e-12);t=np.clip(t,0,1)
    distances=np.linalg.norm(a+t[:,None]*delta-np.asarray(mouse),axis=1)
    depth=ndc[:-1,2]+t*(ndc[1:,2]-ndc[:-1,2])
    allowed=valid[:-1]&valid[1:]&(depth>=-1)&(depth<=1)&(distances<=tolerance)
    indices=np.flatnonzero(allowed)
    if not len(indices):return None
    i=min(indices,key=lambda i:(round(float(distances[i]),6),float(depth[i])))
    return float(distances[i]),float(depth[i])
