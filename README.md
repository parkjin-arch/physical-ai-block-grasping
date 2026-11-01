# 言葉で指示されたブロックを掴むロボットアーム

Genesisシミュレータ上のFranka Emika Pandaに、自然言語の指示文からどのキューブを
掴むかをローカルLLM(Ollama)に判定させ、ピック&プレースを実行させるプロジェクトです。

## 概要

- **Stage1**: 固定された1個のキューブをピック&リフトする（AIなし、動作の土台）
- **Stage2**: 赤・青・緑の3キューブをランダム配置し、自然言語の指示文（例:「青いブロックを取って」）
  をLLMに解釈させ、該当するキューブをピック&プレースする
- **Stage3**: シミュレータの正解座標を使わず、固定俯瞰カメラのRGB-D画像から色セグメンテーション
  でキューブ位置を推定し、その推定座標だけでLLM判定・ピック&プレースまで行う

## セットアップ

### 1. Python環境

Genesisのネイティブランタイム(LLVM)はWindows上で**非ASCIIパスを含むvenv**を正しく
扱えないため、venv自体は必ずASCIIのみのパスに作成してください
（プロジェクトフォルダ自体は日本語パスでも問題ありません）。

```powershell
py -3.11 -m venv C:\dev\venvs\genesis_env
C:\dev\venvs\genesis_env\Scripts\pip install -r requirements.txt
```

GPUがない環境でも動作します（`gs.cpu`バックエンドを使用）。

### 2. LLMバックエンド（Ollama、既定・無料）

```powershell
winget install --id Ollama.Ollama -e
ollama pull qwen2.5:3b-instruct
```

Ollamaサーバがローカルで起動していれば(`ollama serve`、通常はインストール後に自動常駐)、
追加のAPIキーなしでStage2が動作します。

別のモデルを使いたい場合は環境変数`OLLAMA_MODEL`で指定できます。

### 3. (任意) Anthropic APIバックエンド

APIクレジットがある場合は、Anthropic APIに切り替えることもできます。

```
LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

を`.env`ファイル（gitignore済み）に設定してください。

## 実行方法

```powershell
cd src

# Stage1: 固定キューブのピック&リフト
C:\dev\venvs\genesis_env\Scripts\python.exe main.py --stage 1 --no-viewer

# Stage2: 単一の指示文
C:\dev\venvs\genesis_env\Scripts\python.exe main.py --stage 2 --no-viewer --instruction "青いブロックを取って"

# Stage2: 対話入力
C:\dev\venvs\genesis_env\Scripts\python.exe main.py --stage 2 --no-viewer

# Stage2: 3つの指示を連続実行するデモモード
C:\dev\venvs\genesis_env\Scripts\python.exe main.py --stage 2 --no-viewer --demo

# Stage3: カメラ推定座標だけを使ったデモモード
C:\dev\venvs\genesis_env\Scripts\python.exe main.py --stage 3 --no-viewer --demo
```

`--no-viewer`を外すとGenesisのビューアがリアルタイム表示されます（動画は`--no-viewer`
有無にかかわらず`outputs/`に保存されます）。

## リポジトリ構成

```
README.md
requirements.txt
src/
  scene.py         # シーン構築 (build_scene: Stage1, build_scene_multi: Stage2/3)
  robot.py         # move_to, open_gripper, close_gripper, pick_and_place
  llm_planner.py   # 指示文 -> ターゲット色選択 (Ollama/Anthropic)
  perception.py    # RGB-Dからの位置推定 (Stage3)
  main.py          # デモ実行と録画
outputs/           # 動画・ログ（.gitignoreで大きなファイルは除外）。
                    # stage3_perception_errors.csvは精度評価の証跡として同梱
```

## 技術的な工夫

- `plan_path`（OMPL依存）は環境構築で詰まりやすいため使わず、`inverse_kinematics`で
  求めた目標関節角へ関節空間で線形補間する独自の`move_to`を実装
- グリッパーは位置制御で閉じるとキューブを弾いてしまうため、力制御(`control_dofs_force`)
  で一定の把持力を与える方式にしている
- LLMバックエンドを環境変数で切り替え可能にし、APIクレジットがなくてもローカルLLM
  (Ollama)だけでAI推論を完結できるようにした
- LLMの応答はJSON形式のみを期待するが、余計な文字列が混じっても拾えるよう正規表現で
  JSONブロックを抽出し、パース失敗やあり得ない色が返った場合はリトライする
- Stage3では、RGB-D画像の深度がキューブの「上面」を捉える点に注意し、真下視点の
  俯瞰カメラという条件下でキューブ高さの半分だけ補正することで、中心座標の推定誤差を
  約2cmから1〜4mm程度まで改善した（`outputs/stage3_perception_errors.csv`に記録）

## 動画

　[　https://youtu.be/74k_8wUN84I　]

## 個人情報について

本リポジトリ・コミット履歴・動画・ログには氏名・所属・メールアドレス等の個人情報を
含めていません。git の user.name / user.email もこのリポジトリのローカル設定として
匿名の値を使用しています。
