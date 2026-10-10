import struct
import pytest
from alice_renderer.tf import BASE, BODY, META, HEADER_SIZES, inspect_tf
from alice_renderer.inputs import inspect_input


def header(description, payload, origin=b'FLP', *, version=3, flags=0, split=0):
    length=HEADER_SIZES[version]
    wire=BASE.pack(b'O2O2',length,flags,version,b'DataHead',b'NONE\0\0\0\0')
    wire+=BODY.pack(description.ljust(16,b'\0'),origin.ljust(4,b'\0'),2,b'NONE\0\0\0\0',0,split,payload)
    if version>=2:wire+=struct.pack('<I',120)
    if version>=3:wire+=struct.pack('<II',42,560067)
    return wire.ljust(length,b'\0')


def record(*, version=3, next_header=False):
    extension=BASE.pack(b'O2O2',32,0,1,b'DataFlow',b'NONE\0\0\0\0') if next_header else b''
    data=header(b'RAWDATA',5,b'TPC',version=version,flags=int(next_header))+extension+b'ABCDE'
    data+=header(b'RAWDATA',3,b'TPC',version=version,split=1)+b'XYZ'
    data+=header(b'RAWDATA',2,b'FT0',version=version)+b'00'
    index=header(b'FILE_STF_INDEX',48,version=version)+bytes(48)
    length=HEADER_SIZES[version]+META.size+len(index)+len(data)
    return header(b'FILE_STF_META',24,version=version)+META.pack(1,length,1700000000000)+index+data


@pytest.mark.parametrize('version',[1,2,3])
def test_versions_and_header_stacks(tmp_path,version):
    path=tmp_path/'input.tf';part=record(version=version,next_header=True);path.write_bytes(part+part)
    result=inspect_tf(path)
    assert result['timeframes']==2
    assert result['records'][1]['offset']==len(part)
    first=result['records'][0]
    assert first['origins']=={'TPC':{'payload_bytes':8,'blocks':1},'FT0':{'payload_bytes':2,'blocks':1}}
    assert first['run']==(560067 if version==3 else 0)
    assert first['orbit']==(120 if version>=2 else 0)
    info=inspect_input(path)
    assert info.detectors==['FT0','TPC'] and info.timeframes==2


@pytest.mark.parametrize('cut',[0,1,32,96,119,-1])
def test_truncation(tmp_path,cut):
    path=tmp_path/'bad.tf';path.write_bytes(record()[:cut])
    with pytest.raises(ValueError):inspect_tf(path)


def test_unknown_version_and_cancellation(tmp_path):
    path=tmp_path/'unknown.tf';wire=bytearray(record());struct.pack_into('<I',wire,12,99);path.write_bytes(wire)
    with pytest.raises(ValueError,match='Unsupported DataHeader'):inspect_tf(path)
    path.write_bytes(record())
    with pytest.raises(InterruptedError):inspect_tf(path,cancelled=lambda:True)


def test_payload_cannot_cross_record(tmp_path):
    wire=bytearray(record());offset=96+24+96+48
    struct.pack_into('<Q',wire,offset+72,10**12)
    path=tmp_path/'oversized.tf';path.write_bytes(wire)
    with pytest.raises(ValueError,match='boundary'):inspect_tf(path)
