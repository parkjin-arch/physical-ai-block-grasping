"""Stage1: 固定キューブをFranka Pandaでピック＆リフトし、録画・成功判定を行う。"""
import os
import sys

from scene import build_scene, CUBE_SIZE
from robot import move_to, open_gripper, close_gripper

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


if __name__ == "__main__":
    show_viewer = "--no-viewer" not in sys.argv
    ok = run_pick_and_lift(show_viewer=show_viewer)
    sys.exit(0 if ok else 1)
