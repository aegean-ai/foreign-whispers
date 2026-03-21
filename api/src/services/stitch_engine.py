### Algo 1 with the existing 
# Loop over each json element
# read the time stamp and slice the audio/.wav file at the time stamps
# attach the audio to the video 
# also the captions


### Algo 2
## Loop over each json element 
# Use TTS to conver the audiio
# Save the audio file in sequence
# Final func: Stitch the audio and captions
import os
import shutil

from moviepy.editor import VideoFileClip, TextClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip
import json
import pathlib
from moviepy.config import change_settings


def _imagemagick_binary() -> str | None:
    """Auto-detect the ImageMagick binary path."""
    # Prefer IMAGEMAGICK_BINARY env var if set
    env_path = os.environ.get("IMAGEMAGICK_BINARY")
    if env_path and os.path.isfile(env_path):
        return env_path
    # Fall back to PATH discovery
    for name in ("convert", "magick"):
        path = shutil.which(name)
        if path:
            return path
    return None


_im_bin = _imagemagick_binary()
if _im_bin:
    change_settings({"IMAGEMAGICK_BINARY": _im_bin})

# # make a directory to download videos into
# destination_folder = "./videos_out/no_audio"

# pathlib.Path(destination_folder).mkdir(parents=True, exist_ok=True)


# videoclip = VideoFileClip("video.mp4")
# videoclip = VideoFileClip("./videos/Deion Sanders The 2023 60 Minutes Interview.mp4")
# videoclip = VideoFileClip("videos/Pink The 60 Minutes Interview.mp4")
# videos/Attorney General Merrick Garland The 60 Minutes Interview.mp4
# project/AI-project/videos_en
# project/AI-project/videos_en/Pink The 60 Minutes Interview.mp4

# def extract_audio():
#     path = "/Users/banani/Documents/NYU/workpace/python_projects/Fall2023/Projects/AI/project/AI-project/videos_en"
#     video_clip = VideoFileClip(os.path.join(path, "Pink The 60 Minutes Interview.mp4"))
#     new_clip = video_clip.without_audio()
#     new_clip.write_videofile(os.path.join(destination_folder, "Pink The 60 Minutes Interview.mp4"))


def stitch_audio(video_path: str, audio_path: str, output_path: str):
    """Replace video audio track with the dubbed audio using ffmpeg remux.

    Uses -c:v copy to avoid re-encoding video frames — instant and lossless.
    """
    import subprocess

    print("Stitching audio (ffmpeg remux)...")
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",        # copy video stream without re-encoding
        "-map", "0:v:0",       # take video from first input
        "-map", "1:a:0",       # take audio from second input
        "-shortest",           # stop when shortest stream ends
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")
    print("Stitching done.")


# not needed as our converted foramat is already in seconds, but keeping this to generalise for any data
def parse_srt_time(srt_time):
    # Parse SRT time format (hh:mm:ss,ms) into seconds
    time_parts = srt_time.split(":")
    seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2].replace(",", "."))
    return seconds

def stitch_video_with_timestamps(video_path, caption_path, audio_path, output_path):
    # Load video, caption, and audio clips
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)

    # Load and parse subtitles from SRT file
    subtitles = []
    with open(caption_path, 'r') as caption_file:
        # lines = caption_file.readlines()
        # Read the json : for segments, 
        # Loop over each segment , read the :
        #  - start time
        #  - end time
        #  - the text
        # convert and append to the subtitles array to be used to create the text clips for the video in the next section
        print(caption_file)
        trans = json.load(caption_file)
        for segment in trans['segments']:
            start_seconds = segment['start']
            end_seconds = segment['end']
            text = segment['text'].strip()
            # print(f"{start_seconds}: {end_seconds} : {text}")
            subtitles.append((start_seconds, end_seconds, text))

    # Create TextClips for each subtitle
    text_clips = [TextClip(subtitle[2], fontsize=24, color='white', bg_color='black', font='DejaVu-Sans')
                  .set_pos(('center', 'bottom'))
                  .set_start(subtitle[0])
                  .set_end(subtitle[1])
                  for subtitle in subtitles]

    # Overlay each TextClip directly — they already have start/end/pos set
    video_with_subtitles = CompositeVideoClip([video_clip] + text_clips)

    # Create a composite audio clip with both video and additional audio
    final_audio_clip = CompositeAudioClip([video_with_subtitles.audio, audio_clip])

    # Set audio for the combined video
    video_with_audio = video_with_subtitles.set_audio(final_audio_clip)

    # Write the final video — try GPU encoding, fall back to CPU
    codec = "libx264"
    if os.environ.get("FW_USE_GPU_ENCODE"):
        import subprocess
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5
            )
            if "h264_nvenc" in result.stdout:
                codec = "h264_nvenc"
        except Exception:
            pass
    video_with_audio.write_videofile(output_path, codec=codec, audio_codec="aac")

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print("Usage: python translated_output.py <video> <caption_json> <audio> <output>")
        sys.exit(1)
    stitch_video_with_timestamps(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
