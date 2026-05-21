# Wiretap SDK — Python Bindings Reference (Flame 2027)

Python bindings for the Wiretap C++ client API, shipped with Flame 2027 at
`/opt/Autodesk/python/2027/lib/python3.13/site-packages/adsk/libwiretapPythonClientAPI.so`.
Usable from standalone scripts (outside Flame) to traverse the IFFFS node tree,
read/write metadata, and do frame-level media I/O. The C++ `.dylib` lives at
`/opt/Autodesk/lib64/2026.2.2/libwiretapClientAPI.dylib`.

Import pattern:

```python
import sys
sys.path.insert(0, '/opt/Autodesk/python/2027/lib/python3.13/site-packages')
from adsk import libwiretapPythonClientAPI as WT

WT.WireTapClientInit()
try:
    server = WT.WireTapServerHandle('localhost')
    root = WT.WireTapNodeHandle(server, '/')
    # ...
finally:
    WT.WireTapClientUninit()
```

The always-paired `WireTapClientInit()` / `WireTapClientUninit()` calls are mandatory.
Skipping uninit leaks IFFFS connections.

## Blob

Kind: class

### Methods

- `getData` — getData( (Blob)arg1) -> str :
  
      C++ signature :
          char const* getData(Blob_Wrapper {lvalue})
- `getFormat` — getFormat( (Blob)arg1) -> str :
  
      C++ signature :
          char const* getFormat(Blob_Wrapper {lvalue})
- `getRawData` — getRawData( (Blob)arg1) -> str :
  
      C++ signature :
          char const* getRawData(Blob_Wrapper {lvalue})
- `getVersion` — getVersion( (Blob)arg1, (WireTapInt)arg2, (WireTapInt)arg3) -> bool :
  
      C++ signature :
          bool getVersion(Blob_Wrapper {lvalue},WireTapInt {lvalue},WireTapInt {lvalue})

## WireTapAudioFormat

Kind: class

### Methods

- `FORMAT_DL_AUDIO` — FORMAT_DL_AUDIO() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO()
- `FORMAT_DL_AUDIO_FLOAT` — FORMAT_DL_AUDIO_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_FLOAT()
- `FORMAT_DL_AUDIO_FLOAT_LE` — FORMAT_DL_AUDIO_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_FLOAT_LE()
- `FORMAT_DL_AUDIO_INT16` — FORMAT_DL_AUDIO_INT16() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT16()
- `FORMAT_DL_AUDIO_INT16_LE` — FORMAT_DL_AUDIO_INT16_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT16_LE()
- `FORMAT_DL_AUDIO_INT24` — FORMAT_DL_AUDIO_INT24() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24()
- `FORMAT_DL_AUDIO_INT24_LE` — FORMAT_DL_AUDIO_INT24_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24_LE()
- `FORMAT_DL_AUDIO_INT24_MSB32_LE` — FORMAT_DL_AUDIO_INT24_MSB32_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24_MSB32_LE()
- `FORMAT_DL_AUDIO_INT8` — FORMAT_DL_AUDIO_INT8() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT8()
- `FORMAT_DL_AUDIO_INT8_UNSIGNED` — FORMAT_DL_AUDIO_INT8_UNSIGNED() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT8_UNSIGNED()
- `FORMAT_DL_AUDIO_MIXED` — FORMAT_DL_AUDIO_MIXED() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_MIXED()
- `FORMAT_HLS` — FORMAT_HLS() -> str :
  
      C++ signature :
          char const* FORMAT_HLS()
- `FORMAT_HLSA` — FORMAT_HLSA() -> str :
  
      C++ signature :
          char const* FORMAT_HLSA()
- `FORMAT_HLSA_LE` — FORMAT_HLSA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_HLSA_LE()
- `FORMAT_HLS_LE` — FORMAT_HLS_LE() -> str :
  
      C++ signature :
          char const* FORMAT_HLS_LE()
- `FORMAT_MIXED` — FORMAT_MIXED() -> str :
  
      C++ signature :
          char const* FORMAT_MIXED()
- `FORMAT_MONO` — FORMAT_MONO() -> str :
  
      C++ signature :
          char const* FORMAT_MONO()
- `FORMAT_MONO_FLOAT` — FORMAT_MONO_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_FLOAT()
- `FORMAT_MONO_FLOAT_LE` — FORMAT_MONO_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_FLOAT_LE()
- `FORMAT_MONO_LE` — FORMAT_MONO_LE() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_LE()
- `FORMAT_RGB` — FORMAT_RGB() -> str :
  
      C++ signature :
          char const* FORMAT_RGB()
- `FORMAT_RGBA` — FORMAT_RGBA() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA()
- `FORMAT_RGBA_FLOAT` — FORMAT_RGBA_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_FLOAT()
- `FORMAT_RGBA_FLOAT_LE` — FORMAT_RGBA_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_FLOAT_LE()
- `FORMAT_RGBA_LE` — FORMAT_RGBA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_LE()
- `FORMAT_RGB_FLOAT` — FORMAT_RGB_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_FLOAT()
- `FORMAT_RGB_FLOAT_LE` — FORMAT_RGB_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_FLOAT_LE()
- `FORMAT_RGB_LE` — FORMAT_RGB_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_LE()
- `FORMAT_UYVY` — FORMAT_UYVY() -> str :
  
      C++ signature :
          char const* FORMAT_UYVY()
- `FORMAT_UYVY_LE` — FORMAT_UYVY_LE() -> str :
  
      C++ signature :
          char const* FORMAT_UYVY_LE()
- `FORMAT_YUV` — FORMAT_YUV() -> str :
  
      C++ signature :
          char const* FORMAT_YUV()
- `FORMAT_YUVA` — FORMAT_YUVA() -> str :
  
      C++ signature :
          char const* FORMAT_YUVA()
