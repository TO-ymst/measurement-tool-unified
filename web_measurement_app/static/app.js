const form = document.getElementById("config-form");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const statusBadge = document.getElementById("status-indicator");
const statusMessage = document.getElementById("status-message");
const logPathEl = document.getElementById("log-path");
const neighborLogPathEl = document.getElementById("neighbor-log-path");
const advancedLogPathEl = document.getElementById("advanced-log-path");
const pingDetailsEl = document.getElementById("ping-details");
const liveLog = document.getElementById("live-log");
const measurementModeSelect = document.getElementById("measurement-mode-select");
const bandSelect = document.getElementById("band-select");
const mapFileInput = document.getElementById("map-file");
const resetMapBtn = document.getElementById("reset-map");
const undoPointBtn = document.getElementById("undo-point-btn");
const zoomOutBtn = document.getElementById("zoom-out-btn");
const zoomInBtn = document.getElementById("zoom-in-btn");
const zoomResetBtn = document.getElementById("zoom-reset-btn");
const panModeToggle = document.getElementById("pan-mode-toggle");
const modeRadios = document.querySelectorAll("input[name=mode]");
const canvas = document.getElementById("map-canvas");
const ctx = canvas.getContext("2d");
const labelSizeNumber = document.getElementById("label-size-number");
const labelSizeRange = document.getElementById("label-size-range");
const anchorRadiusNumber = document.getElementById("anchor-radius-number");
const anchorRadiusRange = document.getElementById("anchor-radius-range");
const plotRadiusNumber = document.getElementById("plot-radius-number");
const plotRadiusRange = document.getElementById("plot-radius-range");
const plotShapeSelect = document.getElementById("plot-shape-select");
const labelColorInput = document.getElementById("label-color");
const grayscaleToggle = document.getElementById("grayscale-toggle");
const grayscaleRange = document.getElementById("grayscale-range");
const legendToggle = document.getElementById("legend-toggle");
const legendContainer = document.getElementById("legend-container");
const exportTitleInput = document.getElementById("export-title");
const exportButton = document.getElementById("export-btn");
const exportAllButton = document.getElementById("export-all-btn");
const remotePrepareBtn = document.getElementById("remote-prepare-btn");
const bssidSwitchSection = document.getElementById("bssid-switch-section");
const apSwitchSelect = document.getElementById("ap-switch-select");
const apSwitchPassword = document.getElementById("ap-switch-password");
const bssidSwitchSelect = document.getElementById("bssid-switch-select");
const refreshBssidBtn = document.getElementById("refresh-bssid-btn");
const switchApBtn = document.getElementById("switch-ap-btn");
const fixApBtn = document.getElementById("fix-ap-btn");
const clearApFixBtn = document.getElementById("clear-ap-fix-btn");
const switchBssidBtn = document.getElementById("switch-bssid-btn");
const fixBssidBtn = document.getElementById("fix-bssid-btn");
const clearBssidFixBtn = document.getElementById("clear-bssid-fix-btn");
const apSwitchStatus = document.getElementById("ap-switch-status");
const bssidSwitchStatus = document.getElementById("bssid-switch-status");
const titleToggle = document.getElementById("title-toggle");
const timezoneSelect = document.getElementById("timezone-select");
const ssidDatalist = document.getElementById("ssid-options");
const pingTargetInput = document.getElementById("ping-target");
const pingTargetHint = document.getElementById("ping-target-hint");
const autoGatewayCheckbox = document.querySelector("input[name=auto_gateway]");
const pointCsvInput = document.getElementById("point-csv-file");
const importPointBtn = document.getElementById("import-point-btn");
const referenceCsvInput = document.getElementById("reference-csv-file");
const overlayCsvInput = document.getElementById("overlay-csv-file");
const importAlignedBtn = document.getElementById("import-aligned-btn");
const importToleranceInput = document.getElementById("import-tolerance-ms");

const state = {
  running: false,
  localBssidSwitchSupported: false,
  currentWifi: {},
  bssidSwitchEnabledSsid: "",
  bssidLock: {},
  apLock: {},
  bands: {},
  ssidOptions: [],
  timezoneOptions: [],
  pointOffset: 0,
  socket: null,
  reconnectTimer: null,
  liveBuffer: [],
  logsByPoint: new Map(),
  points: [],
  segments: [],
  currentLogFile: "",
  currentMode: "ping",
  image: null,
  view: {
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    panMode: false,
    panning: false,
    lastPanX: 0,
    lastPanY: 0,
  },
  display: {
    labelSize: Number(labelSizeNumber?.value) || 14,
    anchorRadius: Number(anchorRadiusNumber?.value) || 5,
    plotRadius: Number(plotRadiusNumber?.value) || 3,
    plotShape: plotShapeSelect?.value || "dot",
    labelColor: labelColorInput?.value || "#ff5de4",
    grayscaleEnabled: false,
    grayscaleLevel: Number(grayscaleRange?.value) || 100,
  },
};

async function init() {
  await loadDefaults();
  await loadStatus();
  attachEvents();
  connectSocket();
  drawCanvas();
  canvas.style.cursor = "crosshair";
  renderLegend();
}

async function loadDefaults() {
  try {
    const resp = await fetch("/api/defaults");
    const data = await resp.json();
    state.localBssidSwitchSupported = Boolean(data.local_bssid_switch_supported);
    state.bands = data.bands || {};
    state.ssidOptions = data.ssid_options || [];
    state.timezoneOptions = data.timezone_options || [];
    form.ssid.value = data.ssid;
    form.measurement_mode.value = data.measurement_mode || "local";
    form.band.value = data.band;
    form.channel_min.value = data.channel_min;
    form.channel_max.value = data.channel_max;
    form.interval.value = data.interval;
    form.ping_fail_value.value = data.ping_fail_value;
    form.ping_timeout_ms.value = data.ping_timeout_ms;
    form.wifi_disconnected_value.value = data.wifi_disconnected_value;
    form.log_base.value = data.log_base;
    form.timezone.value = data.timezone;
    if (form.remote_host) form.remote_host.value = data.remote_host || "";
    if (form.remote_user) form.remote_user.value = data.remote_user || "";
    if (form.remote_port) form.remote_port.value = data.remote_port || 22;
    if (form.remote_identity_file) form.remote_identity_file.value = data.remote_identity_file || "";
    if (form.remote_neighbor_every) form.remote_neighbor_every.value = data.remote_neighbor_every ?? 5;
    if (form.remote_neighbor_ssid) form.remote_neighbor_ssid.value = data.remote_neighbor_ssid || "";
    if (form.remote_ssh_key_comment) form.remote_ssh_key_comment.value = data.remote_ssh_key_comment || "";
    form.auto_gateway.checked = data.auto_gateway;
    if (form.remote_enable_neighbor_scan) form.remote_enable_neighbor_scan.checked = !!data.remote_enable_neighbor_scan;
    if (form.remote_setup_ssh_key) form.remote_setup_ssh_key.checked = !!data.remote_setup_ssh_key;
    if (form.remote_cleanup_ssh_key) form.remote_cleanup_ssh_key.checked = !!data.remote_cleanup_ssh_key;
    if (form.remote_delete_local_key) form.remote_delete_local_key.checked = !!data.remote_delete_local_key;
    if (form.remote_advanced_enabled) form.remote_advanced_enabled.checked = !!data.remote_advanced_enabled;
    if (form.remote_advanced_include_neighbor) form.remote_advanced_include_neighbor.checked = !!data.remote_advanced_include_neighbor;
    if (form.remote_advanced_include_routes) form.remote_advanced_include_routes.checked = !!data.remote_advanced_include_routes;
    if (form.remote_advanced_include_ip_addr) form.remote_advanced_include_ip_addr.checked = !!data.remote_advanced_include_ip_addr;
    if (form.remote_advanced_include_wifi_details) form.remote_advanced_include_wifi_details.checked = !!data.remote_advanced_include_wifi_details;
    if (form.remote_advanced_include_journal) form.remote_advanced_include_journal.checked = !!data.remote_advanced_include_journal;
    if (form.remote_advanced_snapshot_on_bssid_change) form.remote_advanced_snapshot_on_bssid_change.checked = !!data.remote_advanced_snapshot_on_bssid_change;
    if (form.remote_advanced_snapshot_on_ping_timeout) form.remote_advanced_snapshot_on_ping_timeout.checked = !!data.remote_advanced_snapshot_on_ping_timeout;
    if (form.remote_advanced_ping_timeout_streak) form.remote_advanced_ping_timeout_streak.value = data.remote_advanced_ping_timeout_streak ?? 1;
    if (form.remote_advanced_max_output_chars) form.remote_advanced_max_output_chars.value = data.remote_advanced_max_output_chars ?? 12000;
    renderSsidOptions();
    renderTimezoneOptions(data.timezone);
    syncMeasurementModeState();
  } catch (error) {
    console.error("defaults", error);
  }
}

