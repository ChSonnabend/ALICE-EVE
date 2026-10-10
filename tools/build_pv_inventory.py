#!/usr/bin/env python3
"""Build the independent O2 primary-vertex counter in an activated environment."""
import os,re,shlex,subprocess,sys
from pathlib import Path

source,output=map(Path,sys.argv[1:3]);root=Path(os.environ['O2_ROOT'])
includes={str(root/'include')}
for entry in re.split(r'[:;]',os.environ.get('ROOT_INCLUDE_PATH','')):
    if entry and Path(entry).is_dir():includes.add(entry)
for key,value in os.environ.items():
    if key.endswith('_ROOT') and (Path(value)/'include').is_dir():includes.add(str(Path(value)/'include'))
root_cflags=shlex.split(subprocess.check_output(['root-config','--cflags'],text=True))
root_libs=shlex.split(subprocess.check_output(['root-config','--libs'],text=True))
output.parent.mkdir(parents=True,exist_ok=True)
command=['c++',*root_cflags,'-std=c++20','-O2',str(source),'-o',str(output)]
command+=['-DFMT_SHARED','-DBOOST_ERROR_CODE_HEADER_ONLY','-DBOOST_ASIO_HAS_HAS_STD_CHRONO','-DFAIRMQ_HAS_STD_FILESYSTEM=1','-DFAIRMQ_HAS_STD_PMR=1','-DDPL_ENABLE_BACKTRACE']
if '--fixture' in sys.argv[3:]:command+=['-DALICE_STANDALONE_FIXTURE']
command+=['-I'+p for p in sorted(includes)]
command+=['-L'+str(root/'lib'),'-Wl,-rpath,'+str(root/'lib')]
command+=['-L'+p for p in os.environ.get('LD_LIBRARY_PATH','').split(':') if p]
command+=['-lO2'+p for p in ('GlobalTrackingWorkflowHelpers','GlobalTrackingWorkflowReaders','DataFormatsGlobalTracking',
          'DetectorsRaw','Framework','FrameworkFoundation','CommonUtils','ReconstructionDataFormats')]
command+=root_libs
command+=['-lFairLogger','-lfairmq','-lboost_program_options','-lfmt']
result=subprocess.run(command)
if result.returncode:raise SystemExit(result.returncode)
print(output)
