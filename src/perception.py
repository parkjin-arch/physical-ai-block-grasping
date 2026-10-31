"""カメラ画像(RGB-D)からキューブの3次元位置を推定する(Stage3)。

シミュレータの正解座標(entity.get_pos())は使わず、固定カメラのRGB画像から
色でキューブ領域を検出し、深度画像から得た距離とカメラの内部/外部パラメータを
使って3次元座標へ逆投影する。
"""
import numpy as np

from scene import CUBE_COLORS, CUBE_SIZE


def _color_mask(rgb: np.ndarray, color_rgb: tuple, tol: int = 40) -> np.ndarray:
    """rgb: (H, W, 3) uint8。指定色に近い画素をTrueにしたマスクを返す。"""
    target = np.array([c * 255 for c in color_rgb])
    diff = np.abs(rgb.astype(np.int16) - target.astype(np.int16))
    return np.all(diff <= tol, axis=-1)


def detect_cube_pixel(rgb: np.ndarray, color_name: str):
    """色名からマスクを作り、重心ピクセル座標(u, v)を返す。見つからなければNone。"""
    mask = _color_mask(rgb, CUBE_COLORS[color_name])
    ys, xs = np.nonzero(mask)
    if len(xs) < 5:  # ノイズ程度の画素数しかなければ検出失敗とみなす
        return None
    u = float(np.median(xs))
    v = float(np.median(ys))
    return u, v, mask


def backproject(cam, u: float, v: float, depth: float) -> np.ndarray:
    """ピクセル座標(u, v)と深度(カメラ座標系でのz)から、ワールド座標の3次元点を求める。

    cam.intrinsics: 3x3 Kマトリクス(fx=fy=f, cx, cy)
    cam.extrinsics: 4x4 world->camera変換(OpenCV慣習: x右, y下, z前)
    """
    K = cam.intrinsics
    f, cx, cy = K[0, 0], K[0, 2], K[1, 2]

    x_cam = (u - cx) / f * depth
    y_cam = (v - cy) / f * depth
    z_cam = depth
    point_cam = np.array([x_cam, y_cam, z_cam, 1.0])

    world_from_cam = np.linalg.inv(cam.extrinsics)
    point_world = world_from_cam @ point_cam
    return point_world[:3]


def estimate_cube_position(cam, color_name: str):
    """カメラ画像からcolor_nameのキューブの3次元位置を推定する。

    戻り値: 推定座標(np.ndarray shape(3,)) または検出失敗ならNone。
    """
    rgb_arr, depth_arr, *_ = cam.render(rgb=True, depth=True)
    rgb_arr = np.asarray(rgb_arr)
    depth_arr = np.asarray(depth_arr)

    detected = detect_cube_pixel(rgb_arr, color_name)
    if detected is None:
        return None
    u, v, mask = detected

    # マスク内の深度の中央値を使う(縁の背景画素や反射によるノイズに頑健)。
    depths_in_mask = depth_arr[mask]
    depths_in_mask = depths_in_mask[np.isfinite(depths_in_mask)]
    if len(depths_in_mask) == 0:
        return None
    depth = float(np.median(depths_in_mask))

    point = backproject(cam, u, v, depth)
    # 深度画像が捉えるのはキューブの「上面」であり、キューブの中心ではない。
    # パーセプションカメラはほぼ真下を向いているため、上面から中心への補正は
    # 単純にzをcube_sizeの半分だけ下げるだけでよい(真下視点という前提に依存)。
    point[2] -= 0.5 * CUBE_SIZE
    return point
