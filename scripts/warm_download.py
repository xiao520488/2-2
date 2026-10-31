# -*- coding: utf-8 -*-
"""补下载权重 v2：禁用 Xet 存储后端（镜像站不支持，会 401），走传统 HTTP"""
import os
import sys
import time

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"          # ★ 关键：镜像不支持 cas-server.xethub
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.stdout.reconfigure(encoding="utf-8")

MODEL = "BAAI/bge-small-zh-v1.5"

print("=" * 60)
print("补下载权重 v2（XET disabled）:", MODEL)
print("HF_ENDPOINT =", os.environ["HF_ENDPOINT"])
print("HF_HUB_DISABLE_XET =", os.environ["HF_HUB_DISABLE_XET"])
print("=" * 60, flush=True)

t0 = time.time()

# 直接下单个权重文件，最可控
from huggingface_hub import hf_hub_download

targets = ["model.safetensors", "pytorch_model.bin"]
ok = []
for fn in targets:
    try:
        p = hf_hub_download(repo_id=MODEL, filename=fn)
        print(f"[ok] {fn} -> {p}  ({os.path.getsize(p)/1e6:.1f} MB, {time.time()-t0:.1f}s)", flush=True)
        ok.append(p)
        break   # safetensors 拿到就够了
    except Exception as e:
        print(f"[skip] {fn}: {type(e).__name__}: {str(e)[:160]}", flush=True)

if not ok:
    print("权重下载失败 ❌", flush=True)
    sys.exit(2)

print(f"权重下载完成 ✅  用时 {time.time()-t0:.1f}s", flush=True)
