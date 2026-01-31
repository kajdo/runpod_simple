# runpod_simple
Template for simple setup of ollama + openwebUI for glm-4.7-flash

## Automation CLI
Automated deployment tool for RunPod pods with SSH tunneling.

### Setup
1. Copy `.env.example` to `.env` and fill in your API key:
```bash
cp .env.example .env
# Edit .env with your RUNPOD_API_KEY
```

2. Enter Nix shell (for NixOS) or install dependencies:
```bash
# NixOS
nix-shell

# Other systems
pip install -r requirements.txt
```

### Usage
```bash
python main.py deploy                # Deploy pod with interactive prompts
python main.py deploy --no-reuse      # Always create new pod (skip reuse)
python main.py deploy --no-cleanup    # Keep pod running after Ctrl+C
python main.py list                  # List all pods
python main.py delete <pod_id>       # Delete specific pod
```

### Deploy Command Options
```bash
python main.py deploy [OPTIONS]

Options:
  --no-reuse          Skip existing pod selection, always create new pod
  --template-id ID     Use specific template ID (skip selection)
  --volume-id ID       Use specific network volume ID (skip selection)
  --auto-select-gpu    Auto-select cheapest GPU without prompting
  --no-cleanup        Don't delete pod on exit (keep running)
```

**Notes:**
- When only one template/volume exists, it's auto-selected
- With `--auto-select-gpu`, the cheapest GPU is chosen automatically
- GPU selection shows all 24GB+ options with cheapest marked with ★

### Features
- Interactive template and network volume selection
- Automatic GPU selection (24GB+ vRAM, cheapest option)
- Interactive GPU selection with cheapest as default
- SSH key authentication preferred, password fallback
- SSH tunnels for Ollama (11434) and WebUI (8080)
- Network-wide access (binds to 0.0.0.0) with fallback to localhost
- Automatic pod reuse for existing running pods
- Automatic pod cleanup on exit (unless --no-cleanup)
- Progress bars for pod deployment
- Clear error messages for deployment failures
- Datacenter compatibility checks

### Network Access
The tool tries to bind SSH tunnels to `0.0.0.0` for network-wide access.
If this fails (e.g., permission denied), it falls back to `127.0.0.1` (localhost only).

To enable network-wide access on Linux:
```bash
sudo python main.py deploy
```

Or configure SSH to allow user port binding in `/etc/ssh/ssh_config`.

### Manual tunnel
For manual SSH tunneling:
```bash
ssh -4 -L 0.0.0.0:11434:127.0.0.1:11434 root@<IP> -p <PORT>
ssh -4 -L 0.0.0.0:8080:127.0.0.1:8080 root@<IP> -p <PORT>
```

