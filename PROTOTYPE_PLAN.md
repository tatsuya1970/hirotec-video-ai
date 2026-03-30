# 社内資料 → 動画教材 自動生成AI エディター
## 2日間プロトタイプ計画書

**対象課題:** ひろしまAIサンドボックス #3289（p.19）
**依頼企業:** 株式会社ヒロテック（自動車部品・設備製造業）
**課題URL:** https://hiroshima-ai-sandbox.jp/issue/list/?id=3289
**申込締切:** 2026年4月7日(火)

---

## 背景・課題

製造業における人材不足が深刻化する中、社内教育の重要性が増大している。
社内に散在するPDF・PowerPoint・マニュアル・工程写真などを担当者が組み合わせて教育を行っているが、
**体系だったストーリー性を持つ研修コンテンツへの昇華ができていない**のが実情。

### 求めるソリューション
- 社内ドキュメントをAIに読み込ませ、理解しやすい構成へ再編集
- **ナレーション付きの教育動画として自動生成**する仕組み
- 教育担当者の負担軽減 + 教育内容の標準化を同時実現
- 将来的には外販・展開も視野に

---

## 完成イメージ

```
[PDF / PPTX アップロード]
        ↓
[GPT-4o で教育スクリプト生成]
        ↓
[OpenAI TTS でナレーション音声化]
        ↓
[スライド画像 + 音声 → 動画に合成]
        ↓
[HeyGen アバター解説者を追加（オプション）]
        ↓
[MP4 動画ダウンロード]
```

---

## 技術スタック

| 役割 | ツール | 理由 |
|------|--------|------|
| UI | Streamlit | 1日で動くデモが作れる |
| 文書解析 | pdfplumber / python-pptx | PDF・PPTX両対応 |
| スクリプト生成 | OpenAI GPT-4o | 資料を教育動画の台本に再構成 |
| ナレーション | OpenAI TTS (tts-1-hd) | 日本語の自然な読み上げ |
| 動画合成 | MoviePy + FFmpeg | スライド+音声→MP4 |
| AIアバター（オプション） | HeyGen API | 解説者キャラクターを追加 |

### インストール

```bash
pip install streamlit pdfplumber python-pptx openai moviepy pillow
brew install ffmpeg  # macOS
```

---

## Day 1：基盤パイプライン構築

### AM（〜12:00）：環境構築 + 文書パーサー

```python
# document_parser.py
import pdfplumber
from pptx import Presentation

def parse_pdf(file_path):
    """PDFからテキストと画像を抽出"""
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            img = page.to_image(resolution=150).original
            pages.append({"page": i+1, "text": text, "image": img})
    return pages

def parse_pptx(file_path):
    """PPTXからスライドテキストを抽出"""
    prs = Presentation(file_path)
    slides = []
    for i, slide in enumerate(prs.slides):
        text = "\n".join([s.text for s in slide.shapes if s.has_text_frame])
        slides.append({"page": i+1, "text": text})
    return slides
```

### PM（13:00〜18:00）：GPT-4o スクリプト生成 + TTS 音声化

```python
# script_generator.py
from openai import OpenAI
import os

client = OpenAI()

def generate_script(pages: list[dict]) -> list[dict]:
    """各ページの内容を教育ナレーション台本に変換"""
    scripts = []
    for page in pages:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": """
あなたは製造業の社内教育動画のナレーター台本を書く専門家です。
以下のルールで台本を作成してください：
- 1スライドあたり30〜60秒で読める長さ
- 専門用語には補足説明を入れる
- 「まず」「次に」「ポイントは」など導入フレーズを使う
- 新入社員でも理解できる平易な日本語
"""},
                {"role": "user", "content": f"以下の資料内容をナレーション台本にしてください：\n\n{page['text']}"}
            ]
        )
        scripts.append({
            "page": page["page"],
            "image": page.get("image"),
            "narration": response.choices[0].message.content
        })
    return scripts

def generate_audio(text: str, output_path: str, voice: str = "shimmer"):
    """テキストをMP3音声に変換"""
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice,   # shimmer/nova/onyx
        input=text,
        speed=0.95
    )
    response.stream_to_file(output_path)
```

### 夕方（18:00〜21:00）：MoviePy で動画合成

```python
# video_builder.py
from moviepy.editor import *
from script_generator import generate_audio
import numpy as np

def build_video(scripts: list[dict], output_path: str, voice: str = "shimmer"):
    """スライド画像 + ナレーション音声 → MP4"""
    clips = []

    for i, s in enumerate(scripts):
        audio_path = f"/tmp/audio_{i}.mp3"
        generate_audio(s["narration"], audio_path, voice)
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration

        # スライド画像をビデオクリップに
        if s.get("image"):
            img_array = np.array(s["image"].resize((1280, 720)))
            img_clip = ImageClip(img_array, duration=duration)
        else:
            img_clip = ColorClip(size=(1280, 720), color=[30, 30, 30], duration=duration)

        # テロップ（ナレーションの最初の1文）
        caption = s["narration"].split("。")[0] + "。"
        txt_clip = (TextClip(caption, fontsize=28, color="white",
                             bg_color="rgba(0,0,0,0.6)", font="Noto-Sans-CJK-JP",
                             size=(1200, None), method="caption")
                   .set_position(("center", "bottom"))
                   .set_duration(duration))

        clip = CompositeVideoClip([img_clip, txt_clip]).set_audio(audio_clip)
        clips.append(clip)

    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(output_path, fps=24, codec="libx264")
    return output_path
```

---

## Day 2：UI + 品質向上 + デモ準備

### AM（〜12:00）：Streamlit UI