- `FORMAT_YUVA_LE` — FORMAT_YUVA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_YUVA_LE()
- `FORMAT_YUV_LE` — FORMAT_YUV_LE() -> str :
  
      C++ signature :
          char const* FORMAT_YUV_LE()
- `SCAN_FORMAT_FIELD_1_EVEN_STR` — SCAN_FORMAT_FIELD_1_EVEN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_1_EVEN_STR()
- `SCAN_FORMAT_FIELD_1_ODD_STR` — SCAN_FORMAT_FIELD_1_ODD_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_1_ODD_STR()
- `SCAN_FORMAT_FIELD_2_EVEN_STR` — SCAN_FORMAT_FIELD_2_EVEN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_2_EVEN_STR()
- `SCAN_FORMAT_FIELD_2_ODD_STR` — SCAN_FORMAT_FIELD_2_ODD_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_2_ODD_STR()
- `SCAN_FORMAT_PROGRESSIVE_STR` — SCAN_FORMAT_PROGRESSIVE_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_PROGRESSIVE_STR()
- `SCAN_FORMAT_UNKNOWN_STR` — SCAN_FORMAT_UNKNOWN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_UNKNOWN_STR()
- `ScanFormat` — int([x]) -> integer
  int(x, base=10) -> integer
  
  Convert a number or string to an integer, or return 0 if no arguments
  are given.  If x is a number, return x.__int__().  For floating point
  numbers, this truncates towards zero.
