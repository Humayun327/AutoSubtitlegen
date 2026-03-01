# Auto Subtitle Generator

A Python-based GUI application that automatically generates SRT subtitle files from video or audio files. It transcribes speech using Google Speech Recognition and translates the text into a target language using Google Translate, with an optional manual editing step.

## Features

- Supports various audio/video formats via FFmpeg (e.g., MP3, WAV, MP4, AVI, MKV)
- Choose source language (spoken language) and target language for translation
- Parallel processing for faster transcription
- User-friendly GUI built with tkinter
- Manual review and editing of each subtitle chunk (with "Yes All" option to skip further edits)
- Progress feedback and logging

## Requirements

- Python 3.6+
- FFmpeg installed and accessible in your system PATH (required for audio conversion)
- Internet connection for speech recognition and translation

## Installation

1. Clone or download this repository.
2. Install the required Python packages:

```bash
pip install -r requirements.txt 


## if you don't have a requirements.txt, create one with the following content or install directly:

speechrecognition
pydub
deep-translator


## Install directly:

pip install speechrecognition pydub deep-translator




3.  Ensure FFmpeg is installed:

        Windows: Download from ffmpeg.org and add to PATH.

        macOS: brew install ffmpeg

        Linux: sudo apt install ffmpeg (or equivalent)




Usage:
 
    1: Run the application:

    python subtitle_generator.py


    2: In the GUI:

    Click "Browse" to select your video/audio file.

    Choose the source language (the language spoken in the media).

    Choose the target language (the language you want subtitles in).

    Click "Generate Subtitles".


    3: The process runs in two phases:

    Phase 1: Transcription of 5-second chunks (parallel).

    Phase 2: For each chunk, a popup window appears allowing you to review and edit the transcribed text and its translation. Click "Yes" to accept and continue, or "Yes All" to apply the same decision to all remaining chunks (using automatic translation).


    4: The final SRT file is saved in the same directory as the input file, with the target language appended (e.g., myvideo_English.srt).




Notes:

    The application uses Google's free services, which have usage limits and may not be suitable for very long files.

    The 5-second chunk size is fixed; you can modify it in the code if needed.

    If you experience errors, check that FFmpeg is properly installed and that your internet connection is active.

    Transcription errors may occur; the manual review step helps correct them.
    
    
    'Note:' 
          
          It supports 12 languages, if someone buys this software, they can upgrade.
