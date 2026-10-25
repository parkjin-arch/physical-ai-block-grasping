"""動作プリミティブ: move_to, open_gripper, close_gripper, release。

OMPLベースのplan_pathは依存解決で詰まりやすいため使わず、
目標関節角をinverse_kinematicsで求めて現在角から関節空間で
線形補間するだけの単純なmove_toで代用する。
"""
import numpy as np

from scene import MOTORS_DOF, FINGERS_DOF

GRIPPER_OPEN = 0.04
GRIPPER_CLOSE_FORCE = -0.5  # 指を閉じる力(負=閉方向)。位置制御だとキューブを弾くため力制御にする。


def move_to(scene, franka, pos, quat, steps=100, hold_steps=0):
    """手先リンク'hand'をpos/quatへ、関節空間の線形補間で動かす。

    IKで目標関節角を求め、現在のアーム関節角から目標角まで`steps`ステップで
    線形補間しながらcontrol_dofs_positionを呼ぶ。指の目標値はIK結果のうち
    最後の2要素をそのまま使う（呼び出し側がgripper開閉を別途制御する前提）。
    """
    end_effector = franka.get_link("hand")
    qpos_goal = franka.inverse_kinematics(link=end_effector, pos=np.array(pos), quat=np.array(quat))

    qpos_now = franka.get_dofs_position(MOTORS_DOF).cpu().numpy()
    arm_goal = np.asarray(qpos_goal[:7])

    for i in range(1, steps + 1):
        alpha = i / steps
        waypoint = qpos_now + (arm_goal - qpos_now) * alpha
        franka.control_dofs_position(waypoint, MOTORS_DOF)
        scene.step()

    for _ in range(hold_steps):
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
