"""
script_generator.py
GPT-4o で教育用ナレーション台本を生成し、OpenAI TTS で音声化するモジュール
"""

import json
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

SYSTEM_PROMPT = """
あなたは製造業の社内教育動画のナレーター台本を書く専門家です。
以下のルールで台本を作成してください：

- 1スライドあたり30〜60秒で読める長さ（約150〜300文字）
- 専門用語には補足説明を括弧で入れる
- 「まず」「次に」「ポイントは」「注意が必要なのは」など導入フレーズを使う
- 新入社員でも理解できる平易な日本語
- 箇条書きは使わず、自然に話しかけるような文章にする
- 台本テキストのみを出力し、説明や前置きは不要
""".strip()


def generate_script(pages: list[dict], callback=None) -> list[dict]:
    """
    各ページの内容をナレーション台本に変換する

    Args:
        pages: parse_pdf / parse_pptx の出力
        callback: 進捗通知用コールバック関数 (page_num, total) -> None

    Returns:
        pages に "narration" キーを追加したリスト
    """
    scripts = []
    total = len(pages)

    for page in pages:
        if callback:
            callback(page["page"], total)

        if not page["text"].strip():
            # テキストが空のページはスキップ用の台本を生成
            narration = "このスライドには図や画像が含まれています。担当者の説明をご確認ください。"
        else:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"以下の資料内容をナレーション台本にしてください：\n\n{page['text']}"}
                ],
                temperature=0.7,
                max_tokens=600
            )
            narration = response.choices[0].message.content.strip()

        scripts.append({
            **page,
            "narration": narration
        })

    return scripts


RESTRUCTURE_SYSTEM_PROMPT = """
あなたは製造業の社内教育コンテンツ設計の専門家です。
複数の資料・Webページから集めたテキストを、教育効果の高い動画スライド構成に再編成してください。

ルール：
- 重複・類似するコンテンツを統合して整理する
- 「導入 → 本題 → 詳細説明 → まとめ」の論理的な流れに並び替える
- 必ず最初に全体を紹介する「導入スライド」を置く
- 必ず最後に要点を振り返る「まとめスライド」を置く
- 各スライドの body は要点を簡潔にまとめた150文字以内の文章にする
- original_index は最も内容が近い元ページ番号（0始まり）を指定する
- スライド数は元の枚数の50〜150%程度に収める

出力はJSONオブジェクトのみ（説明文は不要）：
{"slides": [
  {"title": "スライドタイトル", "body": "内容の要点", "original_index": 0},
  ...
]}
""".strip()


def restructure_slides(pages: list[dict], callback=None) -> list[dict]:
    """
    複数ソースのページ群をGPT-4oで論理的に再構築・統合する

    Args:
        pages: load_multiple_files() の出力
        callback: 進捗通知用コールバック () -> None

    Returns:
        再構築されたページリスト（imageは元ページから引き継ぎ）
    """
    if callback:
        callback()

    # 各ページのテキストを収集（トークン削減のため600文字に制限）
    page_summaries = []
    for i, p in enumerate(pages):
        text = p.get("text", "").strip()[:600]
        if text:
            source = p.get("source", "")
            page_summaries.append(f"[ページ{i+1} | {source}]\n{text}")

    if not page_summaries:
        return pages

    combined = "\n\n".join(page_summaries)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": RESTRUCTURE_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下の資料群を再構築してください：\n\n{combined}"}
        ],
        temperature=0.4,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )

    raw = response.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        slides_data = data.get("slides", data) if isinstance(data, dict) else data
    except Exception:
        return pages

    restructured = []
    for i, s in enumerate(slides_data):
        orig_idx = int(s.get("original_index", 0))
        orig_idx = max(0, min(orig_idx, len(pages) - 1))
        orig = pages[orig_idx]

        title = s.get("title", f"スライド {i+1}")
        body = s.get("body", "")
        restructured.append({
            "page": i + 1,
            "text": f"{title}\n{body}",
            "image": orig.get("image"),
            "source": orig.get("source", "再構築"),
            "restructured_title": title,
        })

    return restructured


