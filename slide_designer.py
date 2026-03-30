"""
slide_designer.py
Claude API でスライド内容をJSON生成 → Pythonテンプレートでレンダリング →
Playwright でPNG変換するモジュール

レイアウト: 全幅 1280px
背景: DALL-E 3 で生成したインパクト画像（文字なし） + ダークオーバーレイ
コンテンツ: Claude 生成のタイトル・テキストをグラスモーフィズムパネルでオーバーレイ
"""

import base64
import io
import json
import os
import tempfile
from dotenv import load_dotenv
import anthropic
from PIL import Image

load_dotenv()

SLIDE_W = 1280
SLIDE_H = 720

# ────────────────────────────────────────
# Claude へのJSONプロンプト
# ────────────────────────────────────────
JSON_PROMPT = """あなたはプレゼンテーションコンテンツの専門家です。
以下のスライド内容を分析し、最適なレイアウトと文言をJSONで返してください。

テンプレート選択基準：
- "cards"   : 3〜5つの並列要点（最も汎用的。迷ったらこれ）
- "twocol"  : 左に概念・説明、右に補足・詳細がある場合
- "process" : 手順・フロー・ステップがある場合（3〜5ステップ）
- "stat"    : 重要な数値・割合・金額が主役の場合
- "summary" : まとめ・導入・結論（箇条書きを縦に並べる）

色選択のポイント：
- accent : アクセントカラー（オレンジ・シアン・ゴールドなど鮮やか系を推奨）
{color_hint}

出力はJSONオブジェクトのみ（説明文・コードブロック記号は不要）：
{{
  "template": "cards|twocol|process|stat|summary",
  "title": "タイトル（20文字以内）",
  "subtitle": "サブタイトル（32文字以内、なければ空文字）",
  "tag": "カテゴリタグ（12文字以内、英数字推奨）",
  "accent": "#e94560",
  "items": [
    {{"icon": "🎯", "title": "見出し（14文字以内）", "body": "説明文（48文字以内）"}},
    ...（3〜5個）
  ],
  "stat_value": "数値・割合（例: 87%、1億円）。statテンプレート以外は空文字",
  "stat_label": "数値の説明（20文字以内）。statテンプレート以外は空文字",
  "note": "フッター補足テキスト（45文字以内、任意）"
}}

スライド内容：
{content}"""


# ────────────────────────────────────────
# 共通ヘルパー
# ────────────────────────────────────────

def _html_head(image_b64: str = "", accent: str = "#e94560") -> str:
    """
    背景を画像（あれば）またはダークグラデーションで設定する。
    画像ありの場合はダークオーバーレイを追加。
    """
    if image_b64:
        bg_css = (
            f'background:url("data:image/jpeg;base64,{image_b64}") center/cover no-repeat'
        )
        overlay = (
            f'<div style="position:absolute;inset:0;'
            f'background:linear-gradient(135deg,rgba(5,5,20,0.72) 0%,rgba(5,10,30,0.55) 50%,rgba(0,0,0,0.65) 100%);'
            f'z-index:0"></div>'
        )
    else:
        bg_css = "background:linear-gradient(135deg,#16213e 0%,#0f3460 100%)"
        overlay = ""

    return (
        f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
        f'*{{margin:0;padding:0;box-sizing:border-box}}'
        f'html,body{{width:{SLIDE_W}px;height:{SLIDE_H}px;overflow:hidden;position:relative;'
        f'font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic",system-ui,sans-serif;{bg_css}}}'
        f'</style></head><body>{overlay}'
    )


def _glass(opacity: float = 0.18, blur: int = 8, border_opacity: float = 0.25) -> str:
    """グラスモーフィズム用CSSスタイル文字列"""
    return (
        f"background:rgba(255,255,255,{opacity});"
        f"backdrop-filter:blur({blur}px);-webkit-backdrop-filter:blur({blur}px);"
        f"border:1px solid rgba(255,255,255,{border_opacity});"
    )


