"""
app.py
資料 → 動画教材作成AI
Streamlit メインアプリ
"""

import os
import tempfile
import streamlit as st
from dotenv import load_dotenv

from document_parser import load_multiple_files, parse_url, extract_site_images
from script_generator import generate_script, restructure_slides, generate_full_script, VOICE_OPTIONS
from slide_designer import generate_slide_image, build_design_context
from video_builder import build_single_clip, merge_clips
import heygen_avatar

load_dotenv()

anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))

# ページ設定
st.set_page_config(
    page_title="社内資料 → 動画教材 AI",
    page_icon="📹",
    layout="wide"
)

# カスタムCSS（HIROTECブランドカラー適用）
st.markdown("""
<style>
/* ── ヘッダーバー ── */
[data-testid="stAppViewContainer"] > .main {
    background-color: #ffffff;
}
[data-testid="stHeader"] {
    background-color: #ffffff;
    border-bottom: 3px solid #1e5cb3;
}

/* ── サイドバー ── */
[data-testid="stSidebar"] {
    background-color: #f0f4f8;
    border-right: 1px solid #d0dcea;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #1e5cb3;
}

/* ── プライマリボタン ── */
.stButton > button[kind="primary"] {
    background-color: #1e5cb3;
    color: #ffffff;
    border: none;
    border-radius: 3px;
    font-weight: bold;
    letter-spacing: 0.03em;
}
.stButton > button[kind="primary"]:hover {
    background-color: #174d9a;
    color: #ffffff;
}

/* ── セカンダリボタン ── */
.stButton > button[kind="secondary"] {
    border: 2px solid #1e5cb3;
    color: #1e5cb3;
    border-radius: 3px;
    font-weight: bold;
}
.stButton > button[kind="secondary"]:hover {
    background-color: #e8eff9;
}

/* ── タブ ── */
.stTabs [data-baseweb="tab-list"] {
    border-bottom: 2px solid #1e5cb3;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #1e5cb3;
    border-bottom: 3px solid #1e5cb3;
    font-weight: bold;
}

/* ── divider ── */
hr {
    border-color: #d0dcea;
}

/* ── タイトル ── */
h1 {
    color: #1a2a4a !important;
    border-left: 5px solid #1e5cb3;
    padding-left: 14px;
}
</style>
""", unsafe_allow_html=True)

# ヘッダー
st.title("資料 → 動画教材作成AI")
st.caption("PDF・PowerPoint・画像・ウェブサイトのURLなどを複数アップロードするだけで、ナレーション付き教育動画を自動生成します。（リップシンクアバター機能作成中）")
st.divider()

