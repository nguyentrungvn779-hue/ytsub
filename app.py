# app.py
import os
import re
import io
import csv
import time
from typing import List, Dict, Optional, Tuple

from flask import Flask, render_template, request, jsonify, send_file

from pytube import Channel, YouTube
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    TooManyRequests,
)

app = Flask(__name__)

# -----------------------
# CONFIG
# -----------------------
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "100"))
DEFAULT_LANGS = ["vi", "en"]  # ưu tiên vi trước, không có thì lấy en
REQUEST_SLEEP = float(os.environ.get("REQUEST_SLEEP", "0.2"))  # giảm bị rate limit


# -----------------------
# HELPERS
# -----------------------
def extract_video_id(url: str) -> Optional[str]:
    """
    Hỗ trợ các dạng:
    - https://www.youtube.com/watch?v=VIDEOID
    - https://youtu.be/VIDEOID
    - https://www.youtube.com/shorts/VIDEOID
    """
    if not url:
        return None

    url = url.strip()

    # youtu.be/<id>
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", url)
    if m:
        return m.group(1)

    # watch?v=<id>
    m = re.search(r"v=([A-Za-z0-9_-]{6,})", url)
    if m:
        return m.group(1)

    # shorts/<id>
    m = re.search(r"/shorts/([A-Za-z0-9_-]{6,})", url)
    if m:
        return m.group(1)

    return None


def normalize_channel_url(channel_url: str) -> str:
    """
    Chấp nhận:
    - URL kênh dạng /@handle
    - /channel/<id>
    - /c/<name>
    - /user/<name>
    """
    if not channel_url:
        return ""
    return channel_url.strip()


def get_channel_video_urls(channel_url: str, limit: int = 100) -> List[str]:
    """
    Dùng pytube Channel để lấy danh sách video URL của kênh.
    Lưu ý: YouTube có thể thay đổi, một số kênh sẽ không lấy được.
    """
    ch = Channel(channel_url)
    urls = []
    for u in ch.video_urls:
        urls.append(u)
        if len(urls) >= limit:
            break
    return urls


def get_video_title_and_url(video_url: str) -> Tuple[str, str, str]:
    """
    Trả về (video_id, title, url)
    """
    vid = extract_video_id(video_url) or ""
    title = ""
    try:
        yt = YouTube(video_url)
        title = yt.title or ""
        # chuẩn hoá URL
        video_url = yt.watch_url or video_url
        vid = yt.video_id or vid
    except Exception:
        # nếu pytube fail vẫn trả cái đang có
        pass
    return vid, title, video_url


def transcript_to_text(transcript: List[Dict]) -> str:
    """
    transcript list -> gộp text thành 1 chuỗi
    """
    return " ".join([x.get("text", "").strip() for x in transcript if x.get("text")])


def fetch_transcript(video_id: str, langs: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Trả về (text, reason_if_fail)
    """
    try:
        # ưu tiên transcript theo langs
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        return transcript_to_text(transcript), None
    except TranscriptsDisabled:
        return None, "TRANSCRIPTS_DISABLED"
    except NoTranscriptFound:
        return None, "NO_TRANSCRIPT_FOUND"
    except VideoUnavailable:
        return None, "VIDEO_UNAVAILABLE"
    except TooManyRequests:
        return None, "TOO_MANY_REQUESTS"
    except Exception as e:
        return None, f"ERROR_{type(e).__name__}"


def safe_str(x) -> str:
    return (x or "").strip()


# -----------------------
# ROUTES
# -----------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/fetch", methods=["POST"])
def fetch():
    """
    Nhận channel_url và trả về JSON list:
    [
      {title, url, video_id, status, reason, transcript}
    ]
    """
    channel_url = safe_str(request.form.get("channel_url"))
    channel_url = normalize_channel_url(channel_url)

    if not channel_url:
        return jsonify({"error": "Vui lòng dán link kênh YouTube."}), 400

    results: List[Dict] = []
    try:
        video_urls = get_channel_video_urls(channel_url, limit=MAX_RESULTS)
        if not video_urls:
            return jsonify({"error": "Không lấy được danh sách video. Có thể link kênh sai hoặc YouTube chặn."}), 400

        for idx, vurl in enumerate(video_urls, start=1):
            time.sleep(REQUEST_SLEEP)

            video_id, title, final_url = get_video_title_and_url(vurl)
            if not video_id:
                results.append({
                    "title": title or f"Video {idx}",
                    "url": final_url,
                    "video_id": "",
                    "status": "KHÔNG CÓ SUB",
                    "reason": "INVALID_VIDEO_ID",
