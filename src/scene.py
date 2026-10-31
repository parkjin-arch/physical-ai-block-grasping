"""シーン構築: 地面・キューブ・Franka Pandaを配置する。"""
import random

import genesis as gs


# Pandaの"ready pose"（定番の初期姿勢）。アームが自己干渉せず、手先が前方やや上を
# 向く安全な中立姿勢として広く使われている値。最後の2つはグリッパー(全開=0.04)。
READY_QPOS = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04]

MOTORS_DOF = list(range(7))
FINGERS_DOF = [7, 8]

CUBE_SIZE = 0.04

# 色名 -> RGB（surfaceの色）。LLMにはこの色名をそのまま渡す。
CUBE_COLORS = {
    "red": (0.85, 0.1, 0.1),
    "blue": (0.1, 0.2, 0.85),
    "green": (0.1, 0.7, 0.2),
}

# キューブをランダム配置する範囲（Frankaの可到達範囲内、机の上を想定）。
WORKSPACE_X = (0.35, 0.62)
WORKSPACE_Y = (-0.28, 0.28)
MIN_CUBE_DIST = 0.12  # キューブ同士が重ならない/掴みやすいよう最低限離す距離


def _random_cube_positions(n, rng):
    positions = []
    for _ in range(n):
        for _attempt in range(200):
            x = rng.uniform(*WORKSPACE_X)
            y = rng.uniform(*WORKSPACE_Y)
            if all((x - px) ** 2 + (y - py) ** 2 >= MIN_CUBE_DIST**2 for px, py in positions):
                positions.append((x, y))
                break
        else:
            raise RuntimeError("キューブの非重複配置に失敗しました。ワークスペースを広げてください。")
    return positions


def build_scene(show_viewer: bool = True, enable_record_camera: bool = True):
    """地面・1個の固定キューブ・Franka Pandaを配置したシーンを構築する。

    Returns:
        scene, franka, cube, record_cam (record_camは enable_record_camera=False なら None)
    """
    gs.init(backend=gs.cpu)

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.01),
        viewer_options=gs.options.ViewerOptions(
            camera_pos=(1.2, -1.0, 1.0),
            camera_lookat=(0.3, 0.0, 0.2),
            camera_fov=40,
        ),
        show_viewer=show_viewer,
    )

    scene.add_entity(gs.morphs.Plane())

    cube = scene.add_entity(
        gs.morphs.Box(
            size=(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE),
            pos=(0.5, 0.0, CUBE_SIZE / 2),
        ),
        surface=gs.surfaces.Default(color=(0.8, 0.1, 0.1)),
    )

    franka = scene.add_entity(
        gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"),
    )

    record_cam = None
    if enable_record_camera:
        # ビューア用カメラとは別に、動画保存専用のカメラを置く（GUI=Falseで非表示）。
        record_cam = scene.add_camera(
            res=(1280, 720),
            pos=(1.2, -1.0, 0.8),
            lookat=(0.4, 0.0, 0.1),
            fov=35,
            GUI=False,
        )

    scene.build()

    # PDゲイン・出力制限はFrankaの定番値（Genesis公式サンプル準拠）。
    # アーム7関節は位置制御、指2本はKpを低めにして力制御と併用できるようにする。
    franka.set_dofs_kp(
        [4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100],
    )
    franka.set_dofs_kv(
        [450, 450, 350, 350, 200, 200, 200, 10, 10],
    )
    franka.set_dofs_force_range(
        [-87, -87, -87, -87, -12, -12, -12, -100, -100],
        [87, 87, 87, 87, 12, 12, 12, 100, 100],
    )

    # 初期姿勢をready poseに設定（ゼロ姿勢だとIK探索が不安定になりやすいため）。
    franka.set_qpos(READY_QPOS)
    scene.step()

    return scene, franka, cube, record_cam


def build_scene_multi(
    show_viewer: bool = True,
    enable_record_camera: bool = True,
    enable_perception_camera: bool = False,
    seed: int | None = None,
):
    """赤・青・緑のキューブ3個(位置ランダム)とFranka Pandaを配置する(Stage2/3用)。

    Returns:
        scene, franka, cubes, record_cam, perception_cam
        cubes: {"red": entity, "blue": entity, "green": entity}
        perception_cam: enable_perception_camera=Falseの場合はNone
    """
    rng = random.Random(seed)

    gs.init(backend=gs.cpu)

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.01),
        viewer_options=gs.options.ViewerOptions(
            camera_pos=(1.2, -1.0, 1.0),
            camera_lookat=(0.3, 0.0, 0.2),
            camera_fov=40,
        ),
        show_viewer=show_viewer,
    )

    scene.add_entity(gs.morphs.Plane())

    color_names = list(CUBE_COLORS.keys())
    positions = _random_cube_positions(len(color_names), rng)

    cubes = {}
    for name, (x, y) in zip(color_names, positions):
        cubes[name] = scene.add_entity(
            gs.morphs.Box(
                size=(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE),
                pos=(x, y, CUBE_SIZE / 2),
            ),
            surface=gs.surfaces.Default(color=CUBE_COLORS[name]),
        )

    franka = scene.add_entity(
        gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"),
    )

    record_cam = None
    if enable_record_camera:
        record_cam = scene.add_camera(
            res=(1280, 720),
            pos=(1.2, -1.0, 0.8),
            lookat=(0.4, 0.0, 0.1),
            fov=35,
            GUI=False,
        )

    perception_cam = None
    if enable_perception_camera:
        # 机をほぼ真上から見下ろす固定カメラ。キューブ検出・位置推定専用。
        perception_cam = scene.add_camera(
            res=(640, 480),
            pos=(0.5, 0.0, 1.1),
            lookat=(0.5, 0.0, 0.0),
            fov=50,
            GUI=False,
        )

    scene.build()

    franka.set_dofs_kp(
        [4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100],
    )
    franka.set_dofs_kv(
        [450, 450, 350, 350, 200, 200, 200, 10, 10],
    )
    franka.set_dofs_force_range(
        [-87, -87, -87, -87, -12, -12, -12, -100, -100],
        [87, 87, 87, 87, 12, 12, 12, 100, 100],
    )

    franka.set_qpos(READY_QPOS)
    scene.step()

    return scene, franka, cubes, record_cam, perception_cam
