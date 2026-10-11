#!/usr/bin/env python3
"""Export nominal AO2D solenoid conditions in a loaded O2/PyROOT environment.

The output can travel beside AO2D.root as AO2D.root.renderer.json. Uses official
CCDB HTTP blob alternatives; it does not need AliEn for public conditions.
"""
import argparse,json,urllib.error,urllib.request
from pathlib import Path
from ccdb_http_cache import NoRedirect,fetch_public_blob

def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',type=int,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--ccdb',default='http://alice-ccdb.cern.ch');a=p.parse_args()
    import ROOT
    ROOT.gSystem.Load('libO2DataFormatsParameters');ROOT.gInterpreter.Declare('#include "DataFormatsParameters/GRPMagField.h"')
    result={'fields':{}};opener=urllib.request.build_opener(NoRedirect)
    for run in a.runs:
        url=a.ccdb.rstrip('/')+'/RCT/Info/RunInformation/'+str(run)
        try:r=opener.open(urllib.request.Request(url,method='HEAD'),timeout=30)
        except urllib.error.HTTPError as error:r=error
        headers={k.lower():v for k,v in r.headers.items()};r.close()
        if 'sor' not in headers:raise ValueError('CCDB run information lacks SOR for '+str(run))
        sor=int(headers['sor']);blob,validity=fetch_public_blob(a.ccdb.rstrip('/')+'/GLO/Config/GRPMagField/'+str(sor)+'/',a.cache)
        file=ROOT.TFile.Open(str(blob));field=file.Get('ccdb_object')
        if not field:raise ValueError('GRPMagField object is missing')
        result['fields'][str(run)]={'bz_kG':float(field.getNominalL3Field()),'l3_current_A':float(field.getL3Current()),'run_start_ms':sor,'run_end_ms':int(headers.get('eor',sor)),
                                   'basis':'O2 GRPMagField nominal L3 field at CCDB run start (official HTTP blob); constant-solenoid visualization approximation','ccdb':a.ccdb,'object_headers':dict(validity)}
        file.Close()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2));print('AO2D field conditions written: '+str(a.output))
if __name__=='__main__':main()
