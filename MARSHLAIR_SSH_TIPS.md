# MarshLair SSH & PowerShell Tips
## The Wrestling Match: Linux SSH → Windows PowerShell

### Connection Basics
```bash
# MarshLair has spaces in the username. ALWAYS use -l flag:
ssh -i ~/.ssh/id_desktop -l "Blue Kitty" 10.0.0.123

# SCP works fine with the quoted user:
scp -i ~/.ssh/id_desktop file.txt "Blue Kitty@10.0.0.123:E:/path/file.txt"
```

### The PowerShell Escaping Problem
When running PowerShell commands over SSH, you're fighting THREE layers of escaping:
1. **Bash** on the local machine interprets the command string
2. **SSH** passes it to the remote shell
3. **PowerShell** on Windows interprets what arrives

This means dollar signs, quotes, and backslashes all need careful handling.

### What Works

**Simple commands (no variable interpolation needed):**
```bash
ssh -i ~/.ssh/id_desktop -l "Blue Kitty" 10.0.0.123 \
  'powershell -Command "Get-ChildItem E:\\path\\*.txt | Measure-Object"'
```

**File counts (the pattern we use most):**
```bash
ssh ... 'powershell -Command "(Get-ChildItem \"E:\\path\\*.txt\").Count"'
```

**Process management:**
```bash
ssh ... 'powershell -Command "Get-Process python* | Format-Table"'
ssh ... 'powershell -Command "Stop-Process -Id 1234 -Force"'
```

### What DOESN'T Work
**Writing multi-line PowerShell scripts over SSH.** The escaping becomes
impossible with variables, here-strings, and nested quotes.

### The Solution: SCP the Script
When you need to write or modify a .ps1 file on MarshLair:

1. **Write the file locally** (on MysteryOfGlass)
2. **SCP it over** to MarshLair
3. **Run it remotely**

```bash
# Step 1: Write locally
cat > /tmp/my_script.ps1 << 'EOF'
$var = "hello"
Write-Output $var
EOF

# Step 2: SCP to MarshLair
scp -i ~/.ssh/id_desktop /tmp/my_script.ps1 \
  "Blue Kitty@10.0.0.123:E:/path/my_script.ps1"

# Step 3: Run remotely
ssh -i ~/.ssh/id_desktop -l "Blue Kitty" 10.0.0.123 \
  'powershell -ExecutionPolicy Bypass -File "E:\path\my_script.ps1"'
```

### Launching Long-Running Processes
SSH will kill processes when it disconnects. Use one of:

**Start-Process (detached, preferred):**
```bash
ssh ... 'powershell -Command "Start-Process powershell -ArgumentList \"-ExecutionPolicy Bypass -File E:\\path\\script.ps1\" -WindowStyle Normal"'
```

**schtasks (survives logoff):**
```bash
ssh ... 'powershell -Command "schtasks /create /tn \"MyTask\" /tr \"E:\\path\\launch.bat\" /sc once /st 00:00 /f; schtasks /run /tn \"MyTask\""'
```

Note: schtasks needs a .bat wrapper that calls PowerShell:
```bat
@echo off
powershell -ExecutionPolicy Bypass -File "E:\path\script.ps1"
```

### Tar-Pipe for Bulk File Transfer
When transferring many files (e.g., 401 images):
```bash
tar cf - -C /local/path . | \
  ssh -i ~/.ssh/id_desktop -l "Blue Kitty" 10.0.0.123 \
  'tar xf - -C /cygdrive/e/remote/path'
```
This uses the MSYS/Git-Bash tar on Windows (available via OpenSSH).

### Key Paths on MarshLair
- **kohya_ss:** `E:\kohya_ss\` (NOT `E:\sd-scripts`)
- **kohya venv:** `E:\kohya_ss\venv\Scripts\python.exe`
- **sd-scripts:** `E:\kohya_ss\sd-scripts\`
- **ComfyUI:** `E:\ComfyUI_windows_portable\`
- **ComfyUI Python:** `E:\ComfyUI_windows_portable\python_embeded\python.exe`
- **LoRA output:** `E:\ComfyUI_windows_portable\ComfyUI\models\loras\`
- **Checkpoints:** `E:\ComfyUI_windows_portable\ComfyUI\models\checkpoints\`
- **Ollama:** localhost:11434 (accessible from network at 10.0.0.123:11434)

### Critical Package State (DO NOT CHANGE)
```
torch==2.1.2+cu118
torchvision==0.16.2+cu118
xformers==0.0.23.post1+cu118
bitsandbytes==0.43.3
```
**NEVER** upgrade bitsandbytes without pinning torch. The bnb upgrade
catastrophe of March 2026 cost us half a day.
