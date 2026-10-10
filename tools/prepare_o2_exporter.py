#!/usr/bin/env python3
"""Patch an isolated copy of O2's GPL display helper into a complete exporter.

The reference checkout is never edited. All patch anchors are checked.
"""
import argparse,re,shutil
from pathlib import Path

TOKEN=re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]',re.S)

def body(source,name):
    start=source.index(name);opening=source.index('{',start);depth=0
    for token in TOKEN.finditer(source,opening):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return opening+1,token.start()
    raise ValueError('Unclosed function: '+name)

def function(source,name,transform):
    a,b=body(source,name);return source[:a]+transform(source[a:b])+source[b:]

def replace(source,old,new,count=1):
    if source.count(old)!=count:raise ValueError('Patch anchor mismatch: '+old[:90])
    return source.replace(old,new)

def prepare(reference,destination,templates):
    reference,destination,templates=map(Path,(reference,destination,templates))
    if not (reference/'EventVisualisation/Workflow').is_dir() or not (reference/'COPYING').is_file():
        raise ValueError('Expected the O2 reference root containing EventVisualisation/Workflow and COPYING')
    if destination.exists():shutil.rmtree(destination)
    shutil.copytree(reference/'EventVisualisation/Workflow',destination)
    shutil.copy2(reference/'COPYING',destination/'COPYING')
    header=destination/'include/EveWorkflow/EveWorkflowHelper.h';text=header.read_text()
    text=replace(text,'#include "Framework/AnalysisDataModel.h"','')
    text,n=re.subn(r'  using AODBarrelTracks.*?(  using Bracket)',r'\1',text,flags=re.S)
    if n!=1:raise ValueError('AOD type block anchor mismatch')
    text,n=re.subn(r'  void drawAOD[^\n]*\n','',text)
    if n!=3:raise ValueError('AOD method declarations anchor mismatch')
    extra='''
  struct ExportCluster {std::array<float,3> xyz;std::string detector;int track;};
  std::vector<ExportCluster> mExportClusters;
  std::vector<GID> mExportTrackGIDs;
  GID mExportCurrentGID;
  std::unordered_map<GID,GID> mExportInputGIDs;
  std::vector<std::array<float,5>> mExportKinematics;
  std::vector<std::optional<o2::track::TrackPar>> mExportBarrelFits;
  std::unordered_map<GID,float> mExactTrackTime;
  const o2::gpu::TPCFastTransformPOD* mExportTPCMap=nullptr;
  void recordPoint(const float xyz[],const char* detector,bool associated=true) {
    for(int i=0;i<3;++i)if(!std::isfinite(xyz[i]))throw std::runtime_error("Non-finite calibrated cluster");
    mExportClusters.push_back({{xyz[0],xyz[1],xyz[2]},detector,associated?int(mEvent.getTrackCount())-1:-1});
    if(associated)mEvent.addCluster(xyz);
  }
'''
    text=replace(text,'#include "TPCFastTransform.h"','#include "TPCFastTransform.h"\n#include "TPCFastTransformPOD.h"\n#include <optional>\n#include <limits>\n#include <stdexcept>')
    text=replace(text,'  void clear() { mEvent.clear(); }','  void clear() { mEvent.clear();mExportClusters.clear();mExportTrackGIDs.clear();mExportKinematics.clear();mExportBarrelFits.clear(); }\n'+extra)
    header.write_text(text)
    source=destination/'src/EveWorkflowHelper.cxx';text=source.read_text()
    for name,signature in [('drawAODBarrel','void'),('drawAODMFT','void'),('drawAODFwd','void'),('detectorMapToGIDSource','GID::Source')]:
        declaration=signature+' EveWorkflowHelper::'+name+'('
        start=text.index(declaration);a,b=body(text,declaration)
        text=text[:start]+text[b+1:]
    text=replace(text,'mGIDTrackTime[gid] = flagTime(bracket.mean(), src);','mGIDTrackTime[gid] = flagTime(bracket.mean(), src);\n    mExactTrackTime[gid]=bracket.mean();')
    text=replace(text,'auto tim = unflagTime(mGIDTrackTime.at(gid));','auto tim = mExactTrackTime.at(gid);')
    text=replace(text,'getTPCTOFMatch(gid.getIndex())','getTPCTOFMatch(gid)')
    text=replace(text,'      mTotalAcceptedDataTypes.insert(gid);','      mTotalAcceptedDataTypes.insert(gid);\n      mExportCurrentGID=gid;',count=2)
    text=replace(text,'        GID gid(tvid);\n        fixMFTMCHMIDLabel(gid);','        GID gid(tvid);\n        fixMFTMCHMIDLabel(gid);\n        mExportInputGIDs[gid]=GID(tvid);')
    # The reference assigns every HMP trigger to every PV. HMP triggers are
    # not matched by VertexTrackMatcher; preserve them at TF level instead.
    text=replace(text,'''      for (std::size_t i = 0; i < allTriggersHMP.size(); i++) {
        mTotalDataTypes[GID::HMP]++;
        const auto& trig = allTriggersHMP[i];
        mPrimaryVertexTriggerGIDs[iv].emplace_back(GID{static_cast<unsigned int>(i), GID::HMP});
      }''','')
    text,n=re.subn(r'      if \(pv\.getX\(\) < conf\.PVXYZMin\[0\].*?continue; // skip vertex\n      }','',text,flags=re.S)
    if n!=1:raise ValueError('PV selection filter anchor mismatch')
    text=replace(text,'    if (conf.maxTracks > 0 && trackCount >= conf.maxTracks) {\n      trackCount = conf.maxTracks;\n    }','')
    # This iterator normally consumes component tracks after visiting a match.
    # PV references can explicitly contain those components as well. Retain
    # their original fit/time rather than silently dropping the references.
    text=replace(text,'    return true;\n  };\n\n  auto prop = o2::base::Propagator::Instance();',
                 '    return false;\n  };\n\n  auto prop = o2::base::Propagator::Instance();')
    # MCH-MID is stored in MATCHES, not TRACKS in RecoContainer.
    text=replace(text,'!mRecoCont->isTrackSourceLoaded(tvid.getSource())',
                 '!(tvid.getSource()==GID::MCHMID ? mRecoCont->isMatchSourceLoaded(GID::MCHMID) : mRecoCont->isTrackSourceLoaded(tvid.getSource()))')
    # The reference declares an inner dz and silently leaves the rendered TPC
    # track unshifted. Update the outer value used by drawTPC instead.
    a,b=body(text,'void EveWorkflowHelper::draw(');section=text[a:b]
    section=replace(section,'float dz = (tpcTr.getTime0()', 'dz = (tpcTr.getTime0()')
    text=text[:a]+section+text[b:]
    for name in ('drawTOFClusters','drawITSClusters','drawMFTClusters','drawMCHClusters','drawTRDClusters','drawMIDClusters'):
        detector={'drawTOFClusters':'TOF','drawITSClusters':'ITS','drawMFTClusters':'MFT','drawMCHClusters':'MCH','drawTRDClusters':'TRD','drawMIDClusters':'MID'}[name]
        text=function(text,'void EveWorkflowHelper::'+name+'(',lambda s,d=detector:re.sub(r'drawPoint\(([^;]*?)\);',lambda m:f'recordPoint({m[1]},"{d}");',s))
    def tpc(section):
        section=replace(section,'this->mTPCFastTransform->TransformIdeal(','this->mExportTPCMap->Transform(')
        section=replace(section,'mEvent.addCluster(\n      xyz.data());','recordPoint(xyz.data(),"TPC");')
        return '\n  if(!mExportTPCMap)throw std::runtime_error("Calibrated per-TF TPC map is missing");'+section
    text=function(text,'void EveWorkflowHelper::drawTPCClusters(',tpc)
    text=function(text,'void EveWorkflowHelper::drawHMP(',lambda s:replace(s,'drawGlobalPoint(vec3, gid, time);','float xyz[]={float(vec3.X()),float(vec3.Y()),float(vec3.Z())};recordPoint(xyz,"HMP",false);'))
    text=function(text,'void EveWorkflowHelper::drawPHS(',lambda s:replace(s,'auto vCalo = mEvent.addCalo(','float xyz[]={float(gPos.X()),float(gPos.Y()),float(gPos.Z())};recordPoint(xyz,"PHS",false);\n    auto vCalo = mEvent.addCalo('))
    text=function(text,'void EveWorkflowHelper::drawEMC(',lambda s:replace(s,'auto vCalo = mEvent.addCalo(','float xyz[]={float(gPos[0]),float(gPos[1]),float(gPos[2])};recordPoint(xyz,"EMC",false);\n    auto vCalo = mEvent.addCalo('))
    text,n=re.subn(r'    if \(std::abs\(cellTime\) > conf.EMCCellTimeMax\) {.*?    }\n    if \(cellEnergy < conf.EMCCellEnergyMin\) {.*?    }','',text,flags=re.S)
    if n!=1:raise ValueError('EMCAL display cut anchor mismatch')
    instrument={
      'addTrackToEvent':'mExportKinematics.push_back({tr.getEta(),tr.getTgl(),tr.getPhi(),tr.getP(),tr.getPt()});mExportBarrelFits.emplace_back(tr);mExportBarrelFits.back()->setZ(tr.getZ()+dz);',
      'drawMFTTrack':'mExportKinematics.push_back({float(tr.getEta()),float(std::sinh(tr.getEta())),float(tr.getPhi()),float(tr.getP()),float(tr.getPt())});mExportBarrelFits.emplace_back(std::nullopt);',
      'drawForwardTrack':'const float pt=std::hypot(track.px(),track.py());mExportKinematics.push_back({float(std::asinh(track.pz()/pt)),float(track.pz()/pt),float(std::atan2(track.py(),track.px())),float(track.p()),pt});mExportBarrelFits.emplace_back(std::nullopt);',
      'drawMID':'const float nan=std::numeric_limits<float>::quiet_NaN();mExportKinematics.push_back({nan,nan,nan,nan,nan});mExportBarrelFits.emplace_back(std::nullopt);'}
    for name,code in instrument.items():
        text=function(text,'void EveWorkflowHelper::'+name+'(',lambda s,c=code:replace(s,'.gid = gid});','.gid = gid});\n  mExportTrackGIDs.push_back(mExportCurrentGID);'+c))
    source.write_text(text)
    header=destination/'include/EveWorkflow/O2DPLDisplay.h';text=header.read_text()
    text=replace(text,'#include <memory>','#include <memory>\n#include <fstream>\n#include <set>\n#include <tuple>')
    text=replace(text,'  bool mDisableWrite = false;','  std::ofstream mExportOutput;\n  uint64_t mExportVertices=0;\n  std::set<std::tuple<unsigned,unsigned,unsigned>> mExportTFs;\n  bool mDisableWrite = false;')
    text=text.replace('ITS,TPC,MFT,MCH,MID,ITS-TPC,TPC-TRD,','ITS,TPC,MFT,MCH,MID,ITS-TPC,TPC-TOF,TPC-TRD,TPC-TRD-TOF,')
    text=replace(text,'"ITS,TPC,TRD,TOF,MFT,MCH,MID,PHS,EMC,HMP"','"ITS,TPC,TRD,TOF,MFT,MCH,MID,PHS,EMC,HMP,CPV,FT0,FV0,FDD,ZDC"')
    header.write_text(text)
    source=destination/'src/O2DPLDisplay.cxx';text=source.read_text()
    text=replace(text,'#include <unistd.h>','#include <unistd.h>\n#include <filesystem>\n#include <TFile.h>\n#include <TGeoManager.h>\n#include "canonical_export.h"\n#include "timeframe_export.h"\n#include "ReconstructionDataFormats/VtxTrackRef.h"')
    text=function(text,'void O2DPLDisplaySpec::init(',lambda s:s+'''
  std::filesystem::create_directories(mJsonPath);
  auto path=std::filesystem::path(mJsonPath)/"events.jsonl";
  if(std::filesystem::exists(path))throw std::runtime_error("Export already exists: "+path.string());
  mExportOutput.open(path);if(!mExportOutput)throw std::runtime_error("Export output is not writable");
''')
    text=function(text,'void O2DPLDisplaySpec::run(',lambda s:(templates/'export_run.inc').read_text())
    text=function(text,'void O2DPLDisplaySpec::endOfStream(',lambda s:'''
  mExportOutput.close();if(!mExportOutput)throw std::runtime_error("Export close failed");
  std::ofstream marker(std::filesystem::path(mJsonPath)/"events.jsonl.complete.json");
  marker<<"{\\"schema_version\\":1,\\"timeframes\\":"<<mExportTFs.size()<<",\\"vertices\\":"<<mExportVertices<<"}\\n";
  if(!marker)throw std::runtime_error("Export completion write failed");
''')
    text=replace(text,'const auto& conf = EveConfParam::Instance();','o2::conf::ConfigurableParam::updateFromString("eveconf.PVMode=true;eveconf.maxTracks=-1;eveconf.filterITSROF=false;eveconf.TPCEtaAbsMax=-1;eveconf.timeMinMax[0]=-999;eveconf.timeMinMax[1]=-999;eveconf.TPCOnlyMaxDCARZ[0]=-999;eveconf.TPCOnlyMaxDCARZ[1]=-999;eveconf.calibrateEMC=false");\n  const auto& conf = EveConfParam::Instance();')
    text=replace(text,'o2::tpc::VDriftHelper::requestCCDBInputs(dataRequest->inputs);','o2::tpc::VDriftHelper::requestCCDBInputs(dataRequest->inputs);\n  if(srcCl[GID::TPC])dataRequest->inputs.emplace_back("aliceTPCMap","TPC","TPCCORRMAP",0,Lifetime::Timeframe);')
    text=replace(text,'  dataRequest->requestClusters(srcCl, useMC);','''  dataRequest->requestClusters(srcCl, useMC);
  if(srcCl[GID::FT0])dataRequest->requestFT0RecPoints(false);
  if(srcCl[GID::FV0])dataRequest->requestFV0RecPoints(false);
  if(srcCl[GID::FDD])dataRequest->requestFDDRecPoints(false);
  if(srcCl[GID::ZDC])dataRequest->requestZDCRecEvents(false);
  if(srcCl[GID::MID])dataRequest->requestMIDClusters(false);
''')
    text=replace(text,'"o2-eve-export",','"alice-complete-export",')
    source.write_text(text)
    shutil.copy2(templates/'canonical_export.h',destination/'include/canonical_export.h')
    shutil.copy2(templates/'timeframe_export.h',destination/'include/timeframe_export.h')
    print(destination)

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--output',required=True);p.add_argument('--templates',required=True);a=p.parse_args();prepare(a.reference,a.output,a.templates)

if __name__=='__main__':main()
