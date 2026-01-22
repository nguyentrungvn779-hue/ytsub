from flask import Flask, render_template_string, request, send_file
from youtube_transcript_api import YouTubeTranscriptApi
from pytube import Channel
import csv
import io
import re

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Lấy Sub 100 Video YouTube</title>
  <style>
    body { font-family: Arial; background:#f5f5f5; }
    .box { width: 800px; margin: 50px auto; background:#fff; padding:30px; border-radius:10px; }
    input { width:100%; padding:12px; font-size:16px; }
    button { padding:12px 20px; font-size:16px; background:#e63946; color:#fff; border:none; cursor:pointer; margin-top:15px; }
    table { width:100%; border-collapse: collapse; margin-top:30px; }
    th, td { border:1px solid #ddd; padding:8px; text-align:left; }
    th { background:#f1f1f1; }
    .download { margin-top:20px; display:inline-block; background:#1d3557; color:#fff; padding:10px 15px; text-decoration:none; }
    .note { color:#555; margin-top:10px; }
  </style>
</head>
<body>
  <div class="box">
    <h1>Lấy Sub 100 Video YouTube</h1>

    <form method="post">
      <input name="channel_url" placeholder="Dán link kênh YouTube vào đây" required>
      <button type="submit">Lấy Sub 100 Video</button>
    </form>

    {% if results %}
      <h2>Kết quả</h2>
      <table>
        <tr>
          <th>#</th>
          <th>Video ID</th>
          <th>Transcript</th>
        </tr>
        {% for r in results %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ r.video_id }}</td>
          <td>{{ r.text[:300] }}{% if r.text|length > 300 %}...{% endif %}</td>
        </tr>
        {% endfor %}
      </table>

      <a class="download" href="/download">⬇ Download CSV</a>
    {% endif %}

    <p class="note">Chỉ lấy được video có transcript (phụ đề) công khai</p>
  </div>
</body>
</html>
"""

DATA_CACHE = []

def extract_video_id(url):
    match = re.search(r"v=([^&]+)", url)
    return match.group(1) if match else None

@app.route("/", methods=["GET", "POST"])
def index():
    global DATA_CACHE
    results = []

    if request.method == "POST":
        DATA_CACHE = []
        channel_url = request.form.get("channel_url")

        channel = Channel(channel_url)
        videos = list(channel.video_urls)[:100]

        for url in videos:
            video_id = extract_video_id(url)
            if not video_id:
                continue
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["vi", "en"])
                text = " ".join([x["text"] for x in transcript])
                row = {"video_id": video_id, "text": text}
                results.append(row)
                DATA_CACHE.append(row)
            except:
                continue

    return render_template_string(HTML, results=results)

@app.route("/download")
def download():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["video_id", "transcript"])

    for r in DATA_CACHE:
        writer.writerow([r["video_id"], r["text"]])

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="youtube_transcripts.csv"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
