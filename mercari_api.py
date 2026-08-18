#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""メルカリShops 公式API (GraphQL) クライアント。

メルカリShopsの公式APIを使って商品の出品・取得を行う。
個人向けメルカリ(フリマ)のAPIではないので注意。利用には
メルカリShopsへの出店とAPI利用申請、アクセストークンの発行が必要。

トークンの置き場所(優先順):
  1. 環境変数 MERCARI_SHOPS_TOKEN
  2. mercari_token.txt (このファイルはgit管理外)
  3. mercari_config.json の "access_token" (非推奨)

コマンドライン:
  python3 mercari_api.py test                        # 接続テスト
  python3 mercari_api.py schema CreateProductInput   # 入力型のフィールド確認
  python3 mercari_api.py enum ProductCondition       # enum値の確認
  python3 mercari_api.py ops                         # query/mutation一覧
  python3 mercari_api.py products                    # 商品一覧
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "mercari_config.json")
TOKEN_PATH = os.path.join(BASE, "mercari_token.txt")

USER_AGENT = "iha-mercari-autolist/1.0"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_token(cfg=None):
    tok = os.environ.get("MERCARI_SHOPS_TOKEN", "").strip()
    if tok:
        return tok
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    if cfg is None:
        cfg = load_config()
    return (cfg.get("access_token") or "").strip()


def save_token(token):
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(token.strip() + "\n")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def get_endpoint(cfg=None):
    if cfg is None:
        cfg = load_config()
    if cfg.get("use_sandbox"):
        return cfg.get("sandbox_endpoint") or cfg["endpoint"]
    return cfg["endpoint"]


class MercariAPIError(Exception):
    """API呼び出し失敗。.errors にGraphQLのエラー配列(あれば)。"""

    def __init__(self, message, errors=None, status=None):
        super().__init__(message)
        self.errors = errors or []
        self.status = status


