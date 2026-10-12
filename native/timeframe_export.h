// Preserve detector objects without inventing a primary-vertex association.
#pragma once
#include <rapidjson/filewritestream.h>
#include <limits>
#include "DataFormatsFT0/RecPoints.h"
#include "DataFormatsFV0/RecPoints.h"
#include "DataFormatsFDD/RecPoint.h"
#include "DataFormatsCPV/Cluster.h"
#include "HMPIDBase/Param.h"
#include "DataFormatsHMP/Cluster.h"
#include "DataFormatsTRD/Tracklet64.h"
#include "DataFormatsTRD/CalibratedTracklet.h"
#include "DataFormatsTOF/Cluster.h"
#include "DataFormatsMID/Cluster.h"
#include "MIDBase/GeometryTransformer.h"
#include "DataFormatsZDC/ZDCEnergy.h"
#include "ReconstructionDataFormats/VtxTrackRef.h"
#include "ReconstructionDataFormats/VtxTrackIndex.h"
namespace alice_export {
inline uint64_t writeTimeframe(const std::filesystem::path& path,o2::event_visualisation::EveWorkflowHelper& helper,
                           const o2::globaltracking::RecoContainer& reco,const o2::framework::TimingInfo& timing,
                           o2::dataformats::GlobalTrackID::mask_t mask,bool first) {
  FILE* file=std::fopen(path.c_str(),first?"wb":"ab");if(!file)throw std::runtime_error("Cannot open timeframe sidecar");
  char bytes[65536];rapidjson::FileWriteStream stream(file,bytes,sizeof(bytes));
  rapidjson::Writer<rapidjson::FileWriteStream> w(stream);
  w.StartObject();w.Key("schema_version");w.Int(1);w.Key("kind");w.String("timeframe_objects");
  w.Key("units");w.String("cm");w.Key("run");w.Uint(timing.runNumber);
  w.Key("timeframe");w.Uint(timing.tfCounter);w.Key("orbit");w.Uint(timing.firstTForbit);
  w.Key("association_basis");w.String("All TF objects, independently of track/PV associations. Unassigned objects are not copied into every collision.");
  w.Key("unassigned_reference_ids");w.StartArray();
  auto refs=reco.getPrimaryVertexMatchedTrackRefs();auto ids=reco.getPrimaryVertexMatchedTracks();
  if(refs.empty())throw std::runtime_error("Missing unassigned reference sentinel");
  auto last=refs.back();for(int j=0;j<last.getEntries();++j)w.Uint(ids[last.getFirstEntry()+j].getRaw());w.EndArray();
  w.Key("spatial_objects");w.StartArray();
  uint64_t invalidSpatial=0;
  auto add=[&](const char* detector,size_t index,float x,float y,float z,const char* basis,
              double energy=std::numeric_limits<double>::quiet_NaN(),double time=std::numeric_limits<double>::quiet_NaN()){
    bool valid=std::isfinite(x)&&std::isfinite(y)&&std::isfinite(z);if(!valid)++invalidSpatial;
    w.StartObject();w.Key("detector");w.String(detector);w.Key("index");w.Uint64(index);
    w.Key("position");w.StartArray();for(double value:{double(x),double(y),double(z)}){if(std::isfinite(value))w.Double(value);else w.Null();}w.EndArray();
    w.Key("coordinate_status");w.String(valid?"valid":"nonfinite_conversion_not_renderable");
    w.Key("coordinate_basis");w.String(basis);
    if(std::isfinite(energy)){w.Key("measurement_kind");w.String("calorimeter_cell");w.Key("energy");w.Double(energy);}
    if(std::isfinite(time)){w.Key("trigger_time_us");w.Double(time);}
    w.EndObject();};
  size_t index=0;
  if(mask[GID::ITS])for(const auto& c:helper.mITSClustersArray.getClusters()){
    auto p=helper.mITSGeom->getMatrixT2G(c.getSensorID())*c.getXYZ();add("ITS",index++,p.X(),p.Y(),p.Z(),"O2 compact-cluster topology dictionary and aligned T2G");}
  index=0;if(mask[GID::MFT])for(const auto& c:helper.mMFTClustersArray)add("MFT",index++,c.getX(),c.getY(),c.getZ(),"O2 MFT compact-cluster converter and aligned geometry");
  index=0;if(mask[GID::MCH])for(const auto& c:reco.getMCHClusters())add("MCH",index++,c.x,c.y,c.z,"O2 globally transformed reconstructed MCH clusters");
  if(mask[GID::MID]){auto transformer=o2::mid::createTransformationFromManager(gGeoManager);index=0;
    for(const auto& c:reco.getMIDClusters()){auto p=transformer.localToGlobal(c.deId,c.xCoor,c.yCoor);
      add("MID",index++,p.X(),p.Y(),p.Z(),"O2 MID local reconstructed cluster; aligned geometry transformer");}}
  index=0;if(mask[GID::TOF])for(const auto& c:reco.getTOFClusters()){
    float alpha=o2::math_utils::sector2Angle(c.getSector());add("TOF",index++,c.getX()*std::cos(alpha)-c.getY()*std::sin(alpha),c.getY()*std::cos(alpha)+c.getX()*std::sin(alpha),c.getZ(),"O2 reconstructed TOF cluster; sector to global rotation");}
  if(mask[GID::TRD]){
    auto raw=reco.getTRDTracklets();auto calibrated=reco.getTRDCalibratedTracklets();
    if(raw.size()!=calibrated.size())throw std::runtime_error("TRD calibrated/raw tracklet counts differ");
    for(size_t i=0;i<raw.size();++i){auto& c=calibrated[i];float alpha=o2::math_utils::sector2Angle(raw[i].getDetector()/30);
      add("TRD",i,c.getX()*std::cos(alpha)-c.getY()*std::sin(alpha),c.getY()*std::cos(alpha)+c.getX()*std::sin(alpha),c.getZ(),"O2 calibrated TRD tracklet; sector to global rotation");}}
  if(mask[GID::HMP]){index=0;for(auto c:reco.getHMPClusters()){
    auto p=o2::hmpid::Param::instance()->lors2Mars(c.ch(),c.x(),c.y());add("HMP",index++,p.X(),p.Y(),p.Z(),"O2 HMP reconstructed cluster local to ALICE global");}}
  if(mask[GID::CPV]){index=0;for(const auto& c:reco.getCPVClusters()){
    std::string node="/cave_1/barrel_1/CPV_"+std::to_string(int(c.getModule()));
    if(!gGeoManager->cd(node.c_str()))throw std::runtime_error("Aligned CPV module path is missing");
    float x,z;c.getLocalPosition(x,z);double local[]={x,0.,z},global[3];gGeoManager->GetCurrentMatrix()->LocalToMaster(local,global);
    add("CPV",index++,global[0],global[1],global[2],"O2 CPV local (x,0,z) module-plane convention; complete aligned module transformation");}}
  if(mask[GID::PHS])for(size_t i=0;i<reco.getPHOSTriggers().size();++i)helper.drawPHS(GID(i,GID::PHS));
  if(mask[GID::EMC])for(size_t i=0;i<reco.getEMCALTriggers().size();++i)helper.drawEMC(GID(i,GID::EMC));
  index=0;for(const auto& c:helper.mExportClusters){const auto& cell=helper.mEvent.getCalorimetersSpan()[index];
    add(c.detector.c_str(),index++,c.xyz[0],c.xyz[1],c.xyz[2],"Calorimeter cell, not a fitted track cluster; O2 cell converter and aligned geometry",cell.getEnergy(),cell.getTime());}
  helper.clear();
  w.EndArray();
  // An unassociated TPC cluster has no measured collision t0. Preserve native
  // pad/time/charge rather than creating an apparently calibrated global Z.
  w.Key("tpc_native_clusters");w.StartArray();
  if(mask[GID::TPC]){auto& clusters=reco.getTPCClusters();
    for(int sector=0;sector<36;++sector)for(int row=0;row<o2::tpc::constants::MAXGLOBALPADROW;++row)
      for(unsigned i=0;i<clusters.nClusters[sector][row];++i){const auto& c=clusters.clusters[sector][row][i];
        w.StartObject();w.Key("sector");w.Int(sector);w.Key("row");w.Int(row);w.Key("index");w.Uint(i);
        w.Key("pad");w.Double(c.getPad());w.Key("time_bins");w.Double(c.getTime());
        w.Key("sigma_pad");w.Double(c.getSigmaPad());w.Key("sigma_time_bins");w.Double(c.getSigmaTime());
        w.Key("q_max");w.Double(c.getQmax());w.Key("q_tot");w.Double(c.getQtot());w.EndObject();}}
  w.EndArray();w.Key("tpc_coordinate_basis");w.String("Native measurements retained for every cluster. Calibrated global coordinates require a track/PV t0 and are exported in the corresponding collision associations.");
  w.Key("timing_channels");w.StartArray();
  auto channel=[&](const char* det,int id,double time,double amplitude){w.StartObject();w.Key("detector");w.String(det);w.Key("channel");w.Int(id);w.Key("time_ps");if(std::isfinite(time))w.Double(time);else w.Null();w.Key("amplitude");if(std::isfinite(amplitude))w.Double(amplitude);else w.Null();w.EndObject();};
  if(mask[GID::FT0])for(auto& c:reco.getFT0ChannelsData())channel("FT0",c.ChId,c.CFDTime,c.QTCAmpl);
  if(mask[GID::FV0])for(auto& c:reco.getFV0ChannelsData())channel("FV0",c.channel,c.time*1000.,c.charge);
  if(mask[GID::FDD])for(auto& c:reco.getFDDChannelsData())channel("FDD",c.mPMNumber,c.mTime,c.mChargeADC);
  w.EndArray();w.Key("zdc_energies");w.StartArray();
  if(mask[GID::ZDC])for(auto& e:reco.getZDCEnergy()){w.StartObject();w.Key("channel");w.Uint(e.ch());w.Key("energy");if(std::isfinite(e.energy()))w.Double(e.energy());else w.Null();w.EndObject();}
  w.EndArray();w.Key("invalid_spatial_objects");w.Uint64(invalidSpatial);w.EndObject();stream.Put('\n');stream.Flush();
  bool error=std::ferror(file);if(std::fclose(file)!=0||error)throw std::runtime_error("Timeframe sidecar write failed");
  return invalidSpatial;
}
}
