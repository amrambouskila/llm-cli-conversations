import { useRef, useEffect, useCallback, useState } from "react";
import * as d3 from "d3";

const STORAGE_KEY = "conceptGraphSettings";

const DEFAULTS = {
  centerStrength: 0.03,
  chargeStrength: -200,
  chargeDistanceMax: 400,
  linkStrength: 0.08,
  linkDistance: 120,
  collisionPadding: 4,
  colorScheme: "tableau10",
  labelThreshold: 0.3,
};

const COLOR_SCHEMES = {
  tableau10: d3.schemeTableau10,
  category10: d3.schemeCategory10,
  dark2: d3.schemeDark2,
  set2: d3.schemeSet2,
  paired: d3.schemePaired,
  pastel1: d3.schemePastel1,
};

function loadSettings() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return { ...DEFAULTS, ...JSON.parse(stored) };
  } catch { /* ignore */ }
  return { ...DEFAULTS };
}

function saveSettings(settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

const SLIDERS = [
  { key: "centerStrength", label: "Center Force", min: 0, max: 0.2, step: 0.005 },
  { key: "chargeStrength", label: "Repel Force", min: -600, max: 0, step: 10 },
  { key: "chargeDistanceMax", label: "Repel Range", min: 50, max: 1000, step: 25 },
  { key: "linkStrength", label: "Link Force", min: 0, max: 0.5, step: 0.01 },
  { key: "linkDistance", label: "Link Distance", min: 20, max: 400, step: 5 },
  { key: "collisionPadding", label: "Collision Pad", min: 0, max: 20, step: 1 },
  { key: "labelThreshold", label: "Label Threshold", min: 0, max: 1, step: 0.05 },
];

export default function ConceptGraph({ data, onConceptClick }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const simulationRef = useRef(null);
  const onClickRef = useRef(onConceptClick);
  const prevDataKeyRef = useRef(null);
  const sizeScaleRef = useRef(null);

  const [settings, setSettings] = useState(loadSettings);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => { onClickRef.current = onConceptClick; }, [onConceptClick]);

  const cleanup = useCallback(() => {
    if (simulationRef.current) {
      simulationRef.current.stop();
      simulationRef.current = null;
    }
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
  }, []);

  const updateSetting = useCallback((key, value) => {
    setSettings((prev) => {
      const next = { ...prev, [key]: value };
      saveSettings(next);
      return next;
    });
  }, []);

  const resetSettings = useCallback(() => {
    setSettings({ ...DEFAULTS });
    saveSettings(DEFAULTS);
  }, []);

  // Apply force changes to the running simulation without rebuilding
  const settingsRef = useRef(settings);
  useEffect(() => {
    settingsRef.current = settings;
    const sim = simulationRef.current;
    if (!sim) return;

    const s = settings;
    sim.force("center").strength(s.centerStrength);
    sim.force("charge").strength(s.chargeStrength).distanceMax(s.chargeDistanceMax);
    sim.force("link").strength(s.linkStrength).distance(s.linkDistance);
    sim.force("collision").radius((d) => (sizeScaleRef.current ? sizeScaleRef.current(d.degree || 1) : 6) + s.collisionPadding);

    // Update node colors
    const scheme = COLOR_SCHEMES[s.colorScheme] || COLOR_SCHEMES.tableau10;
    const communityIds = data ? [...new Set(data.nodes.map((n) => n.community_id))] : [];
    const colorScale = d3.scaleOrdinal(scheme).domain(communityIds);
    d3.select(svgRef.current).selectAll(".concept-node").attr("fill", (d) => colorScale(d.community_id));

    // Update label visibility
    if (data) {
      const maxDegree = Math.max(1, ...data.nodes.map((n) => n.degree || 1));
      d3.select(svgRef.current).selectAll(".concept-label").attr("display", (d) => {
        return (d.degree || 0) >= maxDegree * s.labelThreshold || (d.session_count || 0) >= 3 ? null : "none";
      });
    }

    sim.alpha(0.3).restart();
  }, [settings, data]);

  const dataKey = data ? `${data.nodes.length}:${data.edges.length}:${data.nodes.map(n => n.id).join(",")}` : "";

  useEffect(() => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      cleanup();
      prevDataKeyRef.current = null;
      return;
    }

    if (dataKey === prevDataKeyRef.current) return;
    prevDataKeyRef.current = dataKey;

    cleanup();

    const s = settingsRef.current;
    const container = containerRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;

    const svg = d3.select(svgRef.current)
      .attr("width", width)
      .attr("height", height);

    const g = svg.append("g");

    const zoom = d3.zoom()
      .scaleExtent([0.2, 5])
      .on("zoom", (event) => { g.attr("transform", event.transform); });

    svg.call(zoom);

    const communityIds = [...new Set(data.nodes.map((n) => n.community_id))];
    const scheme = COLOR_SCHEMES[s.colorScheme] || COLOR_SCHEMES.tableau10;
    const colorScale = d3.scaleOrdinal(scheme).domain(communityIds);

    const maxDegree = Math.max(1, ...data.nodes.map((n) => n.degree || 1));
    const sizeScale = d3.scaleSqrt().domain([0, maxDegree]).range([4, 20]);
    sizeScaleRef.current = sizeScale;

    const maxWeight = Math.max(1, ...data.edges.map((e) => e.weight || 1));
    const edgeScale = d3.scaleLinear().domain([1, maxWeight]).range([0.5, 4]);

    const nodes = data.nodes.map((n) => ({ ...n }));
    const edges = data.edges.map((e) => ({ ...e }));

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id((d) => d.id).distance(s.linkDistance).strength(s.linkStrength))
      .force("charge", d3.forceManyBody().strength(s.chargeStrength).distanceMax(s.chargeDistanceMax))
      .force("center", d3.forceCenter(width / 2, height / 2).strength(s.centerStrength))
      .force("collision", d3.forceCollide().radius((d) => sizeScale(d.degree || 1) + s.collisionPadding));

    simulationRef.current = simulation;

    const link = g.append("g")
      .selectAll("line")
      .data(edges)
      .join("line")
      .attr("class", "concept-edge")
      .attr("stroke-width", (d) => edgeScale(d.weight || 1));

    const node = g.append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => sizeScale(d.degree || 1))
      .attr("fill", (d) => colorScale(d.community_id))
      .attr("class", "concept-node")
      .call(makeDrag(simulation));

    node.on("click", (event, d) => {
      event.stopPropagation();
      if (onClickRef.current) onClickRef.current(d);
    });

    // All nodes get labels, visibility controlled by threshold
    const label = g.append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .attr("class", "concept-label")
      .text((d) => d.name)
      .attr("display", (d) => {
        return (d.degree || 0) >= maxDegree * s.labelThreshold || (d.session_count || 0) >= 3 ? null : "none";
      });

    const tooltip = d3.select(container)
      .append("div")
      .attr("class", "concept-tooltip")
      .style("opacity", 0);

    node
      .on("mouseenter", (event, d) => {
        tooltip
          .style("opacity", 1)
          .html(
            `<strong>${d.name}</strong><br/>` +
            `Type: ${d.type || "N/A"}<br/>` +
            `Community: ${d.community_id ?? "N/A"}<br/>` +
            `Sessions: ${d.session_count || 0}`
          )
          .style("left", `${event.offsetX + 12}px`)
          .style("top", `${event.offsetY - 12}px`);
      })
      .on("mouseleave", () => {
        tooltip.style("opacity", 0);
      });

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);

      node
        .attr("cx", (d) => d.x)
        .attr("cy", (d) => d.y);

      label
        .attr("x", (d) => d.x)
        .attr("y", (d) => d.y - sizeScale(d.degree || 1) - 4);
    });

    return () => {
      tooltip.remove();
      cleanup();
    };
    // dataKey is a stable string fingerprint of data; including data itself
    // would re-mount the simulation on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey, cleanup]);

  if (!data || !data.nodes || data.nodes.length === 0) return null;

  return (
    <div className="concept-graph-container" ref={containerRef}>
      <svg ref={svgRef} />
      <button
        className="graph-settings-toggle"
        onClick={() => setShowSettings((v) => !v)}
        title="Graph settings"
      >
        <SettingsCog />
      </button>
      {showSettings && (
        <div className="graph-settings-panel">
          <div className="graph-settings-header">
            <span>Graph Settings</span>
            <button className="graph-settings-reset" onClick={resetSettings}>Reset</button>
          </div>
          {SLIDERS.map((s) => (
            <label key={s.key} className="graph-settings-row">
              <span className="graph-settings-label">{s.label}</span>
              <input
                type="range"
                min={s.min}
                max={s.max}
                step={s.step}
                value={settings[s.key]}
                onChange={(e) => updateSetting(s.key, Number(e.target.value))}
              />
              <span className="graph-settings-value">{settings[s.key]}</span>
            </label>
          ))}
          <label className="graph-settings-row">
            <span className="graph-settings-label">Color Scheme</span>
            <select
              className="graph-settings-select"
              value={settings.colorScheme}
              onChange={(e) => updateSetting("colorScheme", e.target.value)}
            >
              {Object.keys(COLOR_SCHEMES).map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </label>
        </div>
      )}
    </div>
  );
}

function SettingsCog() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor">
      <path d="M11.078 0l.941 2.956a7.3 7.3 0 011.8 1.042l3.032-.716 1.078 1.868-2.09 2.24a7.3 7.3 0 010 2.083l2.09 2.24-1.078 1.868-3.032-.716a7.3 7.3 0 01-1.8 1.042L11.078 17H8.922l-.941-2.956a7.3 7.3 0 01-1.8-1.042l-3.032.716-1.078-1.868 2.09-2.24a7.3 7.3 0 010-2.083l-2.09-2.24 1.078-1.868 3.032.716a7.3 7.3 0 011.8-1.042L8.922 0h2.156zM10 6.5a2 2 0 100 4 2 2 0 000-4z" />
    </svg>
  );
}

export function makeDrag(simulation) {
  return d3.drag()
    .on("start", (event, d) => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (event, d) => {
      d.fx = event.x;
      d.fy = event.y;
    })
    .on("end", (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    });
}
