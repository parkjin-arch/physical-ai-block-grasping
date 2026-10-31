"""提出用動画を組み立てる(一時的な動画編集スクリプト)。

タイトルカード -> Stage1説明 -> Stage1クリップ -> Stage2説明 -> Stage2クリップ(字幕付)
-> Stage3説明 -> Stage3クリップ(字幕付) -> アウトロカード、の順に結合してoutputs/submission_video.mp4を作る。
"""
import os
import subprocess

import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
PARTS = os.path.join(OUTPUTS, "video_parts")
CAPTIONS = os.path.join(PARTS, "captions")
SEGMENTS = os.path.join(PARTS, "segments")
os.makedirs(SEGMENTS, exist_ok=True)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1280, 720, 30


def fpath(path: str) -> str:
    """ffmpeg filtergraph内のオプション値として安全なパス文字列に変換する。

    drawtextのオプションは':'区切りのため、Windowsパスのドライブ文字コロンや
    バックスラッシュをエスケープする必要がある。
    """
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    return p


FONT = fpath(r"C:\Windows\Fonts\meiryo.ttc")

BANNER_STYLE = (
    f"fontfile='{FONT}':fontsize=28:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=10"
)
CAPTION_STYLE = (
    f"fontfile='{FONT}':fontsize=30:fontcolor=yellow:box=1:boxcolor=black@0.65:boxborderw=12"
)


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{result.stderr[-4000:]}")


def image_to_clip(image_path, out_path, duration):
    run(
        [
            FFMPEG,
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-t",
            str(duration),
            "-vf",
            f"scale={W}:{H},format=yuv420p",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            out_path,
        ]
    )


def get_duration(path):
    result = subprocess.run(
        [FFMPEG, "-i", path],
        capture_output=True,
        text=True,
    )
    for line in result.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split(",")[0].split("Duration:")[1].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"duration not found for {path}")


def caption_clip(src_path, out_path, banner_textfile, timed_captions=None, speed=1.0):
    """banner_textfile: 常時表示するバナー字幕のtextfileパス
    timed_captions: [(textfile, start_sec, end_sec), ...] 省略可
    """
    filters = [f"scale={W}:{H}", "format=yuv420p"]
    if speed != 1.0:
        filters.append(f"setpts={1/speed}*PTS")

    draw_filters = [f"drawtext=textfile='{fpath(banner_textfile)}':{BANNER_STYLE}:x=(w-text_w)/2:y=h-80"]
    if timed_captions:
        for textfile, start, end in timed_captions:
            draw_filters.append(
                f"drawtext=textfile='{fpath(textfile)}':{CAPTION_STYLE}:x=(w-text_w)/2:y=40:"
                f"enable='between(t,{start},{end})'"
            )

    vf = ",".join(filters + draw_filters)

    run(
        [
            FFMPEG,
            "-y",
            "-i",
            src_path,
            "-vf",
            vf,
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            out_path,
        ]
    )


def static_overlay_clip(src_path, out_path, banner_textfile, extra_textfile, timed_captions):
    filters = [f"scale={W}:{H}", "format=yuv420p"]
    draw_filters = [
        f"drawtext=textfile='{fpath(banner_textfile)}':{BANNER_STYLE}:x=(w-text_w)/2:y=h-80",
        f"drawtext=textfile='{fpath(extra_textfile)}':fontfile='{FONT}':fontsize=24:fontcolor=white:"
        f"box=1:boxcolor=black@0.55:boxborderw=8:x=20:y=20",
    ]
    for textfile, start, end in timed_captions:
        draw_filters.append(
            f"drawtext=textfile='{fpath(textfile)}':{CAPTION_STYLE}:x=(w-text_w)/2:y=70:"
            f"enable='between(t,{start},{end})'"
        )
    vf = ",".join(filters + draw_filters)
    run(
        [
            FFMPEG,
            "-y",
            "-i",
            src_path,
            "-vf",
            vf,
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            out_path,
        ]
    )


def main():
    # --- タイトル/説明/アウトロカード ---
    image_to_clip(os.path.join(PARTS, "title.png"), os.path.join(SEGMENTS, "00_title.mp4"), 5)
    image_to_clip(os.path.join(PARTS, "stage1_intro.png"), os.path.join(SEGMENTS, "01_stage1_intro.mp4"), 3)
    image_to_clip(os.path.join(PARTS, "stage2_intro.png"), os.path.join(SEGMENTS, "03_stage2_intro.mp4"), 3)
    image_to_clip(os.path.join(PARTS, "stage3_intro.png"), os.path.join(SEGMENTS, "05_stage3_intro.mp4"), 3)
    image_to_clip(os.path.join(PARTS, "outro.png"), os.path.join(SEGMENTS, "07_outro.mp4"), 7)

    # --- Stage1クリップ(バナーのみ) ---
    caption_clip(
        os.path.join(OUTPUTS, "stage1_pick_and_lift.mp4"),
        os.path.join(SEGMENTS, "02_stage1.mp4"),
        os.path.join(CAPTIONS, "stage1_caption.txt"),
    )

    # --- Stage2クリップ(バナー+3件の指示タイミング字幕) ---
    stage2_dur = get_duration(os.path.join(OUTPUTS, "stage2_demo.mp4"))
    third = stage2_dur / 3
    stage2_captions = [
        (os.path.join(CAPTIONS, "stage2_cap1.txt"), 0, third),
        (os.path.join(CAPTIONS, "stage2_cap2.txt"), third, 2 * third),
        (os.path.join(CAPTIONS, "stage2_cap3.txt"), 2 * third, stage2_dur),
    ]
    caption_clip(
        os.path.join(OUTPUTS, "stage2_demo.mp4"),
        os.path.join(SEGMENTS, "04_stage2.mp4"),
        os.path.join(CAPTIONS, "stage2_banner.txt"),
        timed_captions=stage2_captions,
    )

    # --- Stage3クリップ(バナー+誤差数値+3件の指示タイミング字幕) ---
    stage3_dur = get_duration(os.path.join(OUTPUTS, "stage3_demo.mp4"))
    third3 = stage3_dur / 3
    stage3_captions = [
        (os.path.join(CAPTIONS, "stage3_cap1.txt"), 0, third3),
        (os.path.join(CAPTIONS, "stage3_cap2.txt"), third3, 2 * third3),
        (os.path.join(CAPTIONS, "stage3_cap3.txt"), 2 * third3, stage3_dur),
    ]
    static_overlay_clip(
        os.path.join(OUTPUTS, "stage3_demo.mp4"),
        os.path.join(SEGMENTS, "06_stage3.mp4"),
        os.path.join(CAPTIONS, "stage3_banner.txt"),
        os.path.join(CAPTIONS, "stage3_err.txt"),
        stage3_captions,
    )

    # --- 結合 ---
    order = [
        "00_title.mp4",
        "01_stage1_intro.mp4",
        "02_stage1.mp4",
        "03_stage2_intro.mp4",
        "04_stage2.mp4",
        "05_stage3_intro.mp4",
        "06_stage3.mp4",
        "07_outro.mp4",
    ]
    concat_list_path = os.path.join(SEGMENTS, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for name in order:
            p = os.path.join(SEGMENTS, name).replace("\\", "/")
            f.write(f"file '{p}'\n")

    final_path = os.path.join(OUTPUTS, "submission_video.mp4")
    run(
        [
            FFMPEG,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c",
            "copy",
            final_path,
        ]
    )
    print("DONE:", final_path)


if __name__ == "__main__":
    main()
