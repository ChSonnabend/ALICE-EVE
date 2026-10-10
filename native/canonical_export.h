// Canonical event writer for the locally compiled O2 display helper.
// ALICE global centimetres; fitted kinematics; calibrated associated clusters.
#pragma once
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <cmath>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <string>
#include "ReconstructionDataFormats/PrimaryVertex.h"

namespace alice_export {
using GID=o2::dataformats::GlobalTrackID;
using Writer=rapidjson::Writer<rapidjson::StringBuffer>;
inline std::string trackID(o2::dataformats::GlobalTrackID gid) {return std::to_string(gid.getRawWOFlags());}
inline void point(Writer& w,const std::array<float,3>& p) {w.StartArray();for(float v:p)w.Double(v);w.EndArray();}
inline void kin(Writer& w,const std::array<float,5>& values) {
  static const char* names[]={"eta","tan_lambda","phi","p","pt"};
  for(int j=0;j<5;++j)if(std::isfinite(values[j])){w.Key(names[j]);w.Double(j==2?std::atan2(std::sin(values[j]),std::cos(values[j])):values[j]);}
}
inline void write(std::ostream& output,o2::event_visualisation::EveWorkflowHelper& helper,
                  const o2::dataformats::PrimaryVertex& pv,size_t index,const o2::framework::TimingInfo& timing,
                  o2::dataformats::GlobalTrackID::mask_t detectorMask,uint64_t invalidTFSpatial=0) {
  auto& event=helper.mEvent;
  if(event.getTrackCount()!=helper.mExportTrackGIDs.size() || event.getTrackCount()!=helper.mExportKinematics.size())
    throw std::runtime_error("Export track instrumentation lost synchronization");
  rapidjson::StringBuffer buffer;Writer w(buffer);w.StartObject();
  auto id=std::to_string(timing.runNumber)+":"+std::to_string(timing.tfCounter)+":"+std::to_string(timing.firstTForbit)+":"+std::to_string(index);
  w.Key("schema_version");w.Int(1);w.Key("units");w.String("cm");w.Key("kind");w.String("collision");
  w.Key("id");w.String(id.c_str());w.Key("run");w.Uint(timing.runNumber);w.Key("timeframe");w.Uint(timing.tfCounter);
  w.Key("orbit");w.Uint(timing.firstTForbit);w.Key("primary_vertex");w.Uint64(index);
  w.Key("calibration_timestamp_ms");w.Uint64(timing.creation);
  w.Key("vertex");point(w,{pv.getX(),pv.getY(),pv.getZ()});w.Key("vertex_time_us");w.Double(pv.getTimeStamp().getTimeStamp());
  w.Key("contributors");w.Uint(pv.getNContributors());
  w.Key("timeframe_invalid_spatial_objects");w.Uint64(invalidTFSpatial);
  w.Key("data_detectors");w.StartArray();
  for(int d=0;d<o2::detectors::DetID::nDetectors;++d)
    if(d!=o2::detectors::DetID::CTP && GID::includesDet(o2::detectors::DetID(d),detectorMask))w.String(o2::detectors::DetID::getName(d));
  w.EndArray();
  std::vector<size_t> failed;
  std::vector<std::optional<std::array<float,2>>> trackDCA(event.getTrackCount());
  w.Key("tracks");w.StartArray();
  for(size_t i=0;i<event.getTrackCount();++i) {
    const auto& track=event.getTrack(i);const auto gid=helper.mExportTrackGIDs[i];
    bool pointsValid=track.getPointCount()>=2;
    for(size_t j=0;j<track.getPointCount();++j)for(auto value:track.getPoint(j))pointsValid=pointsValid&&std::isfinite(value);
    if(!pointsValid){failed.push_back(i);continue;}
    w.StartObject();w.Key("id");w.String(trackID(gid).c_str());w.Key("source");w.String(gid.getSourceName().c_str());
    w.Key("input_gid");w.String(trackID(helper.mExportInputGIDs.at(gid)).c_str());
    w.Key("detectors");w.StartArray();
    for(int d=0;d<o2::detectors::DetID::nDetectors;++d)if(gid.includesDet(o2::detectors::DetID(d)))w.String(o2::detectors::DetID::getName(d));
    w.EndArray();w.Key("time_us");w.Double(track.getTime());w.Key("points");w.StartArray();
    for(size_t j=0;j<track.getPointCount();++j)point(w,track.getPoint(j));w.EndArray();
    w.Key("classification");w.String("unknown");w.Key("kinematics");w.StartObject();kin(w,helper.mExportKinematics[i]);
    std::array<float,2> dca{};bool hasDCA=false;
    if(helper.mExportBarrelFits[i]) {
      auto fitted=*helper.mExportBarrelFits[i];auto propagator=o2::base::Propagator::Instance();
      hasDCA=propagator->propagateToDCA(o2::math_utils::Point3D<float>(pv.getX(),pv.getY(),pv.getZ()),fitted,
        propagator->getNominalBz(),2.f,o2::base::PropagatorF::MatCorrType::USEMatCorrNONE,&dca);
      if(hasDCA && std::isfinite(dca[0]) && std::isfinite(dca[1])){w.Key("dca");w.Double(std::hypot(dca[0],dca[1]));}
      else hasDCA=false;
    }
    if(hasDCA)trackDCA[i]=dca;
    w.EndObject();
    if(hasDCA){w.Key("dca_basis");w.String("sqrt(DCAxy^2+DCAz^2), cm; O2 Propagator::propagateToDCA, nominal Bz, no material correction; TPC Z corrected to this PV time");
      w.Key("dca_xy_cm");w.Double(dca[0]);w.Key("dca_z_cm");w.Double(dca[1]);}
    w.Key("dca_status");w.String(hasDCA?"success":helper.mExportBarrelFits[i]?"propagation_failed":"not_available_for_this_source");
    w.EndObject();
  }
  w.EndArray();w.Key("clusters");w.StartArray();
  size_t calorimeter=0;
  std::vector<size_t> failedClusters;
  for(size_t i=0;i<helper.mExportClusters.size();++i) {
    const auto& cluster=helper.mExportClusters[i];const size_t cellIndex=calorimeter;
    if(cluster.detector=="PHS"||cluster.detector=="EMC")++calorimeter;
    if(!std::all_of(cluster.xyz.begin(),cluster.xyz.end(),[](float v){return std::isfinite(v);})){failedClusters.push_back(i);continue;}
    w.StartObject();
    const auto cid=cluster.detector+":"+std::to_string(timing.tfCounter)+":"+std::to_string(index)+":"+std::to_string(i);
    w.Key("id");w.String(cid.c_str());w.Key("detector");w.String(cluster.detector.c_str());w.Key("position");point(w,cluster.xyz);
    if(cluster.detector=="PHS"||cluster.detector=="EMC") {
      const auto& cell=event.getCalorimetersSpan()[cellIndex];
      w.Key("measurement_kind");w.String("calorimeter_cell");w.Key("energy");if(std::isfinite(cell.getEnergy()))w.Double(cell.getEnergy());else w.Null();
      w.Key("trigger_time_us");if(std::isfinite(cell.getTime()))w.Double(cell.getTime());else w.Null();
    } else {w.Key("measurement_kind");w.String(cluster.detector=="TRD"?"calibrated_tracklet":"cluster");}
    w.Key("association_basis");w.String("O2 reconstructed track/trigger reference to this primary vertex; shared clusters may have multiple associations");
    if(cluster.track>=0) {
      const auto t=size_t(cluster.track);if(t>=helper.mExportTrackGIDs.size())throw std::runtime_error("Invalid exported cluster track reference");
      w.Key("track_id");w.String(trackID(helper.mExportTrackGIDs[t]).c_str());
      w.Key("kinematics_basis");w.String("fitted kinematics of the explicitly associated track; shared-cluster associations are separate records");
      w.Key("kinematics");w.StartObject();kin(w,helper.mExportKinematics[t]);
      if(trackDCA[t]){w.Key("dca");w.Double(std::hypot((*trackDCA[t])[0],(*trackDCA[t])[1]));}
      w.EndObject();
    }
    w.Key("coordinate_basis");w.String(cluster.detector=="TPC"?"O2 per-TF TPCCORRMAP POD Transform; track/PV time; sector-to-global rotation":"O2 detector converter and aligned geometry");
    w.EndObject();
  }
  w.EndArray();w.Key("unrendered_tracks");w.StartArray();
  for(auto i:failed){w.StartObject();w.Key("id");w.String(trackID(helper.mExportTrackGIDs[i]).c_str());w.Key("input_gid");w.String(trackID(helper.mExportInputGIDs.at(helper.mExportTrackGIDs[i])).c_str());w.Key("reason");w.String("O2 propagation produced fewer than two points or nonfinite positions");w.Key("kinematics");w.StartObject();kin(w,helper.mExportKinematics[i]);w.EndObject();w.EndObject();}
  w.EndArray();w.Key("unrendered_clusters");w.StartArray();
  for(auto i:failedClusters){const auto& c=helper.mExportClusters[i];w.StartObject();w.Key("detector");w.String(c.detector.c_str());w.Key("association_index");w.Uint64(i);w.Key("position_components_cm");w.StartArray();for(float v:c.xyz){if(std::isfinite(v))w.Double(v);else w.Null();}w.EndArray();w.Key("reason");w.String("O2 detector conversion produced a nonfinite position");if(c.track>=0){w.Key("track_id");w.String(trackID(helper.mExportTrackGIDs.at(c.track)).c_str());}w.EndObject();}
  w.EndArray();w.Key("warnings");w.StartArray();
  if(invalidTFSpatial)w.String((std::to_string(invalidTFSpatial)+" whole-TF measurements have invalid converted coordinates; retained with coordinate_status in the sidecar, never rendered as finite points.").c_str());
  if(!failedClusters.empty())w.String("Some associated clusters have nonfinite converted positions; preserved in unrendered_clusters.");
  if(!failed.empty())w.String("Some fitted tracks could not be sampled; preserved in unrendered_tracks.");
  w.String("Real data has no MC primary/secondary truth labels. Cluster kinematics are track-associated, not independent cluster momentum measurements.");
  w.String("Unassociated clusters and timing/energy signals are retained in timeframe-objects.jsonl. Detector availability records payload support; a detector can have no spatial objects associated with this collision.");
  w.EndArray();w.EndObject();output<<buffer.GetString()<<'\n';if(!output)throw std::runtime_error("Canonical event write failed");
}
}
