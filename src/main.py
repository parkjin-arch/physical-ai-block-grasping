"""Stage1/Stage2/Stage3デモ実行と録画。"""
import argparse
import csv
import os
import sys

import numpy as np

from scene import build_scene, build_scene_multi, CUBE_SIZE
from robot import move_to, open_gripper, close_gripper, pick_and_place
from llm_planner import choose_target, PlannerError
from perception import estimate_cube_position

# 下向きに手先を向ける姿勢(例の定番値)。グリッパーのfingertip先端は
# 手先リンク原点からz方向に少しオフセットがあるため、把持高さは
# キューブ中心よりやや上(0.5*CUBE_SIZE + 0.09付近)になる。
DOWN_QUAT = [0, 1, 0, 0]
CUBE_XY = (0.5, 0.0)

APPROACH_Z = 0.25
GRASP_Z = 0.5 * CUBE_SIZE + 0.088
LIFT_Z = 0.28
LIFT_SUCCESS_THRESHOLD = 0.15  # これ以上持ち上がっていれば把持成功とみなす


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_pick_and_lift(show_viewer=True, video_path=None):
    if video_path is None:
        video_path = os.path.join(PROJECT_ROOT, "outputs", "stage1_pick_and_lift.mp4")
    scene, franka, cube, cam = build_scene(show_viewer=show_viewer, enable_record_camera=True)

    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    if cam is not None:
        cam.start_recording(save_to_filename=video_path, fps=30)

    x, y = CUBE_XY
    print("[Stage1] 上空へ移動")
    move_to(scene, franka, pos=(x, y, APPROACH_Z), quat=DOWN_QUAT, steps=100)

    print("[Stage1] グリッパーを開く")
    open_gripper(scene, franka, steps=30)

    print("[Stage1] 下降")
    move_to(scene, franka, pos=(x, y, GRASP_Z), quat=DOWN_QUAT, steps=100, hold_steps=20)

    print("[Stage1] 把持(力制御で指を閉じる)")
    close_gripper(scene, franka, steps=80)

    print("[Stage1] 持ち上げ")
    move_to(scene, franka, pos=(x, y, LIFT_Z), quat=DOWN_QUAT, steps=100, hold_steps=30)
    # 持ち上げ中もグリップ力を維持し続ける(位置制御だけだと把持が緩む)。
    close_gripper(scene, franka, steps=40)

    if cam is not None:
        cam.stop_recording()

    cube_z = float(cube.get_pos()[2])
    success = cube_z > LIFT_SUCCESS_THRESHOLD
    print(f"[Stage1] キューブのz座標 = {cube_z:.4f} -> {'成功' if success else '失敗'}")
    return success


# Stage2: 自然言語指示で対象キューブを選び、指定した置き場所まで運ぶ。
DROP_ZONES = [(0.45, -0.35), (0.45, 0.35), (0.3, 0.0)]

# デモモード用の指示列。3個のキューブをそれぞれ別の置き場所へ運ぶ。
DEMO_INSTRUCTIONS = [
    "赤いブロックを取って",
    "青いブロックを持ち上げて",
    "緑のブロックをつかんで",
]


def _cubes_info(cubes):
    info = []
    for color, entity in cubes.items():
        pos = entity.get_pos()
        info.append({"color": color, "x": float(pos[0]), "y": float(pos[1])})
    return info


def run_stage2(instructions, show_viewer=True, video_path=None, seed=None, log_path=None):
    """instructionsに並んだ指示文を順番に実行する(1件でもデモでも同じ経路)。"""
    if video_path is None:
        video_path = os.path.join(PROJECT_ROOT, "outputs", "stage2_demo.mp4")
    if log_path is None:
        log_path = os.path.join(PROJECT_ROOT, "outputs", "stage2_log.txt")

    scene, franka, cubes, cam, _ = build_scene_multi(show_viewer=show_viewer, enable_record_camera=True, seed=seed)

    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    if cam is not None:
        cam.start_recording(save_to_filename=video_path, fps=30)

    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    results = []
    for step, instruction in enumerate(instructions):
        drop_xy = DROP_ZONES[step % len(DROP_ZONES)]
        cubes_info = _cubes_info(cubes)
        log(f"\n[Stage2] 指示 {step + 1}/{len(instructions)}: 「{instruction}」")
        log(f"[Stage2] キューブ一覧: {cubes_info}")

        try:
            decision = choose_target(instruction, cubes_info)
        except PlannerError as e:
            log(f"[Stage2] LLMの判断に失敗したためスキップ: {e}")
            results.append({"instruction": instruction, "success": False, "error": str(e)})
            continue

        target_color = decision["target_color"]
        log(f"[Stage2] LLMの判断 -> target_color={target_color}, reason={decision['reason']}")

        target_cube = cubes[target_color]
        pick_xy = (float(target_cube.get_pos()[0]), float(target_cube.get_pos()[1]))

        pick_and_place(scene, franka, pick_xy=pick_xy, place_xy=drop_xy)

        final_pos = target_cube.get_pos()
        dx = float(final_pos[0]) - drop_xy[0]
        dy = float(final_pos[1]) - drop_xy[1]
        success = (dx**2 + dy**2) ** 0.5 < 0.08
        log(f"[Stage2] 結果: 最終位置=({float(final_pos[0]):.3f}, {float(final_pos[1]):.3f}) -> {'成功' if success else '失敗'}")
        results.append({"instruction": instruction, "target_color": target_color, "success": success})

    if cam is not None:
        cam.stop_recording()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    return results


