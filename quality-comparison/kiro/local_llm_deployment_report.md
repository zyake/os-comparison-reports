# The Ultimate Guide to Local LLM Deployment: Windows vs. macOS vs. Linux

> A comprehensive, technically rigorous reference for deploying and optimizing Large Language Model inference on local hardware. Covers OS architecture implications, kernel tuning, security hardening, performance optimization, and hardware-specific recommendations. Reflects the state of the art as of 2025–2026: Linux kernel 6.x/7.x, macOS Sequoia (15), Windows 11 24H2, and the current local LLM toolchain (Ollama 0.19+, llama.cpp, vLLM, MLX).

---

## 1. Executive Summary

Local LLM inference has moved from a niche hobby to a production-grade workload driven by data sovereignty, latency requirements, and cost control. The three major operating systems present fundamentally different architectures for AI compute, each with distinct trade-offs in control, performance ceiling, and operational complexity.

| Dimension | Windows 11 (24H2) | macOS (Apple Silicon) | Linux (Kernel 6.x+) |
|---|---|---|---|
| Core architecture | WDDM 3.1+ VRAM management; kernel-mode driver validation overhead (~10–30% TPS loss vs. Linux) | XNU kernel + Unified Memory Architecture (UMA); Metal / MLX backends | Native PCIe/NVMe passthrough; deterministic memory locking via `mlock()`; cgroups v2 isolation |
| GPU/VRAM control | Limited pinning; relies on `--ngl` layer offloading and fixed pagefile to prevent WDDM paging | Dynamic UMA partitioning; no static VRAM pool; memory-bandwidth-bound (100–546 GB/s by chip) | Full `cudaMallocHost()` / `mlock()` control; explicit NUMA binding; swap prevention via sysctl |
| Ecosystem maturity | Native Ollama/llama.cpp builds; CUDA 12.x official; vLLM requires WSL 2 | Native ARM64 Python/PyTorch MPS; MLX framework (20–87% faster than llama.cpp for <14B); no CUDA/ROCm | PyTorch 2.x / vLLM / llama.cpp full native support; Docker `nvidia-container-toolkit` mature |
| Performance ceiling | ~70–88% of Linux theoretical limit on equivalent hardware due to WDDM overhead | Strictly memory-bandwidth-bound; MLX is the fastest engine for models under ~14B parameters | Highest sustained TPS; continuous batching (vLLM) eliminates padding waste; deterministic scheduling |
| Security posture | Large attack surface via WDDM paging, Defender scans; requires registry hardening | Permissive native execution; requires `pf` rules, FileVault swap encryption | Container isolation + cgroup limits; requires strict `mlock()` enforcement and LUKS encryption |

Linux remains the uncompromised choice for production-grade, high-throughput local inference. Windows is viable for single-GPU desktop deployments with explicit WDDM tuning. macOS on Apple Silicon delivers exceptional efficiency for bandwidth-constrained workloads and has seen dramatic improvements with the MLX ecosystem, but is architecturally excluded from CUDA/ROCm and multi-GPU scaling.

---

## 2. OS Architecture for LLM Inference

### 2.1 The Bandwidth Bottleneck

LLM token generation is memory-bandwidth-bound, not compute-bound. Every generated token requires reading the entire model's weights from memory once. The theoretical ceiling is:

```
Max tok/s = Memory Bandwidth (GB/s) ÷ Model Size in Memory (GB)
```

Real-world numbers hit 60–80% of theoretical due to KV cache reads, attention computation, and kernel overhead. This means quantization is a direct throughput multiplier — going from FP16 to Q4 yields roughly 4× throughput because 4× less data moves per token. Buying more GPU cores provides diminishing returns compared to increasing memory bandwidth.

### 2.2 Windows — WDDM and the Driver Tax

Windows manages GPU resources through the Windows Display Driver Model (WDDM). WDDM batches kernel launches and introduces scheduling overhead that creates a measurable performance penalty for CUDA workloads:

- WDDM command submission adds latency per kernel launch due to batching and validation
- The GPU scheduler in WDDM introduces context-switch overhead not present in Linux's direct DRM/KMS model
- TDR (Timeout Detection and Recovery) can kill long-running inference operations if not explicitly extended via registry
- Windows Defender real-time scanning of model files (multi-GB GGUF blobs) causes I/O stalls during loading

