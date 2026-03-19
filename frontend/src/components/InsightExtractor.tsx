import { useState } from 'react'
import type { PaperImage, PaperTable } from '@/types/api'

type TabKey = 'formulas' | 'figures' | 'charts'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'formulas', label: 'Formulas' },
  { key: 'figures', label: 'Figures' },
  { key: 'charts', label: 'Charts' },
]

interface InsightExtractorProps {
  images: PaperImage[]
  tables: PaperTable[]
}

const staticFormulaCards = [
  {
    title: 'Formula Storage Ready',
    description:
      'Formula support can be added as a new table + section link with the same pattern used for images/tables/text blocks.',
  },
  {
    title: 'Extensible Schema',
    description:
      'Current pipeline stores extracted elements in structured JSON, making formula ingestion straightforward.',
  },
]

const InsightExtractor = ({ images, tables }: InsightExtractorProps) => {
  const insightData: Record<TabKey, { title: string; description: string }[]> =
    {
      formulas: [...staticFormulaCards],
      figures: images.length
        ? images.slice(0, 8).map((img, idx) => ({
            title: `Figure ${idx + 1} · Page ${img.page_number ?? '?'}`,
            description: img.caption || img.image_path || 'Stored image asset',
          }))
        : [
            {
              title: 'No figures',
              description: 'No stored figures for this paper.',
            },
          ],
      charts: tables.length
        ? tables.slice(0, 8).map((table, idx) => ({
            title: `Table ${idx + 1} · Page ${table.page_number ?? '?'}`,
            description:
              table.text_content ||
              table.markdown_content ||
              'Stored table data',
          }))
        : [
            {
              title: 'No tables',
              description: 'No stored tables for this paper.',
            },
          ],
    }

  const [activeTab, setActiveTab] = useState<TabKey>('formulas')

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
              ${
                activeTab === tab.key
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'text-text-secondary hover:text-foreground'
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
  )
}

export default InsightExtractor