```python
# app.py
import streamlit as st
import tempfile, os
from document_parser import parse_pdf, parse_pptx
from script_generator import generate_script
from video_builder import build_video

st.set_page_config(page_title="社内資料 → 動画教材 AI", layout="wide")
st.title("📹 社内資料 → 動画教材 自動生成AI")
st.caption("PDFまたはPowerPointをアップロードするだけで、ナレーション付き教育動画を自動生成します")

uploaded = st.file_uploader("資料をアップロード", type=["pdf", "pptx"])

voice_map = {
    "shimmer（女性・落ち着き）": "shimmer",
    "nova（女性・明快）": "nova",
    "onyx（男性・低め）": "onyx"
}
voice_label = st.selectbox("ナレーター音声", list(voice_map.keys()))
voice = voice_map[voice_label]

if uploaded and st.button("🎬 動画を生成する"):
    with st.spinner("資料を解析中..."):
        suffix = os.path.splitext(uploaded.name)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(uploaded.read())
            tmp_path = f.name

        pages = parse_pdf(tmp_path) if suffix == ".pdf" else parse_pptx(tmp_path)

    st.success(f"✅ {len(pages)}ページを検出")

    with st.spinner("GPT-4oで台本を生成中..."):
        scripts = generate_script(pages)

    with st.expander("📝 生成された台本を確認・編集"):
        for s in scripts:
            st.markdown(f"**スライド {s['page']}**")
            st.text_area("台本", s["narration"], key=f"script_{s['page']}", height=120)
            st.divider()

    with st.spinner("動画を生成中（数分かかります）..."):
        output_path = "/tmp/output_training.mp4"
        build_video(scripts, output_path, voice)

    st.video(output_path)
    with open(output_path, "rb") as f:
        st.download_button("⬇️ 動画をダウンロード", f, "training_video.mp4", "video/mp4")
```

### PM（13:00〜17:00）：HeyGen アバター追加（オプション）

```python
# heygen_avatar.py
import requests, os, time

def generate_avatar_video(narration: str) -> str:
    """HeyGen APIでアバター解説動画を生成してURLを返す"""
    url = "https://api.heygen.com/v2/video/generate"
    payload = {
        "video_inputs": [{
            "character": {
                "type": "avatar",
                "avatar_id": "Daisy-inskirt-20220818",
                "avatar_style": "normal"
            },
            "voice": {
                "type": "text",
                "input_text": narration,
                "voice_id": "ja-JP-NanamiNeural"
            }
        }],
        "dimension": {"width": 1280, "height": 720}
    }
    headers = {"X-Api-Key": os.environ["HEYGEN_API_KEY"]}
    res = requests.post(url, json=payload, headers=headers).json()
    video_id = res["data"]["video_id"]

    # 生成完了まで待機
    for _ in range(30):
        time.sleep(10)
        status = requests.get(
            f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
            headers=headers
        ).json()
        if status["data"]["status"] == "completed":
            return status["data"]["video_url"]
    raise TimeoutError("HeyGen動画生成タイムアウト")
```

### 夕方（17:00〜21:00）：デモ資料 + 実データテスト

- ヒロテック社の公開資料（採用ページ・製品説明PDF等）でテスト実行
- デモ動画の録画
- 申込フォーム用ソリューション概要文（1000字）の作成

---

## Web 公開方法

### デモ用（即日・無料）：Streamlit Community Cloud

```bash
# 1. GitHubにプッシュ
git init && git add . && git commit -m "initial"
git remote add origin https://github.com/yourname/hirotec-video-ai.git
git push -u origin main

# 2. https://share.streamlit.io でリポジトリを指定するだけ
# → https://yourapp.streamlit.app が発行される
```

### 本番運用：AWS（社内資料を扱うため推奨構成）

```
[社内PC] → HTTPS → [AWS App Runner / EC2]
                           ↓
                    [OpenAI API / HeyGen API]
                           ↓
                    [S3: 生成動画を保存]
```

> ⚠️ ヒロテックの資料は社外秘の可能性が高いため、
> 本番運用はAWS VPC内に閉じるか、オンプレミス構成を推奨。

| フェーズ | 公開方式 | コスト |
|----------|----------|--------|
| デモ・提案段階 | Streamlit Community Cloud | 無料 |
| 検証・評価段階 | Render / Heroku | 月$7〜 |
| 本番運用 | AWS VPC内 or オンプレ | 要見積 |

---

## 2日間での完成物

| 成果物 | 内容 |
|--------|------|
| `app.py` | Streamlit デモアプリ（PDF/PPTX → MP4） |
| 動画サンプル | 実際の資料から生成した3〜5分の教育動画 |
| アバター版（オプション） | HeyGen解説者付きバージョン |
| 申込フォーム用提案文 | ヒロテック向け1000字ソリューション概要 |

---

## 申込時のアピールポイント

- **社内データを外部に出さない**: OpenAI APIへの送信のみで完結（クラウド保存なし）
- **既存スキルで即対応可能**: Runway・HeyGen・OpenAI APIの実績あり
- **外販モデルにも対応**: 汎用フレームワークとして他社展開可能な設計
- **2日でプロトタイプ**: 申込前にデモURLを提示可能

---

## ファイル構成

```
hirotec-video-ai/
├── app.py                  # Streamlit メインアプリ
├── document_parser.py      # PDF/PPTX パーサー
├── script_generator.py     # GPT-4o 台本生成 + TTS
├── video_builder.py        # MoviePy 動画合成
├── heygen_avatar.py        # HeyGen アバター（オプション）
├── requirements.txt        # 依存パッケージ
├── .env.example            # 環境変数サンプル
└── PROTOTYPE_PLAN.md       # 本ドキュメント
```

## 環境変数

```bash
# .env
OPENAI_API_KEY=sk-...
HEYGEN_API_KEY=...          # オプション
```
