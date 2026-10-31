# -*- coding: utf-8 -*-
"""
预热下载 bge-small-zh-v1.5（走国内镜像，带超时保护）
用法: python _warm_model.py
"""
import os
import sys
import time

# ---- 镜像必须在 import huggingface/transformers 之前设置 ----
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")   # 单请求超时，避免无限挂起
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
# 允许从镜像拉取（huggingface_hub >= 0.23）
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

sys.stdout.reconfigure(encoding="utf-8")

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def main():
    print("=" * 60)
    print("预热模型:", MODEL_NAME)
    print("HF_ENDPOINT =", os.environ["HF_ENDPOINT"])
    print("=" * 60)

    t0 = time.time()

    # 1) 先用 huggingface_hub 单独把文件拉下来，能看到进度/及时失败
    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(
            repo_id=MODEL_NAME,
            allow_patterns=[
                "*.json", "*.txt", "*.safetensors", "*.bin",
                "1_Pooling/*", "tokenizer*", "vocab*", "modules.json",
            ],
            max_workers=2,
        )
        print(f"[snapshot] OK  -> {path}  ({time.time()-t0:.1f}s)")
    except Exception as e:
        print(f"[snapshot] 失败: {type(e).__name__}: {e}")
        print("尝试直接走 SentenceTransformer 兜底...")

    # 2) 用 SentenceTransformer 真正加载一次，确认可用
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    vec = model.encode(["测试句子：智能车竞赛"], normalize_embeddings=True)
    print(f"[load] OK  dim={vec.shape[1]}  ({time.time()-t0:.1f}s)")
    print("模型预热完成 ✅")


if __name__ == "__main__":
    main()
