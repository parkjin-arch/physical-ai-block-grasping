"""シーン構築: 地面・キューブ・Franka Pandaを配置する。"""
import genesis as gs


# Pandaの"ready pose"（定番の初期姿勢）。アームが自己干渉せず、手先が前方やや上を
# 向く安全な中立姿勢として広く使われている値。最後の2つはグリッパー(全開=0.04)。
READY_QPOS = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04]

MOTORS_DOF = list(range(7))
FINGERS_DOF = [7, 8]

CUBE_SIZE = 0.04


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
