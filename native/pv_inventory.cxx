// Independent primary-vertex inventory for validating complete event exports.
// Uses the public O2 RecoContainer / InputHelper APIs. Never samples, filters,
// sorts by multiplicity or limits vertices. Timeframes are not collisions.
#include "Framework/CallbacksPolicy.h"
#include "Framework/ConfigParamSpec.h"
#include "Framework/Task.h"
#include "Framework/TimingInfo.h"
#include "DetectorsRaw/HBFUtilsInitializer.h"
#include "DataFormatsGlobalTracking/RecoContainer.h"
#include "GlobalTrackingWorkflowHelpers/InputHelper.h"
#include "ReconstructionDataFormats/GlobalTrackID.h"
#include "ReconstructionDataFormats/PrimaryVertex.h"
#include "ReconstructionDataFormats/VtxTrackRef.h"
#include "ReconstructionDataFormats/VtxTrackIndex.h"
#include "CommonUtils/ConfigurableParam.h"
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <filesystem>
#include <fstream>
#include <set>
#include <tuple>

using namespace o2::framework;
using GID = o2::dataformats::GlobalTrackID;

void customize(std::vector<CallbacksPolicy>& policies) {
  o2::raw::HBFUtilsInitializer::addNewTimeSliceCallback(policies);
}
void customize(std::vector<ConfigParamSpec>& options) {
  options = {{"inventory-output", VariantType::String, "pv-inventory.jsonl", {"Complete TF/PV inventory"}},
             {"disable-mc", VariantType::Bool, true, {"Real-data input"}},
             {"disable-root-input", VariantType::Bool, false, {"Read upstream reconstructed products"}},
             {"configKeyValues", VariantType::String, "", {"O2 configuration"}}};
  o2::raw::HBFUtilsInitializer::addConfigOption(options);
}

#include "Framework/runDataProcessing.h"

class Inventory : public Task {
  std::shared_ptr<o2::globaltracking::DataRequest> request;
  std::string output;
  std::ofstream stream;
  std::set<std::tuple<unsigned,unsigned,unsigned>> seen;
  uint64_t vertexCount=0;
 public:
  Inventory(std::shared_ptr<o2::globaltracking::DataRequest> r, std::string p):request(r),output(p) {}
  void init(InitContext&) final {
    // A fresh filename is required: retries must never append duplicate vertices.
    if (std::filesystem::exists(output)) throw std::runtime_error("Inventory output already exists: "+output);
    stream.open(output);
    if (!stream) throw std::runtime_error("Cannot create inventory output");
  }
  void run(ProcessingContext& pc) final {
    o2::globaltracking::RecoContainer reco;
    reco.collectData(pc,*request);
    const auto& timing=pc.services().get<TimingInfo>();
    if (!seen.emplace(timing.runNumber,timing.tfCounter,timing.firstTForbit).second)
      throw std::runtime_error("Duplicate TF identity in PV inventory");
    auto vertices=reco.getPrimaryVertices();
    auto refs=reco.getPrimaryVertexMatchedTrackRefs();
    auto tracks=reco.getPrimaryVertexMatchedTracks();
    if (refs.size()!=vertices.size()+1) throw std::runtime_error("PV matched-track references lack the unassigned sentinel");
    rapidjson::StringBuffer buffer; rapidjson::Writer<rapidjson::StringBuffer> w(buffer);
    w.StartObject();w.Key("schema_version");w.Int(1);w.Key("run");w.Uint(timing.runNumber);
    w.Key("tf_counter");w.Uint(timing.tfCounter);w.Key("orbit");w.Uint(timing.firstTForbit);
    w.Key("vertex_count");w.Uint64(vertices.size());w.Key("vertices");w.StartArray();
    for(size_t i=0;i<vertices.size();++i) {
      const auto& pv=vertices[i]; const auto& ref=refs[i];
      if (ref.getFirstEntry()<0 || uint64_t(ref.getFirstEntry())+ref.getEntries()>tracks.size())
        throw std::runtime_error("PV track span exceeds collection bounds");
      w.StartObject();w.Key("index");w.Uint64(i);w.Key("position_cm");w.StartArray();
      w.Double(pv.getX());w.Double(pv.getY());w.Double(pv.getZ());w.EndArray();
      w.Key("time_us");w.Double(pv.getTimeStamp().getTimeStamp());
      w.Key("contributors");w.Int(pv.getNContributors());
      w.Key("matched_track_count");w.Int(ref.getEntries());
      w.Key("matched_track_ids");w.StartArray();
      for(int j=0;j<ref.getEntries();++j) w.Uint(tracks[ref.getFirstEntry()+j].getRaw());
      w.EndArray();w.EndObject();
    }
    w.EndArray();w.Key("unassigned_track_count");w.Int(refs.back().getEntries());w.EndObject();
    stream<<buffer.GetString()<<'\n';stream.flush();
    if(!stream) throw std::runtime_error("Inventory write failed");
    vertexCount+=vertices.size();
  }
  void endOfStream(EndOfStreamContext&) final {
    stream.close();
    if (!stream) throw std::runtime_error("Inventory close failed");
    std::ofstream completion(output+".complete.json");
    completion<<"{\"schema_version\":1,\"timeframes\":"<<seen.size()<<",\"vertices\":"<<vertexCount<<"}\n";
    if(!completion) throw std::runtime_error("Inventory completion write failed");
  }
};

WorkflowSpec defineDataProcessing(ConfigContext const& cfg) {
  o2::conf::ConfigurableParam::updateFromString(cfg.options().get<std::string>("configKeyValues"));
  WorkflowSpec specs;
  auto request=std::make_shared<o2::globaltracking::DataRequest>();
  request->requestPrimaryVertices(false);
  o2::globaltracking::InputHelper::addInputSpecsPVertex(cfg,specs,false);
  specs.emplace_back(DataProcessorSpec{"alice-pv-inventory",request->inputs,{},
    AlgorithmSpec{adaptFromTask<Inventory>(request,cfg.options().get<std::string>("inventory-output"))}});
  o2::raw::HBFUtilsInitializer hbf(cfg,specs);
  return specs;
}
