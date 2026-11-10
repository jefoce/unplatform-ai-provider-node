import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "unplatform-ai-provider";
const MODEL_NODE_CLASS = "UPAIModel";
const EXPORT_ROUTE = "/upai/internal/export";
const CONFIG_ROUTE = "/userdata/upai%2Fconfig.json";
const HEALTH_ROUTE = "/upai/api/v1/health";
const FETCH_WRAPPED = Symbol.for(`${EXTENSION_NAME}.fetchApi`);

const SETTING_TOKEN = "UnplatformAI.Token";
const SETTING_ALLOW_LAN = "UnplatformAI.AllowLan";
const SETTING_MAX_RUNNING = "UnplatformAI.MaxRunning";
const SETTING_CATEGORY = ["Unplatform AI", "Server"];

let isSyncingSettings = false;
let configWriteChain = Promise.resolve();

function errorText(error) {
  return error instanceof Error ? error.message : String(error);
}

function showToast(kind, title, options = {}) {
  const toast = app.extensionManager?.toast;
  const notify = toast?.[kind];

  if (typeof notify === "function") {
    notify.call(toast, title, options);
    return;
  }

  if (kind === "error") {
    console.error(`[upai] ${title}`, options.description ?? "");
  }
}

/** Return `workflows/<name>.json` for a successful workflow save route. */
function savedWorkflowPath(route) {
  if (typeof route !== "string") return null;

  let decoded;
  try {
    decoded = decodeURIComponent(route.split(/[?#]/, 1)[0]);
  } catch {
    return null;
  }

  const match = /^(?:\/api)?\/userdata\/(workflows\/.+\.json)$/.exec(decoded);
  return match ? match[1] : null;
}

async function currentPrompt() {
  if (typeof app.graphToPrompt !== "function") {
    throw new Error("ComfyUI graphToPrompt is unavailable");
  }

  const result = await app.graphToPrompt();
  if (!result || typeof result.output !== "object" || result.output === null) {
    throw new Error("ComfyUI returned no API prompt");
  }

  return result.output;
}

async function postExport(source, prompt) {
  const response = await api.fetchApi(EXPORT_ROUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source,
      prompt,
      saved_at: Math.floor(Date.now() / 1000),
    }),
  });

  let result = null;
  try {
    result = await response.json();
  } catch {
    result = null;
  }

  if (!response.ok) {
    const serverMessage = result?.error?.message;
    const message =
      typeof serverMessage === "string"
        ? serverMessage
        : `export failed (${response.status})`;
    showToast("warning", "Unplatform AI: export failed", {
      description: message,
    });
    return;
  }

  if (result?.status === "invalid" && typeof result.status_reason === "string") {
    showToast("error", "Unplatform AI: workflow not published", {
      description: result.status_reason,
    });
  }
}

async function exportCurrentWorkflow(source) {
  try {
    await postExport(source, await currentPrompt());
  } catch (error) {
    showToast("warning", "Unplatform AI: export failed", {
      description: errorText(error),
    });
  }
}

function observeSave(route) {
  const source = savedWorkflowPath(route);
  if (source) void exportCurrentWorkflow(source);
}

function installSaveHook() {
  if (typeof api?.fetchApi !== "function" || api.fetchApi[FETCH_WRAPPED]) return;

  const original = api.fetchApi;
  const wrapped = async function (route, options) {
    const response = await original.call(this, route, options);
    const method = String(options?.method ?? "GET").toUpperCase();

    if (method === "POST" && response?.ok) observeSave(route);
    return response;
  };

  Object.defineProperty(wrapped, FETCH_WRAPPED, { value: true });
  api.fetchApi = wrapped;
}

async function publishWorkflow() {
  const workflow = app.extensionManager?.workflow?.activeWorkflow;
  const source = typeof workflow?.path === "string" ? workflow.path : null;

  if (!source || !source.startsWith("workflows/")) {
    showToast("warning", "Unplatform AI: save the workflow first");
    return;
  }

  await exportCurrentWorkflow(source);
}