# ────────────────────────────────────────
# サイドバー：設定
# ────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

    voice_label = st.selectbox(
        "ナレーター音声（OpenAI TTS）",
        list(VOICE_OPTIONS.keys()),
        index=0
    )
    voice = VOICE_OPTIONS[voice_label]

    st.divider()

    # スライド画像生成モード
    gemini_ok = bool(os.getenv("GEMINI_API_KEY"))
    slide_mode_options = ["Imagen 4.0 + PIL（AI背景画像）", "Claude（グラデーション背景）"] if gemini_ok else ["Claude（グラデーション背景）"]
    slide_mode_label = st.selectbox(
        "スライド画像生成モード",
        slide_mode_options,
        index=0,
        help="GeminiモードはGEMINI_API_KEYが必要です"
    )
    slide_mode = "gemini" if "Imagen" in slide_mode_label else "claude"

    st.divider()

    # APIキー状態
    openai_ok = bool(os.getenv("OPENAI_API_KEY"))
    st.markdown("**APIキー状態**")
    st.caption(f"{'✅' if openai_ok else '❌'} OpenAI（台本・音声）")
    st.caption(f"{'✅' if anthropic_ok else '❌'} Anthropic Claude（スライド生成）")
    st.caption(f"{'✅' if gemini_ok else '❌'} Gemini（AI背景画像）")

    # 抽出済みブランドカラー表示
    design_ctx = st.session_state.get("design_context")
    if design_ctx and design_ctx.get("brand_colors"):
        st.divider()
        st.markdown("**🎨 抽出済みブランドカラー**")
        cols = st.columns(len(design_ctx["brand_colors"]))
        for col, hex_color in zip(cols, design_ctx["brand_colors"]):
            with col:
                st.markdown(
                    f'<div style="background:{hex_color};height:28px;border-radius:4px;'
                    f'border:1px solid #444" title="{hex_color}"></div>',
                    unsafe_allow_html=True
                )
                st.caption(hex_color)

    # デバッグモード
    st.divider()
    if "debug_mode" not in st.session_state:
        st.session_state["debug_mode"] = False

    if st.session_state["debug_mode"]:
        if st.button("🔓 デバッグモード ON（クリックで解除）", use_container_width=True):
            st.session_state["debug_mode"] = False
            st.rerun()

        # デバッグ専用ツール
        if gemini_ok and st.button("🔬 Geminiモデル一覧", use_container_width=True):
            import os as _os
            try:
                from google import genai as _genai
                _client = _genai.Client(api_key=_os.getenv("GEMINI_API_KEY"))
                models = [m.name for m in _client.models.list() if "generat" in m.name.lower()]
                st.caption("\n".join(models[:20]))
            except Exception as e:
                st.error(str(e))

        if gemini_ok and st.button("🔬 Gemini接続テスト", use_container_width=True):
            with st.spinner("Gemini APIをテスト中..."):
                from slide_designer import _generate_gemini_background
                test_img, test_err = _generate_gemini_background("テスト", "製造業の研修スライドです")
            if test_img:
                st.success("✅ Gemini画像生成成功！")
                st.image(test_img, use_container_width=True)
            else:
                st.error(f"❌ Geminiエラー:\n{test_err}")
    else:
        with st.expander("🔧 デバッグモード"):
            debug_pw = st.text_input("パスワード", type="password", key="debug_pw_input")
            if st.button("ログイン", use_container_width=True):
                if debug_pw == os.getenv("DEBUG_PASSWORD", "debug"):
                    st.session_state["debug_mode"] = True
                    st.rerun()
                else:
                    st.error("パスワードが違います")

    st.divider()
    st.markdown("**使い方**")
    st.markdown("""
1. 複数の資料（PDF/PPTX/画像）をアップロード
2. WebページのURLを追加（任意）
3. 「▶ スライド生成」を押す
4. タイムラインで各スライドを確認・編集
5. 「全スライドを動画化」でMP4完成
6. スライドごとに再生成も可能
""")