NVIDIA offers a TCC (Tesla Compute Cluster) driver mode that bypasses WDDM entirely, but it is only available on Tesla/Quadro/data center GPUs — consumer GeForce cards are locked to WDDM.

WSL 2 provides an alternative path by running a real Linux kernel (6.6.x LTS) inside a lightweight Hyper-V VM. GPU passthrough works via `dxcore` → CUDA translation, but adds 15–20% CPU overhead from the Hyper-V syscall translation layer. vLLM's CUDA Graphs feature has known issues under WSL 2.

### 2.3 macOS — Unified Memory and the MLX Revolution

Apple Silicon's Unified Memory Architecture (UMA) is fundamentally different from discrete GPU systems. CPU, GPU, and Neural Engine share the same physical memory pool, eliminating PCIe transfer overhead entirely. The trade-off is that memory bandwidth becomes the singular bottleneck.

Memory bandwidth by chip generation:

| Chip | Bandwidth | 7B Q4 (~4 GB) | 14B Q4 (~8 GB) | 32B Q4 (~18 GB) | 70B Q4 (~40 GB) |
|---|---|---|---|---|---|
| M4 | 120 GB/s | ~30 tok/s | ~15 tok/s | ~7 tok/s | N/A |
| M4 Pro | 273 GB/s | ~68 tok/s | ~34 tok/s | ~15 tok/s | ~7 tok/s |
| M4 Max | 546 GB/s | ~136 tok/s | ~68 tok/s | ~30 tok/s | ~14 tok/s |

The MLX framework, Apple's open-source array framework optimized for Apple Silicon, has become the fastest inference engine for models under ~14B parameters — 20–87% faster than llama.cpp on the same hardware. Ollama 0.19+ ships with an MLX backend that delivers ~93% faster decode and ~57% faster prefill compared to the previous llama.cpp/Metal backend. Key benchmarks on M4 Max 64 GB (Qwen3.5-35B-A3B):

| Metric | llama.cpp (Ollama 0.18) | MLX (Ollama 0.19) | Improvement |
|---|---|---|---|
| Prefill | 1,147 tok/s | 1,804 tok/s | +57% |
| Decode | 57.8 tok/s | 111.4 tok/s | +93% |
| Total duration | 4.2 s | 2.3 s | −45% |

macOS is architecturally excluded from CUDA, ROCm, and vLLM. Docker GPU passthrough is unsupported. All workloads must run natively via MLX, Metal MPS, or CPU fallback.

### 2.4 Linux — Full Control, Maximum Throughput

Linux provides the most direct path from hardware to inference engine:

- DRM/KMS provides direct GPU access without WDDM's batching overhead
- `mlock()` and `mlockall()` prevent the kernel from swapping model weights to disk
- NUMA-aware allocation via `numactl` eliminates cross-socket PCIe hops (which add 50–100 ns per DMA transaction)
- cgroups v2 provides deterministic resource isolation for containerized inference
- `io_uring` enables high-performance async I/O for model loading and KV cache management
- The kernel's CPU governor can be locked to `performance` mode, and deep C-states disabled to eliminate latency jitter

Linux is the only OS where vLLM runs natively with full feature support (PagedAttention, continuous batching, CUDA Graphs, tensor parallelism). The `nvidia-container-toolkit` provides mature GPU passthrough for Docker containers.

---

## 3. Kernel Tuning and Configuration

### 3.1 Linux Kernel Tuning

**Performance sysctls** (`/etc/sysctl.d/99-llm-performance.conf`):

```ini
# Prevent OOM killer during CUDA context initialization
vm.overcommit_memory = 1

# Minimize swap usage — model weights must stay in RAM
vm.swappiness = 10

# Reduce writeback stalls during large tensor checkpoint loads
vm.dirty_ratio = 5
vm.dirty_background_ratio = 2

# Support high-concurrency API servers
net.core.somaxconn = 65535
fs.file-max = 2097152

# Required for Docker mlock() and vLLM page tables
vm.max_map_count = 2147483647
```

**CPU governor and PCIe tuning:**

