"""嵌入模型智能加载器（双轨制：本地离线 / 远程下载，自动降级）。

设计目标
--------
统一项目里所有 Embedding 模型的加载入口，让上层（RAGManager 等）不必关心
"模型从哪里来"，只关心拿到一个可用的 ``langchain_huggingface.HuggingFaceEmbeddings``
实例即可。

配置读取优先级
~~~~~~~~~~~~~~
1. 调用方显式传入的 ``config`` 对象（``RAGConfiguration`` 实例或 dict-like，可选）；
2. 数据库 ``RAGConfiguration``（is_default=True 优先，其次任意 is_active=True）；
3. 环境变量 ``EMBEDDING_LOAD_MODE`` / ``EMBEDDING_MODEL_LOCAL_PATH`` /
   ``EMBEDDING_MODEL_REMOTE_NAME``（开发环境 / Docker 部署兜底）。

加载流程
~~~~~~~~
- mode='local'：
    * 校验 ``local_path`` 存在 + 是目录 + 至少含 ``config.json``；
    * 通过则 ``HuggingFaceEmbeddings(model_name=local_path,
      model_kwargs={'local_files_only': True, 'device': dev})``；
    * 失败则警告日志 + 自动降级到 remote。
- mode='remote'：
    * ``HuggingFaceEmbeddings(model_name=remote_name,
      model_kwargs={'device': dev})``，由 HF Hub 处理本地缓存/联网下载。

GPU 适配：``torch.cuda.is_available()`` 自动选择 ``cuda`` / ``cpu``。

错误处理：最外层 try/except，加载失败抛 ``RuntimeError``，由调用方决定是否拦截，
不会让 Django/Celery 进程因为模型加载失败而直接崩溃。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 国内教学/离线包默认镜像（可被环境变量 HF_ENDPOINT 或 backend/.env 覆盖）
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def ensure_hf_endpoint() -> str:
    """确保 huggingface_hub 使用镜像端点（远程加载嵌入模型前调用）。"""
    endpoint = (os.getenv("HF_ENDPOINT") or "").strip()
    if not endpoint:
        endpoint = DEFAULT_HF_ENDPOINT
        os.environ["HF_ENDPOINT"] = endpoint
        logger.info("HF_ENDPOINT unset, using default mirror: %s", endpoint)
    return endpoint


# 默认远程模型名称，与 RAGConfiguration.embedding_model 默认值保持一致
DEFAULT_REMOTE_MODEL_NAME = "BAAI/bge-large-zh-v1.5"


@dataclass
class EmbeddingLoadResult:
    """加载结果元信息，便于上层（如测试连接接口、前端通知）使用。"""

    embeddings: Any  # HuggingFaceEmbeddings 实例
    mode_requested: str  # 用户请求的模式：'local' / 'remote'
    mode_actual: str  # 实际生效的模式
    model_identifier: str  # 真正传入 HuggingFaceEmbeddings 的 model_name（路径或仓库名）
    device: str  # 'cuda' / 'cpu'
    fallback: bool = False  # 是否触发了降级
    fallback_reason: str = ""  # 降级原因（mode=local 失败时的具体描述）


def _detect_device() -> str:
    """检测可用设备：优先 cuda，否则 cpu。"""
    try:
        import torch  # 延迟导入，避免无 torch 环境出问题
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _read_env_fallback() -> Dict[str, str]:
    """从环境变量读取兜底配置。"""
    return {
        "embedding_load_mode": os.getenv("EMBEDDING_LOAD_MODE", "").strip().lower(),
        "embedding_model_local_path": os.getenv("EMBEDDING_MODEL_LOCAL_PATH", "").strip(),
        "embedding_model_remote_name": os.getenv("EMBEDDING_MODEL_REMOTE_NAME", "").strip(),
    }


def _read_db_fallback() -> Optional[Dict[str, str]]:
    """从数据库 RAGConfiguration 读取兜底配置（按 is_default 优先）。"""
    try:
        # 延迟导入，避免循环依赖与 Django apps loading 顺序问题
        from .models import RAGConfiguration

        cfg = (
            RAGConfiguration.objects.filter(is_default=True, is_active=True).first()
            or RAGConfiguration.objects.filter(is_active=True).first()
        )
        if cfg is None:
            return None
        return {
            "embedding_load_mode": (cfg.embedding_load_mode or "").strip().lower(),
            "embedding_model_local_path": (cfg.embedding_model_local_path or "").strip(),
            "embedding_model_remote_name": (cfg.embedding_model or "").strip(),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"读取数据库 RAGConfiguration 失败（embedding_loader 兜底走环境变量）: {e}")
        return None


def _resolve_config(config: Any) -> Dict[str, str]:
    """合并三层来源（入参 → DB → 环境变量），返回标准化字段。

    返回 dict 含三个 key:``embedding_load_mode`` / ``embedding_model_local_path`` /
    ``embedding_model_remote_name``。
    """
    resolved = {
        "embedding_load_mode": "",
        "embedding_model_local_path": "",
        "embedding_model_remote_name": "",
    }

    def _take(src: Dict[str, str]) -> None:
        """src 中非空的键覆盖 resolved 中尚未填值的位置。"""
        for k in resolved:
            if not resolved[k] and src.get(k):
                resolved[k] = src[k]

    # 1. 入参（RAGConfiguration 或 dict）
    if config is not None:
        if isinstance(config, dict):
            _take({
                "embedding_load_mode": (config.get("embedding_load_mode") or "").strip().lower(),
                "embedding_model_local_path": (config.get("embedding_model_local_path") or "").strip(),
                "embedding_model_remote_name": (
                    config.get("embedding_model_remote_name")
                    or config.get("embedding_model")
                    or ""
                ).strip(),
            })
        else:
            _take({
                "embedding_load_mode": (
                    getattr(config, "embedding_load_mode", "") or ""
                ).strip().lower(),
                "embedding_model_local_path": (
                    getattr(config, "embedding_model_local_path", "") or ""
                ).strip(),
                "embedding_model_remote_name": (
                    getattr(config, "embedding_model_remote_name", None)
                    or getattr(config, "embedding_model", "")
                    or ""
                ).strip(),
            })

    # 2. 数据库
    if not all(resolved.values()):
        db = _read_db_fallback()
        if db:
            _take(db)

    # 3. 环境变量
    if not all(resolved.values()):
        _take(_read_env_fallback())

    # 兜底默认值
    if resolved["embedding_load_mode"] not in ("local", "remote"):
        resolved["embedding_load_mode"] = "remote"
    if not resolved["embedding_model_remote_name"]:
        resolved["embedding_model_remote_name"] = DEFAULT_REMOTE_MODEL_NAME
    return resolved


def validate_local_path(path: str) -> Dict[str, Any]:
    """校验本地模型目录的有效性，前端"检测路径"按钮也复用此方法。

    返回结构：
        {
            'valid': bool,             # 是否可作为有效模型目录
            'exists': bool,
            'is_dir': bool,
            'has_config_json': bool,
            'has_model_file': bool,    # 是否有 pytorch_model.bin / model.safetensors 等任一权重
            'file_count': int,
            'size_mb': float,
            'message': str,            # 给用户看的描述
        }
    """
    info: Dict[str, Any] = {
        "valid": False,
        "exists": False,
        "is_dir": False,
        "has_config_json": False,
        "has_model_file": False,
        "file_count": 0,
        "size_mb": 0.0,
        "message": "",
    }
    if not path:
        info["message"] = "未提供本地路径"
        return info
    info["exists"] = os.path.exists(path)
    if not info["exists"]:
        info["message"] = f"路径不存在：{path}"
        return info
    info["is_dir"] = os.path.isdir(path)
    if not info["is_dir"]:
        info["message"] = f"目标不是文件夹：{path}"
        return info

    weight_candidates = (
        "pytorch_model.bin",
        "model.safetensors",
        "tf_model.h5",
        "model.ckpt.index",
        "flax_model.msgpack",
    )
    total_size = 0
    file_count = 0
    has_config = False
    has_weight = False
    for entry in os.scandir(path):
        if entry.is_file():
            file_count += 1
            try:
                total_size += entry.stat().st_size
            except OSError:
                pass
            name = entry.name
            if name == "config.json":
                has_config = True
            elif name in weight_candidates or name.endswith(".safetensors"):
                has_weight = True
    info["has_config_json"] = has_config
    info["has_model_file"] = has_weight
    info["file_count"] = file_count
    info["size_mb"] = round(total_size / (1024 * 1024), 2)
    info["valid"] = has_config  # 至少需要 config.json；权重文件作为 warning 但不否决
    if info["valid"]:
        if has_weight:
            info["message"] = f"路径有效，含 config.json 与权重文件，共 {file_count} 个文件 / {info['size_mb']} MB"
        else:
            info["message"] = (
                f"路径含 config.json 但未发现 pytorch_model.bin / *.safetensors 等权重文件，"
                f"模型可能不完整，请检查"
            )
    else:
        info["message"] = "路径下未发现 config.json，疑似不是 HuggingFace 模型目录"
    return info


def _build_embeddings(model_name: str, device: str, local_files_only: bool):
    """构建 HuggingFaceEmbeddings 实例。

    与原 rag_service 保持一致的 encode_kwargs / model_kwargs 结构，确保下游 Chroma /
    Milvus 行为不变。
    """
    # 延迟导入：langchain_huggingface 依赖较重，避免模块导入即拉起 torch
    from langchain_huggingface import HuggingFaceEmbeddings

    model_kwargs: Dict[str, Any] = {}
    if device == "cuda":
        model_kwargs["device"] = "cuda"
    if local_files_only:
        # transformers 4.x 支持 local_files_only=True 强制走本地缓存/路径
        model_kwargs["local_files_only"] = True

    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": 32,
        },
        model_kwargs=model_kwargs,
    )


def get_embedding_model(config: Any = None) -> EmbeddingLoadResult:
    """嵌入模型智能加载入口。

    Args:
        config: 可选；优先使用其 ``embedding_load_mode`` /
            ``embedding_model_local_path`` / ``embedding_model``
            （或 ``embedding_model_remote_name``）字段。
            为 None 时按"DB → env"顺序读取。

    Returns:
        :class:`EmbeddingLoadResult`，包含真正加载到的 embeddings 实例与元信息。

    Raises:
        RuntimeError: 远程加载也彻底失败时抛出（已包含 root cause）。调用方负责捕获。
    """
    resolved = _resolve_config(config)
    mode_requested: str = resolved["embedding_load_mode"]
    local_path: str = resolved["embedding_model_local_path"]
    remote_name: str = resolved["embedding_model_remote_name"]
    device = _detect_device()

    # ===== 分支 1：local =====
    if mode_requested == "local":
        path_info = validate_local_path(local_path)
        if path_info["valid"]:
            try:
                embeddings = _build_embeddings(
                    model_name=local_path,
                    device=device,
                    local_files_only=True,
                )
                logger.info(
                    "✅ 成功加载本地离线 Embedding 模型：path=%s | device=%s | size=%sMB",
                    local_path, device, path_info["size_mb"],
                )
                return EmbeddingLoadResult(
                    embeddings=embeddings,
                    mode_requested="local",
                    mode_actual="local",
                    model_identifier=local_path,
                    device=device,
                    fallback=False,
                )
            except Exception as e:
                fallback_reason = f"本地模型加载抛异常：{e}"
                logger.warning(
                    "⚠️ 本地路径有效但加载失败，自动降级到远程：%s", fallback_reason,
                    exc_info=True,
                )
        else:
            fallback_reason = f"本地路径无效（{path_info['message']}）"
            logger.warning("⚠️ %s，自动降级到远程加载：%s", fallback_reason, remote_name)

        # local 失败，进入降级
        return _load_remote(remote_name, device, mode_requested="local",
                             fallback=True, fallback_reason=fallback_reason)

    # ===== 分支 2：remote（默认） =====
    return _load_remote(remote_name, device, mode_requested="remote",
                         fallback=False, fallback_reason="")


def _load_remote(remote_name: str, device: str, *, mode_requested: str,
                 fallback: bool, fallback_reason: str) -> EmbeddingLoadResult:
    """实际执行远程加载，失败抛 RuntimeError。"""
    ensure_hf_endpoint()
    try:
        embeddings = _build_embeddings(
            model_name=remote_name, device=device, local_files_only=False,
        )
        if fallback:
            logger.info(
                "✅ 已降级加载远程 Embedding 模型：name=%s | device=%s | reason=%s",
                remote_name, device, fallback_reason,
            )
        else:
            logger.info(
                "✅ 成功加载远程 Embedding 模型：name=%s | device=%s",
                remote_name, device,
            )
        return EmbeddingLoadResult(
            embeddings=embeddings,
            mode_requested=mode_requested,
            mode_actual="remote",
            model_identifier=remote_name,
            device=device,
            fallback=fallback,
            fallback_reason=fallback_reason,
        )
    except Exception as e:
        logger.error("❌ 远程 Embedding 模型加载失败：name=%s | error=%s",
                     remote_name, e, exc_info=True)
        # 抛 RuntimeError，让调用方决定是否兜底（不让 Django/Celery 整体挂掉）
        raise RuntimeError(f"嵌入模型加载失败 ({remote_name}): {e}") from e
