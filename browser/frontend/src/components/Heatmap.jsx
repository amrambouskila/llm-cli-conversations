import { useMemo, useState } from "react";

const CELL_SIZE = 13;
const CELL_GAP = 2;
const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];
const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function Heatmap({ data }) {
  const [tooltip, setTooltip] = useState(null);

  const { grid, months, maxCost } = useMemo(() => {
    if (!data || data.length === 0) return { grid: [], months: [], maxCost: 0 };

    const dataMap = {};
    let maxC = 0;
    for (const d of data) {
      dataMap[d.date] = d;
      if (d.cost > maxC) maxC = d.cost;
    }

    const today = new Date();
    const cells = [];
    const monthMarkers = [];
    let lastMonth = -1;

    // Build 365 days, ending today
    const startDate = new Date(today);
    startDate.setDate(startDate.getDate() - 364);

    // Align to start of week (Sunday)
    const dayOfWeek = startDate.getDay();
    startDate.setDate(startDate.getDate() - dayOfWeek);

    const totalDays = Math.ceil((today - startDate) / (1000 * 60 * 60 * 24)) + 1;
    const totalWeeks = Math.ceil(totalDays / 7);

    for (let w = 0; w < totalWeeks; w++) {
      for (let d = 0; d < 7; d++) {
        const cellDate = new Date(startDate);
        cellDate.setDate(cellDate.getDate() + w * 7 + d);
        if (cellDate > today) continue;

        const dateStr = cellDate.toISOString().slice(0, 10);
        const entry = dataMap[dateStr];

        if (cellDate.getMonth() !== lastMonth) {
          lastMonth = cellDate.getMonth();
          monthMarkers.push({ label: MONTH_LABELS[lastMonth], week: w });
        }

        cells.push({
          x: w,
          y: d,
          date: dateStr,
          sessions: entry ? entry.sessions : 0,
          cost: entry ? entry.cost : 0,
        });
      }
    }

    return { grid: cells, months: monthMarkers, maxCost: maxC };
  }, [data]);

  if (!data || data.length === 0) return null;

  const totalWeeks = Math.max(1, ...grid.map((c) => c.x)) + 1;
  const svgWidth = 30 + totalWeeks * (CELL_SIZE + CELL_GAP);
  const svgHeight = 20 + 7 * (CELL_SIZE + CELL_GAP);

  return (
    <div className="heatmap-container">
      <div className="heatmap-scroll">
        <svg width={svgWidth} height={svgHeight}>
          {/* Day labels */}
          {DAY_LABELS.map((label, i) =>
            label ? (
              <text
                key={i}
                x={10}
                y={20 + i * (CELL_SIZE + CELL_GAP) + CELL_SIZE * 0.8}
                className="heatmap-day-label"
              >
                {label}
              </text>
            ) : null
          )}
          {/* Month labels */}
          {months.map((m, i) => (
            <text
              key={i}
              x={30 + m.week * (CELL_SIZE + CELL_GAP)}
              y={12}
              className="heatmap-month-label"
            >
              {m.label}
            </text>
          ))}
          {/* Cells */}
          {grid.map((cell, i) => (
            <rect
              key={i}
              x={30 + cell.x * (CELL_SIZE + CELL_GAP)}
              y={20 + cell.y * (CELL_SIZE + CELL_GAP)}
              width={CELL_SIZE}
              height={CELL_SIZE}
              rx={2}
              className={`heatmap-cell heatmap-level-${getLevel(cell.cost, maxCost)}`}
              onMouseEnter={(e) => {
                const rect = e.target.getBoundingClientRect();
                setTooltip({
                  x: rect.left + rect.width / 2,
                  y: rect.top,
                  date: cell.date,
                  sessions: cell.sessions,
                  cost: cell.cost,
                });
              }}
              onMouseLeave={() => setTooltip(null)}
            />
          ))}
        </svg>
      </div>
      {/* Legend */}
      <div className="heatmap-legend">
        <span>Less</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <div key={level} className={`heatmap-legend-cell heatmap-level-${level}`} />
        ))}
        <span>More</span>
      </div>
      {/* Tooltip */}
      {tooltip && (
        <div
          className="heatmap-tooltip"
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y - 40,
            transform: "translateX(-50%)",
          }}
        >
          <strong>{tooltip.date}</strong>: {tooltip.sessions} session{tooltip.sessions !== 1 ? "s" : ""}, ${tooltip.cost.toFixed(2)}
        </div>
      )}
    </div>
  );
}

function getLevel(cost, maxCost) {
  if (cost === 0 || maxCost === 0) return 0;
  const ratio = cost / maxCost;
  if (ratio < 0.15) return 1;
  if (ratio < 0.4) return 2;
  if (ratio < 0.7) return 3;
  return 4;
}
