"""自然言語の指示文から、どのキューブを掴むかをClaudeに判定させる。"""
import json
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT = """あなたはロボットアームへの指示を解釈するプランナーです。
テーブル上に置かれたキューブの一覧(色と座標)と、人間の自然言語の指示文が与えられます。
指示文がどのキューブを指しているかを判断し、次のJSON形式のみで回答してください。
説明文や前置きは一切書かず、JSONオブジェクト1つだけを出力すること。

{"target_color": "<red|blue|green のいずれか>", "reason": "<判断理由を一言で>"}

座標はロボット基準のxy平面(メートル)。xが大きいほど奥、yが正なら左、負なら右。
"一番右" "一番手前" のような相対表現は座標から判断してください。
"""


class PlannerError(Exception):
    pass


def _cubes_info_text(cubes_info):
    lines = [f'- color="{c["color"]}", x={c["x"]:.3f}, y={c["y"]:.3f}' for c in cubes_info]
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    # モデルが前後に余計な文字を付けても拾えるよう、最初の{...}ブロックを抜き出す。
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise PlannerError(f"JSONが見つかりませんでした: {text!r}")
    return json.loads(match.group(0))


def choose_target(instruction: str, cubes_info: list[dict], max_retries: int = 2) -> dict:
    """instruction: 自然言語の指示文
    cubes_info: [{"color": "red", "x": 0.5, "y": 0.1}, ...]

    戻り値: {"target_color": str, "reason": str}
    パース失敗やあり得ない色が返った場合はリトライし、それでも失敗すればPlannerErrorを送出する。
    """
    client = anthropic.Anthropic()
    valid_colors = {c["color"] for c in cubes_info}

    user_text = f"キューブ一覧:\n{_cubes_info_text(cubes_info)}\n\n指示: {instruction}"

    last_error = None
    for attempt in range(max_retries + 1):
        extra = "" if attempt == 0 else f"\n(前回の出力が不正でした: {last_error}。JSONのみを出力し直してください。)"
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text + extra}],
        )
        raw_text = "".join(block.text for block in response.content if block.type == "text")

        try:
            result = _extract_json(raw_text)
            color = result.get("target_color")
            if color not in valid_colors:
                raise PlannerError(f"target_colorが不正です: {color!r} (候補: {sorted(valid_colors)})")
            return {"target_color": color, "reason": result.get("reason", "")}
        except (json.JSONDecodeError, PlannerError) as e:
            last_error = e
            continue

    raise PlannerError(f"LLMの応答を{max_retries + 1}回試しても解釈できませんでした: {last_error}")