function attachEvents() {
  ensurePanToggleUI();

  bandSelect.addEventListener("change", () => {
    const limits = state.bands[bandSelect.value];
    if (limits) {
      form.channel_min.value = limits.min;
      form.channel_max.value = limits.max;
    }
  });
  if (measurementModeSelect) {
    measurementModeSelect.addEventListener("change", syncMeasurementModeState);
  }
  const remoteNeighborToggle = form.querySelector("input[name=remote_enable_neighbor_scan]");
  if (remoteNeighborToggle) {
    remoteNeighborToggle.addEventListener("change", syncMeasurementModeState);
  }
  const remoteAdvancedToggle = form.querySelector("input[name=remote_advanced_enabled]");
  if (remoteAdvancedToggle) {
    remoteAdvancedToggle.addEventListener("change", syncMeasurementModeState);
  }

  startBtn.addEventListener("click", handleStart);
  stopBtn.addEventListener("click", handleStop);
  if (remotePrepareBtn) {
    remotePrepareBtn.addEventListener("click", handleRemotePrepare);
  }
  if (refreshBssidBtn) {
    refreshBssidBtn.addEventListener("click", loadAccessPointCandidates);
  }
  if (bssidSwitchSelect) {
    bssidSwitchSelect.addEventListener("change", syncBssidSwitchState);
  }
  if (apSwitchSelect) {
    apSwitchSelect.addEventListener("change", syncBssidSwitchState);
  }
  if (switchApBtn) {
    switchApBtn.addEventListener("click", handleApSwitch);
  }
  if (fixApBtn) {
    fixApBtn.addEventListener("click", handleApFix);
  }
  if (clearApFixBtn) {
    clearApFixBtn.addEventListener("click", handleClearApFix);
  }
  if (switchBssidBtn) {
    switchBssidBtn.addEventListener("click", handleBssidSwitch);
  }
  if (fixBssidBtn) {
    fixBssidBtn.addEventListener("click", handleBssidFix);
  }
  if (clearBssidFixBtn) {
    clearBssidFixBtn.addEventListener("click", handleClearBssidFix);
  }
  if (undoPointBtn) {
    undoPointBtn.addEventListener("click", handleUndoLastPoint);
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener("click", () => adjustZoom(1 / 1.2));
  }
  if (zoomInBtn) {
    zoomInBtn.addEventListener("click", () => adjustZoom(1.2));
  }
  if (zoomResetBtn) {
    zoomResetBtn.addEventListener("click", resetViewTransform);
  }
  if (panModeToggle) {
    panModeToggle.addEventListener("change", (event) => {
      state.view.panMode = !!event.target.checked;
      state.view.panning = false;
      canvas.style.cursor = state.view.panMode ? "grab" : "crosshair";
    });
  }

  canvas.addEventListener("click", handleCanvasClick);
  canvas.addEventListener("mousedown", handleCanvasMouseDown);
  canvas.addEventListener("mousemove", handleCanvasMouseMove);
  canvas.addEventListener("mouseup", handleCanvasMouseUp);
  canvas.addEventListener("mouseleave", handleCanvasMouseUp);
  mapFileInput.addEventListener("change", handleMapFile);
  resetMapBtn.addEventListener("click", handleResetMap);

  modeRadios.forEach((radio) =>
    radio.addEventListener("change", () => {
      state.currentMode = radio.value;
      renderAll();
    }),
  );

  if (legendToggle) {
    legendToggle.addEventListener("change", renderLegend);
  }
  if (exportButton) {
    exportButton.addEventListener("click", exportPlotImage);
  }
  if (exportAllButton) {
    exportAllButton.addEventListener("click", exportAllLegendImages);
  }
  if (importAlignedBtn) {
    importAlignedBtn.addEventListener("click", handleImportAlignedLogs);
  }
  if (importPointBtn) {
    importPointBtn.addEventListener("click", handleImportPointLogs);
  }

  if (autoGatewayCheckbox && pingTargetInput) {
    const syncPingTargetState = () => {
      const isRemote = measurementModeSelect?.value === "remote_ssh";
      const disabled = !isRemote && autoGatewayCheckbox.checked;
      pingTargetInput.disabled = disabled;
      if (disabled) {
        pingTargetInput.value = "";
        pingTargetInput.placeholder = "Gateway自動検出ONのため入力不可";
      } else if (!isRemote) {
        pingTargetInput.placeholder = "IPまたはホスト名";
      }
    };
    autoGatewayCheckbox.addEventListener("change", syncPingTargetState);
    if (measurementModeSelect) {
      measurementModeSelect.addEventListener("change", syncPingTargetState);
    }
    syncPingTargetState();
  }

  initDisplayControls();
}

function syncMeasurementModeState() {
  const isRemote = measurementModeSelect?.value === "remote_ssh";
  const localSection = document.getElementById("local-config-section");
  const remoteSection = document.getElementById("remote-config-section");
  const neighborEnabled = !!form.querySelector("input[name=remote_enable_neighbor_scan]")?.checked;
  const advancedEnabled = !!form.querySelector("input[name=remote_advanced_enabled]")?.checked;
  localSection?.classList.toggle("is-active", !isRemote);
  localSection?.classList.toggle("is-inactive", isRemote);
  remoteSection?.classList.toggle("is-active", isRemote);
  remoteSection?.classList.toggle("is-inactive", !isRemote);
  bssidSwitchSection?.classList.toggle("is-active", !isRemote);
  bssidSwitchSection?.classList.toggle("is-inactive", isRemote);

  document.querySelectorAll(".remote-config-grid input").forEach((input) => {
    input.disabled = !isRemote;
  });
  document
    .querySelectorAll("input[name=remote_setup_ssh_key], input[name=remote_cleanup_ssh_key], input[name=remote_delete_local_key]")
    .forEach((input) => {
      input.disabled = !isRemote;
    });
  document
    .querySelectorAll(
      "input[name=remote_advanced_enabled], input[name=remote_advanced_include_neighbor], input[name=remote_advanced_include_routes], input[name=remote_advanced_include_ip_addr], input[name=remote_advanced_include_wifi_details], input[name=remote_advanced_include_journal], input[name=remote_advanced_snapshot_on_bssid_change], input[name=remote_advanced_snapshot_on_ping_timeout], input[name=remote_advanced_ping_timeout_streak], input[name=remote_advanced_max_output_chars]",
    )
    .forEach((input) => {
      const isMaster = input.name === "remote_advanced_enabled";
      input.disabled = !isRemote || (!advancedEnabled && !isMaster);
    });
  const remoteComment = document.getElementById("remote-ssh-key-comment");
  if (remoteComment) {
    remoteComment.disabled = !isRemote;
  }
  const remoteNeighborEvery = document.getElementById("remote-neighbor-every");
  const remoteNeighborSsid = document.getElementById("remote-neighbor-ssid");
  if (remoteNeighborEvery) {
    remoteNeighborEvery.disabled = !neighborEnabled;
  }
  if (remoteNeighborSsid) {
    remoteNeighborSsid.disabled = !neighborEnabled;
  }
  if (pingTargetInput) {
    pingTargetInput.placeholder = isRemote
      ? "未指定ならJetson側でデフォルトGatewayを利用"
      : "IPまたはホスト名";
  }
  if (pingTargetHint) {
    pingTargetHint.textContent = isRemote
      ? "remote_ssh では Jetson 側から ping します。未指定なら Jetson 側のデフォルトGatewayを使います。"
      : "Gateway自動検出ON時は入力不可です。";
  }
  syncBssidSwitchState();
}

function syncBssidSwitchState() {
  const isLocal = measurementModeSelect?.value !== "remote_ssh";
  const isSupported = state.localBssidSwitchSupported;
  const isAvailable = isLocal && isSupported;
  const currentSsid = state.currentWifi?.ssid || "";
  const bssidTestEnabled = isAvailable && state.bssidSwitchEnabledSsid === currentSsid;
  const hasCandidate = Boolean(bssidSwitchSelect?.value);
  const hasApCandidate = Boolean(apSwitchSelect?.value);
  bssidSwitchSection?.classList.toggle("is-active", isAvailable);
  bssidSwitchSection?.classList.toggle("is-inactive", !isAvailable);
  if (refreshBssidBtn) refreshBssidBtn.disabled = !isAvailable;
  if (apSwitchSelect) apSwitchSelect.disabled = !isAvailable;
  if (apSwitchPassword) apSwitchPassword.disabled = !isAvailable;
  if (switchApBtn) switchApBtn.disabled = !isAvailable || !hasApCandidate;
  if (fixApBtn) fixApBtn.disabled = !bssidTestEnabled;
  if (clearApFixBtn) clearApFixBtn.disabled = !isAvailable || state.apLock?.locked !== "yes";
  if (bssidSwitchSelect) bssidSwitchSelect.disabled = !bssidTestEnabled;
  if (switchBssidBtn) switchBssidBtn.disabled = !bssidTestEnabled || !state.running || !hasCandidate;
  if (fixBssidBtn) fixBssidBtn.disabled = !bssidTestEnabled || !state.running;
  if (clearBssidFixBtn) clearBssidFixBtn.disabled = !isAvailable || !state.bssidLock?.bssid;
  if (bssidSwitchStatus && !isLocal) {
    bssidSwitchStatus.textContent = "Jetsonローカル測定でのみ使用できます。";
  }
}

function setSelectOptions(select, options, placeholder) {
  if (!select) return;
  const previousValue = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  for (const option of options) {
    select.add(option);
  }
  if ([...select.options].some((option) => option.value === previousValue)) {
    select.value = previousValue;
  }
}

