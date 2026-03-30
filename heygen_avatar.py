"""
heygen_avatar.py
HeyGen API を使ってアバター解説動画を生成するモジュール
"""

import os
import time
import tempfile
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.heygen.com"

# HeyGen の1シーンあたりのテキスト上限（文字数）
TEXT_LIMIT = 1400


def _get_key() -> str:
    """環境変数または引数からAPIキーを取得"""
    return os.getenv("HEYGEN_API_KEY", "")


def is_available() -> bool:
    """HeyGen APIキーが設定されているか確認"""
    return bool(_get_key())


def _headers() -> dict:
    return {
        "X-Api-Key": _get_key(),
        "Content-Type": "application/json"
    }


# ────────────────────────────────────────
# アバター・音声一覧
# ────────────────────────────────────────

def list_avatars() -> list[dict]:
    """
    利用可能なアバター一覧を取得する

    Returns:
        [{"avatar_id": str, "avatar_name": str, "preview_image_url": str}, ...]
    """
    res = requests.get(f"{BASE_URL}/v2/avatars", headers=_headers(), timeout=15)
    res.raise_for_status()
    avatars = res.json().get("data", {}).get("avatars", [])
    return avatars


def list_voices(language: str = "") -> list[dict]:
    """
    利用可能な音声一覧を取得する

    Returns:
        [{"voice_id": str, "display_name": str, "gender": str, "language": str}, ...]
    """
    res = requests.get(f"{BASE_URL}/v2/voices", headers=_headers(), timeout=15)
    res.raise_for_status()
    voices = res.json().get("data", {}).get("voices", [])
    if language:
        voices = [v for v in voices if language.lower() in v.get("language", "").lower()]
    return voices


# ────────────────────────────────────────
# 動画生成
# ────────────────────────────────────────

def _submit_video(narration: str, avatar_id: str, voice_id: str) -> str:
    """HeyGen に動画生成リクエストを送り video_id を返す"""
    payload = {
        "video_inputs": [{
            "character": {
                "type": "avatar",
                "avatar_id": avatar_id,
                "avatar_style": "normal"
            },
            "voice": {
                "type": "text",
                "input_text": narration[:TEXT_LIMIT],
                "voice_id": voice_id,
                "speed": 0.95
            }
        }],
        "dimension": {"width": 1280, "height": 720}
    }
    res = requests.post(
        f"{BASE_URL}/v2/video/generate",
        json=payload,
        headers=_headers(),
        timeout=30
    )
    res.raise_for_status()
    return res.json()["data"]["video_id"]


def _wait_for_video(video_id: str, timeout_sec: int = 900) -> str:
    """動画生成完了を待ち、動画URLを返す"""
    interval = 15
    elapsed = 0
    while elapsed < timeout_sec:
        time.sleep(interval)
        elapsed += interval
        res = requests.get(
            f"{BASE_URL}/v1/video_status.get?video_id={video_id}",
            headers=_headers(),
            timeout=15
        )
        res.raise_for_status()
        data = res.json()["data"]
        status = data["status"]

        if status == "completed":
            return data["video_url"]
        elif status == "failed":
            raise RuntimeError(f"HeyGen動画生成が失敗しました: {data.get('error')}")

    raise TimeoutError(f"HeyGen動画生成がタイムアウトしました（{timeout_sec}秒）")


def download_video(url: str, output_path: str) -> str:
    """動画URLからファイルをダウンロードする"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    res = requests.get(url, timeout=120, stream=True)
    res.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


def generate_single_video(
    narration: str,
    avatar_id: str,
    voice_id: str,
    output_path: str
) -> str:
    """
    1つのナレーションからアバター動画を生成しローカルに保存する

    Returns:
        output_path
    """
    video_id = _submit_video(narration, avatar_id, voice_id)
    video_url = _wait_for_video(video_id)
    return download_video(video_url, output_path)


def generate_slides_videos(
    scripts: list[dict],
    avatar_id: str,
    voice_id: str,
    output_dir: str,
    progress_callback=None
) -> list[str]:
    """
    スライドごとにアバター動画を生成しローカルに保存する（全件並列ではなく順次）

    Returns:
        各スライドの動画パスのリスト
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total = len(scripts)

    # まず全スライドのリクエストを一括送信
    video_ids = []
    for i, s in enumerate(scripts):
        vid = _submit_video(s["narration"], avatar_id, voice_id)
        video_ids.append(vid)
        if progress_callback:
            progress_callback("submit", i + 1, total)

    # 完了を順番に待つ
    video_paths = []
    for i, (video_id, s) in enumerate(zip(video_ids, scripts)):
        video_url = _wait_for_video(video_id)
        path = os.path.join(output_dir, f"slide_{s['page']:03d}.mp4")
        download_video(video_url, path)
        video_paths.append(path)
        if progress_callback:
            progress_callback("download", i + 1, total)

    return video_paths
