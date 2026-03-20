import { useState } from "react";

type TabKey = "formulas" | "figures" | "charts";

const tabs: { key: TabKey; label: string }[] = [
  { key: "formulas", label: "Formulas" },
  { key: "figures", label: "Figures" },
  { key: "charts", label: "Charts" },
];

const insightData: Record<TabKey, { title: string; description: string }[]> = {
  formulas: [
    {
      title: "Attention Complexity",
      description: "O(n · (w + k)) — Combined local windowed and global summary attention complexity, linear in sequence length.",
    },
    {
      title: "Self-Attention",
      description: "Attention(Q, K, V) = softmax(QKᵀ / √dₖ) · V — Standard scaled dot-product attention formulation.",
    },
    {
      title: "Window Partitioning",
      description: "O(n · w) — Local windowed attention complexity for n tokens with window size w.",
    },
  ],
  figures: [
    {
      title: "Architecture Overview",
      description: "Figure 1: Hierarchical attention mechanism with local windows and global summary tokens.",
    },
    {
      title: "Attention Patterns",
      description: "Figure 3: Visualization of learned attention patterns showing locality bias across layers.",
    },
  ],
  charts: [
    {
      title: "Performance vs. FLOPs",
      description: "Chart 1: Trade-off between computational cost and benchmark accuracy across model variants.",
    },
    {
      title: "Scaling Behavior",
      description: "Chart 2: Memory consumption scaling — linear (ours) vs. quadratic (baseline) with sequence length.",
    },
  ],
};

const InsightExtractor = () => {
  const [activeTab, setActiveTab] = useState<TabKey>("formulas");

  return (
    <div className="mb-6">
      <h3 className="font-ui text-xs font-medium uppercase tracking-[0.15em] text-text-secondary mb-4">
        Insight Extractor
      </h3>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              font-ui text-[12px] py-1.5 px-3 rounded-sm transition-all duration-200
              ${activeTab === tab.key
                ? "bg-primary text-primary-foreground font-medium"
                : "text-text-secondary hover:text-foreground"
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Cards */}
      <div className="space-y-2">
        {insightData[activeTab].map((item, i) => (
          <div
            key={i}
            className="p-3 rounded-sm bg-canvas animate-fade-in"
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <h4 className="font-ui text-[13px] font-medium text-foreground mb-1">
              {item.title}
            </h4>
            <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
              {item.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default InsightExtractor;
