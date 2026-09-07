const API = `${location.protocol}//${location.hostname}:8001`;
const SIZE = 64;
const SCALE = 10;
const canvas = document.querySelector('#canvas');
const ctx = canvas.getContext('2d');
const status = document.querySelector('#status');
let version = -1;
let pixels = Array(SIZE * SIZE).fill('#ffffff');
let busy = false;

canvas.style.width = `${SIZE * SCALE}px`;
canvas.style.height = `${SIZE * SCALE}px`;

function render() {
  for (let y = 0; y < SIZE; y += 1) {
    for (let x = 0; x < SIZE; x += 1) {
      ctx.fillStyle = pixels[y * SIZE + x];
      ctx.fillRect(x, y, 1, 1);
    }
  }
}

async function refresh() {
  if (busy) return;
  busy = true;
  try {
    const response = await fetch(`${API}/state`, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    if (state.version !== version) {
      pixels = state.pixels;
      version = state.version;
      render();
    }
    status.textContent = `接続済み · version ${version}`;
    status.classList.remove('error');
  } catch (error) {
    status.textContent = `API接続エラー: ${error.message}`;
    status.classList.add('error');
  } finally {
    busy = false;
  }
}

document.querySelector('#clear').addEventListener('click', async () => {
  const response = await fetch(`${API}/clear`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
  if (response.ok) refresh();
});

document.querySelector('#save').addEventListener('click', () => {
  const link = document.createElement('a');
  link.href = `${API}/image?download=${Date.now()}`;
  link.download = 'pixel-canvas.png';
  link.click();
});

document.querySelector('#grid').addEventListener('change', (event) => {
  document.querySelector('.canvas-wrap').classList.toggle('no-grid', !event.target.checked);
});

render();
refresh();
setInterval(refresh, 250);
