// Changing a collision-time hypothesis must use the same calibration and
// time-bin convention as the measured cluster transformation.
#pragma once
#include <cmath>
#include <stdexcept>
namespace alice_export {
template<class Track>
inline float tpcClusterTimeTB(const Track& track,float vertexTimeTB) {
  // A membrane-crossing fit constrains its own time. Changing the hypothesis
  // would move its two sides in opposite directions and require a refit.
  return track.hasBothSidesClusters()?track.getTime0():vertexTimeTB;
}
template<class Map,class Track>
inline float tpcVertexShift(const Map& map,const Track& track,float vertexTimeMUS,float binsPerMUS) {
  if(track.hasBothSidesClusters())return 0.f; // constrained crossing track
  if(!std::isfinite(vertexTimeMUS) || !std::isfinite(binsPerMUS) || binsPerMUS<=0 ||
     !std::isfinite(track.getTime0()) || !std::isfinite(map.getVDrift()) || map.getVDrift()<=0)
    throw std::runtime_error("Invalid TPC map or vertex-time calibration");
  const int sector=track.hasCSideClustersOnly()?map.getGeometry().getNumberOfSectorsA():0;
  // The POD method changes measured time, hence reversed arguments for a
  // vertex-time change. Map T0 is already calibrated: no extra offset here.
  return map.convDeltaTimeToDeltaZinTimeFrame(sector,track.getTime0()-vertexTimeMUS*binsPerMUS);
}
}
