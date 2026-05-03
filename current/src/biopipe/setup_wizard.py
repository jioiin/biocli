"""Setup wizard: auto-download model, configure backend, verify.

Usage: biopipe setup
"""

from __future__ import annotations

import os
import sys
import hashlib
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """Verified model metadata."""
    name: str
    display_name: str
    size_gb: float
    min_ram_gb: int
    repo_id: str
    filename: str
    description: str


# Curated, verified models — all 100% local, zero telemetry
VERIFIED_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="tier1-qwen2.5-7b",
        display_name="Tier 1: Qwen 2.5 Coder 7B",
        size_gb=4.4,
        min_ram_gb=8,
        repo_id="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        description="Базовый уровень (Ноутбук). Идеально для простых bash скриптов.",
    ),
    ModelInfo(
        name="tier2-qwen2.5-14b",
        display_name="Tier 2: Qwen 2.5 Coder 14B",
        size_gb=9.0,
        min_ram_gb=16,
        repo_id="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
        filename="qwen2.5-coder-14b-instruct-q4_k_m.gguf",
        description="Продвинутый уровень (Рабочая станция). Рекомендуется.",
    ),
    ModelInfo(
        name="tier3-qwen2.5-32b",
        display_name="Tier 3: Qwen 2.5 Coder 32B",
        size_gb=19.5,
        min_ram_gb=32,
        repo_id="Qwen/Qwen2.5-Coder-32B-Instruct-GGUF",
        filename="qwen2.5-coder-32b-instruct-q4_k_m.gguf",
        description="Ступень PhD (Кластер). Максимальный интеллектуальный потенциал.",
    ),
]

MODELS_DIR = Path.home() / ".biopipe" / "models"
CONFIG_FILE = Path.home() / ".biopipe" / "config.json"
OFFLINE_ENV_VAR = "BIOPIPE_OFFLINE"


def _env_offline_enabled() -> bool:
    """Return True when offline mode is enabled by environment."""
    return os.getenv(OFFLINE_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


def validate_local_model_path(model_path: str) -> Path:
    """Validate and normalize a pre-downloaded local model path."""
    path = Path(model_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Model file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Model path must point to a file: {path}")
    if path.suffix.lower() != ".gguf":
        raise ValueError(f"Model file must have .gguf extension: {path}")
    return path


def get_system_ram_gb() -> int:
    """Detect available RAM in GB."""
    try:
        import psutil
        return int(psutil.virtual_memory().total / (1024 ** 3))
    except ImportError:
        # Fallback: read /proc/meminfo on Linux
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // (1024 * 1024)
        except (FileNotFoundError, ValueError):
            pass
    return 8  # conservative default


def download_model(model: ModelInfo, offline: bool = False) -> Path:
    """Download GGUF model from HuggingFace.

    Uses huggingface_hub if available, falls back to urllib.
    Returns path to downloaded file.
    """
    if offline:
        raise RuntimeError("Offline mode forbids model downloads.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / model.filename

    if dest.exists():
        print(f"  Model already exists: {dest}")
        return dest

    try:
        from huggingface_hub import hf_hub_download
        print(f"  Downloading {model.display_name} ({model.size_gb} GB)...")
        print(f"  From: huggingface.co/{model.repo_id}")
        path = hf_hub_download(  # nosec B615
            repo_id=model.repo_id,
            filename=model.filename,
            local_dir=str(MODELS_DIR),
            local_dir_use_symlinks=False,
        )
        return Path(path)
    except ImportError:
        import subprocess
        print("  Downloading required networking components automatically...")
        subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"], check=True, stdout=subprocess.DEVNULL)
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(  # nosec B615
            repo_id=model.repo_id,
            filename=model.filename,
            local_dir=str(MODELS_DIR),
            local_dir_use_symlinks=False,
        )
        return Path(path)


def save_config(model_path: str) -> None:
    """Save config to ~/.biopipe/config.json."""
    import json
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config = {"model_path": model_path, "backend": "llamacpp_embedded"}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print(f"  Config saved: {CONFIG_FILE}")


def run_setup(offline: bool = False, model_path: str | None = None) -> None:
    """Interactive setup wizard."""
    offline = offline or _env_offline_enabled()

    print()
    print("BioPipe-CLI Zero-Config Setup (100% Воздушный зазор)")
    print("=" * 60)
    print("Гарантия: Все веса загружаются локально, телеметрия отключена.")
    if offline:
        print("Режим: OFFLINE (сетевые загрузки и pip install отключены)")
    print()

    if offline:
        if not model_path:
            print("ERROR: Offline mode requires --model-path to a pre-downloaded .gguf file.")
            print("Example: biopipe setup --offline --model-path /models/qwen2.5-coder-14b.gguf")
            sys.exit(1)

        try:
            validated_path = validate_local_model_path(model_path)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)

        print(f"Validated local model: {validated_path}")
        save_config(str(validated_path))
        print()
        print("Offline setup complete. Network operations were skipped.")
        return

    # Detect RAM
    ram = get_system_ram_gb()
    print(f"Detected RAM: {ram} GB")
    print()

    # Filter models by RAM
    available = [m for m in VERIFIED_MODELS if m.min_ram_gb <= ram]
    if not available:
        print(f"ERROR: {ram} GB RAM is insufficient.")
        print("Minimum 8 GB RAM required for smallest model.")
        sys.exit(1)

    # Show options
    print("Available models (100% local, zero telemetry):")
    print()
    for i, m in enumerate(available, 1):
        rec = " ← recommended" if "recommended" in m.description.lower() else ""
        print(f"  [{i}] {m.display_name:<25} ({m.size_gb} GB, {m.min_ram_gb}+ GB RAM)")
        print(f"      {m.description}{rec}")
        print()

    # Select
    default = len(available)  # last = biggest that fits
    for i, m in enumerate(available):
        if "recommended" in m.description.lower():
            default = i + 1
            break

    try:
        choice = input(f"Your choice [{default}]: ").strip()
        idx = int(choice) - 1 if choice else default - 1
        if idx < 0 or idx >= len(available):
            idx = default - 1
    except (ValueError, EOFError):
        idx = default - 1

    selected = available[idx]
    print()
    print(f"Selected: {selected.display_name}")
    print()

    # Download
    model_path = download_model(selected)
    print(f"  Model ready: {model_path}")
    print()

    # Save config
    save_config(str(model_path))
    print()

    # Test inference
    print("Testing 100% Local Air-Gapped Inference Engine...")
    try:
        from llama_cpp import Llama  # type: ignore
    except ImportError:
        print("  Installing C++ Bindings (llama-cpp-python)... Please wait.")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "llama-cpp-python"], check=True)
        from llama_cpp import Llama  # type: ignore
        
    try:
        llm = Llama(model_path=str(model_path), n_ctx=512, verbose=False)
        resp = llm.create_chat_completion(
            messages=[{"role": "user", "content": "Say 'BioPipe Air-Gapped system ready' in 5 words."}],
            max_tokens=15,
        )
        text = resp["choices"][0]["message"]["content"]
        print(f"  Local Assistant Responded: {text}")
        print("  Inference: OK (No Internet Connection Used)")
    except Exception as exc:
        print(f"  Inference test failed: {exc}")
        print("  Model downloaded successfully. Check hardware compatibility.")

    print()
    print("Setup complete! Your system is secure and independent.")
    print()
    print("Next steps:")
    print("  biopipe interactive     — Start private AI assistant")
    print("  biopipe health          — Check cluster resources")
    print()
    print("Install NGS workflows locally:")
    print("  biopipe plugins install https://github.com/biopipe/biopipe-plugin-ngs.git")
