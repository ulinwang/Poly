/* PolyMetl 实验浏览器 — 只读浏览已完成仿真的轨迹与决策。 */
const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
  setup() {
    const suites = ref({});
    const total = ref(0);
    const filter = ref("");
    const selectedId = ref(null);
    const meta = ref(null);
    const agents = ref([]);
    const traj = ref(null);
    const metric = ref("net_value");
    const selectedAgent = ref(null);
    const agentDetail = ref(null);

    const allChart = ref(null);
    const agentChart = ref(null);
    let allInst = null, agentInst = null;

    const cfgAgent = computed(() => (meta.value?.config?.agent) || {});

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

    const fmt = (v, n) => (v === null || v === undefined || Number.isNaN(v))
      ? "—" : Number(v).toFixed(n);
    const fmtNum = (v) => {
      if (v === null || v === undefined) return "—";
      v = Number(v);
      if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + "M";
      if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + "k";
      return v.toFixed(0);
    };
    const shortTime = (t) => t ? String(t).replace("T", " ").slice(0, 19) : "—";

    const loadList = async () => {
      const r = await fetch("/api/experiments");
      const j = await r.json();
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
      const ds = [];
      for (const [aid, series] of Object.entries(t.agents)) {
        ds.push({
          label: `A${aid}`,
          data: series[metric.value],
          borderColor: "rgba(120,128,138,0.30)",
          borderWidth: 1, pointRadius: 0, tension: 0.2,
          yAxisID: "y",
        });
      }
      ds.push({
        label: "市场 P(是)",
        data: t.market_yes_mid,
        borderColor: "#0f9e8c", borderWidth: 2.5,
        pointRadius: 0, tension: 0.2, yAxisID: "y1",
      });
      if (allInst) allInst.destroy();
      allInst = new Chart(allChart.value.getContext("2d"), {
        type: "line",
        data: { labels: t.ticks.map(x => `第${x}轮`), datasets: ds },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: false,
          plugins: { legend: { display: false },
            tooltip: { enabled: true, mode: "nearest", intersect: false } },
          scales: {
            y: { position: "left", title: { display: true, text: metric.value === "cash" ? "现金 $" : "净资产 $" } },
            y1: { position: "right", min: 0, max: 1, grid: { drawOnChartArea: false },
                  title: { display: true, text: "P(是)" } },
          },
        },
      });
    };

    const selectAgent = async (aid) => {
      selectedAgent.value = aid;
      const d = await fetch(
        `/api/experiments/${selectedId.value}/agents/${aid}`).then(r => r.json());
      agentDetail.value = d;
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
          labels: tr.map(p => `第${p.tick}轮`),
          datasets: [
            { label: "净资产", data: tr.map(p => p.net_value),
              borderColor: "#0f9e8c", borderWidth: 2, pointRadius: 2, yAxisID: "y" },
            { label: "现金", data: tr.map(p => p.cash),
              borderColor: "#1565c0", borderWidth: 1.5, pointRadius: 0,
              borderDash: [4, 3], yAxisID: "y" },
            { label: "P(是)", data: tr.map(p => p.yes_mid),
              borderColor: "#c97a1e", borderWidth: 1.5, pointRadius: 0, yAxisID: "y1" },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: true, labels: { boxWidth: 12 } } },
          scales: {
            y: { position: "left", title: { display: true, text: "$" } },
            y1: { position: "right", min: 0, max: 1, grid: { drawOnChartArea: false } },
          },
        },
      });
    };

    onMounted(loadList);
    return {
      suites, total, filter, filteredSuites,
      selectedId, meta, cfgAgent, agents, metric,
      selectedAgent, agentDetail, allChart, agentChart,
      selectExperiment, selectAgent, drawAll,
      fmt, fmtNum, shortTime,
    };
  },
}).mount("#app");