def _pil_to_base64(img: Image.Image, max_size: int = 1024) -> tuple[str, str]:
    img = img.copy()
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


# ────────────────────────────────────────
# HTMLテンプレート群（全幅 1280px）
# ────────────────────────────────────────

def _template_cards(d: dict) -> str:
    acc = d.get("accent", "#e94560")
    image_b64 = d.get("image_b64", "")
    items = d.get("items", [])[:5]
    tag, title, subtitle, note = d.get("tag",""), d.get("title",""), d.get("subtitle",""), d.get("note","")

    cards_html = "".join(
        f'<div style="flex:1;{_glass(0.16,10,0.22)}border-radius:16px;'
        f'padding:26px 20px;border-top:5px solid {acc};display:flex;flex-direction:column;gap:10px">'
        f'<div style="font-size:36px;line-height:1">{it.get("icon","📌")}</div>'
        f'<div style="color:#fff;font-size:19px;font-weight:bold;line-height:1.3;text-shadow:0 1px 3px rgba(0,0,0,.5)">{it.get("title","")}</div>'
        f'<div style="color:rgba(255,255,255,0.88);font-size:15px;line-height:1.75;flex:1;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div>'
        f'</div>'
        for it in items
    )

    header_h = 145 if subtitle else 112
    footer_h = 48 if note else 0
    content_h = SLIDE_H - header_h - footer_h

    return (
        _html_head(image_b64, acc) +
        f'<div style="position:relative;z-index:1;{_glass(0.28,12,0.3)}padding:20px 52px 18px;'
        f'border-bottom:4px solid {acc};height:{header_h}px">'
        f'{"<div style=\"color:"+acc+";font-size:12px;font-weight:bold;letter-spacing:3px;margin-bottom:5px;text-shadow:0 1px 3px rgba(0,0,0,.5)\">"+tag+"</div>" if tag else ""}'
        f'<div style="color:#fff;font-size:46px;font-weight:bold;line-height:1.15;text-shadow:0 2px 8px rgba(0,0,0,.6)">{title}</div>'
        f'{"<div style=\"color:rgba(255,255,255,0.82);font-size:18px;margin-top:6px;text-shadow:0 1px 4px rgba(0,0,0,.5)\">"+subtitle+"</div>" if subtitle else ""}'
        f'</div>'
        f'<div style="position:relative;z-index:1;display:flex;gap:20px;padding:26px 52px;height:{content_h}px;align-items:stretch">'
        f'{cards_html}</div>'
        f'{"<div style=\"position:absolute;bottom:0;left:0;right:0;z-index:1;height:"+str(footer_h)+"px;"+_glass(0.25,8,0.2)+"display:flex;align-items:center;padding:0 52px\"><span style=\"color:rgba(255,255,255,0.65);font-size:13px\">"+note+"</span></div>" if note else ""}'
        f'</body></html>'
    )