# ────────────────────────────────────────
# ファイルアップロード
# ────────────────────────────────────────
uploaded_files = st.file_uploader(
    "📂 資料をアップロード（複数可）",
    type=["pdf", "pptx", "png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    help="PDF・PowerPoint・画像ファイルを複数まとめてアップロードできます"
)

if uploaded_files:
    file_summary = ", ".join(f.name for f in uploaded_files)
    st.success(f"✅ {len(uploaded_files)} ファイルを読み込みました：{file_summary}")

# ────────────────────────────────────────
# URL入力
# ────────────────────────────────────────
st.markdown("**🌐 WebページURLを追加（任意）**")

if "url_list" not in st.session_state:
    st.session_state["url_list"] = []

url_col, btn_col = st.columns([4, 1])
with url_col:
    new_url = st.text_input(
        "URL",
        placeholder="https://example.com/product-page",
        label_visibility="collapsed",
        key="url_input"
    )
with btn_col:
    if st.button("➕ 追加", use_container_width=True) and new_url.strip():
        url = new_url.strip()
        if url not in st.session_state["url_list"]:
            st.session_state["url_list"].append(url)
            st.rerun()

if st.session_state["url_list"]:
    st.markdown("**追加済みURL：**")
    for i, url in enumerate(st.session_state["url_list"]):
        c1, c2 = st.columns([6, 1])
        with c1:
            st.caption(f"🔗 {url}")
        with c2:
            if st.button("✕", key=f"del_url_{i}"):
                st.session_state["url_list"].pop(i)
                st.rerun()

# ────────────────────────────────────────
# STEP 1-2: スライド生成ボタン → 解析 → 台本生成
# ────────────────────────────────────────
has_input = uploaded_files or st.session_state.get("url_list")

st.divider()
run_pipeline = st.button(
    "▶ スライド生成",
    type="primary",
    use_container_width=True,
    disabled=not has_input,
)

if run_pipeline:
    # セッションをリセット
    for key in ["scripts", "slide_clip_paths", "slide_tmp_dir", "final_video_path",
                "editing_slide_idx", "heygen_paths"]:
        st.session_state.pop(key, None)

    # 一時ファイルに保存
    tmp_paths = []
    for uf in uploaded_files:
        suffix = os.path.splitext(uf.name)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(uf.read())
            tmp_paths.append(f.name)

    with st.status("📄 資料を解析中...", expanded=True) as status:
        try:
            pages = load_multiple_files(tmp_paths)
            if pages:
                status.write(f"📁 ファイル: {len(pages)} スライドを検出")
            url_pages = []
            for url in st.session_state.get("url_list", []):
                status.write(f"🌐 取得中: {url}")
                try:
                    url_result = parse_url(url)
                    url_pages.extend(url_result)
                    status.write(f"  → {len(url_result)} スライドを生成")
                except Exception as e:
                    status.write(f"  ⚠️ スキップ ({e})")
            pages.extend(url_pages)
            for i, p in enumerate(pages):
                p["page"] = i + 1
            if not pages:
                st.error("解析できるコンテンツがありませんでした。")
                st.stop()
            status.update(label=f"📄 合計 {len(pages)} スライドを検出", state="complete")
        except Exception as e:
            st.error(f"資料の読み込みに失敗しました: {e}")
            st.stop()

    with st.status("🎨 デザインコンテキストを抽出中...", expanded=False) as dc_status:
        url_ref_images = []
        for url in st.session_state.get("url_list", []):
            dc_status.write(f"🌐 画像取得中: {url}")
            imgs = extract_site_images(url)
            url_ref_images.extend(imgs)
            dc_status.write(f"  → {len(imgs)} 枚取得")
        design_ctx = build_design_context(pages, url_ref_images)
        dc_status.write(f"✅ 参照画像 {len(design_ctx['reference_images'])} 枚 / カラー {len(design_ctx['brand_colors'])} 色抽出")
        st.session_state["design_context"] = design_ctx
        dc_status.update(label="🎨 デザインコンテキスト抽出完了", state="complete")

    with st.status("📝 GPT-4o で全体台本を生成中...", expanded=True) as script_status:
        before = len(pages)
        scripts = generate_full_script(pages)
        script_status.update(
            label=f"✅ 台本生成完了：{before} ページ → {len(scripts)} スライドに再編成",
            state="complete"
        )
    st.success(f"✅ {len(scripts)} スライドの台本を生成しました")

    can_generate = (slide_mode == "claude" and anthropic_ok) or (slide_mode == "gemini" and gemini_ok)
    if can_generate:
        design_ctx = st.session_state.get("design_context", {})
        ref_imgs = design_ctx.get("reference_images", [])
        brand_colors = design_ctx.get("brand_colors", [])
        mode_label = "Imagen 4.0" if slide_mode == "gemini" else "Claude"
        img_progress = st.progress(0, text=f"{mode_label} でスライド画像を生成中...")
        img_errors = []
        for i, s in enumerate(scripts):
            img_progress.progress(
                (i + 1) / len(scripts),
                text=f"スライド画像生成中... {i+1}/{len(scripts)}"
            )
            title = s.get("restructured_title") or s.get("text", "").split("\n")[0][:40]
            try:
                new_img = generate_slide_image(
                    title, s["narration"], s.get("text", ""),
                    ref_imgs, brand_colors,
                    source_image=s.get("image"),
                    use_claude=True,
                    mode=slide_mode,
                    slide_index=i,
                )
                scripts[i]["image"] = new_img
            except Exception as e:
                img_errors.append(f"スライド {i+1}: {e}")
        img_progress.empty()
        if img_errors:
            st.warning("一部のスライド画像生成に失敗しました:\n" + "\n".join(img_errors))
        else:
            st.success(f"✅ {len(scripts)} 枚のスライド画像を生成しました（{mode_label}）")
    else:
        st.info("💡 APIキーを設定するとスライド画像も自動生成されます")

    slide_tmp_dir = tempfile.mkdtemp()
    st.session_state["slide_tmp_dir"] = slide_tmp_dir
    st.session_state["scripts"] = scripts
    st.session_state["slide_clip_paths"] = [None] * len(scripts)

# ────────────────────────────────────────
# メインエディター + 動画生成
# ────────────────────────────────────────
if "scripts" in st.session_state:
    scripts = st.session_state["scripts"]
    slide_clip_paths = st.session_state.get("slide_clip_paths", [None] * len(scripts))
    slide_tmp_dir = st.session_state.get("slide_tmp_dir", tempfile.mkdtemp())

    # ────────────────────────────────────────
    # スライド拡大モーダル（@st.dialog）
    # ────────────────────────────────────────
    @st.dialog("スライド詳細", width="large")
    def show_slide_modal(idx):
        s = st.session_state["scripts"][idx]
        col_slide, col_narration = st.columns([3, 2])
        with col_slide:
            if s.get("image"):
                st.image(s["image"], use_container_width=True)
            else:
                st.info("画像なし")
            st.caption(f"スライド {idx + 1}  |  {s.get('source', '')}")
        with col_narration:
            modal_edit_key = f"modal_editing_{idx}"
            if modal_edit_key not in st.session_state:
                st.session_state[modal_edit_key] = False

            header_col, btn_col = st.columns([2, 1])
            with header_col:
                st.markdown("#### 原稿")
            with btn_col:
                if st.session_state[modal_edit_key]:
                    if st.button("💾 保存", key=f"modal_save_{idx}", type="primary", use_container_width=True):
                        new_text = st.session_state.get(f"modal_narration_{idx}", s["narration"])
                        st.session_state["scripts"][idx]["narration"] = new_text
                        st.session_state[modal_edit_key] = False
                        st.rerun()
                else:
                    if st.button("✏️ 編集", key=f"modal_edit_{idx}", use_container_width=True):
                        st.session_state[modal_edit_key] = True

            if st.session_state[modal_edit_key]:
                st.text_area(
                    "ナレーション台本",
                    value=s["narration"],
                    key=f"modal_narration_{idx}",
                    height=280,
                    label_visibility="collapsed",
                )
            else:
                st.markdown(
                    f'<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;'
                    f'padding:16px;font-size:15px;line-height:1.9;color:#333;white-space:pre-wrap">'
                    f'{s.get("narration", "")}</div>',
                    unsafe_allow_html=True
                )

    tab_editor, tab_heygen = st.tabs(["🎬 タイムライン エディター", "🧑‍💼 HeyGen アバター版"])

    # ════════════════════════════════════════
    # タイムライン エディター タブ
    # ════════════════════════════════════════
    with tab_editor:
        st.subheader("🎞️ スライドタイムライン")

        # ────────────────────────────────────────
        # アクションボタン（上部）
        # ────────────────────────────────────────
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            regen_label = "🎨 全スライドの画像を再生成（Imagen 4.0 + PIL）" if slide_mode == "gemini" else "🎨 全スライドの画像を再生成（Claude）"
            if st.button(regen_label, use_container_width=True, key="btn_gen_all_images"):
                design_ctx = st.session_state.get("design_context", {})
                ref_imgs = design_ctx.get("reference_images", [])
                brand_colors = design_ctx.get("brand_colors", [])
                progress_bar = st.progress(0)
                errors = []
                for i, s in enumerate(scripts):
                    progress_bar.progress((i + 1) / len(scripts), text=f"Claude 画像生成中... {i+1}/{len(scripts)}")
                    title = s.get("restructured_title") or s.get("text", "").split("\n")[0][:40]
                    try:
                        scripts[i]["image"] = generate_slide_image(
                            title, s["narration"], s.get("text", ""), ref_imgs, brand_colors,
                            source_image=s.get("image"),
                            use_claude=True,
                            mode=slide_mode,
                            slide_index=i,
                        )
                    except Exception as e:
                        errors.append(f"スライド {i+1}: {e}")
                progress_bar.empty()
                st.session_state["scripts"] = scripts
                if errors:
                    st.warning("\n".join(errors))
                else:
                    st.success(f"✅ {len(scripts)} 枚の画像を再生成しました")
                st.rerun()
        with action_col2:
            if st.button("▶️ 全スライドを動画化", type="primary", use_container_width=True, key="btn_build_all"):
                progress_bar = st.progress(0, text="動画を生成中...")
                new_clip_paths = []
                for i, s in enumerate(scripts):
                    progress_bar.progress((i + 1) / len(scripts), text=f"生成中... {i+1}/{len(scripts)}")
                    clip_path = os.path.join(slide_tmp_dir, f"clip_{i:03d}.mp4")
                    try:
                        build_single_clip(s, clip_path, voice)
                        new_clip_paths.append(clip_path)
                    except Exception as e:
                        st.error(f"スライド {i+1} エラー: {e}")
                        new_clip_paths.append(None)
                progress_bar.empty()
                st.session_state["slide_clip_paths"] = new_clip_paths
                if all(p and os.path.exists(p) for p in new_clip_paths):
                    final_path = os.path.join(slide_tmp_dir, "final.mp4")
                    with st.spinner("最終動画を結合中..."):
                        merge_clips(new_clip_paths, final_path)
                    st.session_state["final_video_path"] = final_path
                    st.success("✅ 動画が完成しました！")
                else:
                    st.warning("一部のスライドの生成に失敗しました。")
                st.rerun()
        with action_col3:
            all_ready = all(p and os.path.exists(p) for p in slide_clip_paths)
            if all_ready and "final_video_path" in st.session_state:
                if st.button("🔗 最終動画を再結合", use_container_width=True, key="btn_remerge"):
                    final_path = os.path.join(slide_tmp_dir, "final.mp4")
                    with st.spinner("再結合中..."):
                        merge_clips(slide_clip_paths, final_path)
                    st.session_state["final_video_path"] = final_path
                    st.success("✅ 再結合完了")
                    st.rerun()

        st.divider()

        # ────────────────────────────────────────
        # スライドリスト（縦並び：サムネイル + 原稿）
        # ────────────────────────────────────────
        for idx in range(len(scripts)):
            s = scripts[idx]
            clip_path = slide_clip_paths[idx] if idx < len(slide_clip_paths) else None
            is_done = clip_path and os.path.exists(clip_path)
            is_editing = st.session_state.get("editing_slide_idx") == idx

            col_thumb, col_narration = st.columns([1, 2])

            with col_thumb:
                # サムネイル
                if s.get("image"):
                    st.markdown(
                        '<div style="border:2px solid #ddd;border-radius:6px;overflow:hidden">',
                        unsafe_allow_html=True
                    )
                    st.image(s["image"], use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div style="background:#444;height:160px;display:flex;align-items:center;'
                        f'justify-content:center;border-radius:6px;color:white;font-size:14px">'
                        f'スライド {idx+1}</div>',
                        unsafe_allow_html=True
                    )

                status_icon = "✅" if is_done else "⏳"
                source = s.get("source", "")
                short_source = (source[:18] + "…") if len(source) > 18 else source
                st.caption(f"{status_icon} {idx+1}  |  {short_source}")

                if st.button("🔍 拡大", key=f"btn_zoom_{idx}", use_container_width=True):
                    show_slide_modal(idx)

            with col_narration:
                title_col, btn_col = st.columns([3, 1])
                with title_col:
                    st.markdown(f"**スライド {idx+1} 原稿**")
                with btn_col:
                    if is_editing:
                        if st.button("💾 保存", key=f"btn_save_{idx}", type="primary", use_container_width=True):
                            new_narration = st.session_state.get(f"narration_edit_{idx}", s["narration"])
                            scripts[idx]["narration"] = new_narration
                            st.session_state["scripts"] = scripts
                            st.session_state["editing_slide_idx"] = None
                            st.rerun()
                    else:
                        if st.button("✏️ 編集", key=f"btn_edit_{idx}", use_container_width=True):
                            st.session_state["editing_slide_idx"] = idx
                            st.rerun()

                if is_editing:
                    st.text_area(
                        "ナレーション台本",
                        value=s["narration"],
                        key=f"narration_edit_{idx}",
                        height=180,
                        label_visibility="collapsed",
                    )
                else:
                    narration_text = s.get("narration", "（未生成）")
                    st.markdown(
                        f'<div style="background:#fafafa;border:1px solid #e0e0e0;border-radius:8px;'
                        f'padding:18px;font-size:15px;line-height:1.9;color:#333;'
                        f'min-height:160px;white-space:pre-wrap">{narration_text}</div>',
                        unsafe_allow_html=True
                    )

            st.divider()

        # ────────────────
        # 完成動画プレイヤー
        # ────────────────
        if "final_video_path" in st.session_state:
            final_path = st.session_state["final_video_path"]
            if os.path.exists(final_path):
                st.subheader("🎬 完成動画")
                st.video(final_path)
                with open(final_path, "rb") as f:
                    st.download_button(
                        "⬇️ 動画をダウンロード（MP4）",
                        data=f,
                        file_name="training_video.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )

    # ════════════════════════════════════════
    # HeyGen アバター版タブ
    # ════════════════════════════════════════
    with tab_heygen:
        @st.dialog("🚧 アバター機能は作成中です")
        def _heygen_wip_dialog():
            st.write("この機能は現在開発中です。しばらくお待ちください。")
            if st.button("閉じる", use_container_width=True):
                st.rerun()

        if st.button("🧑‍💼 HeyGen アバター動画を生成する", type="primary", use_container_width=True):
            _heygen_wip_dialog()
