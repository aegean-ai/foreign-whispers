import pathlib
import shutil
import json

from pytube import YouTube
from pytube.exceptions import AgeRestrictedError
from youtube_transcript_api import YouTubeTranscriptApi


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

def download_video(url, destination_folder):
    """downloads YouTube Video (mp4) from URL, skipping if file already exists"""
    video = YouTube(url)
    save_path = pathlib.Path(destination_folder) / (video.title + ".mp4")
    if save_path.exists():
        print(f"Skipping (already exists): {video.title}")
        return str(save_path)
    print(f"Downloading: {video.title}...", end=" ", flush=True)
    (video.streams.filter(progressive=True, file_extension='mp4')
     .order_by('resolution').desc().first().download(destination_folder))
    print("Success!")
    return str(save_path)

def get_video_info(url):
    """returns video_id, video_title"""
    video = YouTube(url)
    return video.video_id, video.title

def download_caption(url, destination_folder):
    """download english captions to <video_title.txt> in destination_folder, skipping if file already exists"""
    video_id, title = get_video_info(url)
    save_path = pathlib.Path(destination_folder) / (title + ".txt")
    if save_path.exists():
        print(f"Skipping captions (already exists): {title}")
        return str(save_path)
    print(f"Downloading captions for {title}... ", end=" ", flush=True)
    caption = YouTubeTranscriptApi.get_transcript(video_id)
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
