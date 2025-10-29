#!/usr/bin/env python3
"""
camera.py - aiortc camera device for p2p-demo
Supports:
 - live camera (/dev/video0) or testsrc fallback
 - DataChannel 'ctrl' to receive commands (ptz / playback / record)
 - playback of local MP4 file (path on device)
 - recording current source to MP4 (device local file)
 - signaling via WebSocket to server.js
"""

import os
import asyncio
import json
import time
import websockets
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer
)
from aiortc.contrib.media import MediaPlayer, MediaRecorder

# Load config from env or defaults
SIGNALING = os.getenv("SIGNALING_WS", "ws://localhost:8080")
TURN_URL = os.getenv("TURN_URL", "stun:stun.l.google.com:19302")
TURN_USER = os.getenv("TURN_USER", None)
TURN_PASS = os.getenv("TURN_PASS", None)

ice_servers = [RTCIceServer(urls=[TURN_URL])]
if TURN_USER and TURN_PASS and TURN_URL.startswith("turn"):
    ice_servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=[TURN_URL], username=TURN_USER, credential=TURN_PASS)
    ]

ice_config = RTCConfiguration(ice_servers)

pc = None
player = None
recorder = None
data_channel = None

async def create_pc():
    global pc, player
    pc = RTCPeerConnection(ice_config)

    # Create DataChannel named 'ctrl' so viewer receives it if viewer doesn't create one
    channel = pc.createDataChannel("ctrl")

    @channel.on("open")
    def on_open():
        print("DataChannel open (camera side)")

    @channel.on("message")
    def on_message(msg):
        asyncio.ensure_future(handle_control_message(msg))

    # get video source
    if os.path.exists("/dev/video0"):
        try:
            player = MediaPlayer("/dev/video0", format="v4l2", options={"video_size": "640x480", "framerate": "15"})
            print("Using /dev/video0 as camera source")
        except Exception as e:
            print("Failed to open /dev/video0:", e)
            player = MediaPlayer("testsrc=size=640x480:rate=15", format="lavfi")
    else:
        player = MediaPlayer("testsrc=size=640x480:rate=15", format="lavfi")
        print("No /dev/video0; using testsrc")

    if player.video:
        pc.addTrack(player.video)

    return pc

async def handle_control_message(msg):
    global player, recorder
    print("Control msg:", msg)
    try:
        cmd = json.loads(msg)
    except Exception:
        print("Invalid JSON control msg")
        return

    if cmd.get("cmd") == "ptz":
        dir = cmd.get("dir")
        speed = cmd.get("speed", 1)
        # Replace with actual PTZ control (HTTP/serial/GPIO)
        reply = {"status": "ok", "cmd": "ptz", "dir": dir, "speed": speed}
        print("PTZ:", dir, speed)
        # send ack back if data channel open
        await send_to_viewer(reply)

    elif cmd.get("cmd") == "playback":
        action = cmd.get("action")
        if action == "start":
            path = cmd.get("path")
            if not path or not os.path.exists(path):
                await send_to_viewer({"status":"error","msg":f"file not found: {path}"})
                return
            # switch the outgoing video to file
            new_player = MediaPlayer(path)
            if new_player.video:
                await replace_video_track(new_player.video)
                player = new_player
                await send_to_viewer({"status":"ok","msg":"playback started"})
        elif action == "stop":
            # switch back to live or testsrc
            if os.path.exists("/dev/video0"):
                new_player = MediaPlayer("/dev/video0", format="v4l2", options={"video_size":"640x480","framerate":"15"})
            else:
                new_player = MediaPlayer("testsrc=size=640x480:rate=15", format="lavfi")
            if new_player.video:
                await replace_video_track(new_player.video)
                player = new_player
                await send_to_viewer({"status":"ok","msg":"playback stopped"})

    elif cmd.get("cmd") == "record":
        action = cmd.get("action")
        if action == "start":
            fname = cmd.get("filename", f"record_{int(time.time())}.mp4")
            if recorder:
                await send_to_viewer({"status":"error","msg":"recorder already running"})
                return
            recorder = MediaRecorder(fname)
            # addTrack expects MediaStreamTrack; attach current player.video
            if player and player.video:
                recorder.addTrack(player.video)
            await recorder.start()
            print("Recording started ->", fname)
            await send_to_viewer({"status":"ok","msg":f"recording started: {fname}"})
        elif action == "stop":
            if not recorder:
                await send_to_viewer({"status":"error","msg":"no recorder running"})
                return
            await recorder.stop()
            recorder = None
            print("Recording stopped")
            await send_to_viewer({"status":"ok","msg":"recording stopped"})

    else:
        await send_to_viewer({"status":"error","msg":"unknown command"})

async def send_to_viewer(obj):
    # prefer datachannel; otherwise send via signaling fallback by writing to WS (handled in signaling loop)
    try:
        if data_channel and data_channel.readyState == "open":
            data_channel.send(json.dumps(obj))
        else:
            # fallback: send back via signaling websocket using special 'control_reply' message
            if ws_conn:
                await ws_conn.send(json.dumps({"type":"control_reply","reply":obj}))
    except Exception as e:
        print("send_to_viewer failed:", e)

async def replace_video_track(new_track):
    """
    Replaces the outgoing video track on the existing RTCPeerConnection
    """
    senders = pc.getSenders()
    video_sender = None
    for s in senders:
        if s.track and s.track.kind == "video":
            video_sender = s
            break
    if not video_sender:
        print("No video sender found")
        return
    await video_sender.replace_track(new_track)
    print("Outgoing video track replaced")

ws_conn = None

async def signaling_loop():
    global ws_conn, pc, data_channel
    async with websockets.connect(SIGNALING) as ws:
        ws_conn = ws
        # register
        await ws.send(json.dumps({"type":"register","role":"camera"}))
        print("Registered to signaling")

        pc = await create_pc()

        # If camera already created dataChannel above, keep reference
        # try to find channel object for sending acks later:
        # aiortc's createDataChannel returns a local object assigned earlier. We'll set global after create_pc
        for dc in pc.sctp.transports if False else []:
            pass

        # create offer and set local description
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await ws.send(json.dumps({"type":"offer","offer": {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}}))
        print("Offer sent, waiting for answer...")

        async for raw in ws:
            if raw is None:
                break
            try:
                data = json.loads(raw)
            except Exception:
                continue

            if data.get("type") == "answer":
                desc = RTCSessionDescription(sdp=data["answer"]["sdp"], type=data["answer"]["type"])
                await pc.setRemoteDescription(desc)
                print("Answer applied")

            elif data.get("type") == "ice" and data.get("candidate"):
                try:
                    await pc.addIceCandidate(data["candidate"])
                except Exception as e:
                    print("Error adding ICE candidate:", e)

            elif data.get("type") == "control":
                # fallback control sent via signaling from viewer
                control = data.get("control")
                if control:
                    await handle_control_message(json.dumps(control))

            elif data.get("type") == "control_reply":
                # viewer ack replies (not used often)
                print("control_reply:", data.get("reply"))

async def main():
    await signaling_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down")
