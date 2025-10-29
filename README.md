# cam
===================================================================
# server
===================================================================
cd p2p-demo/server
npm install

cd p2p-demo/server
npm install    # first time
node server.js
# server runs on port 8080 by default

===================================================================
# device
===================================================================
cd p2p-demo/device
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Also need system ffmpeg (apt) for MediaPlayer/MediaRecorder:
# -----------------------------------------------------------------
# Debian/Ubuntu:
sudo apt update && sudo apt install -y ffmpeg
# -----------------------------------------------------------------

cd p2p-demo/device
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# ensure ffmpeg is installed on the device: sudo apt install ffmpeg.
# set environment variables (optional) or edit .env.example and export.
export SIGNALING_WS="ws://<server-ip>:8080"
export TURN_URL="turn:turn.example.com:3478"
export TURN_USER="camera1"
export TURN_PASS="StrongPass123"

# Run the camera device
python3 camera.py

===================================================================
