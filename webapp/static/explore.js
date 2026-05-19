/* PolyMetl 实验浏览器 — 只读浏览已完成仿真的配置、结果与轨迹。 */
const { createApp, ref, computed, onMounted, nextTick } = Vue;

const SUITE_LABEL = {
  b1: "外部效度面板", b2: "随机性基线", b2fix: "修正后对照",
  b3: "群体结构对照", b4: "信念机制对照", b6: "信息冲击对照",
};
const POP_LABEL = {
  archetype: "行为原型采样", marginal_random: "边际匹配随机",
  uniform_random: "均匀随机", calibrated: "真实钱包校准",
  no_signal: "无私有判断（对照）",
};
const SIGNAL_LABEL = {
  first_window_vwap: "市场早期成交量加权价",
  bootstrap_anchor: "开盘盘口中间价",
};
const OBS_LABEL = { quote_only: "仅买卖报价", tape: "含成交流水", full_book: "完整订单簿" };
const SEED_LABEL = {
  from_clob_history: "真实早期成交回放", from_holders: "真实持仓者", none: "无",
};
const BOOT_LABEL = {
  dataapi_trades_dispersion: "真实成交价分布", clob_orderbook: "真实订单簿快照",
  fallback_default: "默认回退值",
};
const ACTION_LABEL = {
  LIMIT: "限价单", MARKET: "市价单", CANCEL: "撤单", HOLD: "不操作",
  SPLIT: "拆分份额", MERGE: "合并份额", UPDATE_BELIEF: "更新信念",
};

