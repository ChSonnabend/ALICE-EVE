"""Synthetic helix fixture, clearly labelled; never used as a real-data fallback."""
import json, math, random
from pathlib import Path

def generate(path: Path, count=3):
    rng=random.Random(560067)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as output:
        for event_index in range(count):
            event={'schema_version':1,'units':'cm','id':f'SYNTHETIC-{event_index+1}','kind':'synthetic','vertex':[0,0,0],'tracks':[],'clusters':[],'warnings':['Synthetic demonstration — not ALICE collision data. Geometry envelopes are approximate.']}
            for index in range(65+event_index*15):
                phi=rng.uniform(-math.pi,math.pi);eta=rng.uniform(-.8,.8);pt=rng.uniform(.2,5.);charge=rng.choice((-1,1))
                radius=pt/(.003*.5);points=[]
                for step in range(81):
                    arc=3.*step;turn=charge*arc/radius
                    x=radius/charge*(math.sin(phi+turn)-math.sin(phi));y=radius/charge*(-math.cos(phi+turn)+math.cos(phi))
                    points.append([x,y,arc*math.sinh(eta)])
                kin={'eta':eta,'phi':phi,'tan_lambda':math.sinh(eta),'pt':pt,'p':pt*math.cosh(eta),'dca':0.}
                track={'id':str(index),'detectors':['ITS','TPC'],'points':points,'kinematics':kin,'classification':'primary','classification_basis':'synthetic generator','dca_basis':'synthetic helix origin'}
                event['tracks'].append(track)
                for i in range(8,81,4):
                    detector='ITS' if i<16 else 'TPC'
                    event['clusters'].append({'id':f'{index}-{i}','detector':detector,'position':points[i], 'track_id':str(index),'kinematics':dict(kin),'kinematics_basis':'associated synthetic track','classification':'primary','classification_basis':'synthetic linked track'})
            output.write(json.dumps(event)+'\n')
    return path
