const COMMANDS = {
  forward: { key: "w", label: "вперёд" },
  backward: { key: "s", label: "назад" },
  left: { key: "a", label: "влево" },
  right: { key: "d", label: "вправо" },
};

const KEY_COMMANDS = Object.fromEntries(
  Object.entries(COMMANDS).map(([command, details]) => [details.key, command]),
);

const videoFeed = document.querySelector("#video-feed");
const videoPlaceholder = document.querySelector("#video-placeholder");
const reconnectButtons = [
  document.querySelector("#reconnect-camera"),
  document.querySelector("#reconnect-camera-small"),
];
const connection = document.querySelector("#connection");
const connectionLabel = document.querySelector("#connection-label");
const videoState = document.querySelector("#video-state");
const videoLabel = document.querySelector("#video-label");
const speedInput = document.querySelector("#speed");
const speedValue = document.querySelector("#speed-value");
const feedback = document.querySelector("#drive-feedback");
const activeKeys = new Set();
let activeButtonCommand = null;
let commandPending = false;
let statusPending = false;
let cameraRetry = 0;

function setConnection(state, label) {
  connection.dataset.state = state;
  connectionLabel.textContent = label;
}

function showVideoFailure() {
  videoFeed.hidden = true;
  videoPlaceholder.hidden = false;
  videoState.dataset.state = "offline";
  videoLabel.textContent = "Камера недоступна";
  document.querySelector("#placeholder-title").textContent = "Нет видеосигнала";
  document.querySelector("#placeholder-copy").textContent =
    "Проверьте питание камеры и подключение робота";
  document.querySelector("#reconnect-camera").hidden = false;
}

function connectCamera() {
  videoState.dataset.state = "connecting";
  videoLabel.textContent = "Подключаем камеру";
  document.querySelector("#placeholder-title").textContent = "Ожидаем изображение";
  document.querySelector("#placeholder-copy").textContent =
    "Подключаемся к камере RobotViRed";
  document.querySelector("#reconnect-camera").hidden = true;
  videoPlaceholder.hidden = false;
  videoFeed.hidden = true;
  cameraRetry += 1;
  videoFeed.src = `/api/robot/video?session=${cameraRetry}`;
}

videoFeed.addEventListener("load", () => {
  videoFeed.hidden = false;
  videoPlaceholder.hidden = true;
  videoState.dataset.state = "live";
  videoLabel.textContent = "Прямой эфир";
});
videoFeed.addEventListener("error", showVideoFailure);
reconnectButtons.forEach((button) => button.addEventListener("click", connectCamera));

function readableState(value) {
  const states = {
    moving: "В движении",
    stopped: "Остановлен",
    idle: "Ожидание",
    stop: "Остановлен",
  };
  return states[value] || value || "Нет данных";
}

function readableCommand(value) {
  if (value === "stop") return "Остановка";
  return COMMANDS[value]?.label
    ? `Движение ${COMMANDS[value].label}`
    : value || "—";
}

async function updateStatus() {
  if (statusPending) return;
  statusPending = true;

  try {
    const response = await fetch("/api/robot/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status");
    const data = await response.json();

    setConnection("connected", "Робот на связи");
    document.querySelector("#status-pulse").dataset.state = "connected";
    document.querySelector("#robot-state").textContent = readableState(data.state);
    document.querySelector("#last-command").textContent = readableCommand(data.last_cmd);

    const battery = data.battery;
    const batteryValue = document.querySelector("#battery-value");
    const batteryLevel = document.querySelector("#battery-level");
    if (typeof battery === "number" && Number.isFinite(battery)) {
      const percent = Math.max(0, Math.min(100, battery));
      batteryValue.textContent = `${Math.round(percent)}%`;
      batteryLevel.style.width = `${percent}%`;
      batteryLevel.style.backgroundColor = percent <= 20 ? "var(--red)" : "var(--green)";
    } else {
      batteryValue.textContent = battery == null ? "Не передаётся" : "—";
      batteryLevel.style.width = "0";
    }

    document.querySelector("#updated-at").textContent =
      `Обновлено в ${new Date().toLocaleTimeString("ru-RU")}`;
  } catch {
    setConnection("offline", "Нет связи с роботом");
    document.querySelector("#status-pulse").dataset.state = "offline";
    document.querySelector("#robot-state").textContent = "Нет связи";
    document.querySelector("#last-command").textContent = "—";
    document.querySelector("#battery-value").textContent = "—";
    document.querySelector("#battery-level").style.width = "0";
    document.querySelector("#updated-at").textContent = "Не удалось получить состояние";
  } finally {
    statusPending = false;
  }
}