def _template_twocol(d: dict) -> str:
    acc = d.get("accent", "#e94560")
    image_b64 = d.get("image_b64", "")
    items = d.get("items", [])
    tag, title, subtitle, note = d.get("tag",""), d.get("title",""), d.get("subtitle",""), d.get("note","")

    left_items = items[:3]
    right_items = items[3:]

    bullets_left = "".join(
        f'<div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:22px">'
        f'<span style="font-size:28px;line-height:1;min-width:34px;text-shadow:0 1px 3px rgba(0,0,0,.5)">{it.get("icon","✅")}</span>'
        f'<div><div style="color:#fff;font-size:18px;font-weight:bold;margin-bottom:4px;text-shadow:0 1px 4px rgba(0,0,0,.5)">{it.get("title","")}</div>'
        f'<div style="color:rgba(255,255,255,0.85);font-size:15px;line-height:1.7;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div></div></div>'
        for it in left_items
    )

    bullets_right = "".join(
        f'<div style="{_glass(0.15,8,0.22)}border-radius:12px;padding:16px 20px;margin-bottom:14px">'
        f'<div style="color:{acc};font-size:20px;font-weight:bold;text-shadow:0 1px 3px rgba(0,0,0,.4)">{it.get("icon","")} {it.get("title","")}</div>'
        f'<div style="color:rgba(255,255,255,0.87);font-size:14px;line-height:1.68;margin-top:6px;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div></div>'
        for it in right_items
    ) if right_items else (
        f'<div style="color:{acc};font-size:86px;font-weight:bold;text-align:center;margin-top:40px;text-shadow:0 4px 12px rgba(0,0,0,.6)">{d.get("stat_value","")}</div>'
        f'<div style="color:rgba(255,255,255,0.85);font-size:22px;text-align:center;margin-top:12px;text-shadow:0 1px 4px rgba(0,0,0,.5)">{d.get("stat_label","")}</div>'
    )

    left_w = int(SLIDE_W * 0.52)

    return (
        _html_head(image_b64, acc) +
        f'<div style="position:relative;z-index:1;{_glass(0.28,12,0.3)}padding:20px 52px 16px;border-bottom:4px solid {acc}">'
        f'{"<div style=\"color:"+acc+";font-size:12px;font-weight:bold;letter-spacing:3px;margin-bottom:5px\">"+tag+"</div>" if tag else ""}'
        f'<div style="color:#fff;font-size:44px;font-weight:bold;line-height:1.15;text-shadow:0 2px 8px rgba(0,0,0,.6)">{title}</div>'
        f'{"<div style=\"color:rgba(255,255,255,0.8);font-size:17px;margin-top:5px;text-shadow:0 1px 4px rgba(0,0,0,.5)\">"+subtitle+"</div>" if subtitle else ""}'
        f'</div>'
        f'<div style="position:relative;z-index:1;display:flex;height:590px">'
        f'<div style="width:{left_w}px;padding:30px 44px;overflow:hidden">{bullets_left}</div>'
        f'<div style="width:2px;{_glass(0.3,0,0.4)}margin:32px 0"></div>'
        f'<div style="flex:1;padding:30px 36px;overflow:hidden">{bullets_right}</div>'
        f'</div>'
        f'{"<div style=\"position:absolute;bottom:0;left:0;right:0;z-index:1;height:48px;"+_glass(0.25,8,0.2)+"display:flex;align-items:center;padding:0 52px\"><span style=\"color:rgba(255,255,255,0.65);font-size:13px\">"+note+"</span></div>" if note else ""}'
        f'</body></html>'
    )


def _template_process(d: dict) -> str:
    acc = d.get("accent", "#e94560")
    image_b64 = d.get("image_b64", "")
    items = d.get("items", [])[:5]
    tag, title, subtitle, note = d.get("tag",""), d.get("title",""), d.get("subtitle",""), d.get("note","")

    steps_html = ""
    for i, it in enumerate(items):
        arrow = (
            f'<div style="color:{acc};font-size:26px;align-self:center;margin:0 4px;'
            f'text-shadow:0 1px 4px rgba(0,0,0,.5)">▶</div>'
        ) if i < len(items) - 1 else ""
        steps_html += (
            f'<div style="flex:1;{_glass(0.16,10,0.22)}border-radius:14px;padding:22px 16px;text-align:center">'
            f'<div style="background:{acc};color:#fff;width:34px;height:34px;border-radius:50%;'
            f'display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:bold;margin:0 auto 12px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.4)">{i+1}</div>'
            f'<div style="font-size:30px;margin-bottom:10px">{it.get("icon","📌")}</div>'
            f'<div style="color:#fff;font-size:16px;font-weight:bold;margin-bottom:7px;line-height:1.3;text-shadow:0 1px 4px rgba(0,0,0,.5)">{it.get("title","")}</div>'
            f'<div style="color:rgba(255,255,255,0.85);font-size:13px;line-height:1.68;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div>'
            f'</div>{arrow}'
        )

    return (
        _html_head(image_b64, acc) +
        f'<div style="position:relative;z-index:1;{_glass(0.28,12,0.3)}padding:20px 52px 16px;border-bottom:4px solid {acc}">'
        f'{"<div style=\"color:"+acc+";font-size:12px;font-weight:bold;letter-spacing:3px;margin-bottom:5px\">"+tag+"</div>" if tag else ""}'
        f'<div style="color:#fff;font-size:44px;font-weight:bold;line-height:1.15;text-shadow:0 2px 8px rgba(0,0,0,.6)">{title}</div>'
        f'{"<div style=\"color:rgba(255,255,255,0.8);font-size:17px;margin-top:5px;text-shadow:0 1px 4px rgba(0,0,0,.5)\">"+subtitle+"</div>" if subtitle else ""}'
        f'</div>'
        f'<div style="position:relative;z-index:1;display:flex;align-items:stretch;gap:0;padding:30px 44px;height:536px">{steps_html}</div>'
        f'{"<div style=\"position:absolute;bottom:0;left:0;right:0;z-index:1;height:48px;"+_glass(0.25,8,0.2)+"display:flex;align-items:center;padding:0 52px\"><span style=\"color:rgba(255,255,255,0.65);font-size:13px\">"+note+"</span></div>" if note else ""}'
        f'</body></html>'
    )