def generate_slide_image(title: str, narration: str):
    """
    DALL-E 3 でスライド用画像を生成する

    Args:
        title: スライドのタイトル
        narration: ナレーション台本（プロンプトの参考に使用）

    Returns:
        PIL.Image オブジェクト
    """
    import io
    import requests
    from PIL import Image

    narration_short = narration[:150].replace("\n", " ")

    prompt = (
        f"製造業の社内教育スライド用のビジュアルイメージ。"
        f"テーマ：「{title}」。"
        f"内容のイメージ：{narration_short}。"
        f"スタイル：クリーンでプロフェッショナルなフラットデザインのインフォグラフィック、"
        f"明るくシンプルな配色、ビジネス向けイラスト。文字・テキストは一切含めない。"
    )

    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1792x1024",
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url
    img_data = requests.get(image_url, timeout=30).content
    return Image.open(io.BytesIO(img_data)).convert("RGB")


VOICE_OPTIONS = {
    "shimmer（女性・落ち着き）": "shimmer",
    "nova（女性・明快）": "nova",
    "alloy（中性・明瞭）": "alloy",
    "onyx（男性・低め）": "onyx",
}


FULL_SCRIPT_SYSTEM_PROMPT = """
あなたは製造業の社内教育コンテンツ制作の専門家です。
複数の資料・Webページから集めたテキストを元に、教育効果の高い動画の全体台本を1回で作成してください。

ルール：
- 全体を通して重複・繰り返しのない、流れのある台本にする（各トピックは1回だけ登場）
- 「導入 → 本題 → 詳細説明 → まとめ」の論理的な流れにする
- 必ず最初に全体を紹介する「導入スライド」を置く
- 必ず最後に要点を振り返る「まとめスライド」を置く
- 各スライドのナレーションは30〜60秒で読める長さ（約150〜300文字）
- 専門用語には補足説明を括弧で入れる
- 「まず」「次に」「ポイントは」「注意が必要なのは」など導入フレーズを使う
- 新入社員でも理解できる平易な日本語
- 箇条書きは使わず、自然に話しかけるような文章にする
- スライド数は入力ページ数の50〜150%程度に収める
- 【Webページ】ソースの内容も必ず動画内に反映すること
- original_index は最も内容が近い元ページ番号（0始まり）を指定する

出力はJSONオブジェクトのみ（説明文・前置きは不要）：
{"slides": [
  {"title": "スライドタイトル（20文字以内）", "narration": "ナレーション台本（150〜300文字）", "original_index": 0},
  ...
]}
""".strip()


def generate_full_script(pages: list[dict], callback=None) -> list[dict]:
    """
    全ページの内容を一括してGPT-4oに渡し、重複のない動画台本を生成する。
    restructure_slides + generate_script の統合版。

    Args:
        pages: load_multiple_files() + parse_url() の出力
        callback: 進捗通知 () -> None

    Returns:
        [{page, text, image, source, narration, restructured_title}, ...]
    """
    if callback:
        callback()

    # 各ページのテキストを収集（ソースタイプを明示してURLコンテンツを区別）
    page_summaries = []
    for i, p in enumerate(pages):
        text = p.get("text", "").strip()[:600]
        if not text:
            continue
        source = p.get("source", "")
        # URLソースは明示的にラベルを付けてGPTに重要性を伝える
        is_url = source.startswith("http") or (len(source) > 4 and "…" in source)
        src_label = f"【Webページ: {source}】" if is_url else f"【資料: {source}】"
        page_summaries.append(f"[ページ{i+1} | {src_label}]\n{text}")

    if not page_summaries:
        return pages

    combined = "\n\n".join(page_summaries)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": FULL_SCRIPT_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下の資料群から動画の全体台本を作成してください：\n\n{combined}"}
        ],
        temperature=0.5,
        max_tokens=6000,
        response_format={"type": "json_object"}
    )

    raw = response.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        slides_data = data.get("slides", []) if isinstance(data, dict) else data
    except Exception:
        return pages  # パース失敗時はフォールバック

    result = []
    for i, s in enumerate(slides_data):
        orig_idx = int(s.get("original_index", 0))
        orig_idx = max(0, min(orig_idx, len(pages) - 1))
        orig = pages[orig_idx]

        title = s.get("title", f"スライド {i+1}")
        narration = s.get("narration", "")
        result.append({
            "page": i + 1,
            "text": title,
            "image": orig.get("image"),
            "source": orig.get("source", ""),
            "narration": narration,
            "restructured_title": title,
        })

    return result


def generate_audio(text: str, output_path: str, voice: str = "shimmer") -> str:
    """
    テキストをMP3音声ファイルに変換する

    Args:
        text: ナレーション文章
        output_path: 保存先パス
        voice: OpenAI TTS の音声種類

    Returns:
        output_path
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice,
        input=text,
        speed=0.95
    )
    response.stream_to_file(output_path)
    return output_path
