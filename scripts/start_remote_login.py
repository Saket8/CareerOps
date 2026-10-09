import subprocess
import os

# Check if x11vnc or any web-based vnc is installed
res = subprocess.run(["which", "x11vnc"], capture_output=True, text=True)
print("x11vnc available:", bool(res.stdout.strip()))

# Check websockify / novnc
res2 = subprocess.run(["which", "websockify"], capture_output=True, text=True)
print("websockify available:", bool(res2.stdout.strip()))