# Stage3: シミュレータの正解座標を使わず、カメラ画像からキューブ位置を推定して掴む。
PERCEPTION_SUCCESS_THRESHOLD = 0.03  # 推定座標と正解座標のユークリッド距離(m)がこれ未満なら検出成功


def run_stage3(instructions, show_viewer=True, video_path=None, seed=None, log_path=None, csv_path=None):
    """perception.pyで推定したキューブ位置を使ってpick_and_placeを行う。"""
    if video_path is None:
        video_path = os.path.join(PROJECT_ROOT, "outputs", "stage3_demo.mp4")
    if log_path is None:
        log_path = os.path.join(PROJECT_ROOT, "outputs", "stage3_log.txt")
    if csv_path is None:
        csv_path = os.path.join(PROJECT_ROOT, "outputs", "stage3_perception_errors.csv")

    scene, franka, cubes, cam, perception_cam = build_scene_multi(
        show_viewer=show_viewer, enable_record_camera=True, enable_perception_camera=True, seed=seed
    )

    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    if cam is not None:
        cam.start_recording(save_to_filename=video_path, fps=30)

    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    # --- 1. カメラ画像から全キューブの位置を推定し、正解座標との誤差を記録する ---
    csv_rows = []
    estimated_positions = {}
    for color, entity in cubes.items():
        true_pos = entity.get_pos()
        true_xyz = (float(true_pos[0]), float(true_pos[1]), float(true_pos[2]))

        est = estimate_cube_position(perception_cam, color)
        if est is None:
            log(f"[Stage3] {color}キューブの検出に失敗しました。正解座標にフォールバックします。")
            est_xyz = true_xyz
            error = None
        else:
            est_xyz = (float(est[0]), float(est[1]), float(est[2]))
            error = float(np.linalg.norm(np.array(est_xyz) - np.array(true_xyz)))

        estimated_positions[color] = est_xyz
        log(
            f"[Stage3] {color}: 推定=({est_xyz[0]:.3f},{est_xyz[1]:.3f},{est_xyz[2]:.3f}) "
            f"正解=({true_xyz[0]:.3f},{true_xyz[1]:.3f},{true_xyz[2]:.3f}) "
            f"誤差={'N/A' if error is None else f'{error:.4f}m'}"
        )
        csv_rows.append(
            {
                "color": color,
                "est_x": est_xyz[0],
                "est_y": est_xyz[1],
                "est_z": est_xyz[2],
                "true_x": true_xyz[0],
                "true_y": true_xyz[1],
                "true_z": true_xyz[2],
                "error_m": error,
            }
        )

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    # --- 2. 推定座標(正解座標ではない)をLLMに渡して対象キューブを選ばせ、推定座標でpick_and_placeする ---
    results = []
    for step, instruction in enumerate(instructions):
        drop_xy = DROP_ZONES[step % len(DROP_ZONES)]
        cubes_info = [
            {"color": c, "x": estimated_positions[c][0], "y": estimated_positions[c][1]} for c in cubes
        ]
        log(f"\n[Stage3] 指示 {step + 1}/{len(instructions)}: 「{instruction}」")
        log(f"[Stage3] カメラ推定によるキューブ一覧: {cubes_info}")

        try:
            decision = choose_target(instruction, cubes_info)
        except PlannerError as e:
            log(f"[Stage3] LLMの判断に失敗したためスキップ: {e}")
            results.append({"instruction": instruction, "success": False, "error": str(e)})
            continue

        target_color = decision["target_color"]
        log(f"[Stage3] LLMの判断 -> target_color={target_color}, reason={decision['reason']}")

        pick_xy = estimated_positions[target_color][:2]
        pick_and_place(scene, franka, pick_xy=pick_xy, place_xy=drop_xy)

        target_cube = cubes[target_color]
        final_pos = target_cube.get_pos()
        dx = float(final_pos[0]) - drop_xy[0]
        dy = float(final_pos[1]) - drop_xy[1]
        success = (dx**2 + dy**2) ** 0.5 < 0.08
        log(f"[Stage3] 結果: 最終位置=({float(final_pos[0]):.3f}, {float(final_pos[1]):.3f}) -> {'成功' if success else '失敗'}")
        results.append({"instruction": instruction, "target_color": target_color, "success": success})

    if cam is not None:
        cam.stop_recording()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["1", "2", "3"], default="2")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Stage2/3: 複数指示を連続実行するデモモード")
    parser.add_argument("--instruction", type=str, default=None, help="Stage2/3: 単一の指示文(未指定なら対話入力)")
    parser.add_argument("--seed", type=int, default=None, help="Stage2/3: キューブ配置の乱数シード")
    args = parser.parse_args()

    show_viewer = not args.no_viewer

    if args.stage == "1":
        ok = run_pick_and_lift(show_viewer=show_viewer)
        sys.exit(0 if ok else 1)
    else:
        if args.demo:
            instructions = DEMO_INSTRUCTIONS
        elif args.instruction:
            instructions = [args.instruction]
        else:
            instructions = [input("指示文を入力してください（例: 青いブロックを取って）: ")]

        if args.stage == "3":
            results = run_stage3(instructions, show_viewer=show_viewer, seed=args.seed)
        else:
            results = run_stage2(instructions, show_viewer=show_viewer, seed=args.seed)
        ok = all(r.get("success") for r in results)
        sys.exit(0 if ok else 1)
