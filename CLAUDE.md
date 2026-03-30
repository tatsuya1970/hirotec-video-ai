# 社内資料 → 動画教材 自動生成AI

## プロジェクト概要

**依頼企業:** 株式会社ヒロテック（自動車部品・設備製造業）
**目的:** PDF・PPTX・画像・WebページをアップロードするだけでMP4教育動画を自動生成するStreamlitアプリ
**申込締切:** 2026年4月7日（ひろしまAIサンドボックス #3289）

## 起動方法

```bash
cd /Users/tatsuya1970/projects/hirotec-video-ai
streamlit run app.py
```

## 環境変数（`.env` ファイルに設定）

```
OPENAI_API_KEY=sk-...        # 必須：台本生成（GPT-4o）・音声合成（TTS）
ANTHROPIC_API_KEY=...        # 任意：Claudeでスライド画像生成
HEYGEN_API_KEY=...           # 任意：HeyGenアバター動画
```

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `app.py` | Streamlit メインUI |
| `document_parser.py` | PDF/PPTX/画像/URL からテキスト・画像抽出 |
| `script_generator.py` | GPT-4o で台本生成・スライド再構築 |
| `slide_designer.py` | Anthropic Claude でスライド画像生成 |
| `video_builder.py` | MoviePy でスライド＋音声→MP4合成 |
| `heygen_avatar.py` | HeyGen API でアバター動画生成 |

## 技術スタック

- **UI:** Streamlit
- **文書解析:** pdfplumber（PDF）、python-pptx（PPTX）、PyMuPDF（PDF埋め込み画像）、BeautifulSoup（URL）
- **台本生成:** OpenAI GPT-4o（`generate_full_script`で全スライドを一括生成）
- **音声合成:** OpenAI TTS tts-1-hd（voice: shimmer/nova/alloy/onyx）
- **スライド画像:** Anthropic Claude（`slide_designer.py`）
- **動画合成:** MoviePy + FFmpeg
- **アバター:** HeyGen API v2

## データフロー

```
[ファイル/URL入力]
    ↓ load_multiple_files() / parse_url()
[pages: {page, text, image, source}]
    ↓ generate_full_script()  ← GPT-4oで一括再構築＋台本生成
[scripts: {page, text, image, source, narration, restructured_title}]
    ↓ generate_slide_image()  ← Claudeでスライド画像生成（任意）
    ↓ build_single_clip()     ← 各スライドをMP4クリップ化
    ↓ merge_clips()           ← 全クリップを結合
[final.mp4]
```

## 重要な設計判断

- `generate_full_script()` は `restructure_slides()` + `generate_script()` の統合版。1回のGPT-4o呼び出しで重複のない台本を生成する
- スライド画像は Anthropic Claude で生成（`ANTHROPIC_API_KEY` がない場合は元の画像をそのまま使用）
- 社内資料の機密性を考慮し、データはローカル処理（OpenAI/HeyGen API への送信のみ、クラウド保存なし）

## インストール

```bash
pip install streamlit pdfplumber python-pptx openai moviepy pillow python-dotenv requests numpy anthropic beautifulsoup4 pymupdf
brew install ffmpeg  # macOS
```