async function loadAccessPointCandidates() {
  if (measurementModeSelect?.value === "remote_ssh" || !state.localBssidSwitchSupported) return;
  try {
    if (refreshBssidBtn) refreshBssidBtn.disabled = true;
    if (apSwitchStatus) apSwitchStatus.textContent = "候補APを取得中...";
    const response = await fetch("/api/local/access-points");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "候補APの取得に失敗しました");
    state.currentWifi = data.current || {};
    state.bssidSwitchEnabledSsid = data.bssid_switch_enabled_ssid || "";
    state.bssidLock = data.bssid_lock || {};
    state.apLock = data.ap_lock || {};
    const accessPoints = data.access_points || [];
    const ssids = [...new Set(accessPoints.map((ap) => ap.ssid).filter(Boolean))].sort();
    setSelectOptions(
      apSwitchSelect,
      ssids.map((ssid) => new Option(ssid, ssid)),
      "接続先SSIDを選択",
    );
    const currentSsid = state.currentWifi.ssid || "";
    setSelectOptions(
      bssidSwitchSelect,
      accessPoints
        .filter((ap) => ap.ssid === currentSsid)
        .map((ap) => {
          const label = `${ap.bssid} | CH ${ap.channel || "-"} | ${ap.signal || "-"}%`;
          const option = new Option(label, ap.bssid || "");
          option.dataset.ssid = ap.ssid || "";
          return option;
        }),
      "同一SSID内のBSSIDを選択",
    );
    if (apSwitchStatus) {
      apSwitchStatus.textContent = state.apLock.locked === "yes"
        ? `AP固定中: ${state.apLock.ssid || currentSsid || "-"} (${state.apLock.connection || "接続プロファイル"})`
        : `現在: ${currentSsid || "-"} / ${state.currentWifi.bssid || "-"}`;
    }
    if (bssidSwitchStatus) {
      bssidSwitchStatus.textContent = state.bssidLock.bssid
        ? `固定中: ${state.bssidLock.bssid} (${state.bssidLock.connection || "接続プロファイル"})`
        : bssidTestEnabledMessage(currentSsid);
    }
  } catch (error) {
    if (apSwitchStatus) apSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

function bssidTestEnabledMessage(currentSsid) {
  return state.bssidSwitchEnabledSsid === currentSsid && currentSsid
    ? `BSSIDテスト有効: ${currentSsid}`
    : "APを切り替えると、同一SSID内のBSSIDテストを有効にできます。";
}

async function handleApSwitch() {
  const ssid = apSwitchSelect?.value || "";
  const password = apSwitchPassword?.value || "";
  if (!ssid) return;
  if (!window.confirm(`Jetsonの接続先を ${ssid} へ切り替えます。USBまたは有線LANで接続中であることを確認してください。`)) return;
  try {
    if (switchApBtn) switchApBtn.disabled = true;
    if (apSwitchStatus) apSwitchStatus.textContent = "APを切り替え中...";
    const response = await fetch("/api/local/switch-ap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ssid, password: password || null, acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "AP切替に失敗しました");
    if (form.ssid && data.connected?.ssid) form.ssid.value = data.connected.ssid;
    if (apSwitchPassword) apSwitchPassword.value = "";
    if (apSwitchStatus) apSwitchStatus.textContent = `AP切替完了: ${data.connected?.ssid || ssid}`;
    await loadAccessPointCandidates();
  } catch (error) {
    if (apSwitchStatus) apSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

async function handleApFix() {
  if (!window.confirm("現在接続中のAP（SSID）を自動接続の最優先に固定します。USBまたは有線LANで接続中であることを確認してください。")) return;
  try {
    if (fixApBtn) fixApBtn.disabled = true;
    if (apSwitchStatus) apSwitchStatus.textContent = "APを固定中...";
    const response = await fetch("/api/local/fix-ap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "AP固定に失敗しました");
    state.apLock = data.ap_lock || {};
    if (apSwitchStatus) apSwitchStatus.textContent = `APを固定しました: ${state.apLock.ssid || "-"}`;
  } catch (error) {
    if (apSwitchStatus) apSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

async function handleClearApFix() {
  if (!window.confirm("APの自動接続優先を通常値へ戻します。USBまたは有線LANで接続中であることを確認してください。")) return;
  try {
    if (clearApFixBtn) clearApFixBtn.disabled = true;
    if (apSwitchStatus) apSwitchStatus.textContent = "AP固定を解除中...";
    const response = await fetch("/api/local/clear-ap-fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "AP固定の解除に失敗しました");
    state.apLock = data.ap_lock || {};
    if (apSwitchStatus) apSwitchStatus.textContent = "AP固定を解除しました。";
  } catch (error) {
    if (apSwitchStatus) apSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

async function handleBssidSwitch() {
  const selected = bssidSwitchSelect?.selectedOptions?.[0];
  const ssid = selected?.dataset?.ssid || "";
  const bssid = selected?.value || "";
  if (!ssid || !bssid) return;
  if (!window.confirm(`JetsonのWi-Fiを ${ssid} / ${bssid} へ切り替えます。USBまたは有線LANで接続中であることを確認してください。`)) return;
  try {
    if (switchBssidBtn) switchBssidBtn.disabled = true;
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = "BSSIDを切り替え中...";
    const response = await fetch("/api/local/switch-bssid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ssid, bssid, acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "BSSID切替に失敗しました");
    if (form.ssid && data.connected?.ssid) form.ssid.value = data.connected.ssid;
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = `切替完了: ${data.connected?.ssid || ssid} / ${data.connected?.bssid || bssid}`;
    await loadAccessPointCandidates();
  } catch (error) {
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

async function handleBssidFix() {
  if (!window.confirm("現在接続中のBSSIDを接続プロファイルへ固定します。USBまたは有線LANで接続中であることを確認してください。")) return;
  try {
    if (fixBssidBtn) fixBssidBtn.disabled = true;
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = "BSSIDを固定中...";
    const response = await fetch("/api/local/fix-bssid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "BSSID固定に失敗しました");
    state.bssidLock = data.bssid_lock || {};
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = `固定しました: ${state.bssidLock.bssid || "-"}`;
  } catch (error) {
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

async function handleClearBssidFix() {
  if (!window.confirm("接続プロファイルのBSSID固定を解除します。USBまたは有線LANで接続中であることを確認してください。")) return;
  try {
    if (clearBssidFixBtn) clearBssidFixBtn.disabled = true;
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = "BSSID固定を解除中...";
    const response = await fetch("/api/local/clear-bssid-fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_usb_or_lan: true }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "BSSID固定の解除に失敗しました");
    state.bssidLock = data.bssid_lock || {};
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = "BSSID固定を解除しました。";
  } catch (error) {
    if (bssidSwitchStatus) bssidSwitchStatus.textContent = error.message;
  } finally {
    syncBssidSwitchState();
  }
}

function ensurePanToggleUI() {
  if (!panModeToggle) return;
  const label = panModeToggle.closest("label");
  if (!label) return;
  if (!label.classList.contains("pan-toggle")) {
    label.classList.add("pan-toggle");
  }
  // Force readable layout even when old cached CSS/HTML is mixed.
  label.style.display = "inline-flex";
  label.style.flexDirection = "row";
  label.style.alignItems = "center";
  label.style.gap = "0.55rem";
  panModeToggle.style.width = "22px";
  panModeToggle.style.height = "22px";
  panModeToggle.style.margin = "0";
}

async function loadStatus() {
  try {
    const resp = await fetch("/api/status");
    if (!resp.ok) {
      throw new Error("status fetch failed");
    }
    const status = await resp.json();
    state.running = Boolean(status.running);
    state.pointOffset = Math.max(0, (status.current_point || 1) - 1);
    updateStatus(status);
    startBtn.disabled = !!status.running;
    stopBtn.disabled = false;
  } catch (error) {
    console.error("status", error);
  }
}

async function triggerSessionReset() {
  try {
    const resetPayload = {
      prefix: form.prefix?.value ?? "",
      log_base: form.log_base?.value ?? "",
    };
    const resp = await fetch("/api/reset-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(resetPayload),
    });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "リセットに失敗しました");
    }
    const status = await resp.json();
    state.running = Boolean(status.running);
    state.points = [];
    state.segments = [];
    state.logsByPoint = new Map();
    state.liveBuffer = [];
    liveLog.textContent = "";
    updateStatus(status);
    startBtn.disabled = !!state.running;
    stopBtn.disabled = !state.running;
    renderAll();
  } catch (error) {
    console.error("auto-reset", error);
  }
}

async function handleStart() {
  const payload = buildPayload();
  try {
    toggleControls(true);
    const resp = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "Failed to start measurement");
    }
    const status = await resp.json();
    state.running = true;
    state.pointOffset = Math.max(0, (status.current_point || 1) - 1);
    updateStatus(status);
    startBtn.disabled = true;
    stopBtn.disabled = false;
  } catch (error) {
    console.error(error);
    statusMessage.textContent = error.message;
  } finally {
    toggleControls(false);
  }
}

async function handleStop() {
  try {
    const resp = await fetch("/api/stop", { method: "POST" });
    const status = await resp.json();
    state.running = false;
    state.pointOffset = Math.max(0, (status.current_point || 1) - 1);
    updateStatus(status);
    startBtn.disabled = false;
    stopBtn.disabled = false;
  } catch (error) {
    console.error(error);
  }
}

async function handleRemotePrepare() {
  const payload = buildRemoteSetupPayload();
  if (!payload.remote_host) {
    statusMessage.textContent = "Jetsonホストを入力してください。";
    return;
  }
  if (measurementModeSelect?.value !== "remote_ssh") {
    statusMessage.textContent = "測定方式を Jetson(SSH) に切り替えてください。";
    return;
  }
  try {
    if (remotePrepareBtn) {
      remotePrepareBtn.disabled = true;
    }
    statusMessage.textContent = "Jetson接続準備中...";
    const resp = await fetch("/api/remote/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "SSH準備に失敗しました");
    }
    if (form.remote_identity_file && data.identity_file) {
      form.remote_identity_file.value = data.identity_file;
    }
    statusMessage.textContent = data.message || "SSH準備完了";
  } catch (error) {
    console.error("remote prepare", error);
    statusMessage.textContent = error.message || "SSH準備に失敗しました";
  } finally {
    if (remotePrepareBtn) {
      remotePrepareBtn.disabled = false;
    }
  }
}

function buildPayload() {
  const fd = new FormData(form);
  const payload = {};
  const booleanFields = [
    "auto_gateway",
    "timeout_as_numeric",
    "use_sudo",
    "sync_time",
    "remote_enable_neighbor_scan",
    "remote_setup_ssh_key",
    "remote_cleanup_ssh_key",
    "remote_delete_local_key",
    "remote_advanced_enabled",
    "remote_advanced_include_neighbor",
    "remote_advanced_include_routes",
    "remote_advanced_include_ip_addr",
    "remote_advanced_include_wifi_details",
    "remote_advanced_include_journal",
    "remote_advanced_snapshot_on_bssid_change",
    "remote_advanced_snapshot_on_ping_timeout",
  ];
  const numericFields = [
    "interval",
    "ping_fail_value",
    "ping_timeout_ms",
    "wifi_disconnected_value",
    "channel_min",
    "channel_max",
    "retain_rows",
    "remote_port",
    "remote_neighbor_every",
    "remote_advanced_ping_timeout_streak",
    "remote_advanced_max_output_chars",
  ];
  fd.forEach((value, key) => {
    if (value === "" && key !== "prefix" && key !== "ping_target") {
      return;
    }
    if (booleanFields.includes(key)) {
      payload[key] = fd.getAll(key).length > 0;
    } else if (numericFields.includes(key)) {
      payload[key] = Number(value);
    } else {
      payload[key] = value;
    }
  });
  booleanFields.forEach((key) => {
    const input = form.querySelector(`[name="${key}"]`);
    if (input) {
      payload[key] = !!input.checked;
    }
  });
  payload.retain_rows = Number(fd.get("retain_rows")) || 20000;
  payload.remote_advanced_ping_timeout_streak = Number(fd.get("remote_advanced_ping_timeout_streak")) || 1;
  payload.remote_advanced_max_output_chars = Number(fd.get("remote_advanced_max_output_chars")) || 12000;
  return payload;
}

function buildRemoteSetupPayload() {
  return {
    remote_host: String(form.remote_host?.value || "").trim(),
    remote_user: String(form.remote_user?.value || "").trim() || "nvidia",
    remote_port: Number(form.remote_port?.value || 22) || 22,
    remote_identity_file: String(form.remote_identity_file?.value || "").trim() || null,
    remote_setup_ssh_key: !!form.remote_setup_ssh_key?.checked,
    remote_cleanup_ssh_key: !!form.remote_cleanup_ssh_key?.checked,
    remote_delete_local_key: !!form.remote_delete_local_key?.checked,
    remote_ssh_key_comment: String(form.remote_ssh_key_comment?.value || "").trim() || null,
  };
}

function toggleControls(pending) {
  if (pending) {
    startBtn.disabled = true;
  } else if (!state.running) {
    startBtn.disabled = false;
  }
}

function updateStatus(status) {
  statusBadge.textContent = status.running ? "Running" : "Idle";
  statusBadge.classList.toggle("running", status.running);
  statusBadge.classList.toggle("idle", !status.running);
  statusMessage.textContent = status.last_error
    ? status.last_error
    : status.running
      ? `Point=${status.current_point} | Log #${status.log_index}`
      : "停止中";
  logPathEl.textContent = status.log_file || "-";
  if (neighborLogPathEl) {
    neighborLogPathEl.textContent = status.neighbor_log_file || "-";
  }
  if (advancedLogPathEl) {
    advancedLogPathEl.textContent = status.advanced_log_file || "-";
  }
  state.currentLogFile = status.log_file || "";
  syncBssidSwitchState();
  if (status.ping_target) {
    pingDetailsEl.textContent = `${status.ping_target} (${status.ping_target_source})`;
  } else if (status.ping_target_source === "remote_gateway_auto") {
    pingDetailsEl.textContent = "自動検出待ち (remote_gateway_auto)";
  } else {
    pingDetailsEl.textContent = "-";
  }
}

function connectSocket() {
  if (state.socket) {
    return;
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.socket = new WebSocket(`${protocol}://${window.location.host}/ws/logs`);

  state.socket.addEventListener("open", () => {
    statusMessage.textContent = "WebSocket接続成功";
  });

  state.socket.addEventListener("message", (event) => {
    try {
      const record = JSON.parse(event.data);
      handleRecord(record);
    } catch (error) {
      console.error("ws parse", error);
    }
  });

  state.socket.addEventListener("close", () => {
    state.socket = null;
    statusMessage.textContent = "WebSocket切断。再接続中...";
    if (!state.reconnectTimer) {
      state.reconnectTimer = setTimeout(() => {
        state.reconnectTimer = null;
        connectSocket();
      }, 2000);
    }
  });
}

function handleRecord(record) {
  if (!state.logsByPoint.has(record.point)) {
    state.logsByPoint.set(record.point, []);
  }
  state.logsByPoint.get(record.point).push(record);
  const channelInfo =
    record.channel !== undefined && record.channel !== null && record.channel !== "" ? ` CH=${record.channel}` : "";
  const ssidInfo = record.ssid ? ` SSID=${record.ssid}` : "";
  const bssidInfo = record.bssid ? ` BSSID=${record.bssid}` : "";
  const signalInfo =
    record.signal_strength !== undefined && record.signal_strength !== null && record.signal_strength !== ""
      ? ` Signal=${record.signal_strength}%`
      : "";
  const pingDisplay = formatPingDisplay(record.ping_ms, record.status);
  const advancedInfo = Array.isArray(record.advanced_snapshot_reasons) && record.advanced_snapshot_reasons.length
    ? ` ADV=${record.advanced_snapshot_reasons.join(",")}`
    : "";
  state.liveBuffer.push(
    `#${record.index} P${record.point} ping=${pingDisplay} RSSI=${record.rssi_dbm}${signalInfo}${channelInfo}${ssidInfo}${bssidInfo}${advancedInfo}`,
  );
  if (state.liveBuffer.length > 12) {
    state.liveBuffer.shift();
  }
  liveLog.textContent = state.liveBuffer.join("\n");
}

function formatPingDisplay(value, status) {
  const numeric = Number.parseFloat(value);
  if (Number.isNaN(numeric)) {
    const normalized = String(value ?? "").trim();
    if (normalized) {
      return normalized.endsWith("ms") ? normalized : `${normalized}ms`;
    }
    const normalizedStatus = String(status ?? "").trim();
    if (normalizedStatus === "timeout") {
      return "timeout";
    }
    if (normalizedStatus === "wifi_disconnected") {
      return "wifi_disconnected";
    }
    if (normalizedStatus.startsWith("ssh")) {
      return normalizedStatus;
    }
    return "-";
  }
  return `${Math.round(numeric)}ms`;
}
function handleCanvasClick(event) {
  if (state.view.panMode) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const screenX = Math.round((event.clientX - rect.left) * scaleX);
  const screenY = Math.round((event.clientY - rect.top) * scaleY);
  const world = fromScreenToWorld(screenX, screenY);
  const x = Math.round(world.x);
  const y = Math.round(world.y);
  state.points.push({ x, y });
  renderAll();
  if (state.points.length >= 2) {
    finalizeSegment();
  }
}

function getCanvasPosition(event) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
  };
}

function fromScreenToWorld(screenX, screenY) {
  const { scale, offsetX, offsetY } = state.view;
  return {
    x: (screenX - offsetX) / scale,
    y: (screenY - offsetY) / scale,
  };
}

function fromWorldToScreen(worldX, worldY) {
  const { scale, offsetX, offsetY } = state.view;
  return {
    x: worldX * scale + offsetX,
    y: worldY * scale + offsetY,
  };
}

function adjustZoom(multiplier) {
  const { x: centerX, y: centerY } = { x: canvas.width / 2, y: canvas.height / 2 };
  const oldScale = state.view.scale;
  const nextScale = clamp(oldScale * multiplier, 0.2, 5);
  if (nextScale === oldScale) return;
  const world = fromScreenToWorld(centerX, centerY);
  state.view.scale = nextScale;
  state.view.offsetX = centerX - world.x * nextScale;
  state.view.offsetY = centerY - world.y * nextScale;
  renderAll();
}

function resetViewTransform() {
  state.view.scale = 1;
  state.view.offsetX = 0;
  state.view.offsetY = 0;
  state.view.panning = false;
  if (panModeToggle) {
    panModeToggle.checked = false;
  }
  state.view.panMode = false;
  canvas.style.cursor = "crosshair";
  renderAll();
}

function handleCanvasMouseDown(event) {
  if (!state.view.panMode) return;
  const pos = getCanvasPosition(event);
  state.view.panning = true;
  state.view.lastPanX = pos.x;
  state.view.lastPanY = pos.y;
  canvas.style.cursor = "grabbing";
}

function handleCanvasMouseMove(event) {
  if (!state.view.panMode || !state.view.panning) return;
  const pos = getCanvasPosition(event);
  const dx = pos.x - state.view.lastPanX;
  const dy = pos.y - state.view.lastPanY;
  state.view.offsetX += dx;
  state.view.offsetY += dy;
  state.view.lastPanX = pos.x;
  state.view.lastPanY = pos.y;
  renderAll();
}

function handleCanvasMouseUp() {
  state.view.panning = false;
  canvas.style.cursor = state.view.panMode ? "grab" : "crosshair";
}

async function finalizeSegment() {
  try {
    const resp = await fetch("/api/advance-point", { method: "POST" });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "advance failed");
    }
    const payload = await resp.json();
    const completed = payload.completed_point;
    const logs = await ensureLogs(completed);
    if (!logs.length) {
      return;
    }

    // completed point id to local points index.
    const startIdx = completed - 1 - state.pointOffset;
    const endIdx = completed - state.pointOffset;
    const startPoint = state.points[startIdx];
    const endPoint = state.points[endIdx];
    if (!startPoint || !endPoint) {
      statusMessage.textContent = "Point alignment error. Please retry by placing points again.";
      return;
    }
    const start = { ...startPoint };
    const end = { ...endPoint };
    state.segments.push({ pointId: completed, start, end, logs });
    renderAll();
  } catch (error) {
    statusMessage.textContent = error.message;
  }
}

async function handleUndoLastPoint() {
  if (!state.points.length) {
    statusMessage.textContent = "Undo target is not available.";
    return;
  }
  const runningNow = state.running;
  const removedPointLabel = state.points.length;
  let removedSegmentPointId = null;

  if (state.segments.length > 0) {
    const removedSegment = state.segments.pop();
    if (removedSegment?.pointId !== undefined && removedSegment?.pointId !== null) {
      removedSegmentPointId = Number(removedSegment.pointId);
      state.logsByPoint.delete(removedSegmentPointId);
    }
  }
  state.points.pop();
  renderAll();

  if (runningNow && removedSegmentPointId !== null) {
    try {
      const rewindResp = await fetch("/api/revert-point", { method: "POST" });
      const rewindData = await rewindResp.json();
      if (!rewindResp.ok) {
        throw new Error(rewindData.detail || "Failed to revert current point");
      }
    } catch (error) {
      statusMessage.textContent = `Point P${removedPointLabel} removed from plot, but point counter revert failed: ${error.message}`;
      return;
    }
  }

  const sourceCsv = (state.currentLogFile || logPathEl.textContent || "").trim();
  if (runningNow) {
    statusMessage.textContent = `Point P${removedPointLabel} removed from plot and point counter reverted.`;
    return;
  }
  if (!sourceCsv || sourceCsv === "-") {
    statusMessage.textContent = `Point P${removedPointLabel} removed from plot. (No CSV path)`;
    return;
  }
  if (removedSegmentPointId === null) {
    statusMessage.textContent = `Point P${removedPointLabel} removed from plot.`;
    return;
  }

  try {
    const resp = await fetch("/api/corrections/hide-point", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_csv: sourceCsv, point_id: removedSegmentPointId }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Failed to create corrected CSV");
    }
    statusMessage.textContent = `P${removedSegmentPointId} hidden. corrected: ${data.corrected_csv}`;
  } catch (error) {
    statusMessage.textContent = `P${removedSegmentPointId} removed from plot, but correction file failed: ${error.message}`;
  }
}

async function ensureLogs(pointId) {
  if (!pointId) {
    return [];
  }
  if (!state.logsByPoint.has(pointId) || state.logsByPoint.get(pointId).length === 0) {
    const resp = await fetch(`/api/logs/${pointId}`);
    if (!resp.ok) {
      return [];
    }
    const data = await resp.json();
    state.logsByPoint.set(pointId, data);
  }
  return state.logsByPoint.get(pointId) || [];
}

function parseCsvText(text) {
  const rows = [];
  let row = [];
  let value = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          value += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        value += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(value);
      value = "";
    } else if (ch === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else if (ch !== "\r") {
      value += ch;
    }
  }
  if (value !== "" || row.length > 0) {
    row.push(value);
    rows.push(row);
  }
  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).filter((cols) => cols.some((item) => item !== "")).map((cols) => {
    const record = {};
    headers.forEach((header, idx) => {
      record[header] = cols[idx] ?? "";
    });
    return record;
  });
}

function normalizeExcelText(value) {
  const raw = String(value ?? "").trim();
  const formulaMatch = raw.match(/^="(.*)"$/);
  if (formulaMatch) {
    return formulaMatch[1];
  }
  return raw;
}

function parsePcTimestamp(row) {
  const dateText = normalizeExcelText(row.Date);
  const timeText = normalizeExcelText(row.Time);
  if (!dateText || !timeText) return null;
  const parsed = new Date(`${dateText}T${timeText}`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseJetsonTimestamp(row) {
  const timestampText = normalizeExcelText(row.timestamp);
  if (!timestampText) return null;
  const parsed = new Date(timestampText);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseNumberValue(value) {
  const numeric = parseFloat(String(value ?? "").trim());
  return Number.isNaN(numeric) ? null : numeric;
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
    reader.readAsText(file, "utf-8");
  });
}

function buildReferenceSamples(rows) {
  return rows
    .map((row) => ({
      point: Number.parseInt(String(row.Point || "").trim(), 10),
      timestamp: parsePcTimestamp(row),
      ping_ms: normalizeExcelText(row.time_ms),
      signal_strength: normalizeExcelText(row.SignalStrength),
      rssi_dbm: normalizeExcelText(row.dBm),
      bssid: normalizeExcelText(row.BSSID).toLowerCase(),
      ssid: normalizeExcelText(row.SSID),
      channel: normalizeExcelText(row.Channel),
      rate: normalizeExcelText(row.Rate),
      status: normalizeExcelText(row.Status),
    }))
    .filter((row) => Number.isInteger(row.point) && row.point > 0 && row.timestamp);
}

function buildJetsonSamples(rows) {
  return rows
    .map((row) => ({
      timestamp: parseJetsonTimestamp(row),
      ping_ms: normalizeExcelText(row.ping_ms),
      signal_strength: normalizeExcelText(row.signal),
      rssi_dbm: normalizeExcelText(row.dbm),
      bssid: normalizeExcelText(row.bssid).toLowerCase(),
      ssid: normalizeExcelText(row.ssid),
      channel: normalizeExcelText(row.channel),
      rate: normalizeExcelText(row.rate),
      status: normalizeExcelText(row.ping_status || row.ssh_status || "ok"),
      best_neighbor_bssid: normalizeExcelText(row.best_neighbor_bssid).toLowerCase(),
      best_neighbor_ssid: normalizeExcelText(row.best_neighbor_ssid),
      best_neighbor_signal: normalizeExcelText(row.best_neighbor_signal),
      best_neighbor_dbm: normalizeExcelText(row.best_neighbor_dbm),
      raw: row,
    }))
    .filter((row) => row.timestamp);
}

function buildPointSamples(rows) {
  return rows
    .map((row) => ({
      point: Number.parseInt(String(row.point ?? row.Point ?? "").trim(), 10),
      timestamp: parseJetsonTimestamp(row),
      ping_ms: normalizeExcelText(row.ping_ms ?? row.time_ms),
      signal_strength: normalizeExcelText(row.signal ?? row.SignalStrength),
      rssi_dbm: normalizeExcelText(row.dbm ?? row.dBm),
      bssid: normalizeExcelText(row.bssid ?? row.BSSID).toLowerCase(),
      ssid: normalizeExcelText(row.ssid ?? row.SSID),
      channel: normalizeExcelText(row.channel ?? row.Channel),
      rate: normalizeExcelText(row.rate ?? row.Rate),
      status: normalizeExcelText(row.ping_status || row.ssh_status || row.status || row.Status || "ok"),
      best_neighbor_bssid: normalizeExcelText(row.best_neighbor_bssid ?? row.BestNeighborBSSID).toLowerCase(),
      best_neighbor_ssid: normalizeExcelText(row.best_neighbor_ssid ?? row.BestNeighborSSID),
      best_neighbor_signal: normalizeExcelText(row.best_neighbor_signal ?? row.BestNeighborSignal),
      best_neighbor_dbm: normalizeExcelText(row.best_neighbor_dbm ?? row.BestNeighborDbm),
      raw: row,
    }))
    .filter((row) => Number.isInteger(row.point) && row.point > 0);
}

function buildImportedPointLog(sample) {
  const timestamp = sample.timestamp ? sample.timestamp.toISOString() : "";
  return {
    point: sample.point,
    date: timestamp ? timestamp.slice(0, 10) : "",
    time: timestamp,
    ssid: sample.ssid || "",
    bssid: sample.bssid || "",
    channel: sample.channel || "",
    rate: sample.rate || "",
    signal_strength: sample.signal_strength || "",
    rssi_dbm: sample.rssi_dbm || "",
    ping_ms: sample.ping_ms || "",
    status: sample.status || "",
    best_neighbor_bssid: sample.best_neighbor_bssid || "",
    best_neighbor_ssid: sample.best_neighbor_ssid || "",
    best_neighbor_signal: sample.best_neighbor_signal || "",
    best_neighbor_dbm: sample.best_neighbor_dbm || "",
  };
}

function findNearestSampleIndex(samples, targetTimeMs, startIdx = 0) {
  let idx = Math.max(0, Math.min(startIdx, Math.max(0, samples.length - 1)));
  while (idx + 1 < samples.length && samples[idx + 1].timestamp.getTime() <= targetTimeMs) {
    idx += 1;
  }
  if (idx + 1 >= samples.length) {
    return idx;
  }
  const currentDiff = Math.abs(samples[idx].timestamp.getTime() - targetTimeMs);
  const nextDiff = Math.abs(samples[idx + 1].timestamp.getTime() - targetTimeMs);
  return nextDiff < currentDiff ? idx + 1 : idx;
}

function buildAlignedLog(refSample, jetSample) {
  const source = jetSample || refSample;
  return {
    point: refSample.point,
    date: refSample.timestamp.toISOString().slice(0, 10),
    time: refSample.timestamp.toISOString(),
    ssid: source.ssid || refSample.ssid || "",
    bssid: source.bssid || refSample.bssid || "",
    channel: source.channel || refSample.channel || "",
    rate: source.rate || refSample.rate || "",
    signal_strength: source.signal_strength || refSample.signal_strength || "",
    rssi_dbm: source.rssi_dbm || refSample.rssi_dbm || "",
    ping_ms: source.ping_ms || refSample.ping_ms || "",
    status: source.status || refSample.status || "",
    best_neighbor_bssid: source.best_neighbor_bssid || "",
    best_neighbor_ssid: source.best_neighbor_ssid || "",
    best_neighbor_signal: source.best_neighbor_signal || "",
    best_neighbor_dbm: source.best_neighbor_dbm || "",
  };
}

async function handleImportAlignedLogs() {
  const referenceFile = referenceCsvInput?.files?.[0];
  const overlayFile = overlayCsvInput?.files?.[0];
  if (!referenceFile) {
    statusMessage.textContent = "PCログCSVを選択してください。";
    return;
  }
  if (state.points.length < 2) {
    statusMessage.textContent = "先にマップ上へポイントを配置してください。";
    return;
  }

  try {
    const toleranceMs = Math.max(0, Number.parseInt(importToleranceInput?.value || "2000", 10) || 2000);
    const referenceRows = parseCsvText(await readFileAsText(referenceFile));
    const overlayRows = overlayFile ? parseCsvText(await readFileAsText(overlayFile)) : [];
    const referenceSamples = buildReferenceSamples(referenceRows);
    const jetsonSamples = buildJetsonSamples(overlayRows).sort(
      (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
    );

    const byPoint = new Map();
    referenceSamples.forEach((sample) => {
      if (!byPoint.has(sample.point)) {
        byPoint.set(sample.point, []);
      }
      byPoint.get(sample.point).push(sample);
    });

    state.segments = [];
    state.logsByPoint = new Map();
    let cursor = 0;
    let matchedCount = 0;

    Array.from(byPoint.keys())
      .sort((a, b) => a - b)
      .forEach((pointId) => {
        const samples = byPoint.get(pointId) || [];
        const start = state.points[pointId - 1];
        const end = state.points[pointId];
        if (!start || !end) {
          return;
        }
        const logs = samples.map((sample) => {
          let matched = null;
          if (jetsonSamples.length) {
            const nearestIdx = findNearestSampleIndex(jetsonSamples, sample.timestamp.getTime(), cursor);
            const nearest = jetsonSamples[nearestIdx];
            if (nearest) {
              const diffMs = Math.abs(nearest.timestamp.getTime() - sample.timestamp.getTime());
              if (diffMs <= toleranceMs) {
                matched = nearest;
                cursor = nearestIdx;
                matchedCount += 1;
              }
            }
          }
          return buildAlignedLog(sample, matched);
        });
        state.logsByPoint.set(pointId, logs);
        state.segments.push({ pointId, start: { ...start }, end: { ...end }, logs });
      });

    renderAll();
    statusMessage.textContent = overlayFile
      ? `PCログ ${referenceSamples.length} 行を基準に Jetsonログ ${matchedCount} 行を時刻照合してプロットしました。`
      : `PCログ ${referenceSamples.length} 行を読み込みました。`;
  } catch (error) {
    console.error("import aligned logs", error);
    statusMessage.textContent = `CSV取込に失敗しました: ${error.message}`;
  }
}

async function handleImportPointLogs() {
  const pointFile = pointCsvInput?.files?.[0];
  if (!pointFile) {
    statusMessage.textContent = "JetsonログCSV(Point)を選択してください。";
    return;
  }
  if (state.points.length < 2) {
    statusMessage.textContent = "先にマップ上へポイントを配置してください。";
    return;
  }

  try {
    const rows = parseCsvText(await readFileAsText(pointFile));
    const samples = buildPointSamples(rows);
    if (!samples.length) {
      throw new Error("Point列付きの有効な行が見つかりませんでした。");
    }

    const byPoint = new Map();
    samples.forEach((sample) => {
      if (!byPoint.has(sample.point)) {
        byPoint.set(sample.point, []);
      }
      byPoint.get(sample.point).push(sample);
    });

    state.segments = [];
    state.logsByPoint = new Map();
    let importedSegments = 0;
    let skippedPoints = 0;

    Array.from(byPoint.keys())
      .sort((a, b) => a - b)
      .forEach((pointId) => {
        const start = state.points[pointId - 1];
        const end = state.points[pointId];
        if (!start || !end) {
          skippedPoints += 1;
          return;
        }
        const logs = (byPoint.get(pointId) || []).map(buildImportedPointLog);
        state.logsByPoint.set(pointId, logs);
        state.segments.push({ pointId, start: { ...start }, end: { ...end }, logs });
        importedSegments += 1;
      });

    renderAll();
    statusMessage.textContent =
      skippedPoints > 0
        ? `Jetsonログ ${samples.length} 行を読み込み、${importedSegments} 区間をプロットしました。ポイント不足で ${skippedPoints} 区間はスキップしました。`
        : `Jetsonログ ${samples.length} 行を読み込み、${importedSegments} 区間をプロットしました。`;
  } catch (error) {
    console.error("import point logs", error);
    statusMessage.textContent = `Point取込に失敗しました: ${error.message}`;
  }
}

function handleMapFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      state.image = img;
      canvas.width = img.width;
      canvas.height = img.height;
      resetViewTransform();
      renderAll();
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
}

async function handleResetMap() {
  const clearClientState = () => {
    state.points = [];
    state.segments = [];
    state.logsByPoint = new Map();
    state.liveBuffer = [];
    liveLog.textContent = "";
    renderAll();
  };

  const payload = buildPayload();
  const wasRunning = state.running;
  statusMessage.textContent = "リセット中...";

  if (wasRunning) {
    try {
      await fetch("/api/stop", { method: "POST" });
      const respStart = await fetch("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!respStart.ok) {
        const data = await respStart.json();
        throw new Error(data.detail || "再開に失敗しました");
      }
      const status = await respStart.json();
      state.running = true;
      state.pointOffset = Math.max(0, (status.current_point || 1) - 1);
      updateStatus(status);
      statusMessage.textContent = status.log_file
        ? `ログを再開しました: ${status.log_file}`
        : "ログを再開しました";
    } catch (error) {
      console.error("reset map restart", error);
      statusMessage.textContent = error.message || "リセットに失敗しました";
    }
  } else {
    statusMessage.textContent = "マップをリセットしました。現在は測定停止中です。";
  }

  clearClientState();
}

function drawCanvas(targetCtx = ctx, targetCanvas = canvas) {
  targetCtx.fillStyle = "#05070c";
  targetCtx.fillRect(0, 0, targetCanvas.width, targetCanvas.height);
  if (state.image) {
    const { scale, offsetX, offsetY } = state.view;
    targetCtx.save();
    targetCtx.filter = state.display.grayscaleEnabled ? `grayscale(${state.display.grayscaleLevel}%)` : "none";
    targetCtx.drawImage(state.image, offsetX, offsetY, targetCanvas.width * scale, targetCanvas.height * scale);
    targetCtx.restore();
  }
}

function renderAll() {
  drawCanvas();
  state.segments.forEach((segment) => drawSegment(segment));
  drawPointLabels();
  renderLegend();
}

function drawPointLabels(targetCtx = ctx) {
  const { labelColor, labelSize, anchorRadius } = state.display;
  targetCtx.fillStyle = labelColor;
  targetCtx.font = `${labelSize}px sans-serif`;
  targetCtx.textBaseline = "top";
  targetCtx.textAlign = "left";
  state.points.forEach((pt, idx) => {
    const screen = fromWorldToScreen(pt.x, pt.y);
    targetCtx.beginPath();
    targetCtx.fillStyle = labelColor;
    targetCtx.arc(screen.x, screen.y, anchorRadius, 0, Math.PI * 2);
    targetCtx.fill();
    const offset = anchorRadius + 4;
    targetCtx.fillText(`P${idx + 1}`, screen.x + offset, screen.y + offset);
  });
}

function drawSegment(segment, mode = state.currentMode, targetCtx = ctx) {
  const logs = segment.logs;
  if (!logs || logs.length === 0) return;
  if (state.display.plotShape === "strip") {
    drawStripSegment(segment, mode, targetCtx);
    return;
  }
  const coords = interpolate(segment.start, segment.end, logs.length);
  coords.forEach((coord, idx) => {
    drawDotSample(coord, logs[idx], mode, targetCtx);
  });
}

function drawDotSample(coord, log, mode, targetCtx) {
  const color = resolveColor(mode, log);
  if (!color) return;
  const screen = fromWorldToScreen(coord.x, coord.y);
  targetCtx.fillStyle = color;
  targetCtx.beginPath();
  targetCtx.arc(screen.x, screen.y, state.display.plotRadius, 0, Math.PI * 2);
  targetCtx.fill();
}

function drawStripSegment(segment, mode = state.currentMode, targetCtx = ctx) {
  const logs = segment.logs;
  if (!logs || logs.length === 0) return;
  const startScreen = fromWorldToScreen(segment.start.x, segment.start.y);
  const endScreen = fromWorldToScreen(segment.end.x, segment.end.y);
  const dx = endScreen.x - startScreen.x;
  const dy = endScreen.y - startScreen.y;
  const segmentLength = Math.hypot(dx, dy);
  if (segmentLength <= 0.001) {
    drawDotSample(segment.start, logs[0], mode, targetCtx);
    return;
  }
  const angle = Math.atan2(dy, dx);
  const sampleLength = Math.max(segmentLength / logs.length, 1);
  const thickness = Math.max(state.display.plotRadius * 2, 1);
  logs.forEach((log, idx) => {
    const color = resolveColor(mode, log);
    if (!color) return;
    const centerT = (idx + 0.5) / logs.length;
    const centerX = startScreen.x + dx * centerT;
    const centerY = startScreen.y + dy * centerT;
    targetCtx.save();
    targetCtx.translate(centerX, centerY);
    targetCtx.rotate(angle);
    targetCtx.fillStyle = color;
    targetCtx.fillRect(-sampleLength / 2, -thickness / 2, sampleLength, thickness);
    targetCtx.restore();
  });
}

function interpolate(start, end, steps) {
  const coords = [];
  if (steps <= 1) {
    return [{ x: start.x, y: start.y }];
  }
  for (let i = 0; i < steps; i += 1) {
    const t = i / (steps - 1);
    coords.push({
      x: start.x + (end.x - start.x) * t,
      y: start.y + (end.y - start.y) * t,
    });
  }
  return coords;
}

function normalizeMode(mode) {
  const raw = String(mode || "").trim().toLowerCase();
  if (raw === "ping" || raw === "ping_jet" || raw === "pingjet") return "ping";
  if (raw === "ping_levels" || raw === "ping-levels" || raw === "ping4" || raw === "ping_4_levels") return "ping_levels";
  if (raw === "ping_300" || raw === "ping300" || raw === "ping_300ms" || raw.includes("0-300")) return "ping_300";
  if (raw === "signal" || raw === "signal_%") return "signal";
  if (raw === "rssi" || raw === "rssi_dbm") return "rssi";
  if (raw === "bssid") return "bssid";
  if (raw === "best_neighbor_rssi" || raw === "best-neighbor-rssi") return "best_neighbor_rssi";
  if (raw === "best_neighbor_bssid" || raw === "best-neighbor-bssid") return "best_neighbor_bssid";
  if (raw.startsWith("ping")) return "ping_300";
  return raw;
}

function resolveColor(mode, log) {
  const modeKey = normalizeMode(mode);
  const pingCap = 30;
  const ping300Cap = 300;
  if (modeKey === "ping") {
    const value = clamp(parseFloat(log.ping_ms), 0, pingCap);
    return gradientColor(pingCap, value, pingGradient);
  }
  if (modeKey === "ping_300") {
    const value = clamp(parseFloat(log.ping_ms), 0, ping300Cap);
    return gradientColor(ping300Cap, value, ping300Gradient);
  }
  if (modeKey === "ping_levels") {
    const value = parseFloat(log.ping_ms);
    if (Number.isNaN(value)) return null;
    for (let i = 0; i < pingLevelsBounds.length - 1; i += 1) {
      if (value >= pingLevelsBounds[i] && value < pingLevelsBounds[i + 1]) {
        return pingLevelsColors[i];
      }
    }
    return pingLevelsColors.at(-1);
  }
  if (modeKey === "signal") {
    const value = clamp(parseFloat(log.signal_strength), 0, 100);
    return gradientStops(value, 0, 100, signalStops);
  }
  if (modeKey === "rssi") {
    const value = clamp(parseFloat(log.rssi_dbm), -100, -30);
    return gradientStops(value, -100, -30, rssiStops);
  }
  if (modeKey === "bssid") {
    return colorFromBssid(log.bssid);
  }
  if (modeKey === "best_neighbor_rssi") {
    const value = clamp(parseFloat(log.best_neighbor_dbm), -100, -30);
    return gradientStops(value, -100, -30, rssiStops);
  }
  if (modeKey === "best_neighbor_bssid") {
    return colorFromBssid(log.best_neighbor_bssid);
  }
  return null;
}

const bssidPalette = [
  "#00d4ff",
  "#ff6b6b",
  "#ffd166",
  "#06d6a0",
  "#118ab2",
  "#ef476f",
  "#8ecae6",
  "#ffb703",
  "#90be6d",
  "#f9844a",
  "#43aa8b",
  "#577590",
];

const pingGradient = [
  { value: 0, color: "#0010ff" },
  { value: 5.4, color: "#008dff" },
  { value: 9.9, color: "#00f4ff" },
  { value: 15, color: "#06ff6b" },
  { value: 19.5, color: "#f3ff00" },
  { value: 24, color: "#ff9c00" },
  { value: 30, color: "#b30000" },
];

const pingLevelsBounds = [0, 10, 20, 50, 100];
const pingLevelsColors = ["#00ff87", "#d6ff00", "#ffb100", "#ff3d00"];
const pingLevelsLegend = [
  { label: "0-10 ms", color: "#00ff87" },
  { label: "10-20 ms", color: "#d6ff00" },
  { label: "20-50 ms", color: "#ffb100" },
  { label: ">=50 ms", color: "#ff3d00" },
];
const ping300Gradient = [
  { value: 0, color: "#00e676" },
  { value: 50, color: "#59d64a" },
  { value: 100, color: "#a6d83b" },
  { value: 150, color: "#f4dd45" },
  { value: 200, color: "#ffb74d" },
  { value: 250, color: "#ff7043" },
  { value: 300, color: "#d32f2f" },
];

const signalStops = [
  { value: 0, color: "#c20000" },
  { value: 30, color: "#ff8200" },
  { value: 50, color: "#ffe000" },
  { value: 70, color: "#76d228" },
  { value: 85, color: "#00a2d3" },
  { value: 100, color: "#0057c0" },
];

const rssiStops = [
  { value: -100, color: "#c40000" },
  { value: -90, color: "#ff7a00" },
  { value: -80, color: "#ffe000" },
  { value: -70, color: "#cfff00" },
  { value: -62, color: "#3fbf1a" },
  { value: -50, color: "#00906d" },
  { value: -40, color: "#006cbf" },
  { value: -30, color: "#003a8c" },
];

const legendConfigs = {
  ping: {
    label: "Ping (0-30ms)",
    type: "gradient",
    stops: pingGradient,
    reverseStops: true,
    ticks: [30, 25, 20, 15, 10, 5, 0],
    formatter: (value) => formatLegendValue(value, "ms"),
  },
  ping_levels: {
    label: "Ping (4-Levels)",
    type: "steps",
    steps: pingLevelsLegend,
    reverseSteps: true,
  },
  ping_300: {
    label: "Ping (0-300ms)",
    type: "gradient",
    stops: ping300Gradient,
    reverseStops: true,
    ticks: [300, 250, 200, 150, 100, 50, 0],
    formatter: (value) => formatLegendValue(value, "ms"),
  },
  signal: {
    label: "Signal Strength (%)",
    type: "gradient",
    stops: signalStops,
    ticks: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    formatter: (value) => formatLegendValue(value, "%"),
  },
  rssi: {
    label: "RSSI (dBm)",
    type: "gradient",
    stops: rssiStops,
    ticks: [-100, -90, -80, -70, -60, -50, -40, -30],
    formatter: (value) => formatLegendValue(value, "dBm"),
  },
  best_neighbor_rssi: {
    label: "Best Neighbor RSSI (dBm)",
    type: "gradient",
    stops: rssiStops,
    ticks: [-100, -90, -80, -70, -60, -50, -40, -30],
    formatter: (value) => formatLegendValue(value, "dBm"),
  },
};

function hashString(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function colorFromBssid(bssid) {
  const normalized = (bssid || "").trim();
  if (!normalized) {
    return "#b5b5b5";
  }
  const idx = hashString(normalized.toLowerCase()) % bssidPalette.length;
  return bssidPalette[idx];
}

function buildBssidLegendConfig() {
  return buildCategoricalLegendConfig("bssid", "BSSID");
}

function buildBestNeighborBssidLegendConfig() {
  return buildCategoricalLegendConfig("best_neighbor_bssid", "Best Neighbor BSSID");
}

function buildCategoricalLegendConfig(fieldName, label) {
  const unique = new Map();
  state.segments.forEach((segment) => {
    (segment.logs || []).forEach((log) => {
      const rawValue = fieldName === "best_neighbor_bssid" ? log.best_neighbor_bssid : log.bssid;
      const key = (rawValue || "").trim() || "(No BSSID)";
      if (!unique.has(key)) {
        unique.set(key, colorFromBssid(rawValue));
      }
    });
  });
  if (unique.size === 0) {
    unique.set("(No Data)", "#b5b5b5");
  }
  const steps = Array.from(unique.entries()).map(([label, color]) => ({ label, color }));
  return {
    label,
    type: "steps",
    steps,
    reverseSteps: false,
  };
}

function gradientColor(max, value, stops) {
  return gradientStops(value, 0, max, stops);
}

function gradientStops(value, min, max, stops) {
  if (Number.isNaN(value)) return null;
  const clamped = clamp(value, min, max);
  if (clamped <= stops[0].value) {
    return stops[0].color;
  }
  for (let i = 0; i < stops.length - 1; i += 1) {
    const a = stops[i];
    const b = stops[i + 1];
    if (clamped >= a.value && clamped <= b.value) {
      const t = (clamped - a.value) / (b.value - a.value || 1);
      return mixColors(a.color, b.color, t);
    }
  }
  return stops.at(-1).color;
}

function mixColors(a, b, t) {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  const r = Math.round(ca.r + (cb.r - ca.r) * t);
  const g = Math.round(ca.g + (cb.g - ca.g) * t);
  const bl = Math.round(ca.b + (cb.b - ca.b) * t);
  return `rgb(${r},${g},${bl})`;
}

function hexToRgb(hex) {
  const normalized = hex.replace("#", "");
  const bigint = parseInt(normalized, 16);
  return {
    r: (bigint >> 16) & 255,
    g: (bigint >> 8) & 255,
    b: bigint & 255,
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function renderLegend() {
  if (!legendContainer) return;
  if (legendToggle && !legendToggle.checked) {
    legendContainer.classList.add("hidden");
    legendContainer.innerHTML = "";
    return;
  }
  legendContainer.classList.remove("hidden");
  legendContainer.innerHTML = "";
  const modeKey = normalizeMode(state.currentMode);
  const config =
    modeKey === "bssid"
      ? buildBssidLegendConfig()
      : modeKey === "best_neighbor_bssid"
        ? buildBestNeighborBssidLegendConfig()
        : legendConfigs[modeKey];
  if (!config) return;

  if (config.type === "gradient") {
    legendContainer.appendChild(createVerticalGradientLegend(config));
  } else if (config.type === "steps") {
    legendContainer.appendChild(createStepLegend(config));
  }
}

function createVerticalGradientLegend(config) {
  const wrapper = document.createElement("div");
  wrapper.className = "legend-vertical";
  const barWrap = document.createElement("div");
  barWrap.className = "legend-bar-wrap";
  const gradient = document.createElement("div");
  gradient.className = "legend-gradient-vertical";
  const colors = getLegendColors(config);
  gradient.style.background = `linear-gradient(180deg, ${colors.join(",")})`;
  barWrap.appendChild(gradient);
  if (config.ticks?.length) {
    const ticksEl = document.createElement("div");
    ticksEl.className = "legend-ticks";
    config.ticks.forEach((value) => {
      const tick = document.createElement("div");
      tick.className = "legend-tick";
      tick.textContent = config.formatter ? config.formatter(value) : value;
      ticksEl.appendChild(tick);
    });
    barWrap.appendChild(ticksEl);
  }
  wrapper.appendChild(barWrap);
  const axis = document.createElement("div");
  axis.className = "legend-axis-label";
  axis.textContent = config.label || "";
  wrapper.appendChild(axis);
  return wrapper;
}

function createStepLegend(config) {
  const wrapper = document.createElement("div");
  wrapper.className = "legend-vertical";
  const stepsColumn = document.createElement("div");
  stepsColumn.className = "legend-steps";
  const entries = config.reverseSteps ? [...config.steps].reverse() : config.steps;
  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "legend-step";
    const swatch = document.createElement("span");
    swatch.className = "legend-color";
    swatch.style.background = entry.color;
    row.appendChild(swatch);
    const label = document.createElement("span");
    label.textContent = entry.label;
    row.appendChild(label);
    stepsColumn.appendChild(row);
  });
  wrapper.appendChild(stepsColumn);
  const axis = document.createElement("div");
  axis.className = "legend-axis-label";
  axis.textContent = config.label || "";
  wrapper.appendChild(axis);
  return wrapper;
}

function getLegendColors(config) {
  const stops = config.stops || [];
  const ordered = config.reverseStops ? [...stops].reverse() : stops;
  return ordered.map((stop) => stop.color);
}

function drawLegendOnCanvas(ctx, config, x, y, height, width, options = {}) {
  const showAxisLabel = options.showAxisLabel !== false;
  const radius = 30;
  ctx.save();
  ctx.fillStyle = "#11141d";
  ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
  ctx.lineWidth = 4;
  drawRoundedRect(ctx, x, y, width, height, radius);
  ctx.fill();
  ctx.stroke();
  const padding = 40;
  const innerX = x + padding;
  const innerY = y + padding;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;

  if (config.type === "gradient") {
    drawGradientLegendOnCanvas(ctx, config, innerX, innerY, innerWidth, innerHeight);
  } else if (config.type === "steps") {
    drawStepLegendOnCanvas(ctx, config, innerX, innerY, innerWidth, innerHeight);
  }

  if (showAxisLabel) {
    // Axis label (vertical)
    ctx.translate(x + width - padding / 2, y + height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "bold 64px 'Segoe UI', 'Helvetica Neue', sans-serif";
    ctx.fillStyle = "#f7f7fb";
    ctx.fillText(config.label || "", 0, 0);
  }
  ctx.restore();
}

function drawGradientLegendOnCanvas(ctx, config, x, y, width, height) {
  const barWidth = Math.min(140, width * 0.5);
  const colors = getLegendColors(config);
  const gradient = ctx.createLinearGradient(0, y, 0, y + height);
  colors.forEach((color, idx) => {
    const ratio = colors.length === 1 ? 1 : idx / (colors.length - 1);
    gradient.addColorStop(ratio, color);
  });
  ctx.fillStyle = gradient;
  ctx.fillRect(x, y, barWidth, height);
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.strokeRect(x, y, barWidth, height);

  const ticks = config.ticks || [];
  if (ticks.length) {
    const tickX = x + barWidth + 28;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = "42px 'Segoe UI', 'Helvetica Neue', sans-serif";
    ctx.fillStyle = "#f7f7fb";
    const values = config.stops.map((stop) => stop.value);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const span = maxValue - minValue || 1;
    ticks.forEach((value) => {
      const normalized = (value - minValue) / span;
      const position = config.reverseStops ? 1 - normalized : normalized;
      const tickY = y + height * position;
      const label = config.formatter ? config.formatter(value) : `${value}`;
      ctx.fillText(label, tickX, tickY);
      ctx.beginPath();
      ctx.moveTo(x + barWidth, tickY);
      ctx.lineTo(tickX - 6, tickY);
      ctx.stroke();
    });
  }
}

function drawStepLegendOnCanvas(ctx, config, x, y, width, height) {
  const entries = config.reverseSteps ? [...config.steps].reverse() : config.steps;
  const rowHeight = height / entries.length;
  ctx.font = "42px 'Segoe UI', 'Helvetica Neue', sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  entries.forEach((entry, idx) => {
    const rowY = y + idx * rowHeight;
    const swatchSize = Math.min(110, rowHeight * 0.7);
    const swatchY = rowY + rowHeight / 2 - swatchSize / 2;
    ctx.fillStyle = entry.color;
    ctx.fillRect(x, swatchY, swatchSize, swatchSize);
    ctx.strokeStyle = "rgba(255,255,255,0.35)";
    ctx.strokeRect(x, swatchY, swatchSize, swatchSize);
    ctx.fillStyle = "#f7f7fb";
    ctx.fillText(entry.label, x + swatchSize + 12, rowY + rowHeight / 2);
  });
}

function drawRoundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function formatLegendValue(value, unit) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return `${value}${unit}`;
  }
  const formatted = Number.isInteger(numeric) ? numeric.toString() : numeric.toFixed(1).replace(/\.0$/, "");
  if (unit === "ms") {
    return `${formatted} ms`;
  }
  if (unit === "%") {
    return `${formatted} %`;
  }
  if (unit === "dBm") {
    return `${formatted} dBm`;
  }
  return `${formatted} ${unit}`;
}

function estimateLegendExportWidth(config) {
  const defaultWidth = 360;
  if (!config || config.type !== "steps" || !Array.isArray(config.steps) || config.steps.length === 0) {
    return defaultWidth;
  }
  const measureCanvas = document.createElement("canvas");
  const measureCtx = measureCanvas.getContext("2d");
  if (!measureCtx) {
    return defaultWidth;
  }
  measureCtx.font = "42px 'Segoe UI', 'Helvetica Neue', sans-serif";
  const entries = config.reverseSteps ? [...config.steps].reverse() : config.steps;
  const maxLabelWidth = entries.reduce((max, entry) => {
    const label = entry?.label ? String(entry.label) : "";
    return Math.max(max, measureCtx.measureText(label).width);
  }, 0);
  const outerPadding = 80; // drawLegendOnCanvas padding * 2
  const swatchAndGap = 122; // swatch(110) + gap(12)
  const axisReserve = 96; // vertical axis label room
  const computed = Math.ceil(outerPadding + swatchAndGap + maxLabelWidth + axisReserve);
  return Math.max(defaultWidth, computed);
}

function buildExportCanvas(modeKey, baseTitle) {
  const currentLegendConfig =
    modeKey === "bssid"
      ? buildBssidLegendConfig()
      : modeKey === "best_neighbor_bssid"
        ? buildBestNeighborBssidLegendConfig()
        : legendConfigs[modeKey];
  const legendConfig = currentLegendConfig;
  const modeLabel = legendConfig?.label || modeKey;
  const suffix = modeLabel ? ` ${modeLabel}` : "";
  const finalTitle = baseTitle ? `${baseTitle}${suffix}` : suffix.trim();
  const margin = 80;
  const includeTitle = titleToggle ? titleToggle.checked : true;
  const titleHeight = includeTitle && finalTitle ? 220 : 0;
  const legendWidth = legendConfig ? estimateLegendExportWidth(legendConfig) : 0;
  const legendGap = legendConfig ? 60 : 0;
  const totalWidth = canvas.width + legendWidth + legendGap + margin * 2;
  const totalHeight = canvas.height + margin * 2 + titleHeight;

  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = totalWidth;
  tempCanvas.height = totalHeight;
  const tempCtx = tempCanvas.getContext("2d");
  if (!tempCtx) {
    return null;
  }
  tempCtx.fillStyle = "#0f1115";
  tempCtx.fillRect(0, 0, totalWidth, totalHeight);

  const plotCanvas = document.createElement("canvas");
  plotCanvas.width = canvas.width;
  plotCanvas.height = canvas.height;
  const plotCtx = plotCanvas.getContext("2d");
  if (!plotCtx) {
    return null;
  }
  drawCanvas(plotCtx, plotCanvas);
  state.segments.forEach((segment) => drawSegment(segment, modeKey, plotCtx));
  drawPointLabels(plotCtx);

  const mapX = margin;
  const mapY = margin + titleHeight;
  tempCtx.drawImage(plotCanvas, mapX, mapY);

  if (includeTitle && finalTitle) {
    const size = Math.max(120, state.display.labelSize + 60);
    tempCtx.font = `600 ${size}px "Segoe UI", "Helvetica Neue", sans-serif`;
    tempCtx.textAlign = "left";
    tempCtx.textBaseline = "top";
    const titleX = margin;
    const titleY = margin;
    tempCtx.lineWidth = 10;
    tempCtx.strokeStyle = "rgba(4, 9, 15, 0.85)";
    tempCtx.strokeText(finalTitle, titleX, titleY);
    tempCtx.fillStyle = "#f7f7fb";
    tempCtx.fillText(finalTitle, titleX, titleY);
  }

  if (legendConfig) {
    const legendX = mapX + canvas.width + legendGap;
    const legendY = mapY;
    // The mode label is already in the export title, so hide duplicated legend axis label.
    drawLegendOnCanvas(tempCtx, legendConfig, legendX, legendY, canvas.height, legendWidth, { showAxisLabel: false });
  }
  return { canvas: tempCanvas, modeLabel };
}

const MAX_EXPORT_DIMENSION = 8192;
const MAX_EXPORT_PIXELS = 64 * 1024 * 1024;

function getSafeExportScale(width, height) {
  if (!width || !height) return 0;
  return Math.min(
    1,
    MAX_EXPORT_DIMENSION / width,
    MAX_EXPORT_DIMENSION / height,
    Math.sqrt(MAX_EXPORT_PIXELS / (width * height)),
  );
}

function downloadCanvasPng(exportCanvas, filename, successMessage) {
  if (!exportCanvas?.width || !exportCanvas?.height) {
    statusMessage.textContent = "画像の生成に失敗しました。";
    return;
  }
  try {
    exportCanvas.toBlob((blob) => {
      if (!blob || !blob.size) {
        statusMessage.textContent = "PNGを生成できませんでした。出力サイズを小さくして再試行してください。";
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (successMessage) statusMessage.textContent = successMessage;
    }, "image/png");
  } catch (error) {
    statusMessage.textContent = `PNGを生成できませんでした: ${error.message}`;
  }
}

function exportPlotImage(options = {}) {
  if (!canvas) return;
  const baseTitle = (options.filePrefix || exportTitleInput?.value || "").trim();
  const modeKey = normalizeMode(options.modeOverride || state.currentMode);
  const exportData = buildExportCanvas(modeKey, baseTitle);
  if (!exportData) {
    statusMessage.textContent = "画像の生成に失敗しました。";
    return;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const safeTitle = baseTitle ? sanitizeFileName(baseTitle) : "plot";
  const modeToken = sanitizeFileName(modeKey.replace(/_/g, "-"));
  downloadCanvasPng(exportData.canvas, `${safeTitle}_${modeToken}_${timestamp}.png`, "画像を書き出しました。");
}

function hasAnyBestNeighborData() {
  return state.segments.some((segment) =>
    (segment.logs || []).some((log) => (log.best_neighbor_bssid || "").trim() || (log.best_neighbor_dbm || "").trim()),
  );
}

function getExportAllLayout() {
  const modes = [
    { mode: "ping", row: 0, col: 0 },
    { mode: "rssi", row: 0, col: 1 },
    { mode: "ping_300", row: 1, col: 0 },
    { mode: "signal", row: 1, col: 1 },
    { mode: "ping_levels", row: 2, col: 0 },
    { mode: "bssid", row: 3, col: 0 },
  ];
  if (hasAnyBestNeighborData()) {
    modes.push(
      { mode: "best_neighbor_bssid", row: 3, col: 1 },
      { mode: "best_neighbor_rssi", row: 4, col: 0 },
    );
  }
  return modes;
}

function exportAllLegendImages() {
  const layout = getExportAllLayout();
  const prefix = (exportTitleInput?.value || "").trim() || "plot";
  const cards = [];

  for (const entry of layout) {
    const modeKey = normalizeMode(entry.mode);
    const exportData = buildExportCanvas(modeKey, prefix);
    if (!exportData) continue;
    cards.push({ modeKey, row: entry.row, col: entry.col, ...exportData });
  }

  if (!cards.length) {
    statusMessage.textContent = "書き出し対象がありません。";
    return;
  }

  const cols = 2;
  const rows = Math.max(...cards.map((card) => card.row)) + 1;
  const rawTileWidth = Math.max(...cards.map((card) => card.canvas.width));
  const rawTileHeight = Math.max(...cards.map((card) => card.canvas.height));
  const rawWidth = 80 + cols * rawTileWidth + (cols - 1) * 24;
  const rawHeight = 80 + 90 + rows * rawTileHeight + (rows - 1) * 24;
  const scale = getSafeExportScale(rawWidth, rawHeight);
  if (!scale) {
    statusMessage.textContent = "画像の生成に失敗しました。";
    return;
  }
  const gapX = Math.max(8, Math.round(24 * scale));
  const gapY = Math.max(8, Math.round(24 * scale));
  const margin = Math.max(16, Math.round(40 * scale));
  const titleHeight = Math.max(36, Math.round(90 * scale));
  const tileWidth = Math.max(1, Math.round(rawTileWidth * scale));
  const tileHeight = Math.max(1, Math.round(rawTileHeight * scale));
  const sheetWidth = margin * 2 + cols * tileWidth + (cols - 1) * gapX;
  const sheetHeight = margin * 2 + titleHeight + rows * tileHeight + (rows - 1) * gapY;

  const sheet = document.createElement("canvas");
  sheet.width = sheetWidth;
  sheet.height = sheetHeight;
  const sctx = sheet.getContext("2d");
  if (!sctx) {
    statusMessage.textContent = "画像の生成に失敗しました。";
    return;
  }
  sctx.imageSmoothingEnabled = true;
  sctx.imageSmoothingQuality = "high";

  sctx.fillStyle = "#0f1115";
  sctx.fillRect(0, 0, sheetWidth, sheetHeight);

  const title = `${prefix} all-modes`;
  sctx.fillStyle = "#f7f7fb";
  sctx.font = `600 ${Math.max(18, Math.round(42 * scale))}px 'Segoe UI', 'Helvetica Neue', sans-serif`;
  sctx.textAlign = "left";
  sctx.textBaseline = "top";
  sctx.fillText(title, margin, margin);

  cards.forEach((card) => {
    const x = margin + card.col * (tileWidth + gapX);
    const y = margin + titleHeight + card.row * (tileHeight + gapY);
    sctx.drawImage(card.canvas, x, y, tileWidth, tileHeight);
  });

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const safePrefix = sanitizeFileName(prefix);
  const resizeNote = scale < 0.999 ? "（ブラウザ上限に合わせて縮小）" : "";
  downloadCanvasPng(
    sheet,
    `${safePrefix}_all-modes_${timestamp}.png`,
    `全モードのレジェンド付きプロット画像を書き出しました。${resizeNote}`,
  );
}
function sanitizeFileName(name) {
  return name.replace(/[\\/:*?"<>|]/g, "_") || "plot";
}

function renderSsidOptions() {
  if (!ssidDatalist) return;
  ssidDatalist.innerHTML = "";
  state.ssidOptions.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    ssidDatalist.appendChild(opt);
  });
}

function renderTimezoneOptions(current) {
  if (timezoneSelect) {
    const currentValue = current || timezoneSelect.value || "Asia/Tokyo";
    const options = state.timezoneOptions.length ? state.timezoneOptions : [currentValue, "Etc/GMT"];
    timezoneSelect.innerHTML = "";
    options.forEach((tz) => {
      const opt = document.createElement("option");
      opt.value = tz;
      opt.textContent = tz;
      timezoneSelect.appendChild(opt);
    });
    timezoneSelect.value = currentValue;
  } else if (form.timezone) {
    form.timezone.value = current || form.timezone.value || "Asia/Tokyo";
  }
}

function initDisplayControls() {
  bindDualInput(labelSizeNumber, labelSizeRange, state.display.labelSize, (value) => {
    state.display.labelSize = value;
    renderAll();
  });
  bindDualInput(anchorRadiusNumber, anchorRadiusRange, state.display.anchorRadius, (value) => {
    state.display.anchorRadius = value;
    renderAll();
  });
  bindDualInput(plotRadiusNumber, plotRadiusRange, state.display.plotRadius, (value) => {
    state.display.plotRadius = value;
    renderAll();
  });
  if (plotShapeSelect) {
    plotShapeSelect.addEventListener("change", (event) => {
      state.display.plotShape = event.target.value || "dot";
      renderAll();
    });
  }
  labelColorInput.addEventListener("input", (event) => {
    state.display.labelColor = event.target.value || "#ff5de4";
    renderAll();
  });
  grayscaleToggle.addEventListener("change", (event) => {
    state.display.grayscaleEnabled = event.target.checked;
    grayscaleRange.disabled = !event.target.checked;
    renderAll();
  });
  grayscaleRange.addEventListener("input", (event) => {
    state.display.grayscaleLevel = Number(event.target.value) || 100;
    if (state.display.grayscaleEnabled) {
      renderAll();
    }
  });
  grayscaleRange.disabled = !grayscaleToggle.checked;
}

function bindDualInput(numberEl, rangeEl, initialValue, onChange) {
  const applyValue = (value) => {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
      return;
    }
    numberEl.value = numeric;
    rangeEl.value = numeric;
    onChange(numeric);
  };
  numberEl.addEventListener("input", (event) => applyValue(event.target.value));
  rangeEl.addEventListener("input", (event) => applyValue(event.target.value));
  applyValue(initialValue);
}

window.addEventListener("error", (event) => {
  console.error("window error", event.error || event.message);
  if (statusMessage) {
    statusMessage.textContent = `UIエラー: ${event.message || "unknown"}`;
  }
});

window.addEventListener("unhandledrejection", (event) => {
  console.error("unhandled rejection", event.reason);
  if (statusMessage) {
    const msg = event?.reason?.message || String(event.reason || "unknown");
    statusMessage.textContent = `初期化エラー: ${msg}`;
  }
});

init().catch((error) => {
  console.error("init failed", error);
  if (statusMessage) {
    statusMessage.textContent = `初期化失敗: ${error?.message || "unknown"}`;
  }
});


