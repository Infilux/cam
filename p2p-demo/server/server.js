// server.js - simple WebSocket signaling server
const express = require("express");
const http = require("http");
const WebSocket = require("ws");
const app = express();

app.use(express.static("public"));

const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// We keep references to one camera and one viewer for this demo.
// For production you'd support many devices and auth.
let cameraSocket = null;
let viewerSocket = null;

wss.on("connection", (ws) => {
  ws.on("message", (message) => {
    let data;
    try { data = JSON.parse(message); } catch (e) { return; }

    // Registration messages
    if (data.type === "register" && data.role === "camera") {
      cameraSocket = ws;
      ws._role = "camera";
      console.log("📷 Camera connected");
      return;
    }
    if (data.type === "register" && data.role === "viewer") {
      viewerSocket = ws;
      ws._role = "viewer";
      console.log("👀 Viewer connected");
      return;
    }

    // Forward offer/answer/ice/control messages between camera & viewer
    // Offer from camera -> viewer
    if (data.type === "offer" && viewerSocket) {
      viewerSocket.send(JSON.stringify(data));
      return;
    }
    // Answer from viewer -> camera
    if (data.type === "answer" && cameraSocket) {
      cameraSocket.send(JSON.stringify(data));
      return;
    }
    // ICE candidates - route based on sender role field or ws._role
    if (data.type === "ice") {
      // require data.role = 'camera' or 'viewer' for clarity in messages
      if (data.role === "camera" && viewerSocket) {
        viewerSocket.send(JSON.stringify(data));
      } else if (data.role === "viewer" && cameraSocket) {
        cameraSocket.send(JSON.stringify(data));
      }
      return;
    }

    // Control fallbacks (if client didn't open datachannel)
    if (data.type === "control") {
      // control from viewer to camera
      if (data.role === "viewer" && cameraSocket) {
        cameraSocket.send(JSON.stringify({ type: "control", control: data.control }));
      }
      return;
    }
  });

  ws.on("close", () => {
    if (ws === cameraSocket) {
      console.log("Camera disconnected");
      cameraSocket = null;
    } else if (ws === viewerSocket) {
      console.log("Viewer disconnected");
      viewerSocket = null;
    }
  });
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => console.log(`✅ Signaling server running on http://0.0.0.0:${PORT}`));