- `bitsPerPixel` — bitsPerPixel( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int bitsPerPixel(WireTapClipFormat {lvalue})
- `bitsPerSample` — bitsPerSample( (WireTapAudioFormat)arg1) -> int :
  
      C++ signature :
          int bitsPerSample(WireTapAudioFormat {lvalue})
- `colourSpace` — colourSpace( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* colourSpace(WireTapClipFormat {lvalue})
- `formatTag` — formatTag( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* formatTag(WireTapClipFormat {lvalue})
- `frameBufferSize` — frameBufferSize( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          unsigned long frameBufferSize(WireTapClipFormat {lvalue})
- `frameRate` — frameRate( (WireTapClipFormat)arg1) -> float :
  
      C++ signature :
          float frameRate(WireTapClipFormat {lvalue})
- `height` — height( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int height(WireTapClipFormat {lvalue})
- `metaData` — metaData( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* metaData(WireTapClipFormat {lvalue})
- `metaDataTag` — metaDataTag( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* metaDataTag(WireTapClipFormat {lvalue})
- `numChannels` — numChannels( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int numChannels(WireTapClipFormat {lvalue})
- `numSamples` — numSamples( (WireTapAudioFormat)arg1) -> int :
  
      C++ signature :
          int numSamples(WireTapAudioFormat {lvalue})
- `pixelRatio` — pixelRatio( (WireTapClipFormat)arg1) -> float :
  
      C++ signature :
          float pixelRatio(WireTapClipFormat {lvalue})
- `sampleRate` — sampleRate( (WireTapAudioFormat)arg1) -> float :
  
      C++ signature :
          float sampleRate(WireTapAudioFormat {lvalue})
- `scanFormat` — scanFormat( (WireTapClipFormat)arg1) -> ScanFormat :
  
      C++ signature :
          WireTapClipFormat::ScanFormat scanFormat(WireTapClipFormat {lvalue})
- `scanFormatStr` — scanFormatStr( (ScanFormat)arg1) -> str :
  
      C++ signature :
          char const* scanFormatStr(WireTapClipFormat::ScanFormat)
- `setBitsPerPixel` — setBitsPerPixel( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setBitsPerPixel(WireTapClipFormat {lvalue},int)
- `setBitsPerSample` — setBitsPerSample( (WireTapAudioFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setBitsPerSample(WireTapAudioFormat {lvalue},int)
- `setColourSpace` — setColourSpace( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setColourSpace(WireTapClipFormat {lvalue},char const*)
- `setFormatTag` — setFormatTag( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setFormatTag(WireTapClipFormat {lvalue},char const*)
- `setFrameBufferSize` — setFrameBufferSize( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setFrameBufferSize(WireTapClipFormat {lvalue},unsigned long)
- `setFrameRate` — setFrameRate( (WireTapClipFormat)arg1, (float)arg2) -> None :
  
      C++ signature :
          void setFrameRate(WireTapClipFormat {lvalue},float)
- `setHeight` — setHeight( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setHeight(WireTapClipFormat {lvalue},int)
- `setMetaData` — setMetaData( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setMetaData(WireTapClipFormat {lvalue},char const*)
- `setMetaDataTag` — setMetaDataTag( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setMetaDataTag(WireTapClipFormat {lvalue},char const*)
- `setNumChannels` — setNumChannels( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setNumChannels(WireTapClipFormat {lvalue},int)
- `setNumSamples` — setNumSamples( (WireTapAudioFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setNumSamples(WireTapAudioFormat {lvalue},int)
- `setPixelRatio` — setPixelRatio( (WireTapClipFormat)arg1, (float)arg2) -> None :
  
      C++ signature :
          void setPixelRatio(WireTapClipFormat {lvalue},float)
- `setSampleRate` — setSampleRate( (WireTapAudioFormat)arg1, (float)arg2) -> None :
  
      C++ signature :
          void setSampleRate(WireTapAudioFormat {lvalue},float)
- `setScanFormat` — setScanFormat( (WireTapClipFormat)arg1, (ScanFormat)arg2) -> None :
  
      C++ signature :
          void setScanFormat(WireTapClipFormat {lvalue},WireTapClipFormat::ScanFormat)
- `setWidth` — setWidth( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setWidth(WireTapClipFormat {lvalue},int)
- `strToScanFormat` — strToScanFormat( (str)arg1) -> ScanFormat :
  
      C++ signature :
          WireTapClipFormat::ScanFormat strToScanFormat(char const*)
- `width` — width( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int width(WireTapClipFormat {lvalue})

## WireTapClient

Kind: class

### Methods

- `init` — init( (WireTapClient)arg1) -> bool :
  
      C++ signature :
          bool init(WireTapClient {lvalue})

## WireTapClipFormat

Kind: class

### Methods

- `FORMAT_DL_AUDIO` — FORMAT_DL_AUDIO() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO()
- `FORMAT_DL_AUDIO_FLOAT` — FORMAT_DL_AUDIO_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_FLOAT()
- `FORMAT_DL_AUDIO_FLOAT_LE` — FORMAT_DL_AUDIO_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_FLOAT_LE()
- `FORMAT_DL_AUDIO_INT16` — FORMAT_DL_AUDIO_INT16() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT16()
- `FORMAT_DL_AUDIO_INT16_LE` — FORMAT_DL_AUDIO_INT16_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT16_LE()
- `FORMAT_DL_AUDIO_INT24` — FORMAT_DL_AUDIO_INT24() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24()
- `FORMAT_DL_AUDIO_INT24_LE` — FORMAT_DL_AUDIO_INT24_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24_LE()
- `FORMAT_DL_AUDIO_INT24_MSB32_LE` — FORMAT_DL_AUDIO_INT24_MSB32_LE() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT24_MSB32_LE()
- `FORMAT_DL_AUDIO_INT8` — FORMAT_DL_AUDIO_INT8() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT8()
- `FORMAT_DL_AUDIO_INT8_UNSIGNED` — FORMAT_DL_AUDIO_INT8_UNSIGNED() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_INT8_UNSIGNED()
- `FORMAT_DL_AUDIO_MIXED` — FORMAT_DL_AUDIO_MIXED() -> str :
  
      C++ signature :
          char const* FORMAT_DL_AUDIO_MIXED()
- `FORMAT_HLS` — FORMAT_HLS() -> str :
  
      C++ signature :
          char const* FORMAT_HLS()
- `FORMAT_HLSA` — FORMAT_HLSA() -> str :
  
      C++ signature :
          char const* FORMAT_HLSA()
- `FORMAT_HLSA_LE` — FORMAT_HLSA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_HLSA_LE()
- `FORMAT_HLS_LE` — FORMAT_HLS_LE() -> str :
  
      C++ signature :
          char const* FORMAT_HLS_LE()
- `FORMAT_MIXED` — FORMAT_MIXED() -> str :
  
      C++ signature :
          char const* FORMAT_MIXED()
- `FORMAT_MONO` — FORMAT_MONO() -> str :
  
      C++ signature :
          char const* FORMAT_MONO()
- `FORMAT_MONO_FLOAT` — FORMAT_MONO_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_FLOAT()
- `FORMAT_MONO_FLOAT_LE` — FORMAT_MONO_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_FLOAT_LE()
- `FORMAT_MONO_LE` — FORMAT_MONO_LE() -> str :
  
      C++ signature :
          char const* FORMAT_MONO_LE()
- `FORMAT_RGB` — FORMAT_RGB() -> str :
  
      C++ signature :
          char const* FORMAT_RGB()
- `FORMAT_RGBA` — FORMAT_RGBA() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA()
- `FORMAT_RGBA_FLOAT` — FORMAT_RGBA_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_FLOAT()
- `FORMAT_RGBA_FLOAT_LE` — FORMAT_RGBA_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_FLOAT_LE()
- `FORMAT_RGBA_LE` — FORMAT_RGBA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGBA_LE()
- `FORMAT_RGB_FLOAT` — FORMAT_RGB_FLOAT() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_FLOAT()
- `FORMAT_RGB_FLOAT_LE` — FORMAT_RGB_FLOAT_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_FLOAT_LE()
- `FORMAT_RGB_LE` — FORMAT_RGB_LE() -> str :
  
      C++ signature :
          char const* FORMAT_RGB_LE()
- `FORMAT_UYVY` — FORMAT_UYVY() -> str :
  
      C++ signature :
          char const* FORMAT_UYVY()
- `FORMAT_UYVY_LE` — FORMAT_UYVY_LE() -> str :
  
      C++ signature :
          char const* FORMAT_UYVY_LE()
- `FORMAT_YUV` — FORMAT_YUV() -> str :
  
      C++ signature :
          char const* FORMAT_YUV()
- `FORMAT_YUVA` — FORMAT_YUVA() -> str :
  
      C++ signature :
          char const* FORMAT_YUVA()
- `FORMAT_YUVA_LE` — FORMAT_YUVA_LE() -> str :
  
      C++ signature :
          char const* FORMAT_YUVA_LE()
- `FORMAT_YUV_LE` — FORMAT_YUV_LE() -> str :
  
      C++ signature :
          char const* FORMAT_YUV_LE()
- `SCAN_FORMAT_FIELD_1_EVEN_STR` — SCAN_FORMAT_FIELD_1_EVEN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_1_EVEN_STR()
- `SCAN_FORMAT_FIELD_1_ODD_STR` — SCAN_FORMAT_FIELD_1_ODD_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_1_ODD_STR()
- `SCAN_FORMAT_FIELD_2_EVEN_STR` — SCAN_FORMAT_FIELD_2_EVEN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_2_EVEN_STR()
- `SCAN_FORMAT_FIELD_2_ODD_STR` — SCAN_FORMAT_FIELD_2_ODD_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_FIELD_2_ODD_STR()
- `SCAN_FORMAT_PROGRESSIVE_STR` — SCAN_FORMAT_PROGRESSIVE_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_PROGRESSIVE_STR()
- `SCAN_FORMAT_UNKNOWN_STR` — SCAN_FORMAT_UNKNOWN_STR() -> str :
  
      C++ signature :
          char const* SCAN_FORMAT_UNKNOWN_STR()
- `ScanFormat` — int([x]) -> integer
  int(x, base=10) -> integer
  
  Convert a number or string to an integer, or return 0 if no arguments
  are given.  If x is a number, return x.__int__().  For floating point
  numbers, this truncates towards zero.
- `bitsPerPixel` — bitsPerPixel( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int bitsPerPixel(WireTapClipFormat {lvalue})
- `colourSpace` — colourSpace( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* colourSpace(WireTapClipFormat {lvalue})
- `formatTag` — formatTag( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* formatTag(WireTapClipFormat {lvalue})
- `frameBufferSize` — frameBufferSize( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          unsigned long frameBufferSize(WireTapClipFormat {lvalue})
- `frameRate` — frameRate( (WireTapClipFormat)arg1) -> float :
  
      C++ signature :
          float frameRate(WireTapClipFormat {lvalue})
- `height` — height( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int height(WireTapClipFormat {lvalue})
- `metaData` — metaData( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* metaData(WireTapClipFormat {lvalue})
- `metaDataTag` — metaDataTag( (WireTapClipFormat)arg1) -> str :
  
      C++ signature :
          char const* metaDataTag(WireTapClipFormat {lvalue})
- `numChannels` — numChannels( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int numChannels(WireTapClipFormat {lvalue})
- `pixelRatio` — pixelRatio( (WireTapClipFormat)arg1) -> float :
  
      C++ signature :
          float pixelRatio(WireTapClipFormat {lvalue})
- `scanFormat` — scanFormat( (WireTapClipFormat)arg1) -> ScanFormat :
  
      C++ signature :
          WireTapClipFormat::ScanFormat scanFormat(WireTapClipFormat {lvalue})
- `scanFormatStr` — scanFormatStr( (ScanFormat)arg1) -> str :
  
      C++ signature :
          char const* scanFormatStr(WireTapClipFormat::ScanFormat)
- `setBitsPerPixel` — setBitsPerPixel( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setBitsPerPixel(WireTapClipFormat {lvalue},int)
- `setColourSpace` — setColourSpace( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setColourSpace(WireTapClipFormat {lvalue},char const*)
- `setFormatTag` — setFormatTag( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setFormatTag(WireTapClipFormat {lvalue},char const*)
- `setFrameBufferSize` — setFrameBufferSize( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setFrameBufferSize(WireTapClipFormat {lvalue},unsigned long)
- `setFrameRate` — setFrameRate( (WireTapClipFormat)arg1, (float)arg2) -> None :
  
      C++ signature :
          void setFrameRate(WireTapClipFormat {lvalue},float)
- `setHeight` — setHeight( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setHeight(WireTapClipFormat {lvalue},int)
- `setMetaData` — setMetaData( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setMetaData(WireTapClipFormat {lvalue},char const*)
- `setMetaDataTag` — setMetaDataTag( (WireTapClipFormat)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setMetaDataTag(WireTapClipFormat {lvalue},char const*)
- `setNumChannels` — setNumChannels( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setNumChannels(WireTapClipFormat {lvalue},int)
- `setPixelRatio` — setPixelRatio( (WireTapClipFormat)arg1, (float)arg2) -> None :
  
      C++ signature :
          void setPixelRatio(WireTapClipFormat {lvalue},float)
- `setScanFormat` — setScanFormat( (WireTapClipFormat)arg1, (ScanFormat)arg2) -> None :
  
      C++ signature :
          void setScanFormat(WireTapClipFormat {lvalue},WireTapClipFormat::ScanFormat)
- `setWidth` — setWidth( (WireTapClipFormat)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setWidth(WireTapClipFormat {lvalue},int)
- `strToScanFormat` — strToScanFormat( (str)arg1) -> ScanFormat :
  
      C++ signature :
          WireTapClipFormat::ScanFormat strToScanFormat(char const*)
- `width` — width( (WireTapClipFormat)arg1) -> int :
  
      C++ signature :
          int width(WireTapClipFormat {lvalue})

## WireTapFrameId

Kind: class

### Methods

- `id` — id( (WireTapFrameId)arg1) -> str :
  
      C++ signature :
          char const* id(WireTapFrameId {lvalue})
- `id_` — (no docstring)
- `setId` — setId( (WireTapFrameId)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setId(WireTapFrameId {lvalue},char const*)

## WireTapInt

Kind: class

## WireTapMetaData

Kind: class

### Methods

- `Blob_base` — (no docstring)
- `STREAM_BLOB` — STREAM_BLOB() -> str :
  
      C++ signature :
          char const* STREAM_BLOB()
- `STREAM_XML` — STREAM_XML() -> str :
  
      C++ signature :
          char const* STREAM_XML()

## WireTapNodeHandle

Kind: class

### Methods

- `canCreateNode` — canCreateNode( (WireTapNodeHandle)arg1, (str)arg2, (bool)arg3) -> bool :
  
      C++ signature :
          bool canCreateNode(WireTapNodeHandle {lvalue},char const*,bool {lvalue})
- `createClipNode` — createClipNode( (WireTapNodeHandle)arg1, (str)arg2, (WireTapClipFormat)arg3, (str)arg4, (WireTapNodeHandle)arg5) -> bool :
  
      C++ signature :
          bool createClipNode(WireTapNodeHandle {lvalue},char const*,WireTapClipFormat,char const*,WireTapNodeHandle {lvalue})
  
  createClipNode( (WireTapNodeHandle)arg1, (str)arg2, (WireTapClipFormat)arg3, (int)arg4, (WireTapNodeHandle)arg5) -> bool :
- `createNode` — createNode( (WireTapNodeHandle)arg1, (str)arg2, (int)arg3, (WireTapNodeHandle)arg4) -> bool :
  
      C++ signature :
          bool createNode(WireTapNodeHandle {lvalue},char const*,int,WireTapNodeHandle {lvalue})
  
  createNode( (WireTapNodeHandle)arg1, (str)arg2, (str)arg3, (WireTapNodeHandle)arg4) -> bool :
- `destroyNode` — destroyNode( (WireTapNodeHandle)arg1) -> bool :
  
      C++ signature :
          bool destroyNode(WireTapNodeHandle {lvalue})
- `duplicateNode` — duplicateNode( (WireTapNodeHandle)arg1, (WireTapNodeHandle)arg2, (str)arg3, (WireTapNodeHandle)arg4) -> bool :
  
      C++ signature :
          bool duplicateNode(WireTapNodeHandle {lvalue},WireTapNodeHandle,char const*,WireTapNodeHandle {lvalue})
- `getAvailableMetaDataStream` — getAvailableMetaDataStream( (WireTapNodeHandle)arg1, (int)arg2, (WireTapStr)arg3) -> bool :
  
      C++ signature :
          bool getAvailableMetaDataStream(WireTapNodeHandle {lvalue},int,WireTapStr {lvalue})
- `getChild` — getChild( (WireTapNodeHandle)arg1, (int)arg2, (WireTapNodeHandle)arg3) -> bool :
  
      C++ signature :
          bool getChild(WireTapNodeHandle {lvalue},int,WireTapNodeHandle {lvalue})
- `getClipFormat` — getClipFormat( (WireTapNodeHandle)arg1, (WireTapClipFormat)arg2) -> bool :
  
      C++ signature :
          bool getClipFormat(WireTapNodeHandle {lvalue},WireTapClipFormat {lvalue})
- `getDisplayName` — getDisplayName( (WireTapNodeHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getDisplayName(WireTapNodeHandle {lvalue},WireTapStr {lvalue})
- `getFrameId` — getFrameId( (WireTapNodeHandle)arg1, (int)arg2, (WireTapStr)arg3) -> bool :
  
      C++ signature :
          bool getFrameId(WireTapNodeHandle {lvalue},int,WireTapStr {lvalue})
- `getFrameIdPath` — getFrameIdPath( (WireTapNodeHandle)arg1, (int)arg2, (WireTapStr)arg3) -> bool :
  
      C++ signature :
          bool getFrameIdPath(WireTapNodeHandle {lvalue},int,WireTapStr {lvalue})
- `getIsClipNode` — getIsClipNode( (WireTapNodeHandle)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getIsClipNode(WireTapNodeHandle_Wrapper {lvalue},WireTapInt {lvalue})
- `getMetaData` — getMetaData( (WireTapNodeHandle)arg1, (str)arg2, (str)arg3, (int)arg4, (WireTapStr)arg5) -> bool :
  
      C++ signature :
          bool getMetaData(WireTapNodeHandle {lvalue},char const*,char const*,int,WireTapStr {lvalue})
  
  getMetaData( (WireTapNodeHandle)arg1, (str)arg2, (str)arg3, (int)arg4, (WireTapStr)arg5) -> bool :
- `getNodeId` — getNodeId( (WireTapNodeHandle)arg1) -> WireTapNodeId :
  
      C++ signature :
          WireTapNodeId {lvalue} getNodeId(WireTapNodeHandle {lvalue})
- `getNodeType` — getNodeType( (WireTapNodeHandle)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getNodeType(WireTapNodeHandle_Wrapper {lvalue},WireTapInt {lvalue})
- `getNodeTypeStr` — getNodeTypeStr( (WireTapNodeHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getNodeTypeStr(WireTapNodeHandle {lvalue},WireTapStr {lvalue})
- `getNumAvailableMetaDataStreams` — getNumAvailableMetaDataStreams( (WireTapNodeHandle)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getNumAvailableMetaDataStreams(WireTapNodeHandle_Wrapper {lvalue},WireTapInt {lvalue})
- `getNumChildren` — getNumChildren( (WireTapNodeHandle)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getNumChildren(WireTapNodeHandle_Wrapper {lvalue},WireTapInt {lvalue})
- `getNumFrames` — getNumFrames( (WireTapNodeHandle)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getNumFrames(WireTapNodeHandle_Wrapper {lvalue},WireTapInt {lvalue})
- `getParentNode` — getParentNode( (WireTapNodeHandle)arg1, (WireTapNodeHandle)arg2) -> bool :
  
      C++ signature :
          bool getParentNode(WireTapNodeHandle {lvalue},WireTapNodeHandle {lvalue})
- `getServer` — getServer( (WireTapNodeHandle)arg1) -> WireTapServerHandle :
  
      C++ signature :
          WireTapServerHandle getServer(WireTapNodeHandle {lvalue})
- `getStreamId` — getStreamId( (WireTapNodeHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getStreamId(WireTapNodeHandle {lvalue},WireTapStr {lvalue})
- `lastError` — lastError( (WireTapNodeHandle)arg1) -> str :
  
      C++ signature :
          char const* lastError(WireTapNodeHandle {lvalue})
- `linkToFrames` — linkToFrames( (WireTapNodeHandle)arg1, (list)arg2) -> bool :
  
      C++ signature :
          bool linkToFrames(WireTapNodeHandle_Wrapper {lvalue},boost::python::list)
- `readFrame` — readFrame( (WireTapNodeHandle)arg1, (int)arg2, (str)arg3, (int)arg4, (str)arg5, (int)arg6) -> bool :
  
      C++ signature :
          bool readFrame(WireTapNodeHandle_Wrapper {lvalue},int,char*,int,char*,int)
  
  readFrame( (WireTapNodeHandle)arg1, (int)arg2, (str)arg3, (int)arg4) -> bool :
- `renameNode` — renameNode( (WireTapNodeHandle)arg1, (str)arg2) -> bool :
  
      C++ signature :
          bool renameNode(WireTapNodeHandle {lvalue},char const*)
- `setMetaData` — setMetaData( (WireTapNodeHandle)arg1, (str)arg2, (str)arg3) -> bool :
  
      C++ signature :
          bool setMetaData(WireTapNodeHandle {lvalue},char const*,char const*)
- `setNodeId` — setNodeId( (WireTapNodeHandle)arg1, (WireTapNodeId)arg2) -> None :
  
      C++ signature :
          void setNodeId(WireTapNodeHandle {lvalue},WireTapNodeId)
- `setNumFrames` — setNumFrames( (WireTapNodeHandle)arg1, (int)arg2) -> bool :
  
      C++ signature :
          bool setNumFrames(WireTapNodeHandle {lvalue},unsigned int)
- `setServer` — setServer( (WireTapNodeHandle)arg1, (WireTapServerHandle)arg2) -> None :
  
      C++ signature :
          void setServer(WireTapNodeHandle {lvalue},WireTapServerHandle)
- `writeFrame` — writeFrame( (WireTapNodeHandle)arg1, (int)arg2, (str)arg3, (int)arg4) -> bool :
  
      C++ signature :
          bool writeFrame(WireTapNodeHandle_Wrapper {lvalue},int,char const*,int)

## WireTapNodeId

Kind: class

### Methods

- `id` — id( (WireTapNodeId)arg1) -> str :
  
      C++ signature :
          char const* id(WireTapNodeId {lvalue})
- `setId` — setId( (WireTapNodeId)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setId(WireTapNodeId {lvalue},char const*)

## WireTapOS

Kind: class

### Methods

- `OS_TYPE_IRIX_STR` — OS_TYPE_IRIX_STR() -> str :
  
      C++ signature :
          char const* OS_TYPE_IRIX_STR()
- `OS_TYPE_LINUX_STR` — OS_TYPE_LINUX_STR() -> str :
  
      C++ signature :
          char const* OS_TYPE_LINUX_STR()
- `OS_TYPE_MACOSX_STR` — OS_TYPE_MACOSX_STR() -> str :
  
      C++ signature :
          char const* OS_TYPE_MACOSX_STR()
- `OS_TYPE_UNKNOWN_STR` — OS_TYPE_UNKNOWN_STR() -> str :
  
      C++ signature :
          char const* OS_TYPE_UNKNOWN_STR()
- `OS_TYPE_WINNT_STR` — OS_TYPE_WINNT_STR() -> str :
  
      C++ signature :
          char const* OS_TYPE_WINNT_STR()
- `OsType` — int([x]) -> integer
  int(x, base=10) -> integer
  
  Convert a number or string to an integer, or return 0 if no arguments
  are given.  If x is a number, return x.__int__().  For floating point
  numbers, this truncates towards zero.
- `OsTypeStr` — OsTypeStr( (OsType)arg1) -> str :
  
      C++ signature :
          char const* OsTypeStr(WireTapOS::OsType)
- `getHostName` — getHostName() -> WireTapStr :
  
      C++ signature :
          WireTapStr getHostName()
- `getOSType` — getOSType() -> OsType :
  
      C++ signature :
          WireTapOS::OsType getOSType()
- `getOSVersion` — getOSVersion() -> WireTapStr :
  
      C++ signature :
          WireTapStr getOSVersion()
- `strToOsType` — strToOsType( (str)arg1) -> OsType :
  
      C++ signature :
          WireTapOS::OsType strToOsType(char const*)

## WireTapServerHandle

Kind: class

### Methods

- `disconnect` — disconnect( (WireTapServerHandle)arg1) -> None :
  
      C++ signature :
          void disconnect(WireTapServerHandle {lvalue})
- `getDisplayName` — getDisplayName( (WireTapServerHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getDisplayName(WireTapServerHandle {lvalue},WireTapStr {lvalue})
- `getHostName` — getHostName( (WireTapServerHandle)arg1) -> str :
  
      C++ signature :
          char const* getHostName(WireTapServerHandle {lvalue})
- `getHostUUID` — getHostUUID( (WireTapServerHandle)arg1) -> str :
  
      C++ signature :
          char const* getHostUUID(WireTapServerHandle {lvalue})
- `getId` — getId( (WireTapServerHandle)arg1) -> WireTapServerId :
  
      C++ signature :
          WireTapServerId getId(WireTapServerHandle {lvalue})
- `getIdStr` — getIdStr( (WireTapServerHandle)arg1) -> str :
  
      C++ signature :
          char const* getIdStr(WireTapServerHandle {lvalue})
- `getInfo` — getInfo( (WireTapServerHandle)arg1, (WireTapServerInfo)arg2) -> bool :
  
      C++ signature :
          bool getInfo(WireTapServerHandle {lvalue},WireTapServerInfo {lvalue})
- `getProduct` — getProduct( (WireTapServerHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getProduct(WireTapServerHandle {lvalue},WireTapStr {lvalue})
- `getProtocolVersion` — getProtocolVersion( (WireTapServerHandle)arg1, (WireTapInt)arg2, (WireTapInt)arg3) -> bool :
  
      C++ signature :
          bool getProtocolVersion(WireTapServerHandle_Wrapper {lvalue},WireTapInt {lvalue},WireTapInt {lvalue})
- `getRootNode` — getRootNode( (WireTapServerHandle)arg1, (WireTapNodeHandle)arg2) -> bool :
  
      C++ signature :
          bool getRootNode(WireTapServerHandle {lvalue},WireTapNodeHandle {lvalue})
- `getStorageId` — getStorageId( (WireTapServerHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getStorageId(WireTapServerHandle {lvalue},WireTapStr {lvalue})
- `getVendor` — getVendor( (WireTapServerHandle)arg1, (WireTapStr)arg2) -> bool :
  
      C++ signature :
          bool getVendor(WireTapServerHandle {lvalue},WireTapStr {lvalue})
- `getVersion` — getVersion( (WireTapServerHandle)arg1, (WireTapInt)arg2, (WireTapInt)arg3) -> bool :
  
      C++ signature :
          bool getVersion(WireTapServerHandle_Wrapper {lvalue},WireTapInt {lvalue},WireTapInt {lvalue})
- `isConnected` — isConnected( (WireTapServerHandle)arg1) -> bool :
  
      C++ signature :
          bool isConnected(WireTapServerHandle {lvalue})
- `lastError` — lastError( (WireTapServerHandle)arg1) -> str :
  
      C++ signature :
          char const* lastError(WireTapServerHandle {lvalue})
- `ping` — ping( (WireTapServerHandle)arg1 [, (int)arg2]) -> bool :
  
      C++ signature :
          bool ping(WireTapServerHandle_Wrapper {lvalue} [,int])
- `pullStream` — pullStream( (WireTapServerHandle)arg1, (str)arg2, (str)arg3) -> bool :
  
      C++ signature :
          bool pullStream(WireTapServerHandle {lvalue},char const*,char const*)
- `pushStream` — pushStream( (WireTapServerHandle)arg1, (str)arg2, (str)arg3) -> bool :
  
      C++ signature :
          bool pushStream(WireTapServerHandle {lvalue},char const*,char const*)
- `readAhead` — readAhead( (WireTapServerHandle)arg1, (str)arg2, (int)arg3) -> bool :
  
      C++ signature :
          bool readAhead(WireTapServerHandle_Wrapper {lvalue},char const*,int)
- `readFrame` — readFrame( (WireTapServerHandle)arg1, (str)arg2, (str)arg3, (int)arg4) -> bool :
  
      C++ signature :
          bool readFrame(WireTapServerHandle_Wrapper {lvalue},char const*,char*,int)
- `readStream` — readStream( (WireTapServerHandle)arg1, (str)arg2, (str)arg3, (int)arg4, (int)arg5, (int)arg6, (WireTapInt)arg7) -> bool :
  
      C++ signature :
          bool readStream(WireTapServerHandle_Wrapper {lvalue},char const*,char*,unsigned long,unsigned long,unsigned long,WireTapInt {lvalue})
- `stop` — stop( (WireTapServerHandle)arg1, (str)arg2) -> None :
  
      C++ signature :
          void stop(WireTapServerHandle {lvalue},char const*)
- `translatePath` — translatePath( (WireTapServerHandle)arg1, (WireTapStr)arg2, (WireTapStr)arg3, (str)arg4, (str)arg5, (OsType)arg6, (OsType)arg7) -> bool :
  
      C++ signature :
          bool translatePath(WireTapServerHandle {lvalue},WireTapStr,WireTapStr {lvalue},char const*,char const*,WireTapOS::OsType,WireTapOS::OsType)
- `translatePaths` — translatePaths( (WireTapServerHandle)arg1, (WireTapStrList)arg2, (WireTapStrList)arg3, (str)arg4, (str)arg5, (OsType)arg6, (OsType)arg7) -> bool :
  
      C++ signature :
          bool translatePaths(WireTapServerHandle {lvalue},WireTapStrList,WireTapStrList {lvalue},char const*,char const*,WireTapOS::OsType,WireTapOS::OsType)
- `writeFrame` — writeFrame( (WireTapServerHandle)arg1, (str)arg2, (str)arg3, (int)arg4) -> bool :
  
      C++ signature :
          bool writeFrame(WireTapServerHandle_Wrapper {lvalue},char const*,char const*,int)

## WireTapServerId

Kind: class

### Methods

- `getDB` — getDB( (WireTapServerId)arg1) -> str :
  
      C++ signature :
          char const* getDB(WireTapServerId {lvalue})
- `getIPAddr` — getIPAddr( (WireTapServerId)arg1) -> str :
  
      C++ signature :
          char const* getIPAddr(WireTapServerId {lvalue})
  
  getIPAddr( (WireTapServerId)arg1) -> str :
- `getId` — getId( (WireTapServerId)arg1) -> str :
  
      C++ signature :
          char const* getId(WireTapServerId {lvalue})
- `getPort` — getPort( (WireTapServerId)arg1) -> int :
  
      C++ signature :
          int getPort(WireTapServerId {lvalue})
- `getStorageId` — getStorageId( (WireTapServerId)arg1) -> str :
  
      C++ signature :
          char const* getStorageId(WireTapServerId {lvalue})
- `isValid` — isValid( (WireTapServerId)arg1) -> bool :
  
      C++ signature :
          bool isValid(WireTapServerId {lvalue})
- `setIPAddr` — setIPAddr( (WireTapServerId)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setIPAddr(WireTapServerId {lvalue},char const*)
- `setId` — setId( (WireTapServerId)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setId(WireTapServerId {lvalue},char const*)
- `setPort` — setPort( (WireTapServerId)arg1, (int)arg2) -> None :
  
      C++ signature :
          void setPort(WireTapServerId {lvalue},int)
- `setStorageId` — setStorageId( (WireTapServerId)arg1, (str)arg2) -> None :
  
      C++ signature :
          void setStorageId(WireTapServerId {lvalue},char const*)

## WireTapServerInfo

Kind: class

### Methods

- `getDisplayName` — getDisplayName( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getDisplayName(WireTapServerInfo {lvalue})
- `getHostname` — getHostname( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getHostname(WireTapServerInfo {lvalue})
- `getId` — getId( (WireTapServerInfo)arg1) -> WireTapServerId :
  
      C++ signature :
          WireTapServerId getId(WireTapServerInfo {lvalue})
- `getProduct` — getProduct( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getProduct(WireTapServerInfo {lvalue})
- `getProductBuild` — getProductBuild( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getProductBuild(WireTapServerInfo {lvalue})
- `getProductVersionMaint` — getProductVersionMaint( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getProductVersionMaint(WireTapServerInfo {lvalue})
- `getProductVersionMajor` — getProductVersionMajor( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getProductVersionMajor(WireTapServerInfo {lvalue})
- `getProductVersionMinor` — getProductVersionMinor( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getProductVersionMinor(WireTapServerInfo {lvalue})
- `getProductVersionStr` — getProductVersionStr( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getProductVersionStr(WireTapServerInfo {lvalue})
- `getStorageId` — getStorageId( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getStorageId(WireTapServerInfo {lvalue})
- `getVendor` — getVendor( (WireTapServerInfo)arg1) -> str :
  
      C++ signature :
          char const* getVendor(WireTapServerInfo {lvalue})
- `getVersionMaint` — getVersionMaint( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getVersionMaint(WireTapServerInfo {lvalue})
- `getVersionMajor` — getVersionMajor( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getVersionMajor(WireTapServerInfo {lvalue})
- `getVersionMinor` — getVersionMinor( (WireTapServerInfo)arg1) -> int :
  
      C++ signature :
          int getVersionMinor(WireTapServerInfo {lvalue})

## WireTapServerList

Kind: class

### Methods

- `getNode` — getNode( (WireTapServerList)arg1, (int)arg2, (WireTapServerInfo)arg3) -> bool :
  
      C++ signature :
          bool getNode(WireTapServerList_Wrapper {lvalue},int,WireTapServerInfo {lvalue})
- `getNumNodes` — getNumNodes( (WireTapServerList)arg1, (WireTapInt)arg2) -> bool :
  
      C++ signature :
          bool getNumNodes(WireTapServerList_Wrapper {lvalue},WireTapInt {lvalue})
- `lastError` — lastError( (WireTapServerList)arg1) -> str :
  
      C++ signature :
          char const* lastError(WireTapServerList_Wrapper {lvalue})
- `resolve` — resolve( (WireTapServerList)arg1, (WireTapServerId)arg2, (WireTapServerInfo)arg3) -> bool :
  
      C++ signature :
          bool resolve(WireTapServerList_Wrapper {lvalue},WireTapServerId,WireTapServerInfo {lvalue})
- `resolveStorageId` — resolveStorageId( (WireTapServerList)arg1, (str)arg2, (WireTapServerId)arg3) -> bool :
  
      C++ signature :
          bool resolveStorageId(WireTapServerList_Wrapper {lvalue},char const*,WireTapServerId {lvalue})

## WireTapServerList_Base

Kind: class

### Methods

- `getNode` — getNode( (WireTapServerList_Base)arg1, (int)arg2, (WireTapServerInfo)arg3) -> bool :
  
      C++ signature :
          bool getNode(WireTapServerList {lvalue},int,WireTapServerInfo {lvalue})
- `getNumNodes` — getNumNodes( (WireTapServerList_Base)arg1, (int)arg2) -> bool :
  
      C++ signature :
          bool getNumNodes(WireTapServerList {lvalue},int {lvalue})
- `lastError` — lastError( (WireTapServerList_Base)arg1) -> str :
  
      C++ signature :
          char const* lastError(WireTapServerList {lvalue})
- `resolve` — resolve( (WireTapServerList_Base)arg1, (WireTapServerId)arg2, (WireTapServerInfo)arg3) -> bool :
  
      C++ signature :
          bool resolve(WireTapServerList {lvalue},WireTapServerId,WireTapServerInfo {lvalue})
- `resolveStorageId` — resolveStorageId( (WireTapServerList_Base)arg1, (str)arg2, (WireTapServerId)arg3) -> bool :
  
      C++ signature :
          bool resolveStorageId(WireTapServerList {lvalue},char const*,WireTapServerId {lvalue})

## WireTapStr

Kind: class

### Methods

- `c_str` — c_str( (WireTapStr)arg1) -> str :
  
      C++ signature :
          char const* c_str(WireTapStr {lvalue})
- `length` — length( (WireTapStr)arg1) -> int :
  
      C++ signature :
          unsigned int length(WireTapStr {lvalue})
- `reset` — reset( (WireTapStr)arg1) -> None :
  
      C++ signature :
          void reset(WireTapStr {lvalue})

## WireTapStrList

Kind: class

### Methods

- `getStr` — getStr( (WireTapStrList)arg1, (int)arg2) -> str :
  
      C++ signature :
          char const* getStr(WireTapStrList {lvalue},unsigned int)
- `push_back` — push_back( (WireTapStrList)arg1, (str)arg2) -> None :
  
      C++ signature :
          void push_back(WireTapStrList {lvalue},char const*)
- `reserve` — reserve( (WireTapStrList)arg1, (int)arg2) -> None :
  
      C++ signature :
          void reserve(WireTapStrList {lvalue},int)
- `resize` — resize( (WireTapStrList)arg1, (int)arg2) -> None :
  
      C++ signature :
          void resize(WireTapStrList {lvalue},int)
- `size` — size( (WireTapStrList)arg1) -> int :
  
      C++ signature :
          unsigned int size(WireTapStrList {lvalue})

## WireTapClientInit

Kind: function

```
WireTapClientInit() -> bool :

    C++ signature :
        bool WireTapClientInit()
```

## WireTapClientUninit

Kind: function

```
WireTapClientUninit() -> None :

    C++ signature :
        void WireTapClientUninit()
```

## WireTapFindChild

Kind: function

```
WireTapFindChild( (WireTapNodeHandle)arg1, (str)arg2, (WireTapNodeHandle)arg3) -> bool :

    C++ signature :
        bool WireTapFindChild(WireTapNodeHandle,char const*,WireTapNodeHandle {lvalue})
```

## WireTapResolveDisplayPath

Kind: function

```
WireTapResolveDisplayPath( (WireTapServerHandle)arg1, (str)arg2, (WireTapNodeHandle)arg3) -> bool :

    C++ signature :
        bool WireTapResolveDisplayPath(WireTapServerHandle,char const*,WireTapNodeHandle {lvalue})
```

## WireTapSetDefaultCallTimeoutMS

Kind: function

```
WireTapSetDefaultCallTimeoutMS( (int)arg1) -> int :

    C++ signature :
        unsigned int WireTapSetDefaultCallTimeoutMS(unsigned int)
```
