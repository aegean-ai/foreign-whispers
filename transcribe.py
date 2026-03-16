from typing import Literal
import pathlib
import glob
from pprint import pprint
import json

import whisper

def load_model(model_name: Literal["tiny", "base", "small", "medium", "large"] = "tiny"):
    print(f"Downloading Whisper Model: {model_name}")
    model = whisper.load_model(model_name)
    return model

def transcribe_videos(video_directory: str, model, destination_folder: str):
    if (not pathlib.Path(video_directory).exists() 
        or not pathlib.Path(destination_folder).exists()):
        raise ValueError("video or destination folder do not exist")
    
    files = glob.glob(video_directory + "/*.mp4")
    if not files:
        raise ValueError("No mp4 files found in given directory")
    
    for file_path in files:
        file = pathlib.Path(file_path)
        print(f"Transcribing {file.name}...", end=" ", flush=True)
        try:
            transcript = model.transcribe(file_path)
        except Exception as e:
            print(e)
            raise
        else:
            print("Success!")
            # print(transcript["text"])
            save_path = pathlib.Path(destination_folder) / (str(file.stem) + ".json")
            print(f"saving result to {save_path}")
            with open(save_path, 'w') as output_file:
                json.dump(transcript, output_file)
    return None


if __name__ == '__main__':
    video_folder = "./videos"
    destination_folder = "./transcriptions_en"
    pathlib.Path(destination_folder).mkdir(parents=True, exist_ok=True)
    model = load_model("tiny")
    transcribe_videos(video_folder, model, destination_folder)
