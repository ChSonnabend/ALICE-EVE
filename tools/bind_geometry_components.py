"""Blender entry point: verify component indices against assets without changing assets.

blender -b --python-exit-code 1 --python tools/bind_geometry_components.py --
  --indices hierarchy-folder --assets aligned-bundle
"""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy
from components import verify_group
from alice_renderer.geometry_components import sidecar_path

def main():
    p=argparse.ArgumentParser();p.add_argument('--indices',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    for source in sorted(a.indices.glob('*.component-index.json.gz')):
        metadata=json.load(gzip.open(source,'rt'));asset=a.assets/(metadata['detector']+'.blend')
        with bpy.data.libraries.load(str(asset),link=False) as (library,target):target.objects=library.objects
        objects=[o for o in target.objects if o];matched=set()
        for obj in objects:
            if 'num_instances' not in obj:continue
            if obj.name not in metadata['groups']:raise ValueError('Unexpected instancer: '+obj.name)
            verify_group(obj,metadata['groups'][obj.name]);matched.add(obj.name)
        if matched!=set(metadata['groups']):raise ValueError('Missing aligned instance groups: '+asset.name)
        metadata['asset_sha256']=hashlib.sha256(asset.read_bytes()).hexdigest()
        target=sidecar_path(asset)
        with gzip.open(target,'wt') as out:json.dump(metadata,out,separators=(',',':'))
        print(asset.name+': verified '+str(sum(len(g['ids']) for g in metadata['groups'].values()))+' placements, '+str(len(metadata['components']))+' components',flush=True)
        for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.orphans_purge(do_recursive=True)
if __name__=='__main__':main()