def _template_stat(d: dict) -> str:
    acc = d.get("accent", "#e94560")
    image_b64 = d.get("image_b64", "")
    items = d.get("items", [])[:3]
    tag, title, subtitle, note = d.get("tag",""), d.get("title",""), d.get("subtitle",""), d.get("note","")
    stat_value, stat_label = d.get("stat_value",""), d.get("stat_label","")

    sub_items = "".join(
        f'<div style="{_glass(0.15,8,0.22)}border-radius:12px;padding:16px 18px;text-align:center;flex:1">'
        f'<div style="font-size:24px;margin-bottom:8px">{it.get("icon","")}</div>'
        f'<div style="color:{acc};font-size:18px;font-weight:bold;text-shadow:0 1px 3px rgba(0,0,0,.4)">{it.get("title","")}</div>'
        f'<div style="color:rgba(255,255,255,0.82);font-size:13px;margin-top:5px;line-height:1.55;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div>'
        f'</div>'
        for it in items
    )

    left_w = int(SLIDE_W * 0.48)

    return (
        _html_head(image_b64, acc) +
        f'<div style="position:relative;z-index:1;display:flex;height:{SLIDE_H}px">'
        f'<div style="width:{left_w}px;display:flex;flex-direction:column;justify-content:center;padding:52px">'
        f'{"<div style=\"color:"+acc+";font-size:12px;font-weight:bold;letter-spacing:3px;margin-bottom:12px;text-shadow:0 1px 3px rgba(0,0,0,.5)\">"+tag+"</div>" if tag else ""}'
        f'<div style="color:#fff;font-size:46px;font-weight:bold;line-height:1.2;margin-bottom:10px;text-shadow:0 2px 10px rgba(0,0,0,.6)">{title}</div>'
        f'{"<div style=\"color:rgba(255,255,255,0.78);font-size:18px;line-height:1.65;text-shadow:0 1px 4px rgba(0,0,0,.5)\">"+subtitle+"</div>" if subtitle else ""}'
        f'</div>'
        f'<div style="width:2px;{_glass(0.3,0,0.4)}margin:52px 0"></div>'
        f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px">'
        f'<div style="color:{acc};font-size:96px;font-weight:bold;line-height:1;text-align:center;text-shadow:0 4px 16px rgba(0,0,0,.6)">{stat_value}</div>'
        f'<div style="color:rgba(255,255,255,0.87);font-size:22px;margin-top:12px;text-align:center;text-shadow:0 1px 4px rgba(0,0,0,.5)">{stat_label}</div>'
        f'<div style="display:flex;gap:16px;margin-top:40px;width:100%">{sub_items}</div>'
        f'</div>'
        f'</div>'
        f'<div style="position:absolute;bottom:0;left:0;right:0;z-index:1;height:5px;background:{acc};box-shadow:0 0 12px {acc}"></div>'
        f'{"<div style=\"position:absolute;bottom:5px;left:0;right:0;z-index:1;height:48px;"+_glass(0.25,8,0.2)+"display:flex;align-items:center;padding:0 52px\"><span style=\"color:rgba(255,255,255,0.65);font-size:13px\">"+note+"</span></div>" if note else ""}'
        f'</body></html>'
    )


