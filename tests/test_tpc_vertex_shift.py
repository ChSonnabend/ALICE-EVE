"""Physical calibration invariant, independent of O2 installation or renderer."""
import shutil,subprocess
from pathlib import Path
import pytest

def test_vertex_hypothesis_matches_absolute_drift_transform_on_both_sides(tmp_path):
    compiler=shutil.which('c++') or shutil.which('g++')
    if not compiler:pytest.skip('Native C++ compiler unavailable')
    source=tmp_path/'invariant.cpp';source.write_text(r'''
#include "tpc_vertex_shift.h"
#include <cassert>
#include <initializer_list>
struct Geo {int getNumberOfSectorsA()const{return 18;}};
struct Map {
 float v=.5306115f,t0=8.671564f;
 Geo getGeometry()const{return {};}
 float getVDrift()const{return v;}
 float convDeltaTimeToDeltaZinTimeFrame(int sector,float delta)const{return (sector<18?-1:1)*delta*v;}
 // Independent absolute drift-length / endcap geometry convention.
 float measuredZ(int sector,float measuredTime,float vertexTime)const {
  float length=(measuredTime-t0-vertexTime)*v;
  return (sector<18?1:-1)*(250.f-length);
 }
};
struct Track {float time;bool c,crossing=false;float getTime0()const{return time;}bool hasCSideClustersOnly()const{return c;}bool hasBothSidesClusters()const{return crossing;}};
int main(){Map map;for(int side:{0,18})for(float reference:{0.f,400.f,877.2673f})for(float vertex:{1.f,150.f,211.72583f}){
 Track tr{reference,side==18};float factor=1.f/.19960627f;
 float atReference=map.measuredZ(side,1239.5156f,reference);
 float shifted=atReference+alice_export::tpcVertexShift(map,tr,vertex,factor);
 float direct=map.measuredZ(side,1239.5156f,vertex*factor);
 assert(std::abs(shifted-direct)<.0002f);
}
Track constrained{500.f,false,true};assert(alice_export::tpcVertexShift(map,constrained,10,5)==0);
for(int side:{0,18}){
 float native=map.measuredZ(side,1239.5f,constrained.getTime0());
 float displayed=map.measuredZ(side,1239.5f,alice_export::tpcClusterTimeTB(constrained,999.f));
 assert(native==displayed);
}
Track ordinary{500.f,false};assert(alice_export::tpcClusterTimeTB(ordinary,999.f)==999.f);
try{Track tr{0,false};alice_export::tpcVertexShift(map,tr,10,0);return 1;}catch(const std::runtime_error&){}
}
''')
    exe=tmp_path/'invariant'
    subprocess.run([compiler,'-std=c++17','-I'+str(Path(__file__).parents[1]/'native'),str(source),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe)],check=True,capture_output=True)
