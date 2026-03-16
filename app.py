import pathlib
import whisper

from download_video import (
    create_folder,
    delete_folder,
    download_video,
    download_caption,
    get_video_info,
)
from transcribe import load_model, transcribe_videos
from translate_en_to_es import download_and_install_package, translate_all_files
from tts_es import files_from_dir, text_file_to_speech
from translated_output import stitch_video_with_timestamps

import json
import streamlit as st
import pandas as pd

raw_video = "./ui/raw_video"
translated_videos = "./ui/translated_video"
raw_transcription = "./ui/raw_transcription"
translated_transcription = "./ui/translated_transcription"
raw_caption = "./ui/raw_caption"  # not used in final video
raw_transcription = "./ui/raw_transcription"
translated_transcription = "./ui/translated_transcription"
translated_audio = "./ui/translated_audio"
translated_video = "./ui/translated_video"


def video_cached(url) -> bool:
    vid_id, title = get_video_info(url)
    title2 = title.replace(":", "")
    vid_path = pathlib.Path(raw_video) / pathlib.Path(title2 + ".mp4")
    r_trans_path = pathlib.Path(raw_transcription) / pathlib.Path(title2 + ".json")
    t_trans_path = pathlib.Path(translated_transcription) / pathlib.Path(
        title2 + ".json"
    )
    vid = str(vid_path) if vid_path.exists() else False
    r_trans = str(r_trans_path) if r_trans_path.exists() else False
    t_trans = str(t_trans_path) if t_trans_path.exists() else False
    return vid, r_trans, t_trans


def translate_video(url):
    create_folder(raw_video)
    create_folder(raw_caption)
    create_folder(raw_transcription)
    create_folder(translated_transcription)
    create_folder(translated_audio)

    vid_id, title = get_video_info(url)

    download_video(url, raw_video)
    download_caption(url, raw_caption)

    model = load_model("tiny")

    transcribe_videos(raw_video, model, raw_transcription)

    from_code = "en"
    to_code = "es"
    download_and_install_package(from_code, to_code)
    translate_all_files(raw_transcription, translated_transcription)

    json_files = files_from_dir(translated_transcription)
    for file in json_files:
        text_file_to_speech(file, translated_audio)

    vid_path, raw_captions, translated_caption = video_cached(url)
    audio_path = pathlib.Path(translated_audio) / pathlib.Path(title + ".wav")
    output_path = translated_video
    stitch_video_with_timestamps(vid_path, translated_caption, audio_path, output_path)
    return True


st.header("Foreign Whispers")
st.write(
    "Given a yotube URL of a video in English, it would output a video to your language of choice"
)


url = st.text_input("YouTube URL")
vid_id, title = get_video_info(url)
st.write(title)

lang = st.selectbox("Target Lang", ["Spanish", "French"])
col1, col2, col3 = st.columns(3)

vid_cach, r_cach, t_cach = video_cached(url)

if col1.button("Translate Video"):
    if vid_cach and r_cach and t_cach:
        st.success("video translated!")
    else:
        st.info("translating video...")
        translate_video(url)
        st.success("video translated!")

if col2.button("View Video"):
    if vid_cach:
        video_file = open(vid_cach, "rb")
        video_bytes = video_file.read()
        st.video(video_bytes)
    else:
        st.write("video is not cached, translating...")

if col3.button("View Captions"):
    if r_cach and t_cach:
        with open(r_cach, "r") as file:
            raw = json.load(file)

        with open(t_cach, "r") as file:
            trans = json.load(file)

        # col1.header("Time Stamp")
        # col2.header("English")
        # col3.header(lang)

        segments = []
        seg_ids = [seg["id"] for seg in raw["segments"]]
        for seg_id in seg_ids:
            s1_start = round(raw["segments"][seg_id]["start"], 2)
            s1_end = round(raw["segments"][seg_id]["end"], 2)
            s1_text = raw["segments"][seg_id]["text"]

            s2_start = round(trans["segments"][seg_id]["start"], 2)
            s2_end = round(trans["segments"][seg_id]["end"], 2)
            s2_text = trans["segments"][seg_id]["text"]

            # with st.container():
            #     col1.write(f"{s1_start} : {s1_end} | {s2_start} : {s2_end} ")
            #     col2.write(s1_text)
            #     col3.write(s2_text)
            segments.append(
                {
                    "Time Stamp": f"{s1_start} : {s1_end}",
                    "English": s1_text,
                    lang: s2_text,
                }
            )

        df = pd.DataFrame(segments)
        st.table(df)

    else:
        st.warning("video has not been translated, press translate first")


# if __name__ == "__main__":