```bash
# Lock CPU to performance state
sudo cpupower frequency-set -g performance

# Disable deep C-states (Intel)
# Add to /etc/default/grub GRUB_CMDLINE_LINUX:
intel_idle.max_cstate=0 pcie_aspm=off

# AMD equivalent
amd_pstate=active pcie_aspm=off

# Apply and reboot
sudo update-grub && sudo reboot
```

**NUMA binding for GPU inference:**

```bash
# Bind inference process to the NUMA node closest to the GPU
numactl --cpunodebind=0 --membind=0 ollama serve

# Verify GPU NUMA topology
nvidia-smi topo -m
```

### 3.2 Windows Registry Tuning

```reg
; Extend GPU timeout to prevent TDR crashes on long inference
HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\TdrDelay = 60 (DWORD)

; Memory management — prevent model thrashing
HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\LargeSystemCache = 0

; Disable NVMe interrupt moderation for faster model loading
HKLM\SYSTEM\CurrentControlSet\Storage\stornvme\Parameters\Device\InterruptModeration = 0
```

**WSL 2 configuration** (`%USERPROFILE%\.wslconfig`):

```ini
[wsl2]
memory=80%
swap=0
gpuSupport=true
```

### 3.3 macOS Kernel Tuning

macOS kernel tuning is constrained by SIP but several parameters are adjustable:

```bash
# Prevent file descriptor exhaustion during token streaming
sudo sysctl -w kern.maxfiles=524288

# Disable hibernation to prevent swap-to-NVMe thrashing
sudo pmset -a hibernatemode 0 standby 0

# Disable App Nap and power throttling for sustained inference
sudo pmset -a womp 0 sleep 0
defaults write NSGlobalDomain NSAppSleepDisabled -bool true
```

**Enable MLX backend in Ollama:**

```bash
export OLLAMA_MLX=1
ollama run qwen3:14b
```

The MLX backend requires 32 GB+ unified memory and Ollama 0.19+.

---

## 4. Security Hardening

### 4.1 Attack Surface Analysis

Local LLM deployments introduce several attack vectors specific to the inference context:

| Vector | Mechanism | Risk |
|---|---|---|
| API exposure | Ollama defaults to `0.0.0.0:11434`; unauthenticated endpoints | LAN scanning → unauthenticated `/api/generate` flooding; research shows over 35% of Ollama instances respond to unauthenticated API requests, with ~15% leaking model or system information |
| Model poisoning | GGUF is a binary format with unsigned metadata/tensor blobs | Crafted headers can trigger buffer overflows in C++ FFI bridges; adversarial weight injection can embed backdoored response behaviors |
| Prompt injection | Local LLMs integrated with shell executors lack sandboxing | Malicious prompt outputs structured commands; if executed without sandboxing, enables privilege escalation |
| Memory leakage | Model weights and prompts in RAM may be swapped to disk unencrypted | Sensitive data recoverable from swap/pagefile forensics |
| Supply chain | Model downloads from untrusted sources | Tampered model files; no built-in signature verification in most tools |

### 4.2 Linux Hardening

```bash
# 1. Bind to localhost only
export OLLAMA_HOST=127.0.0.1

# 2. Firewall rules (ufw)
sudo ufw allow from 127.0.0.1 to any port 11434 proto tcp
sudo ufw deny in to any port 11434
sudo ufw default deny incoming
sudo ufw enable

# 3. Docker container security
docker run -d \
  --name local-llm \
  --gpus all \
  -p 127.0.0.1:11434:11434 \
  --security-opt=no-new-privileges:true \
  --cap-drop=ALL \
  --cap-add=SYS_ADMIN \
  --ulimit memlock=-1:-1 \
  -v /mnt/models:/models:ro \
  ollama/ollama

# 4. Model integrity verification
sha256sum /mnt/models/your-model.gguf
# Compare against published hash from model provider

# 5. Encrypt swap
sudo cryptsetup luksFormat --type luks2 /dev/sdXN_swap
sudo cryptsetup open /dev/sdXN_swap swap_crypt
sudo mkswap /dev/mapper/swap_crypt
sudo swapon /dev/mapper/swap_crypt
```

### 4.3 Windows Hardening

