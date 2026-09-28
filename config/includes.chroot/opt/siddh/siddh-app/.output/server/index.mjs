import http from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const PORT = process.env.PORT || 3000;
const HOST = '0.0.0.0';

// Simple offline fallback API + kiosk HTML
const server = http.createServer((req, res) => {
  if (req.url === '/api/health') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({status: 'ok', time: new Date().toISOString()}));
    return;
  }

  if (req.url === '/api/telemetry/latest') {
    // Replace with real SQLite read
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({temperature: null, humidity: null, ammonia: null}));
    return;
  }

  // Serve kiosk HTML
  res.writeHead(200, {'Content-Type': 'text/html'});
  res.end(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FarmOS Kiosk</title>
<style>body{font-family:sans-serif;background:#1a1a2e;color:#e0e0e0;padding:2rem}
h1{color:#4ecca3} .card{background:#16213e;padding:1rem;border-radius:8px;margin:1rem 0}
</style></head>
<body><h1>🐔 FarmOS</h1>
<div class="card"><h2>Sensor Readings</h2><p id="sensors">Loading...</p></div>
<div class="card"><h2>Camera Feed</h2><p>go2rtc WebRTC stream goes here</p></div>
<script>
async function poll(){try{
  const r=await fetch('/api/telemetry/latest');
  const d=await r.json();
  document.getElementById('sensors').textContent=JSON.stringify(d);
}catch(e){document.getElementById('sensors').textContent='Offline — using local buffer'}
}
setInterval(poll,5000);poll();
</script></body></html>`);
});

server.listen(PORT, HOST, () => {
  console.log(`FarmOS kiosk server listening on http://${HOST}:${PORT}`);
});
