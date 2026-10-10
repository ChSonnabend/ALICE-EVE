// Metadata-only ALICE TF inspector using the installed O2 format definitions.
// Layout and version-upgrade behavior follow O2 TFReaderDD (GPL-3.0).
#include <Headers/DataHeader.h>
#include <TFReaderDD/SubTimeFrameFile.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <algorithm>
#include <cstring>
#include <cstddef>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace h = o2::header;
using Meta = o2::rawdd::SubTimeFrameFileMeta;
using Index = o2::rawdd::SubTimeFrameFileDataIndex;

class Reader {
  std::ifstream file;
 public:
  uint64_t position=0, size=0;
  explicit Reader(const std::string& path):file(path,std::ios::binary) {
    if(!file)throw std::runtime_error("Cannot open input");
    file.seekg(0,std::ios::end);size=file.tellg();file.seekg(0);
  }
  void read(void* data,uint64_t length,uint64_t bound) {
    if(position>bound || length>bound-position || bound>size)throw std::runtime_error("Truncated or oversized TF block at byte "+std::to_string(position));
    file.read(static_cast<char*>(data),length);
    if(!file)throw std::runtime_error("Short read at byte "+std::to_string(position));
    position+=length;
  }
  void skip(uint64_t length,uint64_t bound) {
    if(position>bound || length>bound-position || bound>size)throw std::runtime_error("Payload exceeds TF/file boundary at byte "+std::to_string(position));
    position+=length;file.seekg(position);
    if(!file)throw std::runtime_error("Seek failed");
  }
  h::DataHeader stack(uint64_t bound) {
    h::DataHeader result{};bool found=false;
    for(int count=0;count<16;++count){
      h::DataHeader storage{};
      read(&storage,sizeof(h::BaseHeader),bound);
      if(storage.magicStringInt!=h::BaseHeader::sMagicString)throw std::runtime_error("Invalid O2 header magic");
      auto length=storage.headerSize;
      if(length<sizeof(h::BaseHeader)||length>65536)throw std::runtime_error("Invalid O2 header size");
      std::vector<char> buffer(length);std::memcpy(buffer.data(),&storage,sizeof(h::BaseHeader));
      read(buffer.data()+sizeof(h::BaseHeader),length-sizeof(h::BaseHeader),bound);
      if(storage.description==h::DataHeader::sHeaderType){
        if(found)throw std::runtime_error("Multiple DataHeaders in one stack");
        const auto expected=storage.headerVersion==1?80:storage.headerVersion==2?88:storage.headerVersion==h::DataHeader::sVersion?sizeof(h::DataHeader):0;
        if(!expected || length!=expected)throw std::runtime_error("Unsupported DataHeader version/size");
        std::memcpy(&result,buffer.data(),length);
        if(storage.headerVersion<3){result.tfCounter=0;result.runNumber=0;}
        result.headerSize=sizeof(h::DataHeader);result.headerVersion=h::DataHeader::sVersion;
        found=true;
      }
      if(!storage.flagsNextHeader){if(!found)throw std::runtime_error("Header stack lacks DataHeader");return result;}
    }
    throw std::runtime_error("Header stack exceeds 16 headers");
  }
};

template<size_t N> std::string string(const char (&value)[N]) { return std::string(value,strnlen(value,N)); }
struct Payload {uint64_t bytes=0,blocks=0;};
struct TF {uint64_t offset,size,creation;uint32_t run=0,orbit=0,counter=0;std::map<std::string,Payload> origins;};

int main(int argc,char** argv){
  try{
    if(argc!=3)throw std::runtime_error("Usage: alice-tf-inspect INPUT.tf OUTPUT.json");
    Reader reader(argv[1]);std::vector<TF> records;
    while(reader.position<reader.size){
      const auto start=reader.position;
      auto dh=reader.stack(reader.size);
      if(dh.dataDescription!=Meta::sDataDescFileSubTimeFrame || dh.payloadSize!=sizeof(Meta) || dh.payloadSerializationMethod!=h::gSerializationMethodNone)throw std::runtime_error("TF metadata header mismatch");
      // Meta declares version const: decode its wire fields using official offsets,
      // without overwriting a const C++ subobject or relying on constant-folded checks.
      std::vector<char> metadata(sizeof(Meta));reader.read(metadata.data(),metadata.size(),reader.size);
      uint64_t version=0,recordSize=0,creation=0;
      std::memcpy(&version,metadata.data()+offsetof(Meta,mStfFileVersion),sizeof(version));
      std::memcpy(&recordSize,metadata.data()+offsetof(Meta,mStfSizeInFile),sizeof(recordSize));
      std::memcpy(&creation,metadata.data()+offsetof(Meta,mWriteTimeMs),sizeof(creation));
      if(version!=1)throw std::runtime_error("Unsupported STF file version");
      if(recordSize>reader.size-start || recordSize<reader.position-start)throw std::runtime_error("Incomplete or invalid TF size");
      const auto end=start+recordSize;
      TF tf{start,recordSize,creation};
      if(reader.position<end){
        auto index=reader.stack(end);
        if(index.dataDescription!=Index::sDataDescFileStfDataIndex || index.payloadSize%sizeof(Index::DataIndexElem))throw std::runtime_error("Invalid TF index header");
        reader.skip(index.payloadSize,end);
        bool identity=false;
        while(reader.position<end){
          const auto block=reader.stack(end);
          if(!identity && block.payloadSize){tf.run=block.runNumber;tf.orbit=block.firstTForbit;tf.counter=block.tfCounter;identity=true;}
          auto& payload=tf.origins[string(block.dataOrigin.str)];
          payload.bytes+=block.payloadSize;
          if(block.splitPayloadIndex==0)++payload.blocks;
          reader.skip(block.payloadSize,end);
        }
      }
      if(reader.position!=end)throw std::runtime_error("TF boundary mismatch");
      records.push_back(tf);
    }
    rapidjson::StringBuffer text;rapidjson::Writer<rapidjson::StringBuffer> w(text);
    w.StartObject();w.Key("schema_version");w.Int(1);w.Key("format");w.String("raw_tf");w.Key("bytes");w.Uint64(reader.size);w.Key("timeframes");w.Uint64(records.size());w.Key("records");w.StartArray();
    for(const auto& tf:records){w.StartObject();w.Key("offset");w.Uint64(tf.offset);w.Key("size");w.Uint64(tf.size);w.Key("creation_ms");w.Uint64(tf.creation);w.Key("run");w.Uint(tf.run);w.Key("orbit");w.Uint(tf.orbit);w.Key("tf_counter");w.Uint(tf.counter);w.Key("origins");w.StartObject();for(const auto& [name,p]:tf.origins){w.Key(name.c_str());w.StartObject();w.Key("payload_bytes");w.Uint64(p.bytes);w.Key("blocks");w.Uint64(p.blocks);w.EndObject();}w.EndObject();w.EndObject();}
    w.EndArray();w.EndObject();
    std::ofstream output(argv[2]);if(!output)throw std::runtime_error("Output not writable");output<<text.GetString()<<'\n';
    if(!output)throw std::runtime_error("Output write failed");
    std::cout<<"Inspected "<<records.size()<<" timeframe records without reading payloads\n";
  }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