createApp({
  setup() {
    const suites = ref({}), total = ref(0), filter = ref("");
    const selectedId = ref(null), meta = ref(null);
    const agents = ref([]), traj = ref(null), metric = ref("net_value");
    const selectedAgent = ref(null), agentDetail = ref(null);
    const sortKey = ref("agent_id"), sortDir = ref(1);
    const allChart = ref(null), agentChart = ref(null);
    let allInst = null, agentInst = null;

    const cfgAgent = computed(() => meta.value?.config?.agent || {});
    const cfgEnv = computed(() => meta.value?.config?.environment || {});
    const cfgLlm = computed(() => meta.value?.config?.llm || {});
    const priors = computed(() => meta.value?.priors_summary || {});
    const pnl = computed(() => meta.value?.pnl_stats || null);
    const drift = computed(() => {
      const m = meta.value;
      return (m && m.final_yes_mid != null && m.start_yes_mid != null)
        ? m.final_yes_mid - m.start_yes_mid : 0;
    });

    const filteredSuites = computed(() => {
      const q = filter.value.trim().toLowerCase();
      if (!q) return suites.value;
      const out = {};
      for (const [s, runs] of Object.entries(suites.value)) {
        const f = runs.filter(r =>
          (r.name || "").toLowerCase().includes(q) ||
          (r.slug || "").toLowerCase().includes(q));
        if (f.length) out[s] = f;
      }
      return out;
    });

    const sortedAgents = computed(() => {
      const k = sortKey.value, d = sortDir.value;
      return [...agents.value].sort((a, b) => {
        const x = a[k], y = b[k];
        return (x < y ? -1 : x > y ? 1 : 0) * d;
      });
    });
    const sortBy = (k) => {
      if (sortKey.value === k) sortDir.value *= -1;
      else { sortKey.value = k; sortDir.value = 1; }
    };

    const fmt = (v, n) => (v === null || v === undefined || Number.isNaN(v))
      ? "—" : Number(v).toFixed(n);
    const fmtNum = (v) => {
      if (v === null || v === undefined) return "—";
      v = Number(v);
      if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + "M";
      if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + "k";
      return v.toFixed(0);
    };
    const shortTime = (t) => t ? String(t).replace("T", " ").replace("Z", "").slice(0, 19) : "—";
    const suiteLabel = (s) => SUITE_LABEL[s] || s;
    const populationLabel = (p) => POP_LABEL[p] || p || "—";
    const signalLabel = (s) => SIGNAL_LABEL[s] || s || "默认";
    const observerLabel = (o) => OBS_LABEL[o] || o || "—";
    const seederLabel = (s) => SEED_LABEL[s] || s || "—";
    const bootstrapLabel = (b) => BOOT_LABEL[b] || b || "—";
    const actionLabel = (a) => ACTION_LABEL[a] || a;
    const tradeLike = (a) => ["LIMIT", "MARKET", "SPLIT", "MERGE"].includes(a);

    const loadList = async () => {
      const j = await fetch("/api/experiments").then(r => r.json());
      suites.value = j.suites || {};
      total.value = j.total || 0;
    };

    const selectExperiment = async (eid) => {
      selectedId.value = eid;
      meta.value = null; agents.value = []; traj.value = null;
      agentDetail.value = null; selectedAgent.value = null;
      const [m, a, t] = await Promise.all([
        fetch(`/api/experiments/${eid}`).then(r => r.json()),
        fetch(`/api/experiments/${eid}/agents`).then(r => r.json()),
        fetch(`/api/experiments/${eid}/trajectories`).then(r => r.json()),
      ]);
      meta.value = m;
      agents.value = a.agents || [];
      traj.value = t;
      await nextTick();
      drawAll();
    };

    const drawAll = () => {
      if (!traj.value || !allChart.value) return;
      const t = traj.value;
      const ds = Object.entries(t.agents).map(([aid, s]) => ({
        label: `A${aid}`, data: s[metric.value],
        borderColor: "rgba(120,128,138,0.28)", borderWidth: 1,
        pointRadius: 0, tension: 0.2, yAxisID: "y",
      }));
      ds.push({
        label: "市场 P(是)", data: t.market_yes_mid,
        borderColor: "#0f9e8c", borderWidth: 2.5, pointRadius: 0,
        tension: 0.2, yAxisID: "y1",
      });
      if (allInst) allInst.destroy();
      allInst = new Chart(allChart.value.getContext("2d"), {
        type: "line",
        data: { labels: t.ticks.map(x => x), datasets: ds },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: false },
            tooltip: { enabled: true, mode: "nearest", intersect: false } },
          scales: {
            x: { title: { display: true, text: "轮次" } },
            y: { position: "left",
                 title: { display: true, text: metric.value === "cash" ? "现金（美元）" : "净资产（美元）" } },
            y1: { position: "right", min: 0, max: 1,
                  grid: { drawOnChartArea: false },
                  title: { display: true, text: "P(是)" } },
          },
        },
      });
    };

    const selectAgent = async (aid) => {
      selectedAgent.value = aid;
      agentDetail.value = await fetch(
        `/api/experiments/${selectedId.value}/agents/${aid}`).then(r => r.json());
      await nextTick();
      drawAgent();
    };

    const drawAgent = () => {
      if (!agentDetail.value || !agentChart.value) return;
      const tr = agentDetail.value.trajectory;
      if (agentInst) agentInst.destroy();
      agentInst = new Chart(agentChart.value.getContext("2d"), {
        type: "line",
        data: {
          labels: tr.map(p => p.tick),
          datasets: [
            { label: "净资产", data: tr.map(p => p.net_value),
              borderColor: "#0f9e8c", borderWidth: 2, pointRadius: 2, yAxisID: "y" },
            { label: "现金", data: tr.map(p => p.cash),
              borderColor: "#1565c0", borderWidth: 1.5, pointRadius: 0,
              borderDash: [4, 3], yAxisID: "y" },
            { label: "市场 P(是)", data: tr.map(p => p.yes_mid),
              borderColor: "#c97a1e", borderWidth: 1.5, pointRadius: 0, yAxisID: "y1" },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: true, labels: { boxWidth: 12, font: { size: 11 } } } },
          scales: {
            x: { title: { display: true, text: "轮次" } },
            y: { position: "left", title: { display: true, text: "美元" } },
            y1: { position: "right", min: 0, max: 1, grid: { drawOnChartArea: false } },
          },
        },
      });
    };

    onMounted(loadList);
    return {
      suites, total, filter, filteredSuites, selectedId, meta,
      cfgAgent, cfgEnv, cfgLlm, priors, pnl, drift,
      agents, sortedAgents, sortBy, metric,
      selectedAgent, agentDetail, allChart, agentChart,
      selectExperiment, selectAgent, drawAll,
      fmt, fmtNum, shortTime, suiteLabel, populationLabel, signalLabel,
      observerLabel, seederLabel, bootstrapLabel, actionLabel, tradeLike,
    };
  },
}).mount("#app");
