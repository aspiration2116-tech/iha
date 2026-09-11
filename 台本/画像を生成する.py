#!/usr/bin/env python3
"""台本/2026-10_扇風機しまう前_Lovart貼り付け用.txt を Gemini API (nanobanana2 = gemini-3-pro-image-preview)
で直接生成し、画像/扇風機/ に保存する。Lovartもブラウザも使わない。

    export GEMINI_API_KEY=あなたのキー
    python3 台本/画像を生成する.py            # 全カット
    python3 台本/画像を生成する.py T-01 T-02   # 指定カットだけ
    python3 台本/画像を生成する.py --from C003 --to C010

人物の基準(C003)・扇風機の基準(C007)は、生成済みならそれを参照画像として
自動で渡す（同じ人物・同じ個体をそろえるため）。
"""
import os
import re
import sys
from pathlib import Path

PROMPTS = Path("台本/2026-10_扇風機しまう前_Lovart貼り付け用.txt")
OUT_DIR = Path("画像/扇風機")
MODEL = "gemini-3-pro-image-preview"

REF_PERSON = "C003"   # 人物の基準カット
REF_FAN = "C007"      # 扇風機の基準カット


def load_prompts() -> list[tuple[str, str]]:
    """[C001（S01）｜…] の見出しごとに (カット番号, プロンプト本文) を返す。"""
    txt = PROMPTS.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"^\[((?:T-\d+|C\d+))[^\]]*\]\n(.+)$", txt, re.M):
        out.append((m.group(1), m.group(2).strip()))
    return out


def existing_path(cut: str) -> Path | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = OUT_DIR / f"{cut}.{ext}"
        if p.exists():
            return p
    return None


def generate(client, cut: str, prompt: str, refs: list[Path]) -> Path:
    from google.genai import types

    parts = [types.Part.from_text(text=prompt)]
    for ref in refs:
        parts.append(types.Part.from_bytes(data=ref.read_bytes(), mime_type="image/png"))

    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=parts)],
    )
    for cand in resp.candidates or []:
        for part in cand.content.parts or []:
            if part.inline_data and part.inline_data.data:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                out = OUT_DIR / f"{cut}.png"
                out.write_bytes(part.inline_data.data)
                return out
    raise RuntimeError(f"{cut}: 画像が返らなかった（テキストのみの応答だった可能性）")


def main() -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY が設定されていません。 export GEMINI_API_KEY=... してから実行してください。")

    from google import genai
    client = genai.Client(api_key=key)

    all_prompts = load_prompts()
    by_id = dict(all_prompts)

    args = sys.argv[1:]
    if "--from" in args:
        start = args[args.index("--from") + 1]
        end = args[args.index("--to") + 1] if "--to" in args else all_prompts[-1][0]
        ids = [c for c in by_id if c == c]  # keep order
        order = [c for c, _ in all_prompts]
        targets = order[order.index(start):order.index(end) + 1]
    elif args:
        targets = args
    else:
        targets = [c for c, _ in all_prompts]

    print(f"対象 {len(targets)}件 / モデル {MODEL}\n")

    ok, skip, fail = 0, 0, 0
    for cut in targets:
        if cut not in by_id:
            print(f"  {cut}: プロンプト集に無い番号。スキップ")
            fail += 1
            continue

        existing = existing_path(cut)
        if existing:
            print(f"  {cut}: 既にある（{existing.name}）。スキップ")
            skip += 1
            continue

        refs = []
        if cut != REF_PERSON:
            p = existing_path(REF_PERSON)
            if p:
                refs.append(p)
        if cut != REF_FAN:
            p = existing_path(REF_FAN)
            if p:
                refs.append(p)

        try:
            out = generate(client, cut, by_id[cut], refs)
            print(f"  {cut}: 生成完了 → {out}" + ("（参照あり）" if refs else ""))
            ok += 1
        except Exception as e:
            print(f"  {cut}: 失敗 — {e}")
            fail += 1

    print(f"\n完了 {ok} / 既存スキップ {skip} / 失敗 {fail}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