function setFeedback(message, state = "") {
  feedback.textContent = message;
  feedback.dataset.state = state;
}

async function sendDrive(command) {
  if (commandPending && command !== "stop") {
    setFeedback("Ожидаем подтверждение предыдущей команды", "error");
    return false;
  }

  const isStop = command === "stop";
  if (!isStop) commandPending = true;
  try {
    const response = await fetch("/api/robot/drive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cmd: command,
        speed: command === "stop" ? 0 : Number(speedInput.value),
        ms: 0,
      }),
    });

    if (!response.ok) throw new Error("drive");
    const label = command === "stop" ? "Остановка подтверждена" : `Робот принял команду: ${COMMANDS[command].label}`;
    setFeedback(label, "success");
    return true;
  } catch {
    setFeedback("Нет подтверждения от робота. Проверьте связь и состояние движения.", "error");
    return false;
  } finally {
    if (!isStop) commandPending = false;
    updateStatus();
  }
}

function setActiveDirection(command, active) {
  const button = document.querySelector(`[data-command="${command}"]`);
  if (button) button.dataset.active = String(active);
}

function startDirection(command) {
  if (command === activeButtonCommand) return;
  if (activeButtonCommand) setActiveDirection(activeButtonCommand, false);
  activeButtonCommand = command;
  setActiveDirection(command, true);
  sendDrive(command);
}

function stopDirection() {
  if (!activeButtonCommand) return;
  const previous = activeButtonCommand;
  activeButtonCommand = null;
  setActiveDirection(previous, false);
  sendDrive("stop");
}

function stopKeyboardDirections() {
  if (activeKeys.size === 0) return;
  activeKeys.clear();
  document.querySelectorAll(".direction-key[data-active='true']").forEach((button) => {
    button.dataset.active = "false";
  });
  sendDrive("stop");
}

document.querySelectorAll(".direction-key").forEach((button) => {
  const command = button.dataset.command;
  button.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    startDirection(command);
  });
  button.addEventListener("pointerup", stopDirection);
  button.addEventListener("pointercancel", stopDirection);
  button.addEventListener("pointerleave", (event) => {
    if (event.buttons !== 0) stopDirection();
  });
  button.addEventListener("keydown", (event) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    startDirection(command);
  });
  button.addEventListener("keyup", (event) => {
    if (event.key === " " || event.key === "Enter") stopDirection();
  });
});

document.querySelector("#stop-button").addEventListener("click", () => {
  activeButtonCommand = null;
  activeKeys.clear();
  document.querySelectorAll(".direction-key").forEach((button) => {
    button.dataset.active = "false";
  });
  sendDrive("stop");
});

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;

  if (key === " " && !["INPUT", "BUTTON"].includes(document.activeElement?.tagName)) {
    event.preventDefault();
    document.querySelector("#stop-button").click();
    return;
  }

  const command = KEY_COMMANDS[key];
  if (!command || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
  event.preventDefault();
  activeKeys.add(key);
  const button = document.querySelector(`[data-command="${command}"]`);
  if (button) button.dataset.active = "true";
  sendDrive(command);
});

document.addEventListener("keyup", (event) => {
  const key = event.key.toLowerCase();
  if (!KEY_COMMANDS[key] || !activeKeys.delete(key)) return;
  const command = KEY_COMMANDS[key];
  const button = document.querySelector(`[data-command="${command}"]`);
  if (button) button.dataset.active = "false";
  if (activeKeys.size === 0) sendDrive("stop");
});

window.addEventListener("blur", stopKeyboardDirections);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopKeyboardDirections();
    stopDirection();
  }
});
window.addEventListener("pagehide", () => {
  if (activeKeys.size > 0 || activeButtonCommand) {
    fetch("/api/robot/drive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd: "stop", speed: 0, ms: 0 }),
      keepalive: true,
    }).catch(() => {});
  }
});

speedInput.addEventListener("input", () => {
  speedValue.textContent = speedInput.value;
});

function updateClock() {
  document.querySelector("#camera-clock").textContent =
    new Date().toLocaleTimeString("ru-RU", { hour12: false });
}

connectCamera();
updateClock();
updateStatus();
window.setInterval(updateStatus, 5000);
window.setInterval(updateClock, 1000);
