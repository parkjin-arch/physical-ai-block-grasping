"""自然言語の指示文から、どのキューブを掴むかをLLMに判定させる。

バックエンドは環境変数LLM_BACKENDで切り替える:
  - "ollama"    (既定): ローカルで動くOllama経由。APIキー・クレジット不要。
  - "anthropic": Anthropic API (ANTHROPIC_API_KEY必須)。クレジットがあればこちらも使える。
"""
import json
import os
import re
import urllib.request

from dotenv import load_dotenv

load_dotenv()

LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

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


def _call_anthropic(user_text: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _call_ollama(user_text: str) -> str:
    # ローカルで常駐するOllamaサーバ(既定: localhost:11434)のchat APIを叩く。
    # format="json" を指定することでJSON以外の出力を抑え、パース失敗を減らす。
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.0},
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise PlannerError(
            f"Ollamaサーバへの接続に失敗しました({OLLAMA_HOST})。"
            f"`ollama serve`が起動しているか、モデル'{OLLAMA_MODEL}'をpull済みか確認してください。詳細: {e}"
        )
    return body["message"]["content"]


def _call_llm(user_text: str) -> str:
    if LLM_BACKEND == "anthropic":
        return _call_anthropic(user_text)
    return _call_ollama(user_text)


def choose_target(instruction: str, cubes_info: list[dict], max_retries: int = 2) -> dict:
    """instruction: 自然言語の指示文
    cubes_info: [{"color": "red", "x": 0.5, "y": 0.1}, ...]

    戻り値: {"target_color": str, "reason": str}
    パース失敗やあり得ない色が返った場合はリトライし、それでも失敗すればPlannerErrorを送出する。
    """
    valid_colors = {c["color"] for c in cubes_info}
    user_text = f"キューブ一覧:\n{_cubes_info_text(cubes_info)}\n\n指示: {instruction}"

    last_error = None
    for attempt in range(max_retries + 1):
        extra = "" if attempt == 0 else f"\n(前回の出力が不正でした: {last_error}。JSONのみを出力し直してください。)"
        raw_text = _call_llm(user_text + extra)

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