def graphql(query, variables=None, cfg=None, retries=3):
    """GraphQLリクエストを送り、dataを返す。429/5xxは指数バックオフで再試行。"""
    if cfg is None:
        cfg = load_config()
    token = get_token(cfg)
    if not token:
        raise MercariAPIError(
            "アクセストークンが未設定です。ショップ管理画面の [設定] → "
            "[APIアクセストークンを発行] で発行し、mercari_token.txt に保存してください。",
            status=401)

    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        get_endpoint(cfg), data=body, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        })

    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                payload = json.loads(res.read().decode("utf-8"))
            if payload.get("errors"):
                msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
                raise MercariAPIError("GraphQLエラー: " + msgs,
                                      errors=payload["errors"])
            return payload.get("data") or {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code == 401:
                raise MercariAPIError(
                    "認証エラー(401)。トークンが無効か期限切れです。", status=401)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                last_err = MercariAPIError(
                    "HTTP %d: %s" % (e.code, detail), status=e.code)
                time.sleep(2 ** (attempt + 1))
                continue
            raise MercariAPIError("HTTP %d: %s" % (e.code, detail), status=e.code)
        except urllib.error.URLError as e:
            if attempt < retries:
                last_err = MercariAPIError("接続エラー: %s" % e.reason)
                time.sleep(2 ** (attempt + 1))
                continue
            raise MercariAPIError("接続エラー: %s" % e.reason)
    raise last_err or MercariAPIError("不明なエラー")


# ---------------------------------------------------------------- 基本操作

TEST_QUERY = """
query {
  shops(first: 1) {
    edges { node { id name } }
  }
}
"""

PRODUCTS_QUERY = """
query ($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges { node { id name status } }
  }
}
"""

CREATE_PRODUCT_MUTATION = """
mutation ($input: CreateProductInput!) {
  createProduct(input: $input) {
    product { id name }
  }
}
"""


def test_connection(cfg=None):
    """接続テスト。成功したらショップ情報らしきものを返す。"""
    data = graphql(TEST_QUERY, cfg=cfg)
    return data


def fetch_products(limit=50, cfg=None):
    """出品済み商品を最大limit件取得。"""
    items, after = [], None
    while len(items) < limit:
        first = min(50, limit - len(items))
        data = graphql(PRODUCTS_QUERY, {"first": first, "after": after}, cfg=cfg)
        conn = data.get("products") or {}
        for edge in conn.get("edges") or []:
            items.append(edge.get("node") or {})
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    return items


def create_product(item, cfg=None):
    """商品を1件出品する。

    item: name/description/price/stock/category_id/condition/image_urls(list)
          と extra(dict, CreateProductInputへそのまま追加) を持つdict。
    cfg["product_defaults"] を下敷きにitem側の値で上書きした入力を送る。
    戻り値: 作成された商品のdict(idなど)。
    """
    if cfg is None:
        cfg = load_config()
    defaults = dict(cfg.get("product_defaults") or {})
    defaults.pop("_comment", None)

    inp = dict(defaults)
    inp.update(item.get("extra") or {})
    inp["name"] = item["name"]
    inp["description"] = item.get("description", "")
    inp["price"] = int(item["price"])
    if item.get("category_id"):
        inp["categoryId"] = str(item["category_id"])
    if item.get("condition"):
        inp["condition"] = item["condition"]
    urls = item.get("image_urls") or []
    if urls:
        bad = [u for u in urls if not u.startswith("https://")]
        if bad:
            raise MercariAPIError(
                "画像URLはhttpsの公開URLのみ指定できます: " + ", ".join(bad))
        inp["imageUrls"] = urls
    if item.get("stock") is not None:
        inp.setdefault("stock", int(item["stock"]))

    data = graphql(CREATE_PRODUCT_MUTATION, {"input": inp}, cfg=cfg)
    return (data.get("createProduct") or {}).get("product") or {}


# ---------------------------------------------------------- スキーマ確認用

TYPE_QUERY = """
query ($name: String!) {
  __type(name: $name) {
    name kind
    inputFields { name type { kind name ofType { kind name ofType { kind name } } } }
    fields { name type { kind name ofType { kind name ofType { kind name } } } }
    enumValues { name }
  }
}
"""

OPS_QUERY = """
query {
  __schema {
    queryType { fields { name } }
    mutationType { fields { name } }
  }
}
"""


def _type_str(t):
    if not t:
        return "?"
    if t.get("kind") == "NON_NULL":
        return _type_str(t.get("ofType")) + "!"
    if t.get("kind") == "LIST":
        return "[" + _type_str(t.get("ofType")) + "]"
    return t.get("name") or "?"


def describe_type(name, cfg=None):
    """型のフィールド一覧を人が読める文字列で返す(スキーマ確認用)。"""
    data = graphql(TYPE_QUERY, {"name": name}, cfg=cfg)
    t = data.get("__type")
    if not t:
        return "型 %s は見つかりませんでした" % name
    lines = ["%s (%s)" % (t["name"], t["kind"])]
    for f in (t.get("inputFields") or []) + (t.get("fields") or []):
        lines.append("  %s: %s" % (f["name"], _type_str(f.get("type"))))
    for v in t.get("enumValues") or []:
        lines.append("  " + v["name"])
    return "\n".join(lines)


def list_operations(cfg=None):
    data = graphql(OPS_QUERY, cfg=cfg)
    schema = data.get("__schema") or {}
    q = [f["name"] for f in (schema.get("queryType") or {}).get("fields") or []]
    m = [f["name"] for f in (schema.get("mutationType") or {}).get("fields") or []]
    return {"queries": sorted(q), "mutations": sorted(m)}


# ---------------------------------------------------------------- CLI

def main(argv):
    cmd = argv[1] if len(argv) > 1 else "test"
    try:
        if cmd == "test":
            print(json.dumps(test_connection(), ensure_ascii=False, indent=2))
            print("OK: 接続に成功しました")
        elif cmd in ("schema", "enum"):
            if len(argv) < 3:
                print("使い方: python3 mercari_api.py schema <型名>")
                return 1
            print(describe_type(argv[2]))
        elif cmd == "ops":
            print(json.dumps(list_operations(), ensure_ascii=False, indent=2))
        elif cmd == "products":
            for p in fetch_products():
                print(json.dumps(p, ensure_ascii=False))
        else:
            print(__doc__)
            return 1
    except MercariAPIError as e:
        print("エラー:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