function addPublishButton(node) {
  if (node?.constructor?.comfyClass !== MODEL_NODE_CLASS) return;
  if (node.__upaiPublishButton || typeof node.addWidget !== "function") return;

  node.addWidget("button", "Publish workflow", null, () => {
    void publishWorkflow();
  });
  node.__upaiPublishButton = true;
}

async function readServerConfig() {
  const response = await api.fetchApi(CONFIG_ROUTE);
  if (response.status === 404) return {};
  if (!response.ok) {
    throw new Error(`config read failed (${response.status})`);
  }

  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error("config.json is not valid JSON");
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("config.json is not a JSON object");
  }

  return body;
}

async function writeServerConfig(patch) {
  const config = { ...(await readServerConfig()), ...patch };
  const response = await api.fetchApi(CONFIG_ROUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    throw new Error(`config save failed (${response.status})`);
  }
}

function saveSettings(patch) {
  if (isSyncingSettings) return Promise.resolve();

  configWriteChain = configWriteChain
    .catch(() => undefined)
    .then(() => writeServerConfig(patch))
    .then(() => {
      showToast("info", "Unplatform AI settings saved", {
        description: "Restart ComfyUI to apply them.",
      });
    })
    .catch((error) => {
      showToast("error", "Unplatform AI settings not saved", {
        description: errorText(error),
      });
    });

  return configWriteChain;
}

/** Skip the registration-time onChange call; only user edits write config. */
function persistOnChange(patchForValue) {
  return (value, oldValue) => {
    if (oldValue === undefined) return undefined;
    return saveSettings(patchForValue(value));
  };
}

async function syncSettingsFromHealth() {
  const setting = app.extensionManager?.setting;
  if (typeof setting?.set !== "function") return;

  let health;
  try {
    const response = await api.fetchApi(HEALTH_ROUTE);
    if (!response.ok) return;
    health = await response.json();
  } catch {
    return;
  }

  isSyncingSettings = true;
  try {
    if (typeof health?.lan_allowed === "boolean") {
      await setting.set(SETTING_ALLOW_LAN, health.lan_allowed);
    }
    if (Number.isInteger(health?.max_running)) {
      await setting.set(SETTING_MAX_RUNNING, health.max_running);
    }
  } finally {
    isSyncingSettings = false;
  }
}

const settings = [
  {
    id: SETTING_TOKEN,
    category: SETTING_CATEGORY,
    name: "API token",
    tooltip:
      "Bearer token for the pack routes. Stored in upai config.json and never logged. Leave blank to keep the current token.",
    type: "text",
    defaultValue: "",
    onChange: persistOnChange((value) => ({
      token: typeof value === "string" ? value.trim() : "",
    })),
  },
  {
    id: SETTING_ALLOW_LAN,
    category: SETTING_CATEGORY,
    name: "Allow LAN clients",
    tooltip:
      "Let LAN peers reach the pack routes. Without a token this lets anyone on the network run workflows.",
    type: "boolean",
    defaultValue: false,
    onChange: persistOnChange((value) => ({ allow_lan: value === true })),
  },
  {
    id: SETTING_MAX_RUNNING,
    category: SETTING_CATEGORY,
    name: "Maximum running jobs",
    tooltip: "Pack jobs that run at the same time, from 1 to 8.",
    type: "number",
    attrs: { min: 1, max: 8, step: 1 },
    defaultValue: 1,
    onChange: persistOnChange((value) => {
      const number = Number(value);
      const clamped = Number.isFinite(number)
        ? Math.min(8, Math.max(1, Math.round(number)))
        : 1;
      return { max_running: clamped };
    }),
  },
];

app.registerExtension({
  name: EXTENSION_NAME,
  settings,
  commands: [
    {
      id: "upai.publishWorkflow",
      label: "Unplatform: Publish workflow",
      function: () => publishWorkflow(),
    },
  ],
  nodeCreated(node) {
    addPublishButton(node);
  },
  async setup() {
    installSaveHook();
    await syncSettingsFromHealth();
  },
});