```powershell
# 1. Bind Ollama to localhost
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "127.0.0.1", "Machine")

# 2. Firewall rules
netsh advfirewall firewall add rule name="Block LLM Inbound" dir=in action=block protocol=TCP localport=11434
netsh advfirewall firewall add rule name="Allow Localhost LLM" dir=in action=allow protocol=TCP localip=127.0.0.1 localport=11434

# 3. Encrypt pagefile (prevents model weight leakage to disk)
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" /v EncryptPagedFile /t REG_DWORD /d 1 /f

# 4. Disable crash dumps (prevent memory dumps containing model data)
reg add "HKLM\SYSTEM\CurrentControlSet\Control\CrashControl" /v CrashDumpEnabled /t REG_DWORD /d 0 /f

# 5. Exclude model directory from Defender scanning (performance + prevents file locks)
Set-MpPreference -ExclusionPath "C:\Models" -ExclusionExtension ".gguf",".bin"
```

### 4.4 macOS Hardening

```bash
# 1. Verify SIP is active (non-negotiable)
csrutil status

# 2. Enable FileVault swap encryption
sudo sysctl -w vm.swapcrypto=2
sudo fdesetup status

# 3. Packet filter rules for API isolation
# Add to /etc/pf.conf:
# block all
# pass out proto tcp to any port {80, 443} keep state
# pass out proto udp to any port 53 keep state
# pass in proto tcp from 127.0.0.1 to any port 11434 keep state
sudo pfctl -f /etc/pf.conf
sudo pfctl -e

# 4. Verify no external listeners
sudo lsof -iTCP -sTCP:LISTEN | grep 11434
```

---

## 5. Performance Benchmarks

### 5.1 NVIDIA GPU Benchmarks (llama.cpp, Q4_K_M, Linux)

Real-world measured results from community benchmarks:

| GPU | VRAM | 7B Q4 (tok/s) | 8B Q4 (tok/s) | 14B Q4 (tok/s) | Notes |
|---|---|---|---|---|---|
| RTX 3060 12 GB | 12 GB | ~60 | ~42 | ~23 | Budget sweet spot; 14B Q4 fits in VRAM |
| RTX 4070 | 12 GB | ~75 | ~55 | ~30 | Higher bandwidth than 3060 |
| RTX 4090 | 24 GB | ~130 | ~95 | ~55 | Full GPU offload for 14B; 32B Q4 fits |
| A100 80 GB | 80 GB | ~150+ | ~120+ | ~70+ | Data center; supports 70B Q4 |

