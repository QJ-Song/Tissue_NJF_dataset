# Isaac Sim Workspace

This directory is prepared for NVIDIA Isaac Sim on the remote Ubuntu server:

- Host: `renlab-Z790-EAGLE-AX`
- OS: Ubuntu `24.04.4 LTS`
- Architecture: `x86_64`
- GPU: NVIDIA GeForce RTX 5090, 32 GB VRAM
- Driver: `595.71.05`
- CUDA reported by driver: `13.2`
- Python: `3.12.3`
- Isaac Sim target: `6.0.0.1`

The selected installation method is the official Python/pip workflow. It keeps
Isaac Sim inside `env_isaacsim/` under this workspace.

## Install

Run these commands on the Ubuntu server, not from the macOS SMB client:

```bash
cd ~/issacsim
chmod +x scripts/check_host.sh scripts/install_isaacsim.sh
./scripts/install_isaacsim.sh
```

The script installs:

- PyTorch `2.11.0` from the CUDA 13 wheel index
- Isaac Sim `6.0.0.1` with the `all` extra

The optional extension cache is split out because it is a very large download:

```bash
./scripts/install_extscache.sh
```

## Run

After installation:

```bash
cd ~/issacsim
source env_isaacsim/bin/activate
export OMNI_KIT_ACCEPT_EULA=YES
isaacsim isaacsim.exp.compatibility_check
bash scripts/runisaacsim.sh
```

The compatibility check passed on this host after clearing a stale
`/tmp/fuse` mount. If it fails again with `df: /tmp/fuse: Transport endpoint is
not connected`, run:

```bash
bash scripts/fixfuse.sh
```

Set `OMNI_KIT_ACCEPT_EULA=YES` only after reviewing and accepting the NVIDIA
Omniverse license terms.

When running through a plain SSH or VS Code Remote terminal, Isaac Sim can pass
the system checks but still report that no display was detected. Start the GUI
from the server's desktop session or use a supported livestreaming/remote
desktop method for interactive graphics.

The helper script `scripts/runisaacsim.sh` starts Isaac Sim with the ROS 2
bridge disabled. Isaac Sim Full enables the ROS 2 bridge by default on Linux,
but it requires a working ROS 2 environment. Enable it only after sourcing the
intended ROS 2 setup.

## Notes

The directory name is currently `issacsim`. NVIDIA's product name is
`Isaac Sim`; the scripts work with the current directory name.
