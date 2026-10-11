  o2::globaltracking::RecoContainer recoCont;
  recoCont.collectData(pc,*mDataRequest);
  updateTimeDependentParams(pc);
  const auto& timing=pc.services().get<o2::framework::TimingInfo>();
  if(!mExportTFs.emplace(timing.runNumber,timing.tfCounter,timing.firstTForbit).second)throw std::runtime_error("Duplicate exported timeframe");
  if(mExportTFs.size()==1) {
    if(!gGeoManager)throw std::runtime_error("Aligned geometry was not loaded");
    TFile geometry((std::filesystem::path(mJsonPath)/"aligned-geometry.root").c_str(),"CREATE");
    if(geometry.IsZombie())throw std::runtime_error("Cannot write aligned geometry snapshot");
    if(gGeoManager->Write("ccdb_object")<=0)throw std::runtime_error("Aligned geometry snapshot failed");
    geometry.Close();
  }
  EveWorkflowHelper helper;helper.setRecoContainer(&recoCont);helper.setTPCVDrift(&mTPCVDriftHelper.getVDriftObject());
  if(mClMask[GID::TPC] || mTrkMask[GID::TPC]) {
    auto raw=pc.inputs().get<const char*>("aliceTPCMap");
    helper.mExportTPCMap=&o2::gpu::TPCFastTransformPOD::get(raw);
  }
  if(mEMCALCalibLoader) {
    mEMCALCalibLoader->checkUpdates(pc);
    mEMCALCalibrator->setBadChannelMap(mEMCALCalibLoader->getBadChannelMap());
    mEMCALCalibrator->setTimeCalibration(mEMCALCalibLoader->getTimeCalibration());
    mEMCALCalibrator->setGainCalibration(mEMCALCalibLoader->getGainCalibration());
    helper.setEMCALCellRecalibrator(mEMCALCalibrator.get());
  }
  helper.setITSROFs();helper.selectTracks(&mData.mConfig.configCalib,mClMask,mTrkMask,mTrkMask);helper.selectTowers();
  helper.prepareITSClusters(mData.mITSDict);helper.prepareMFTClusters(mData.mMFTDict);
  auto vertices=recoCont.getPrimaryVertices();
  if(recoCont.getPrimaryVertexMatchedTrackRefs().size()!=vertices.size()+1)throw std::runtime_error("Invalid primary-vertex match references");
  const auto invalidTFSpatial=alice_export::writeTimeframe(std::filesystem::path(mJsonPath)/"timeframe-objects.jsonl",helper,recoCont,timing,mClMask,mExportTFs.size()==1);
  for(size_t i=0;i<vertices.size();++i) {
    helper.draw(i,false);
    alice_export::write(mExportOutput,helper,vertices[i],i,timing,mClMask|mTrkMask,invalidTFSpatial);
    helper.clear();++mExportVertices;
  }
  mExportOutput.flush();
