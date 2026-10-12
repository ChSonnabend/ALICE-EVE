#!/usr/bin/env python3
"""Compile the isolated helper against installed O2 headers/libraries."""
import concurrent.futures,hashlib,os,re,shlex,subprocess,sys
from pathlib import Path

source,output=map(Path,sys.argv[1:3]);root=Path(os.environ['O2_ROOT'])
includes={str(root/'include'),str(root/'include/GPU'),str(source/'include')}
for item in re.split(r'[:;]',os.environ.get('ROOT_INCLUDE_PATH','')):
    if item and Path(item).is_dir():includes.add(item)
for key,value in os.environ.items():
    if key.endswith('_ROOT') and (Path(value)/'include').is_dir():includes.add(str(Path(value)/'include'))
flags=shlex.split(subprocess.check_output(['root-config','--cflags'],text=True))
flags+=['-std=c++20','-O2','-DFMT_SHARED','-DBOOST_ERROR_CODE_HEADER_ONLY']
flags+=['-DBOOST_ASIO_HAS_HAS_STD_CHRONO','-DFAIRMQ_HAS_STD_FILESYSTEM=1','-DFAIRMQ_HAS_STD_PMR=1','-DDPL_ENABLE_BACKTRACE']
flags+=['-I'+item for item in sorted(includes)]
objects=[];build=source/'build';build.mkdir(exist_ok=True)
header_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((source/'include').rglob('*.h')))).digest()
def compile_one(name):
    obj=build/(name+'.o');cpp=source/'src'/f'{name}.cxx';stamp=build/(name+'.sha256')
    signature=hashlib.sha256(cpp.read_bytes()+header_hash+repr(flags).encode()).hexdigest()
    if obj.exists() and stamp.exists() and stamp.read_text()==signature:return str(obj)
    result=subprocess.run(['c++',*flags,'-c',str(cpp),'-o',str(obj)])
    if result.returncode:raise RuntimeError('Compile failed: '+name)
    stamp.write_text(signature)
    return str(obj)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    objects=list(executor.map(compile_one,['O2DPLDisplay','DetectorData','FileProducer','EveWorkflowHelper','EveConfiguration']))
libraries=['DataFormatsGlobalTracking','DetectorsRaw','DetectorsVertexing','EventVisualisationBase','EventVisualisationDetectors','EventVisualisationDataConverter','Framework','FrameworkFoundation','FT0Workflow','GlobalTrackingWorkflowHelpers','GlobalTrackingWorkflowReaders','ITSMFTWorkflow','MFTWorkflow','TOFBase','PHOSBase','EMCALBase','EMCALCalib','EMCALWorkflow','MIDBase','TOFWorkflowIO','TPCReconstruction','TPCWorkflow','TRDBase','TRDWorkflowIO','SpacePoints','ReconstructionDataFormats','DetectorsBase','TPCCalibration','GPUTracking','GPUO2Interface']
libraries+=['DataFormatsMCH','DataFormatsMID','DataFormatsTPC','MCHTracking','ITSBase','MFTBase','ITStracking','MFTTracking','HMPIDBase']
libraries+=['GPUDataTypes','DetectorsCommonDataFormats']
command=['c++',*objects,'-o',str(output),'-L'+str(root/'lib'),'-Wl,-rpath,'+str(root/'lib')]
command+=['-L'+item for item in os.environ.get('LD_LIBRARY_PATH','').split(':') if item]
command+=['-lO2'+name for name in libraries]
command+=[str(path) for path in sorted((root/'lib').glob('libO2DataFormats*.so'))]
command+=shlex.split(subprocess.check_output(['root-config','--libs'],text=True))
command+=['-lFairLogger','-lfairmq','-lboost_program_options','-lfmt','-lGeom']
added=[]
for attempt in range(12):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode==0:break
    match=re.search(r': (/[^:\n]+): error adding symbols: DSO missing from command line',result.stderr)
    dependency=Path(match[1]) if match else None
    if not dependency or dependency.parent.resolve()!=(root/'lib').resolve() or str(dependency) in command:
        print(result.stderr,file=sys.stderr);raise SystemExit(result.returncode)
    command.append(str(dependency));added.append(str(dependency))
else:
    print(result.stderr,file=sys.stderr);raise SystemExit(result.returncode)
(build/'link-dependencies.json').write_text(__import__('json').dumps(added,indent=2))
print(output)
