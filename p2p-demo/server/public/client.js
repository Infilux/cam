// client.js - browser viewer
const ws = new WebSocket(`ws://${location.host}`);
let pc;
let dataChannel;
const video = document.getElementById("remoteVideo");

// Replace with your TURN server details if using TURN
const turnConfig = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    // Example TURN (replace host/creds)
    {
      urls: ["turn:turn.example.com:3478", "turns:turn.example.com:5349"],
      username: "camera1",
      credential: "StrongPass123"
    }
  ]
};

function setupPeerConnection() {
  pc = new RTCPeerConnection(turnConfig);

  pc.ontrack = (event) => {
    video.srcObject = event.streams[0];
  };

  pc.onicecandidate = (event) => {
    if (event.candidate) {
      ws.send(JSON.stringify({ type: "ice", role: "viewer", candidate: event.candidate }));
    }
  };

  // If camera creates a datachannel, receive it here
  pc.ondatachannel = (evt) => {
    dataChannel = evt.channel;
    console.log("Received datachannel:", dataChannel.label);
    attachDataChannelHandlers();
  };
}

ws.onopen = () => {
  ws.send(JSON.stringify({ type: "register", role: "viewer" }));
  setupPeerConnection();
};

ws.onmessage = async (msg) => {
  const data = JSON.parse(msg.data);
  if (data.type === "offer") {
    await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify({ type: "answer", answer }));
  } else if (data.type === "ice" && data.candidate) {
    try {
      await pc.addIceCandidate(data.candidate);
    } catch (e) {
      console.warn("Add ICE failed:", e);
    }
  } else if (data.type === "control") {
    // fallback ack from camera via signaling
    console.log("Control fallback reply:", data);
  }
};

function attachDataChannelHandlers() {
  if (!dataChannel) return;
  dataChannel.onopen = () => console.log("DataChannel open");
  dataChannel.onmessage = (ev) => {
    console.log("From camera:", ev.data);
    // show ack or status in UI if desired
  };
  dataChannel.onclose = () => console.log("DataChannel closed");
}

// Controls
document.getElementById("ptzLeft").onclick = () => sendControl({ cmd: "ptz", dir: "left", speed: 1 });
document.getElementById("ptzRight").onclick = () => sendControl({ cmd: "ptz", dir: "right", speed: 1 });
document.getElementById("ptzUp").onclick = () => sendControl({ cmd: "ptz", dir: "up", speed: 1 });
document.getElementById("ptzDown").onclick = () => sendControl({ cmd: "ptz", dir: "down", speed: 1 });

document.getElementById("playbackStart").onclick = () => {
  const path = document.getElementById("playbackPath").value.trim();
  if (!path) return alert("Enter MP4 path accessible to camera machine");
  sendControl({ cmd: "playback", action: "start", path });
};
document.getElementById("playbackStop").onclick = () => sendControl({ cmd: "playback", action: "stop" });

document.getElementById("recStart").onclick = () => {
  const name = document.getElementById("recName").value.trim() || `record_${Date.now()}.mp4`;
  sendControl({ cmd: "record", action: "start", filename: name });
};
document.getElementById("recStop").onclick = () => sendControl({ cmd: "record", action: "stop" });

function sendControl(obj) {
  // Create datachannel from viewer side if needed
  if (!dataChannel) {
    try {
      dataChannel = pc.createDataChannel("ctrl");
      attachDataChannelHandlers();
    } catch (e) {
      console.warn("createDataChannel failed:", e);
    }
  }

  const msg = JSON.stringify(obj);
  if (dataChannel && dataChannel.readyState === "open") {
    dataChannel.send(msg);
  } else {
    // fallback: send control via signaling server to camera
    ws.send(JSON.stringify({ type: "control", role: "viewer", control: obj }));
  }
}
