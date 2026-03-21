import os
import pathlib
import re
import shutil
import json

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

# Cookie handling: inside Docker use a mounted cookies file,
# on the host use Chrome cookies directly.
_COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "/app/cookies.txt")

def _yt_dlp_opts(**extra):
    """Base yt-dlp options. Cookies are optional — yt-dlp works without them
    by using alternative YouTube clients (Android VR) that bypass n-challenge."""
    opts = {"quiet": True, "no_warnings": True}
    if pathlib.Path(_COOKIES_FILE).exists():
        opts["cookiefile"] = _COOKIES_FILE
    opts.update(extra)
    return opts


def create_folder(folder_name):
    """creates folder (and parents) if it does not exist -- relative path"""
    print(f"creating path: {folder_name}")
    pathlib.Path(folder_name).mkdir(parents=True, exist_ok=True)
    return True

def delete_folder(folder_name, ignore_error=True):
    """deletes <folder_name> and all its content"""
    print(f"removing path: {folder_name}")
    shutil.rmtree(folder_name, ignore_errors=ignore_error)
    return True

def _extract_video_id(url):
    """Extract the 11-char video ID from a YouTube URL."""
    m = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", url)
    if not m:
        raise ValueError(f"Cannot extract video ID from URL: {url}")
    return m.group(1)

def get_video_info(url):
    """returns video_id, video_title"""
    with yt_dlp.YoutubeDL(_yt_dlp_opts(skip_download=True)) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
    return info["id"], info["title"]

def download_video(url, destination_folder, filename=None):
    """downloads YouTube Video (mp4) from URL, skipping if file already exists.
    If *filename* is given it is used as the stem; otherwise the YouTube title
    is used with colons and pipes stripped."""
    vid_id, title = get_video_info(url)
    safe_title = filename or re.sub(r'[:|]', '', title).strip()
    save_path = pathlib.Path(destination_folder) / (safe_title + ".mp4")
    if save_path.exists():
        print(f"Skipping (already exists): {title}")
        return str(save_path)
    print(f"Downloading: {title}...", end=" ", flush=True)
    ydl_opts = _yt_dlp_opts(
        format="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        merge_output_format="mp4",
        outtmpl=str(pathlib.Path(destination_folder) / (safe_title + ".%(ext)s")),
    )
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print("Success!")
    return str(save_path)

def download_caption(url, destination_folder, filename=None):
    """download english captions to <filename.txt> in destination_folder, skipping if file already exists.
    If *filename* is given it is used as the stem; otherwise the YouTube title
    is used with colons and pipes stripped."""
    video_id, title = get_video_info(url)
    safe_title = filename or re.sub(r'[:|]', '', title).strip()
    save_path = pathlib.Path(destination_folder) / (safe_title + ".txt")
    if save_path.exists():
        print(f"Skipping captions (already exists): {title}")
        return str(save_path)
    print(f"Downloading captions for {title}... ", end=" ", flush=True)
    api = YouTubeTranscriptApi()
    caption = api.fetch(video_id).to_raw_data()
    with open(save_path, 'w') as outfile:
        for segment in caption:
            outfile.write(json.dumps(segment) + "\n")
    print("Success!")
    return str(save_path)

if __name__ == '__main__':
    vid_urls = ["https://www.youtube.com/watch?v=G3Eup4mfJdA&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=1",
                "https://www.youtube.com/watch?v=480OGItLZNo&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=2",
                "https://www.youtube.com/watch?v=OA2Tj75T3fI&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=4",
                "https://www.youtube.com/watch?v=qrvK_KuIeJk&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=5",
                "https://www.youtube.com/watch?v=oFVuQ0RP_As&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=6",
                "https://www.youtube.com/watch?v=4aPp8KX6EiU&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=7",
                "https://www.youtube.com/watch?v=h8PSWeRLGXs&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=8",
                "https://www.youtube.com/watch?v=Z8qC2tVkGeU&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=9",
                "https://www.youtube.com/watch?v=Y9nM_9oBj2k&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=10",
                "https://www.youtube.com/watch?v=ervLwxz7xPo&list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL&index=11"]

    # make a directory and download 10 videos into it
    video_folder = "./raw_videos"
    captions_folder = "./raw_captions"

    delete_folder(video_folder)
    delete_folder(captions_folder)
    create_folder(video_folder)
    create_folder(captions_folder)

    for url in vid_urls:
        download_video(url, video_folder)
        download_caption(url, captions_folder)
