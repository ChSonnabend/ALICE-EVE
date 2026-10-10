#!/usr/bin/env python3
"""Losslessly compress completed native products without altering originals."""
import argparse,gzip,shutil,subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    for name in ('events.jsonl','timeframe-objects.jsonl'):
        source=a.directory/name;target=a.directory/(name+'.gz');temporary=target.with_suffix('.gz.part')
        with temporary.open('wb') as output:
            if shutil.which('pigz'):
                subprocess.run(['pigz','-p','8','-1','-c',str(source)],stdout=output,check=True)
            else:
                with source.open('rb') as input_,gzip.GzipFile(fileobj=output,mode='wb',compresslevel=1) as compressed:
                    shutil.copyfileobj(input_,compressed,8<<20)
        temporary.replace(target)
        print(name,source.stat().st_size,'->',target.stat().st_size,flush=True)

if __name__=='__main__':main()
