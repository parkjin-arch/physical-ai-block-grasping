"""動作プリミティブ: move_to, open_gripper, close_gripper, release。

OMPLベースのplan_pathは依存解決で詰まりやすいため使わず、
目標関節角をinverse_kinematicsで求めて現在角から関節空間で
線形補間するだけの単純なmove_toで代用する。
"""
import numpy as np

from scene import MOTORS_DOF, FINGERS_DOF

GRIPPER_OPEN = 0.04
GRIPPER_CLOSE_FORCE = -0.5  # 指を閉じる力(負=閉方向)。位置制御だとキューブを弾くため力制御にする。


def move_to(scene, franka, pos, quat, steps=100, hold_steps=0, grip_force=None):
    """手先リンク'hand'をpos/quatへ、関節空間の線形補間で動かす。

    IKで目標関節角を求め、現在のアーム関節角から目標角まで`steps`ステップで
    線形補間しながらcontrol_dofs_positionを呼ぶ。

    grip_forceを指定すると、移動中も毎ステップ指に同じ力制御を掛け続ける。
    移動中に指への力指令を送らないと把持が緩んでキューブを落とすことがあるため、
    キューブを掴んだまま運ぶ区間ではこれを使う。
    """
    end_effector = franka.get_link("hand")
    qpos_goal = franka.inverse_kinematics(link=end_effector, pos=np.array(pos), quat=np.array(quat))

    qpos_now = franka.get_dofs_position(MOTORS_DOF).cpu().numpy()
    arm_goal = np.asarray(qpos_goal[:7])

    for i in range(1, steps + 1):
        alpha = i / steps
        waypoint = qpos_now + (arm_goal - qpos_now) * alpha
        franka.control_dofs_position(waypoint, MOTORS_DOF)
        if grip_force is not None:
            franka.control_dofs_force([grip_force, grip_force], FINGERS_DOF)
        scene.step()

    for _ in range(hold_steps):
        if grip_force is not None:
            franka.control_dofs_force([grip_force, grip_force], FINGERS_DOF)
        scene.step()

    return qpos_goal


def open_gripper(scene, franka, steps=40):
    franka.control_dofs_position([GRIPPER_OPEN, GRIPPER_OPEN], FINGERS_DOF)
    for _ in range(steps):
        scene.step()


def close_gripper(scene, franka, steps=60, force=GRIPPER_CLOSE_FORCE):
    # 位置制御で閉じるとキューブを弾いてしまうため、指は力制御で一定の把持力を与える。
    for _ in range(steps):
        franka.control_dofs_force([force, force], FINGERS_DOF)
        scene.step()


# 下向きに手先を向ける姿勢(Genesis公式サンプルの定番値)。
DOWN_QUAT = [0, 1, 0, 0]
APPROACH_Z = 0.25
GRASP_Z_OFFSET = 0.088  # キューブ中心から把持高さへのオフセット(フィンガー先端分)
LIFT_Z = 0.28


def pick_and_place(scene, franka, pick_xy, place_xy, cube_size=0.04):
    """pick_xyにあるキューブを掴み、place_xyまで運んで置く一連の動作。"""
    px, py = pick_xy
    grasp_z = 0.5 * cube_size + GRASP_Z_OFFSET

    move_to(scene, franka, pos=(px, py, APPROACH_Z), quat=DOWN_QUAT, steps=100)
    open_gripper(scene, franka, steps=30)
    move_to(scene, franka, pos=(px, py, grasp_z), quat=DOWN_QUAT, steps=100, hold_steps=20)
    close_gripper(scene, franka, steps=80)

    move_to(scene, franka, pos=(px, py, LIFT_Z), quat=DOWN_QUAT, steps=80, grip_force=GRIPPER_CLOSE_FORCE)

    tx, ty = place_xy
    move_to(scene, franka, pos=(tx, ty, LIFT_Z), quat=DOWN_QUAT, steps=120, grip_force=GRIPPER_CLOSE_FORCE)
    move_to(
        scene, franka, pos=(tx, ty, grasp_z), quat=DOWN_QUAT, steps=80, hold_steps=10, grip_force=GRIPPER_CLOSE_FORCE
    )

    open_gripper(scene, franka, steps=30)
    move_to(scene, franka, pos=(tx, ty, APPROACH_Z), quat=DOWN_QUAT, steps=60)