def _template_summary(d: dict) -> str:
    acc = d.get("accent", "#e94560")
    image_b64 = d.get("image_b64", "")
    items = d.get("items", [])[:6]
    tag, title, subtitle, note = d.get("tag",""), d.get("title",""), d.get("subtitle",""), d.get("note","")

    rows = [items[i:i+2] for i in range(0, len(items), 2)]
    grid_html = ""
    for row in rows:
        grid_html += '<div style="display:flex;gap:18px;margin-bottom:16px">'
        for it in row:
            grid_html += (
                f'<div style="flex:1;{_glass(0.15,8,0.22)}border-radius:12px;'
                f'padding:17px 20px;border-left:5px solid {acc};display:flex;gap:14px;align-items:flex-start">'
                f'<span style="font-size:26px;line-height:1;min-width:30px">{it.get("icon","✅")}</span>'
                f'<div><div style="color:#fff;font-size:17px;font-weight:bold;margin-bottom:4px;text-shadow:0 1px 4px rgba(0,0,0,.5)">{it.get("title","")}</div>'
                f'<div style="color:rgba(255,255,255,0.82);font-size:13px;line-height:1.65;text-shadow:0 1px 2px rgba(0,0,0,.4)">{it.get("body","")}</div></div></div>'
            )
        grid_html += '</div>'

    return (
        _html_head(image_b64, acc) +
        f'<div style="position:relative;z-index:1;{_glass(0.3,14,0.3)}height:150px;padding:22px 60px;'
        f'display:flex;flex-direction:column;justify-content:center;border-bottom:5px solid {acc}">'
        f'{"<div style=\"color:"+acc+";font-size:12px;font-weight:bold;letter-spacing:3px;margin-bottom:6px\">"+tag+"</div>" if tag else ""}'
        f'<div style="color:#fff;font-size:48px;font-weight:bold;line-height:1.2;text-shadow:0 2px 10px rgba(0,0,0,.6)">{title}</div>'
        f'{"<div style=\"color:rgba(255,255,255,0.78);font-size:17px;margin-top:5px;text-shadow:0 1px 4px rgba(0,0,0,.5)\">"+subtitle+"</div>" if subtitle else ""}'
        f'</div>'
        f'<div style="position:relative;z-index:1;padding:26px 60px;height:522px;overflow:hidden">{grid_html}</div>'
        f'{"<div style=\"position:absolute;bottom:0;left:0;right:0;z-index:1;height:50px;"+_glass(0.28,8,0.2)+"display:flex;align-items:center;padding:0 60px\"><span style=\"color:rgba(255,255,255,0.65);font-size:13px\">"+note+"</span></div>" if note else ""}'
        f'</body></html>'
    )


TEMPLATE_FUNCS = {
    "cards":   _template_cards,
    "twocol":  _template_twocol,
    "process": _template_process,
    "stat":    _template_stat,
    "summary": _template_summary,
}


def render_slide_from_json(data: dict) -> str:
    """JSONデータをHTMLスライドにレンダリングする"""
    template = data.get("template", "cards")
    func = TEMPLATE_FUNCS.get(template, _template_cards)
    return func(data)


# ────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────

def extract_dominant_colors(images: list, n: int = 6) -> list[str]:
    all_hex, seen = [], set()
    for img in images:
        if img is None:
            continue
        try:
            small = img.copy().resize((120, 120)).convert("RGB")
            palette = small.quantize(colors=24).getpalette()
            for i in range(0, 72, 3):
                r, g, b = palette[i], palette[i+1], palette[i+2]
                if 25 < (r+g+b)/3 < 230 and max(r,g,b)-min(r,g,b) > 30:
                    h = f"#{r:02x}{g:02x}{b:02x}"
                    if h not in seen:
                        seen.add(h)
                        all_hex.append(h)
        except Exception:
            continue
    return all_hex[:n]