Sources: [Hardware Corner GPU benchmarks](https://singhajit.com/llm-inference-speed-comparison/), [geerlingguy ai-benchmarks](https://github.com/geerlingguy/ai-benchmarks)

Context length impact (RTX 3060 12 GB, Qwen3 8B Q4):
- 16K context: ~42 tok/s
- 32K context: ~32 tok/s (~24% reduction due to KV cache pressure)

### 5.2 Apple Silicon Benchmarks (MLX, Q4_K_M)

| Chip | RAM | 7B Q4 (tok/s) | 14B Q4 (tok/s) | 27B+ Q4 (tok/s) | Engine |
|---|---|---|---|---|---|
| M2 Pro | 32 GB | ~25 | ~14 | N/A | llama.cpp Metal |
| M3 Pro | 36 GB | ~35 | ~20 | ~10 | MLX |
| M4 Pro | 48 GB | ~68 | ~34 | ~15 | MLX |
| M4 Max | 64–128 GB | ~136 | ~68 | ~30 | MLX |

Source: [Starmorph Apple Silicon LLM Guide](https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide)

MLX advantage collapses at 27B+ where memory bandwidth saturates and both MLX and llama.cpp hit the same ceiling.

### 5.3 Windows vs. Linux Performance Delta

CUDA applications experience a 10–30% performance penalty on Windows compared to Linux due to WDDM overhead. The penalty varies by workload:

- Single-user inference (Ollama/llama.cpp): ~10–15% slower on Windows
- Batched inference (vLLM): Not natively supported on Windows; WSL 2 adds ~15–20% overhead
- Model loading: Windows Defender scanning can add seconds to multi-GB model loads unless exclusions are configured

### 5.4 Quantization Impact

| Quantization | Size (7B) | Quality Loss | Throughput vs. FP16 | Recommendation |
|---|---|---|---|---|
| FP16 | ~14 GB | Baseline | 1× | Only if VRAM permits; highest quality |
| Q8_0 | ~7.5 GB | ~0.5% | ~1.9× | Best quality-to-size ratio |
| Q5_K_M | ~5.3 GB | ~1.5% | ~2.6× | Good balance |
| Q4_K_M | ~4.2 GB | ~3.3% | ~3.3× | Sweet spot for most deployments |
| Q3_K_M | ~3.3 GB | ~6%+ | ~4.2× | Noticeable quality degradation |
| Q2_K | ~2.7 GB | ~10%+ | ~5.2× | Not recommended; significant quality loss |

Q4_K_M is the consensus sweet spot — 75% size reduction with only ~3.3% quality loss. It allows a 7B model to fit comfortably in 8 GB VRAM or 16 GB unified memory with room for KV cache.

---

## 6. Software Ecosystem Comparison

### 6.1 Inference Engines

| Engine | Linux | Windows | macOS | Best For |
|---|---|---|---|---|
| llama.cpp | Full CUDA/ROCm/Vulkan | Native CUDA; Vulkan fallback | Metal; MLX via Ollama | Single-user, maximum compatibility, GGUF models |
| Ollama | Full support | Native app or WSL 2 | Native with MLX backend (0.19+) | Easiest setup; wraps llama.cpp/MLX with model management |
| vLLM | Full native (PagedAttention, continuous batching, CUDA Graphs) | WSL 2 only (CUDA Graphs broken) | Experimental via vllm-mlx | Production serving; multi-user; batched inference |
| MLX | N/A | N/A | Native (fastest for <14B) | Apple Silicon optimization; training and inference |
| LM Studio | Full support | Native | Native | GUI-based; good for experimentation |

### 6.2 Key Compatibility Notes

- vLLM on Windows: Requires WSL 2. CUDA Graphs (a key performance feature) have known issues under WSL 2's GPU passthrough layer. For production serving on Windows hardware, running a full Linux installation is recommended over WSL 2.
- ROCm (AMD GPUs): Linux-only. ROCm 6.x supports RX 7000 series and MI-series accelerators. PagedAttention in vLLM has known segfault issues on ROCm 6.x that require explicit kernel patches.
- Docker GPU passthrough: Mature on Linux via `nvidia-container-toolkit`. Not supported on macOS. On Windows, requires WSL 2 backend.

---

## 7. Deployment Recommendations

### 7.1 Hardware-Mapped Decision Matrix

| Hardware Setup | Recommended OS | Quantization Strategy | Key Configuration | Expected Throughput |
|---|---|---|---|---|
| 8–12 GB VRAM (RTX 3060/4060 Ti) | Windows or Linux | Q4_K_M (7B–14B); max 8–16K context | Win: TdrDelay=60, Defender exclusions. Lin: `mlock()`, `pcie_aspm=off` | 23–60 tok/s (model-dependent) |
| 24 GB VRAM (RTX 4090) | Linux (preferred) | Q4_K_M (7B–32B); 16–32K context | `numactl --membind=0`, vLLM continuous batching, `io_uring` | 55–130 tok/s |
| Multi-GPU (2× 4090 / NVLink) | Linux only | Tensor parallelism; Q5_K_M or FP16 | `CUDA_VISIBLE_DEVICES=0,1`, `numactl --interleave=all` | 70–95 tok/s (13B Q5) |
| 32 GB unified (M2/M3/M4 Pro) | macOS | Q4_K_M (7B–14B); max 8K context | `OLLAMA_MLX=1`, disable hibernation, `mlockall()` | 25–68 tok/s |
| 64–128 GB unified (M4 Max/Ultra) | macOS | Q4_K_M to FP16 (7B–70B); 32K+ context | MLX backend, full UMA bandwidth | 14–136 tok/s |
| 80 GB+ VRAM (A100/H100) | Linux only | FP16 or Q5_K_M; 32–128K context | `nvidia-container-toolkit`, FlashAttention-2, `torch.compile(mode="max-autotune")` | 120+ tok/s (vLLM) |

### 7.2 Decision Framework

1. Choose Linux if: You need maximum throughput, deterministic latency, containerized deployment, multi-GPU scaling, or vLLM with full feature support. Accept the operational overhead of manual kernel tuning and driver management.

2. Choose Windows if: You operate a single-GPU desktop/workstation, need native Ollama/llama.cpp without WSL translation overhead, or require DirectML fallback for cross-vendor inference. Accept the ~10–30% TPS penalty and enforce registry hardening to mitigate WDDM paging.

3. Choose macOS if: You prioritize power efficiency, portability, and are running models under ~14B parameters on Apple Silicon. The MLX ecosystem has matured dramatically — Ollama 0.19+ with MLX delivers 2× faster inference than the previous Metal backend. Accept the architectural exclusion from CUDA/ROCm/vLLM and the lack of multi-GPU scaling.

### 7.3 Universal Best Practices

Regardless of OS:

- Bind inference APIs to `127.0.0.1` — never expose to `0.0.0.0` without authentication
- Verify model checksums (SHA-256) before execution
- Encrypt swap/pagefile to prevent model weight and prompt leakage
- Use Q4_K_M as the default quantization unless quality requirements demand higher
- Monitor VRAM usage — exceeding physical VRAM triggers catastrophic performance degradation (swap thrashing on macOS, WDDM paging on Windows, OOM kill on Linux)
- Isolate inference processes via containers (Linux), sandboxed users, or dedicated service accounts

---

## 8. Known Issues and Gotchas

| Issue | OS | Impact | Workaround |
|---|---|---|---|
| WDDM VRAM paging | Windows | 40%+ latency spikes when model exceeds VRAM | Reduce `--ngl` layers; increase pagefile; use Q4 quantization |
| TDR timeout | Windows | GPU driver reset kills inference mid-generation | Set `TdrDelay=60` in registry |
| Windows Defender model scanning | Windows | Multi-second delays on model load | Add model directory to exclusion list |
| Swap thrashing on <32 GB | macOS | >5 s/token latency spikes | Use Q4_K_M; limit context length; disable hibernation |
| MPS precision instability | macOS | NaN outputs with Q2/Q3 quantization | Use Q4_K_M or higher; prefer MLX over MPS |
| ROCm PagedAttention segfaults | Linux (AMD) | vLLM crashes under load | Pin ROCm version; apply kernel patches; use `HSA_OVERRIDE_GFX_VERSION` |
| WSL 2 CUDA Graphs | Windows (WSL) | vLLM performance degradation | Use native Linux instead of WSL 2 for production |
| Docker `mlock()` limits | Linux | Model weights swapped to disk inside containers | Set `--ulimit memlock=-1:-1` and configure cgroup memory limits |
| CUDA 13.x incompatibility | Windows | llama.cpp CUDA builds fail with CUDA 13.x | Use CUDA 12.x runtime; copy DLLs next to executable if PATH fails |

---

## 9. Sources and References

- [Apple Silicon LLM Inference Optimization Guide — Starmorph](https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide)
- [OS-Level Challenges in LLM Inference — eunomia.dev](https://eunomia.dev/blog/2025/02/18/os-level-challenges-in-llm-inference-and-optimizations/)
- [Local AI Performance Optimization — FOSS Linux](https://www.fosslinux.com/155039/local-ai-performance-optimizing-llm-inference-on-linux-2026-admin-guide.htm)
- [Local LLM Speed Benchmarks — singhajit.com](https://singhajit.com/llm-inference-speed-comparison/)
- [OWASP Top 10 for LLM Applications 2025](https://deepstrike.io/blog/owasp-llm-top-10-vulnerabilities-2025)
- [Exposed LLM Endpoints Research — arxiv.org](https://arxiv.org/html/2505.02502)
- [vLLM or llama.cpp — Red Hat Developers](https://developers.redhat.com/articles/2025/09/30/vllm-or-llamacpp-choosing-right-llm-inference-engine-your-use-case)
- [Ollama on Windows: Native vs WSL — WindowsForum](https://windowsforum.com/threads/ollama-on-windows-11-native-app-vs-wsl-for-local-llms.379552/)
- [Local LLM Hardware Guide 2025 — Introl](https://introl.com/blog/local-llm-hardware-pricing-guide-2025)

Content was rephrased for compliance with licensing restrictions.
