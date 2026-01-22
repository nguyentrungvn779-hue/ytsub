from flask import Flask, render_template, request, send_file
import yt_dlp
import csv
import uuid
import os
import shutil
import re

import webvtt  # pip install webvtt-py

app = Flask(__name__)

# -----------------------------
# LẤY 100 VIDEO GẦN NHẤT TỪ KÊNH
# -----------------------------
def get_latest_video_ids(channel_url: str, limit: int = 100) -> list[str]:
    url = channel_url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    # Ưu tiên /videos để giảm dính Shorts
    if "youtube.com/" in url and "/videos" not in url and "/watch" not in url:
        url = url.rstrip("/") + "/videos"

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries") or []
    video_ids = []

    for e in entries:
        vid = e.get("id")
        duration = e.get("duration")

        # BỎ SHORTS nếu có duration < 60 giây
        if duration is not None and duration < 60:
            continue

        if vid:
            video_ids.append(vid)

        if len(video_ids) >= limit:
            break

    return video_ids


# -----------------------------
# ĐỌC SUBTITLE TỪ FILE .VTT -> TEXT
# -----------------------------
def vtt_to_text(vtt_path: str) -> str:
    texts = []
    for caption in webvtt.read(vtt_path):
        t = caption.text.strip()
        if t:
            texts.append(t)

    # làm sạch bớt ký tự lặp
    raw = " ".join(texts)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


# -----------------------------
# LẤY SUB CHO 1 VIDEO BẰNG yt-dlp
# Ưu tiên: VI manual -> EN manual -> VI auto -> EN auto
# -----------------------------
def fetch_subtitle_text(video_id: str, workdir: str):
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # yt-dlp sẽ tải sub về workdir
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,        # sub người upload
        "writeautomaticsub": True,     # sub auto
        "subtitlesformat": "vtt",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "nocheckcertificate": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # download() để nó thật sự ghi file sub ra ổ
            ydl.download([video_url])
    except Exception as e:
        return ("KHÔNG CÓ SUB", f"YTDLP_ERROR_{type(e).__name__}", "")

    # Sau khi tải xong, tìm file vtt theo thứ tự ưu tiên
    # Một số file sẽ có dạng: <id>.vi.vtt, <id>.en.vtt, <id>.vi-orig.vtt, <id>.en-orig.vtt...
    candidates = [
        f"{video_id}.vi.vtt",
        f"{video_id}.vi-orig.vtt",
        f"{video_id}.en.vtt",
        f"{video_id}.en-orig.vtt",
    ]

    # auto-captions đôi khi ra dạng: <id>.vi.vtt nhưng nội dung là auto,
    # nên mình ghi reason theo file tìm được là đủ để anh kiểm tra.
    for name in candidates:
        path = os.path.join(workdir, name)
        if os.path.exists(path):
            text = vtt_to_text(path)
            if text:
                return ("CÓ SUB", f"FOUND_{name}", text)
            else:
                return ("KHÔNG CÓ SUB", f"EMPTY_{name}", "")

    # Nếu không thấy trong candidates, quét hết file vtt trong folder
    all_vtt = [f for f in os.listdir(workdir) if f.endswith(".vtt") and f.startswith(video_id)]
    if all_vtt:
        # lấy cái đầu tiên cho chắc
        path = os.path.join(workdir, all_vtt[0])
        text = vtt_to_text(path)
        if text:
            return ("CÓ SUB", f"FOUND_{all_vtt[0]}", text)
        return ("KHÔNG CÓ SUB", f"EMPTY_{all_vtt[0]}", "")

    return ("KHÔNG CÓ SUB", "NO_VTT_FILE", "")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        channel_url = request.form.get("channel_url", "").strip()

        # Tạo thư mục tạm để chứa subtitle
        job_id = str(uuid.uuid4())
        tmp_dir = f"tmp_{job_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        csv_name = f"subs_{job_id}.csv"

        try:
            video_ids = get_latest_video_ids(channel_url, limit=100)
            if not video_ids:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return "<h3>Không lấy được video từ kênh này. Anh thử link kênh khác.</h3>"
        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return f"<h3>Lỗi khi lấy danh sách video:</h3><pre>{str(e)}</pre>"

        results = []
        for idx, video_id in enumerate(video_ids, start=1):
            print(f"Đang xử lý {idx}/{len(video_ids)}: {video_id}")
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            status, reason, text = fetch_subtitle_text(video_id, tmp_dir)
            results.append([video_url, status, reason, text])

        with open(csv_name, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Video URL", "Status", "Reason", "Transcript"])
            writer.writerows(results)

        # dọn thư mục tạm
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return send_file(csv_name, as_attachment=True)

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
