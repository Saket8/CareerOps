# CareerOps — Permanent System Memory & Operational Runbook

Last Updated: 2026-09-25  
Repository: [CareerOps (Saket8/CareerOps)](https://github.com/Saket8/CareerOps)  
Target Candidate: Saket Saurav (Principal Cloud Architect / GenAI & LLM Solutions Architect)  
Verified Live Applications: **77 Confirmed on Naukri** (with physical green badge proof)

---

## 1. Executive Summary & Purpose

**CareerOps** is an autonomous, truthful, proof-guaranteed career intelligence and application agent. It searches, qualifies, tailors ATS resumes, and applies live to high-paying Oracle Cloud Infrastructure (OCI), GenAI/LLM Architecture, Cloud Architecture, and Big Data roles on Naukri, delivering daily and weekly executive briefings directly to the candidate's inbox.

### Core Candidate Profile
* **Current Role:** Principal Cloud Architect / Technology Lead
* **Experience:** 12+ Years Enterprise Architecture
* **Current Compensation:** ₹30.0 LPA (Strict floor: never applies to roles $< ₹30$ LPA)
* **Target Roles:** OCI Architect, Oracle Cloud Administrator, GenAI Architect, LLMOps Architect, AI Solutions Architect, Cloud Architect
* **Current Employer (Blocked):** Cognizant / CTS (Hard safety gate: zero applications, zero visibility)

---

## 2. OCI Linux Production Environment

The system is deployed on an **Oracle Cloud Infrastructure (OCI) Free Tier Compute Instance** running Oracle Linux 9.

| Attribute | Specification |
|---|---|
| **Host IP** | `129.158.196.248` |
| **SSH User** | `opc` |
| **SSH Key Path (Local)** | `C:\Users\2016tu\Desktop\Projects\VPS\id_ed25519` |
| **SSH Access Command** | `ssh -i "C:\Users\2016tu\Desktop\Projects\VPS\id_ed25519" opc@129.158.196.248` |
| **CPU Architecture** | AMD EPYC 7551 (2 vCPUs) |
| **Physical Memory (RAM)** | **945 MB** (Strict low-memory constraints applied) |
| **Swap Storage** | **3.9 GB Total** (945 MB fast in-RAM ZRAM + 3.0 GB disk swapfiles) |
| **Disk Space** | 19 GB available on root partition (`/`) |
| **OS Distribution** | Oracle Linux Server 9.6 (UEK 6.12.0 x86_64) |
| **System Timezone** | UTC (`GMT +0000`) |
| **Project Directory** | `/home/opc/CareerOps` |
| **Virtual Environment** | `/home/opc/CareerOps/venv` (Python 3.11.13) |
| **Playwright Browser** | `/home/opc/.cache/ms-playwright/chromium-1243` |
| **Production Database** | `/home/opc/CareerOps/naukri_career_agent.sqlite` |
| **Visual Proof Artifacts** | `/home/opc/CareerOps/artifacts/evidence/` |
| **Naukri Auth Session** | `/home/opc/CareerOps/artifacts/naukri_auth.json` |
| **Display Server** | Xvfb Virtual Framebuffer on `:99` (`xorg-x11-server-Xvfb`) |

---

## 3. Automated Scheduling & Crontab Architecture

The autonomous pipeline is scheduled for the user `opc` on the VPS to align with peak recruiter screening windows in India Standard Time (IST = UTC+5:30):

```cron
# CareerOps - Autonomous Naukri Career Intelligence Agent
# Execution Windows:
#   1. 08:53 IST (03:23 UTC) - Morning recruiter screening window
#   2. 13:53 IST (08:23 UTC) - Post-lunch recruiter review window
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

23 3 * * * /home/opc/CareerOps/run_daily.sh
23 8 * * * /home/opc/CareerOps/run_daily.sh
```

> [!NOTE]
> **GitHub Actions Status:** Paused (`gh workflow disable career_agent_daily.yml` and `schedule:` triggers commented out). The OCI Linux Server crontab is now the primary and sole scheduled execution engine, eliminating queue delays and preventing duplicate submissions. Manual runs remain available via GitHub Actions `workflow_dispatch` if ever needed as a backup.

### Production Execution Invariants & Enhancements
* **Akamai Anti-Bot Bypass (`Xvfb :99`):** Naukri's Akamai Bot Manager blocks headless Chromium with `HTTP 403 Access Denied`. The wrapper script launches a lightweight virtual display (`Xvfb :99`), runs headed Chromium, and injects anti-detection stealth scripts, achieving `HTTP 200 OK` and 100% search listing extraction.
* **Lock FD Leak Prevention (`200>&-`):** When backgrounding Xvfb, file descriptor 200 is explicitly closed (`200>&- >/dev/null 2>&1 &`) so background daemons cannot leak or retain the `/tmp/careerops.lock` file descriptor.
* **Autonomous IMAP 2FA / OTP Resolution:** When challenged for 2FA on datacenter IPs, `playwright_adapter.py` autonomously connects to Gmail IMAP via Google App Password, extracts the 6-digit OTP, fills `#Input_1`..`#Input_6`, clicks Verify, and saves `artifacts/naukri_auth.json`.
* **Single Consolidated Email Architecture:** All Friday and daily dispatches are consolidated into **EXACTLY 1 single email** per run (Daily Application Report + Weekly Career Intelligence HTML + attached PDF and DOCX Interview Dossiers). Zero multi-email spam.

### Wrapper Script: `/home/opc/CareerOps/run_daily.sh`
* **Concurrency Guard (`flock`):** Acquires non-blocking lock on `/tmp/careerops.lock`. If another run is in progress, exits immediately to prevent cumulative memory spikes and Linux OOM killing.
* **CPU Niceness:** Executes with `nice -n 10` so the agent runs smoothly without starving SSH, networking, or kernel processes.
* **Disk Protection:** Checks log file size (`/home/opc/CareerOps/logs/cron_run.log`). If $> 10$ MB, rotates to keep only the latest 5,000 lines.
* **Telemetry:** Records pre-run and post-run `free -h` memory states, execution duration, and exit codes.
* **Environment:** Automatically exports `PYTHONPATH=/home/opc/CareerOps`, activates virtualenv, and sets `HEADLESS=true`.

---

## 4. Low-Resource CPU & Memory Optimization

To operate reliably on a **945 MB RAM** server alongside other services without triggering the Linux OOM Killer, the following kernel and application tunings are enforced:

### A. Kernel Sysctl Configuration (`/etc/sysctl.d/99-vps-tuning.conf`)
```ini
# Swappiness: Set to 80 to push cold/idle daemon memory into 4:1 compressed ZRAM
vm.swappiness = 80

# VFS Cache Pressure: Aggressively reclaims inode and dentry caches when workloads need RAM
vm.vfs_cache_pressure = 100

# Min Free Kbytes: Reduced from 42 MB to 16 MB, unlocking ~26 MB of locked RAM for user workloads
vm.min_free_kbytes = 16384

# Dirty Ratios: Flushes dirty buffers early before memory balloons
vm.dirty_background_ratio = 5
vm.dirty_ratio = 10

# Standard heuristic memory overcommit protection
vm.overcommit_memory = 0
```

### B. In-Memory Compressed ZRAM Synergy
* `/dev/zram0` (945 MB partition) is mounted as swap with **Priority 100** using `lzo-rle` compression (~4:1 compression ratio).
* Setting `vm.swappiness = 80` forces the Linux kernel to push idle background daemon pages into fast ZRAM (occupying only ~25% of their original size), freeing up the other 75% as pure, uncompressed physical RAM for Python, Playwright, and Chromium.

### C. Background Bloat Daemon Elimination
* **Performance Co-Pilot (PCP) Disabled:** Stopped and disabled `pmcd`, `pmie`, `pmlogger`, `pmie_farm`, `pmlogger_farm`, and background Python metrics collectors. (Reclaimed **~50 MB RSS** and eliminated continuous disk I/O).
* **XDG Desktop Portals Masked:** Masked `xdg-desktop-portal`, `xdg-document-portal`, and `xdg-permission-store` under user `opc`. (Reclaimed **~15 MB RSS** on headless server).

### D. Headless Chromium CPU & Memory Throttling
In `src/naukri/playwright_adapter.py`, Chromium launches with aggressive resource throttling:
* Memory flags: `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`, `--disable-software-rasterizer`, `--disable-extensions`.
* CPU flags: `--disable-background-networking`, `--disable-background-timer-throttling`, `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, `--disable-features=Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider`.
* Headless auto-detection: Automatically falls back to `headless=True` on Linux without `$DISPLAY` to avoid X11 aborts.

### Performance Impact
* **Active Memory Used:** Dropped from **385 MB** to **266 MB** (-31% memory footprint).
* **Available Memory:** Increased from **560 MB** to **679 MB** (+119 MB for workloads).
* **Pure Free RAM:** Increased from **164 MB** to **521 MB** (+357 MB unfragmented free memory).
* **Idle System Load:** Dropped to **0.16**.

---

## 5. Non-Negotiable System Invariants

1. **Candidate Truth Invariant:** Never fabricate or infer unverified certifications, titles, or experiences. Derives strictly from `candidate/candidate_facts.yaml` and `resumes/master/Saket_Saurav_OCI.docx`.
2. **Current Employer Blocklist:** Absolute block on Cognizant, CTS, Cognizant Cloud Solutions across discovery, scoring, and application phases.
3. **Compensation Floor:** Strict ₹30.0 LPA minimum. Disclosed jobs with a maximum ceiling $< 30$ LPA are automatically rejected. Undisclosed compensation is permitted.
4. **Physical Evidence & Click-to-Verify Guarantee:** No application is marked `APPLIED_CONFIRMED` without authentic proof:
   - Green `.already-applied` badge on listing page, or
   - Level 1 direct modal confirmation reference ID (`CHATBOT_CONFIRMED`), accompanied by
   - Visual screenshot saved on disk in `artifacts/evidence/<job_id>_already_applied.png`.
5. **Daily Cumulative Email Reporting:** Daily emails query all applications recorded today (`submitted_at >= today_start` or `started_at >= today_start`), guaranteeing zero blank emails on subsequent runs and zero historical leaks from previous days.
6. **Application Quota:** Enforces hard daily cap of 35 automated applications to protect candidate account standing.

---

## 6. Operational Runbook & Common Commands

### Connect to VPS
```bash
ssh -i "C:\Users\2016tu\Desktop\Projects\VPS\id_ed25519" opc@129.158.196.248
```

### Check Real-Time Memory & Swap Health
```bash
free -h
swapon --show
uptime
```

### View Live Execution Logs
```bash
tail -f /home/opc/CareerOps/logs/cron_run.log
```

### Run Phase Gate Audit (Proof Verification)
```bash
cd /home/opc/CareerOps
PYTHONPATH=. venv/bin/python main.py --validate-phase
```

### Execute Manual Pipeline Run (Live Mode)
```bash
/home/opc/CareerOps/run_daily.sh
```

### Execute Manual Dry-Run (Safe Validation)
```bash
/home/opc/CareerOps/run_daily.sh --dry-run
```

### Run Full Test Suite on Server
```bash
cd /home/opc/CareerOps
PYTHONPATH=. venv/bin/pytest tests/unit/ tests/integration/
```

### View or Edit Crontab Schedule
```bash
crontab -l
crontab -e
```
