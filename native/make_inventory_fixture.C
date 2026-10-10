// Synthetic QA fixture only. It is not a simulated or reconstructed ALICE event.
#include "ReconstructionDataFormats/PrimaryVertex.h"
#include "ReconstructionDataFormats/VtxTrackRef.h"
#include "ReconstructionDataFormats/VtxTrackIndex.h"
#include <TFile.h>
#include <TTree.h>
#include <vector>

void make_inventory_fixture() {
  TFile file("o2_primary_vertex.root","CREATE");
  if (file.IsZombie()) throw std::runtime_error("Fixture file already exists or cannot be created");
  TTree tree("o2sim","Synthetic PV inventory QA");
  std::vector<o2::dataformats::PrimaryVertex> vertices;
  std::vector<o2::dataformats::VtxTrackRef> refs;
  std::vector<o2::dataformats::VtxTrackIndex> tracks;
  tree.Branch("PrimaryVertex",&vertices);tree.Branch("PV2TrackRefs",&refs);tree.Branch("PVTrackIndices",&tracks);
  for (int i=0;i<32;++i) {
    if (i<31) {
      o2::dataformats::PrimaryVertex pv;pv.setXYZ(0.1f,0.2f,i-15.f);pv.setNContributors(i%4);
      vertices.push_back(pv);
    }
    o2::dataformats::VtxTrackRef ref;ref.setVtxID(i<31?i:-1);
    for(int s=0;s<o2::dataformats::GlobalTrackID::NSources;++s) {
      ref.setFirstEntryOfSource(s,tracks.size());
      if(s==o2::dataformats::GlobalTrackID::TPC && i%3==0) tracks.emplace_back(i,o2::dataformats::GlobalTrackID::TPC);
    }
    ref.setEnd(tracks.size());refs.push_back(ref);
  }
  tree.Fill();
  vertices.clear();refs.clear();tracks.clear();
  o2::dataformats::VtxTrackRef sentinel;
  for(int s=0;s<o2::dataformats::GlobalTrackID::NSources;++s) sentinel.setFirstEntryOfSource(s,0);
  sentinel.setEnd(0);refs.push_back(sentinel);
  tree.Fill();tree.Write();file.Close();
}

#ifdef ALICE_STANDALONE_FIXTURE
int main() { make_inventory_fixture(); }
#endif
