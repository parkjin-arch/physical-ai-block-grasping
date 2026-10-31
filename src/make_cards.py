"""タイトルカード・アウトロカードの静止画(PNG)を生成する。動画編集用の一時スクリプト。"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FONT_PATH = r"C:\Windows\Fonts\meiryo.ttc"
FONT_PATH_BOLD = r"C:\Windows\Fonts\meiryob.ttc"

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "video_parts")
os.makedirs(OUT_DIR, exist_ok=True)

BG = (20, 28, 46)
FG = (235, 240, 250)
ACCENT = (120, 190, 255)


def draw_multiline_centered(draw, lines, y_start, font, fill, line_spacing=16):
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y), line, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def draw_multiline_left(draw, lines, y_start, x_start, font, fill, line_spacing=16):
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text((x_start, y), line, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def make_title_card():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_PATH_BOLD, 56)
    sub_font = ImageFont.truetype(FONT_PATH, 28)

    lines = ["言葉で指示されたブロックを掴む", "ロボットアーム"]
    y = draw_multiline_centered(d, lines, 250, title_font, FG, line_spacing=10)
    draw_multiline_centered(
        d,
        ["Genesisシミュレータ × ローカルLLM(Ollama) × カメラ画像からの物体位置推定"],
        y + 30,
        sub_font,
        ACCENT,
    )
    img.save(os.path.join(OUT_DIR, "title.png"))


def make_outro_card():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_PATH_BOLD, 44)
    body_font = ImageFont.truetype(FONT_PATH, 26)

    y = draw_multiline_centered(d, ["工夫した点"], 90, title_font, ACCENT, line_spacing=10)
    bullets = [
        "・OMPL非依存の独自move_to(IK + 関節空間線形補間)",
        "・力制御によるロバストな把持(位置制御だとキューブを弾く)",
        "・LLMバックエンドを抽象化し、APIクレジット不要の",
        "  ローカルLLM(Ollama)に切替可能な設計",
        "・深度画像の系統誤差(キューブ上面 vs 中心)を補正し、",
        "  位置推定誤差を約2cm→1〜4mmへ改善",
    ]
    draw_multiline_left(d, bullets, y + 40, 110, body_font, FG, line_spacing=18)
    img.save(os.path.join(OUT_DIR, "outro.png"))


def make_stage_card(filename, stage_label, lines):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    label_font = ImageFont.truetype(FONT_PATH_BOLD, 34)
    body_font = ImageFont.truetype(FONT_PATH, 40)

    draw_multiline_centered(d, [stage_label], 220, label_font, ACCENT, line_spacing=10)
    draw_multiline_centered(d, lines, 300, body_font, FG, line_spacing=16)
    img.save(os.path.join(OUT_DIR, filename))


if __name__ == "__main__":
    make_title_card()
    make_outro_card()
    make_stage_card(
        "stage1_intro.png",
        "STAGE 1 - 土台(AIなし)",
        ["固定キューブをIK + 関節空間補間で", "ピック&リフト"],
    )
    make_stage_card(
        "stage2_intro.png",
        "STAGE 2 - 自然言語 × LLM",
        ["ローカルLLM(Ollama)が指示文を解釈し", "3色のキューブから対象を選んで搬送"],
    )
    make_stage_card(
        "stage3_intro.png",
        "STAGE 3 - カメラ画像からの知覚",
        ["シミュレータの正解座標を使わず", "RGB-D画像だけでキューブ位置を推定"],
    )
    print("saved to", OUT_DIR)
