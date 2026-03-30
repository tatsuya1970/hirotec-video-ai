"""
video_builder.py
スライド画像 + ナレーション音声 → MP4 動画を生成するモジュール
"""

import os
import tempfile
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    ImageClip, AudioFileClip, TextClip,
    CompositeVideoClip, concatenate_videoclips, ColorClip,
    VideoFileClip,
)
from script_generator import generate_audio

VIDEO_W, VIDEO_H = 1280, 720
BG_COLOR = (30, 30, 40)
CAPTION_FONT_SIZE = 30


def _make_blank_slide(text: str) -> Image.Image:
    """テキストのみのシンプルなスライド画像を生成する"""
    img = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 36)
    except Exception:
        font = ImageFont.load_default()

    lines = []
    words = text.split("\n")
    for word in words:
        if len(word) > 30:
            lines += [word[i:i+30] for i in range(0, len(word), 30)]
        else:
            lines.append(word)

    total_height = len(lines) * 50
    y = (VIDEO_H - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_W - w) // 2, y), line, fill="white", font=font)
        y += 50

    return img


def _resize_image(img: Image.Image) -> np.ndarray:
    """画像を動画サイズにリサイズしてnumpyに変換する"""
    img = img.convert("RGB")
    img_ratio = img.width / img.height
    target_ratio = VIDEO_W / VIDEO_H

    if img_ratio > target_ratio:
        new_w = VIDEO_W
        new_h = int(VIDEO_W / img_ratio)
    else:
        new_h = VIDEO_H
        new_w = int(VIDEO_H * img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    offset_x = (VIDEO_W - new_w) // 2
    offset_y = (VIDEO_H - new_h) // 2
    canvas.paste(img, (offset_x, offset_y))
    return np.array(canvas)


def build_single_clip(script: dict, output_path: str, voice: str = "shimmer") -> str:
    """
    単一スライドのMP4クリップを生成する

    Args:
        script: {"page", "text", "image", "narration", ...}
        output_path: 出力先MP4パス
        voice: TTS音声の種類

    Returns:
        output_path
    """
    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, "audio.mp3")
    generate_audio(script["narration"], audio_path, voice)
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    if script.get("image"):
        img_array = _resize_image(script["image"])
    else:
        blank = _make_blank_slide(script.get("text", f"スライド {script['page']}"))
        img_array = np.array(blank)

    img_clip = ImageClip(img_array, duration=duration)

    first_sentence = script["narration"].split("。")[0] + "。"
    if len(first_sentence) > 40:
        first_sentence = first_sentence[:40] + "…"

    try:
        txt_clip = (
            TextClip(
                text=first_sentence,
                font_size=CAPTION_FONT_SIZE,
                color="white",
                bg_color="black",
                font="Hiragino-Sans-W3",
                size=(VIDEO_W - 80, None),
                method="caption",
                duration=duration
            )
            .with_position(("center", VIDEO_H - 80))
        )
        clip = CompositeVideoClip([img_clip, txt_clip]).with_audio(audio_clip)
    except Exception:
        clip = img_clip.with_audio(audio_clip)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None
    )
    try:
        clip.close()
        audio_clip.close()
    except Exception:
        pass
    return output_path


def merge_clips(clip_paths: list[str], output_path: str) -> str:
    """
    複数のMP4クリップを結合して最終動画を生成する

    Args:
        clip_paths: 個別クリップのパスリスト（順序通りに結合）
        output_path: 出力先MP4パス

    Returns:
        output_path
    """
    clips = [VideoFileClip(p) for p in clip_paths]
    final = concatenate_videoclips(clips, method="compose")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None
    )
    try:
        final.close()
        for c in clips:
            c.close()
    except Exception:
        pass
    return output_path


def build_video(
    scripts: list[dict],
    output_path: str,
    voice: str = "shimmer",
    progress_callback=None
) -> str:
    """
    スクリプトリストから MP4 動画を生成する（後方互換）

    Args:
        scripts: script_generator.generate_script() の出力
        output_path: 出力先MP4パス
        voice: TTS音声の種類
        progress_callback: 進捗通知 (current, total) -> None

    Returns:
        output_path
    """
    tmp_dir = tempfile.mkdtemp()
    clip_paths = []
    total = len(scripts)

    for i, s in enumerate(scripts):
        if progress_callback:
            progress_callback(i + 1, total)
        clip_path = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")
        build_single_clip(s, clip_path, voice)
        clip_paths.append(clip_path)

    return merge_clips(clip_paths, output_path)
