"""Reproduce imports in the approved order, using verified accessible sources."""
from dataset_io import DATA,download,extract_zip,extract_tar
from import_datasets import gtzan,guitarset,pop909,ANNOTATION_REV

def main():
    download('https://www.kaggle.com/api/v1/datasets/download/carlthome/gtzan-genre-collection',DATA/'downloads/gtzan-kaggle-original-au.zip','sha256:4bf23f68dcd77f46f6530c64710a5a9dee08fa6be4c17ef8b15e6bb31026402b',1225975597)
    download('https://api.github.com/repos/CPJKU/beat_this_annotations/zipball/'+ANNOTATION_REV,DATA/'downloads/beat-this-annotations-v1.1.zip','sha256:16dc6feebee0efb9e7d3ad15cb81d93d8c7ad18bae606877914d82d1aba8de95',7354873)
    gtzan()
    download('https://zenodo.org/api/records/3371780/files/audio_mono-mic.zip/content',DATA/'downloads/guitarset-mic.zip','md5:275966d6610ac34999b58426beb119c3',656927981)
    download('https://zenodo.org/api/records/3371780/files/annotation.zip/content',DATA/'downloads/guitarset-annotation.zip','md5:b39b78e63d3446f2e54ddb7a54df9b10',39132574)
    guitarset()
    download('https://raw.githubusercontent.com/AndyWeasley2004/POP909-CL-Dataset/0e06063995ef237585c2ad48336cfae1b960beae/POP909_processed.zip',
             DATA/'downloads/pop909-processed.zip','sha256:d18882cb5f4a633fe607bcb69c76c47021032d74b9c3b143aa3d34b85269b4a7',4814351)
    pop909()
    download('https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.2/fluidsynth-v2.6.2-win10-x64-cpp11.zip',DATA/'downloads/fluidsynth-2.6.2.zip',size=2729665)
    download('https://deb.debian.org/debian/pool/main/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3.orig.tar.gz',DATA/'downloads/timgm6mb-1.3.tar.gz')
    extract_zip(DATA/'downloads/fluidsynth-2.6.2.zip',DATA/'renderer/fluidsynth')
    extract_tar(DATA/'downloads/timgm6mb-1.3.tar.gz',DATA/'renderer/soundfont')

if __name__=='__main__':main()
