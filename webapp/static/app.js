/* PolyMetl Live — Vue 3 SPA. Streams events from /api/runs/{id}/events
   into a multi-pane dashboard (market picker | chart + tick log |
   agent reasoning stream + roster). */

const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

createApp({
  setup() {
    // ---- state -----------------------------------------------------
    const markets = ref([]);
    const marketQuery = ref("");
    const liveOnly = ref(true);

    const slug = ref("");
    const nAgents = ref(20);
    const nTicks = ref(12);
    const personaSet = ref("archetype");

    const runId = ref(null);
    const running = ref(false);
    const runError = ref(null);
    const runDone = ref(false);

    const meta = ref(null);
    const priors = ref(null);

    const agents = ref([]);
    const decisions = ref([]);
    const tickLog = ref([]);
    const yesMid = ref(0.5);
    const yesHistory = ref([]);
    const currentTick = ref(null);
    const totalTicks = ref(0);
    const nFills = ref(0);
    const nActions = ref(0);
    const lastTickElapsed = ref(0);

    // chart
    const chart = ref(null);
    let chartInst = null;
    let evtSource = null;
    let logId = 0;
    let decisionId = 0;

    // ---- computed --------------------------------------------------
    const runStatusClass = computed(() => {
      if (runError.value) return "error";
      if (running.value) return "running";
      if (runDone.value) return "done";
      return "idle";
    });
    const runStatusLabel = computed(() => {
      if (runError.value) return "ERROR";
      if (running.value) return "RUNNING";
      if (runDone.value) return "DONE";
      return "IDLE";
    });

    // ---- utils -----------------------------------------------------
    const nowStr = () => {
      const d = new Date();
      return d.toTimeString().slice(0, 8);
    };
    const formatNumber = (n) => {
      if (n === null || n === undefined) return "—";
      n = Number(n);
      if (!Number.isFinite(n)) return "—";
      if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + "M";
      if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "k";
      return n.toFixed(0);
    };
    const pushLog = (label, msg, kind = "info") => {
      tickLog.value.push({
        id: ++logId, time: nowStr(),
        label, msg, kind,
      });
      if (tickLog.value.length > 300) tickLog.value.shift();
    };
    const clearTickLog = () => { tickLog.value = []; };

    // ---- API calls -------------------------------------------------
    const searchMarkets = async () => {
      const url = new URL("/api/markets", window.location.origin);
      if (marketQuery.value) url.searchParams.set("q", marketQuery.value);
      if (liveOnly.value) url.searchParams.set("live_only", "1");
      url.searchParams.set("limit", "30");
      try {
        const resp = await fetch(url);
        const j = await resp.json();
        markets.value = j.markets || [];
      } catch (e) {
        pushLog("HTTP", "市场列表加载失败: " + e.message, "error");
      }
    };

    const bootstrapMeta = (m) => {
      // populated with metadata once the run starts
      meta.value = {
        question: m.question, is_live: m.is_live,
        tick_size: "—", taker_fee_bps: "—", volume: m.volume,
      };
    };

    const startRun = async () => {
      resetRunState();
      running.value = true;
      try {
        const resp = await fetch("/api/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            slug: slug.value,
            n_agents: nAgents.value,
            n_ticks: nTicks.value,
            persona_set: personaSet.value,
          }),
        });
        if (!resp.ok) {
          const txt = await resp.text();
          throw new Error("HTTP " + resp.status + ": " + txt);
        }
        const j = await resp.json();
        runId.value = j.run_id;
        pushLog("RUN", `已启动 run ${j.run_id.slice(0,8)} · slug=${slug.value}`);
        connectSSE(j.run_id);
      } catch (e) {
        running.value = false;
        runError.value = e.message;
        pushLog("HTTP", "启动失败: " + e.message, "error");
      }
    };

    const cancelRun = async () => {
      if (!runId.value) return;
      try {
        await fetch(`/api/runs/${runId.value}/cancel`, { method: "POST" });
        pushLog("RUN", "请求中止仿真", "warn");
      } catch (e) {
        pushLog("HTTP", "中止失败: " + e.message, "error");
      }
    };

    const resetRunState = () => {
      if (evtSource) { evtSource.close(); evtSource = null; }
      runId.value = null;
      runError.value = null;
      runDone.value = false;
      agents.value = [];
      decisions.value = [];
      yesMid.value = 0.5;
      yesHistory.value = [];
      currentTick.value = null;
      totalTicks.value = 0;
      nFills.value = 0;
      nActions.value = 0;
      lastTickElapsed.value = 0;
      priors.value = null;
      if (chartInst) {
        chartInst.data.labels = [];
        chartInst.data.datasets[0].data = [];
        chartInst.update("none");
      }
    };

    // ---- SSE -------------------------------------------------------
    const connectSSE = (rid) => {
      evtSource = new EventSource(`/api/runs/${rid}/events`);
      const on = (type, fn) => evtSource.addEventListener(type, (e) => {
        let data = {};
        try { data = JSON.parse(e.data); } catch (_) {}
        fn(data);
      });

      on("run_started", (d) => {
        totalTicks.value = d.n_ticks_requested || 0;
        pushLog("START", `slug=${d.slug} · n_agents=${d.n_agents} · persona=${d.persona_set}`);
      });
      on("market_resolved", (d) => {
        meta.value = {
          question: d.question, is_live: d.is_live,
          tick_size: d.tick_size, taker_fee_bps: d.taker_fee_bps,
          volume: d.volume,
        };
        pushLog("MARKET", (d.is_live ? "未结算" : "已结算") + " · " + d.question);
      });
      on("priors_ready", (d) => {
        priors.value = d;
        pushLog("PRIORS",
          `μ=${d.signal_mu.toFixed(3)} · tick_size=${d.tick_size} · ` +
          `n_ticks(priors)=${d.n_ticks_priors} · ${d.bootstrap_source}`);
      });
      on("population_built", (d) => {
        agents.value = d.agents;
        pushLog("POP", `${d.n_agents} 个 agent 已构造`);
      });
      on("env_ready", (d) => {
        totalTicks.value = d.n_ticks;
        yesMid.value = d.yes_mid_post_seed;
        yesHistory.value = [d.yes_mid_post_seed];
        updateChart();
        pushLog("ENV", `yes_mid post-seed=${d.yes_mid_post_seed.toFixed(3)} · n_ticks=${d.n_ticks}`);
      });
      on("tick_started", (d) => {
        currentTick.value = d.tick;
        pushLog("TICK", `▶ tick ${d.tick + 1}/${d.total} 启动`);
      });
      on("agent_decision", (d) => {
        decisions.value.push({ id: ++decisionId, ...d });
        if (decisions.value.length > 400) decisions.value.shift();
      });
      on("agent_decision_error", (d) => {
        pushLog("LLM",
          `A${d.agent_id} t${d.tick + 1} 决策失败: ${d.message}`, "error");
      });
      on("tick_finished", (d) => {
        yesMid.value = d.yes_mid;
        yesHistory.value = d.yes_mid_history;
        nFills.value = d.n_fills + nFills.value;
        nActions.value = d.n_actions;
        lastTickElapsed.value = d.elapsed_s;
        updateChart();
        pushLog("TICK",
          `✓ tick ${d.tick + 1} 完成 · fills=${d.n_fills} · yes_mid=${d.yes_mid.toFixed(3)} · ${d.elapsed_s}s`);
      });
      on("settled", (d) => {
        pushLog("SETTLE",
          `actions=${d.n_actions} · fills=${d.n_fills} · ` +
          `yes_mid_final=${d.yes_mid_final.toFixed(3)} · wall=${d.wall_seconds}s`);
      });
      on("done", (d) => {
        running.value = false;
        runDone.value = true;
        pushLog("DONE", `sim_id=${(d.sim_id||"").slice(0,8)}`);
        if (evtSource) { evtSource.close(); evtSource = null; }
      });
      on("error", (d) => {
        runError.value = d.message || "unknown";
        running.value = false;
        pushLog("ERROR", `${d.where}: ${d.message}`, "error");
      });
      on("warn", (d) => {
        pushLog("WARN", `${d.where}: ${d.message}`, "warn");
      });
      on("cancelled", (d) => {
        running.value = false;
        pushLog("CANCEL", `tick=${d.tick} 已取消`, "warn");
        if (evtSource) { evtSource.close(); evtSource = null; }
      });
      on("end", () => {
        if (evtSource) { evtSource.close(); evtSource = null; }
      });
      on("ping", () => { /* keep-alive */ });
      evtSource.onerror = () => {
        // EventSource will retry; we just surface the disconnection.
        pushLog("SSE", "连接中断,正在重连…", "warn");
      };
    };

    // ---- chart -----------------------------------------------------
    const setupChart = () => {
      const ctx = chart.value.getContext("2d");
      chartInst = new Chart(ctx, {
        type: "line",
        data: {
          labels: [],
          datasets: [{
            label: "YES_mid",
            data: [],
            borderColor: "#0f9e8c",
            backgroundColor: "rgba(15, 158, 140, 0.14)",
            tension: 0.25,
            pointRadius: 2,
            fill: true,
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 300 },
          scales: {
            y: { min: 0, max: 1, ticks: { stepSize: 0.25 } },
            x: { ticks: { autoSkip: true, maxTicksLimit: 12 } },
          },
          plugins: {
            legend: { display: false },
            tooltip: { mode: "index", intersect: false },
          },
        },
      });
    };
    const updateChart = () => {
      if (!chartInst) return;
      const data = yesHistory.value.slice(-200);
      chartInst.data.labels = data.map((_, i) => `t${i}`);
      chartInst.data.datasets[0].data = data;
      chartInst.update("none");
    };

    // ---- lifecycle -------------------------------------------------
    onMounted(async () => {
      setupChart();
      await searchMarkets();
    });

    return {
      // state
      markets, marketQuery, liveOnly, slug,
      nAgents, nTicks, personaSet,
      runId, running, runError, runDone,
      meta, priors,
      agents, decisions, tickLog,
      yesMid, currentTick, totalTicks,
      nFills, nActions, lastTickElapsed,
      chart,
      // computed
      runStatusClass, runStatusLabel,
      // methods
      searchMarkets, bootstrapMeta,
      startRun, cancelRun, clearTickLog,
      formatNumber,
    };
  },
}).mount("#app");