def build_design_context(source_pages: list, url_reference_images: list) -> dict:
    doc_images = [p["image"] for p in source_pages if p.get("image")][:5]
    reference_images = (url_reference_images + doc_images)[:3]
    brand_colors = extract_dominant_colors(url_reference_images + doc_images)
    return {"reference_images": reference_images, "brand_colors": brand_colors}


# ────────────────────────────────────────
# スライド生成
# ────────────────────────────────────────

def generate_slide_json(
    title: str,
    narration: str,
    source_text: str = "",
    reference_images: list = None,
    brand_colors: list = None,
) -> dict:
    """Claude API でスライド内容のJSONを生成する"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY が設定されていません。")

    client = anthropic.Anthropic(api_key=api_key)

    content_block = f"タイトル：{title}\n\nナレーション：{narration}"
    if source_text:
        content_block += f"\n\n元資料：{source_text[:400]}"

    color_hint = ""
    if brand_colors:
        color_hint = f"\n参考アクセントカラー（accent に使用推奨）：{', '.join(brand_colors[:4])}"

    prompt = JSON_PROMPT.format(content=content_block, color_hint=color_hint)

    content_parts = []
    for img in (reference_images or [])[:2]:
        b64, mt = _pil_to_base64(img)
        content_parts.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}})
    content_parts.append({"type": "text", "text": prompt})

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": content_parts}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _get_font(size: int, bold: bool = False):
    """日本語対応フォントを取得（なければデフォルト）"""
    from PIL import ImageFont
    import glob
    candidates = []

    # Linux (Streamlit Cloud) - Noto Sans CJK
    candidates += glob.glob("/usr/share/fonts/**/Noto*CJK*Bold*.ttc", recursive=True)
    candidates += glob.glob("/usr/share/fonts/**/Noto*CJK*.ttc", recursive=True)
    candidates += glob.glob("/usr/share/fonts/**/NotoSans*.ttf", recursive=True)
    # Linux - DejaVu（確実に存在）
    if bold:
        candidates += glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
    candidates += glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
    # macOS
    if bold:
        candidates += ["/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
                       "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
    candidates += ["/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                   "/System/Library/Fonts/Supplemental/Arial.ttf"]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    # フォールバック：load_default はサイズ指定できないので size を近似
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """テキストを指定幅で折り返す"""
    lines = []
    for paragraph in text.split("\n"):
        words = list(paragraph)
        line = ""
        for ch in words:
            test = line + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and line:
                lines.append(line)
                line = ch
            else:
                line = test
        if line:
            lines.append(line)
    return lines


def render_slide_pil(data: dict) -> Image.Image:
    """PIL でスライドを直接描画する（外部ブラウザ不要）"""
    from PIL import ImageDraw

    W, H = SLIDE_W, SLIDE_H
    accent_hex = data.get("accent", "#1e5cb3")
    accent = _hex_to_rgb(accent_hex)
    title_text = data.get("title", "")
    subtitle_text = data.get("subtitle", "")
    items = data.get("items", [])
    tag_text = data.get("tag", "")
    note_text = data.get("note", "")

    # ── 背景グラデーション ──
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    bg_top = (16, 26, 54)
    bg_bot = (10, 18, 40)
    for y in range(H):
        r = int(bg_top[0] + (bg_bot[0] - bg_top[0]) * y / H)
        g = int(bg_top[1] + (bg_bot[1] - bg_top[1]) * y / H)
        b = int(bg_top[2] + (bg_bot[2] - bg_top[2]) * y / H)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── ヘッダーバー ──
    header_h = 130
    draw.rectangle([(0, 0), (W, header_h)], fill=(255, 255, 255, 0))
    overlay = Image.new("RGBA", (W, header_h), (255, 255, 255, 35))
    img.paste(Image.new("RGB", (W, header_h),
              (int(bg_top[0]*1.3), int(bg_top[1]*1.3), int(bg_top[2]*1.5))),
              (0, 0))
    # アクセントライン
    draw.rectangle([(0, header_h - 4), (W, header_h)], fill=accent)
    draw = ImageDraw.Draw(img)

    # ── タグ ──
    px = 52
    py = 20
    if tag_text:
        tag_font = _get_font(12, bold=True)
        draw.text((px, py), tag_text.upper(), font=tag_font, fill=accent)
        py += 22

    # ── タイトル ──
    title_font = _get_font(44, bold=True)
    draw.text((px, py), title_text, font=title_font, fill=(255, 255, 255))
    py += 56

    # ── サブタイトル ──
    if subtitle_text:
        sub_font = _get_font(18)
        draw.text((px, py), subtitle_text, font=sub_font, fill=(200, 215, 235))

    # ── カード（items） ──
    if items:
        n = len(items)
        margin = 52
        gap = 14
        card_w = (W - margin * 2 - gap * (n - 1)) // n
        card_y = header_h + 18
        card_h = H - header_h - 18 - (52 if note_text else 10)

        ct_font = _get_font(16, bold=True)
        cb_font = _get_font(13)
        num_font = _get_font(18, bold=True)

        for i, item in enumerate(items):
            cx = margin + i * (card_w + gap)
            # カード背景（明るめのネイビー）
            img.paste(Image.new("RGB", (card_w, card_h), (38, 58, 95)), (cx, card_y))
            draw = ImageDraw.Draw(img)
            # アクセントトップボーダー
            draw.rectangle([(cx, card_y), (cx + card_w, card_y + 5)], fill=accent)
            # 番号バッジ（絵文字の代わり）
            badge_r = 16
            bx, by = cx + 22, card_y + 22
            draw.ellipse([(bx, by), (bx + badge_r*2, by + badge_r*2)], fill=accent)
            draw.text((bx + badge_r - 5, by + badge_r - 10), str(i + 1),
                      font=num_font, fill=(255, 255, 255))

            # カードタイトル
            ct_lines = _wrap_text(item.get("title", ""), ct_font, card_w - 28, draw)
            cy = card_y + 60
            for line in ct_lines[:2]:
                draw.text((cx + 14, cy), line, font=ct_font, fill=(255, 255, 255))
                cy += 22

            # カード本文
            cb_lines = _wrap_text(item.get("body", ""), cb_font, card_w - 28, draw)
            cy += 4
            for line in cb_lines[:6]:
                draw.text((cx + 14, cy), line, font=cb_font, fill=(190, 210, 240))
                cy += 19

    # ── フッターノート ──
    if note_text:
        draw.rectangle([(0, H - 42), (W, H)], fill=(10, 18, 40))
        note_font = _get_font(13)
        draw.text((52, H - 30), note_text, font=note_font, fill=(140, 160, 190))

    return img.convert("RGB")


def generate_slide_image(
    title: str,
    narration: str,
    source_text: str = "",
    reference_images: list = None,
    brand_colors: list = None,
    source_image: Image.Image = None,
    use_claude: bool = True,
) -> Image.Image:
    """
    Claude でスライドコンテンツJSONを生成し、PILで直接描画する。
    """
    if not use_claude:
        return source_image

    data = generate_slide_json(title, narration, source_text, reference_images, brand_colors)

    # ブランドカラーをアクセントに強制適用
    if brand_colors and len(brand_colors) >= 1:
        def saturation(hex_color: str) -> float:
            try:
                r = int(hex_color[1:3], 16) / 255
                g = int(hex_color[3:5], 16) / 255
                b = int(hex_color[5:7], 16) / 255
                mx, mn = max(r, g, b), min(r, g, b)
                return (mx - mn) / mx if mx > 0 else 0
            except Exception:
                return 0
        best_accent = max(brand_colors[:4], key=saturation)
        if saturation(best_accent) > 0.3:
            data["accent"] = best_accent

    return render_slide_pil(data)
