#!/usr/bin/env python3
"""Build the inspector against the activated O2 installation."""
import os,subprocess,sys,shutil,re
from pathlib import Path
source=Path(sys.argv[1]);output=Path(sys.argv[2]);root=Path(os.environ['O2_ROOT'])
output.parent.mkdir(parents=True,exist_ok=True)
if shutil.which('cmake') and (root/'lib/cmake/O2/O2Config.cmake').exists():
    build=output.parent/'build-tf-inspector'
    subprocess.run(['cmake','-S',str(source.parent),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DO2_DIR='+str(root/'lib/cmake/O2')],check=True)
    subprocess.run(['cmake','--build',str(build),'--target','alice-tf-inspect','--parallel','4'],check=True)
    shutil.copy2(build/'alice-tf-inspect',output)
else:
    # Runtime-only O2PDPSuite environments need not load CMake. ROOT's published
    # include path carries header dependencies such as Boost and fmt.
    include={str(root/'include')}
    for entry in re.split(r'[:;]',os.environ.get('ROOT_INCLUDE_PATH','')):
        if entry and Path(entry).is_dir():include.add(entry)
    for key,value in os.environ.items():
        if key.endswith('_ROOT') and (Path(value)/'include').is_dir():include.add(str(Path(value)/'include'))
    command=['c++','-std=c++20','-O2',str(source),'-o',str(output)]
    command += ['-I'+entry for entry in sorted(include)]
    command += ['-L'+str(root/'lib'),'-Wl,-rpath,'+str(root/'lib'),'-lO2TFReaderDD','-lO2Headers','-lO2Framework']
    subprocess.run(command,check=True)
print(output)
