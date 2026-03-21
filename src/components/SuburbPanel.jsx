import React, { useState, useMemo } from 'react'
import PriceChart from './PriceChart'
import PropertyList from './PropertyList'
import { formatPrice } from '../utils/formatters'
import { median, average } from '../utils/statistics'
import './SuburbPanel.css'

const TABS = ['Chart', 'Properties']

const TYPE_COLORS = {
  House: '#4f6ef7',
  Unit: '#34d399',
  Townhouse: '#fbbf24',
  Land: '#a78bfa',
}

export default function SuburbPanel({ suburb, properties, filters, onClose, onFilterChange }) {
  const [activeTab, setActiveTab] = useState('Chart')
  const [expandedType, setExpandedType] = useState(null)

  const stats = useMemo(() => {
    if (!properties.length) return null
    const prices = properties.map(p => p.price)
    const byType = {}
    properties.forEach(p => {
      if (!byType[p.type]) byType[p.type] = []
      byType[p.type].push(p.price)
    })

    return {
      count: properties.length,
      median: median(prices),
      average: average(prices),
      min: Math.min(...prices),
      max: Math.max(...prices),
      byType: Object.entries(byType).map(([type, ps]) => ({
        type,
        count: ps.length,
        median: median(ps),
        average: average(ps),
        min: Math.min(...ps),
        max: Math.max(...ps),
      })).sort((a, b) => b.count - a.count),
    }
  }, [properties])

  const toggleTypeExpand = (type) => {
    setExpandedType(prev => prev === type ? null : type)
  }

  // Title-case the suburb name
  const displayName = suburb
    .split(' ')
    .map(w => w.charAt(0) + w.slice(1).toLowerCase())
    .join(' ')

  // Get postcode from first property
  const suburbPostcode = properties.length > 0 ? properties[0].postcode : ''

  return (
    <div className="suburb-panel">
      {/* Panel header */}
      <div className="panel-header">
        <div className="panel-title-row">
          <div>
            <h2 className="panel-suburb-name">{displayName}</h2>
            <p className="panel-subtitle">
              {filters.months} month{filters.months !== 1 ? 's' : ''} · {properties.length} transaction{properties.length !== 1 ? 's' : ''}
            </p>
          </div>
          <button className="panel-close-btn" onClick={onClose} title="Close">✕</button>
        </div>

        {/* Stats row - All property types combined */}
        {stats && (
          <>
            <div className="panel-stats-section-label">All Types Combined ({stats.count} transactions)</div>
            <div className="panel-stats-row">
              <div className="stat-card">
                <span className="stat-label">Median</span>
                <span className="stat-value accent">{formatPrice(stats.median)}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Average</span>
                <span className="stat-value">{formatPrice(stats.average)}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Lowest</span>
                <span className="stat-value green">{formatPrice(stats.min)}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Highest</span>
                <span className="stat-value red">{formatPrice(stats.max)}</span>
              </div>
            </div>
          </>
        )}

        {/* Expandable type breakdown */}
        {stats?.byType.length > 0 && (
          <div className="panel-type-row">
            {stats.byType.map(({ type, count, median: med, average: avg, min, max }) => (
              <div key={type} className="type-stat-wrapper">
                <button
                  className={`type-stat-bar ${expandedType === type ? 'expanded' : ''}`}
                  onClick={() => toggleTypeExpand(type)}
                >
                  <span className="type-stat-dot" style={{ background: TYPE_COLORS[type] }} />
                  <span className="type-stat-name">{type}</span>
                  <span className="type-stat-count">{count}</span>
                  <span className="type-stat-median">{formatPrice(med)}</span>
                  <span className={`type-stat-chevron ${expandedType === type ? 'open' : ''}`}>&#9662;</span>
                </button>
                {expandedType === type && (
                  <div className="type-stat-detail">
                    <div className="type-detail-grid">
                      <div className="type-detail-item">
                        <span className="type-detail-label">Median</span>
                        <span className="type-detail-value accent">{formatPrice(med)}</span>
                      </div>
                      <div className="type-detail-item">
                        <span className="type-detail-label">Average</span>
                        <span className="type-detail-value">{formatPrice(avg)}</span>
                      </div>
                      <div className="type-detail-item">
                        <span className="type-detail-label">Lowest</span>
                        <span className="type-detail-value green">{formatPrice(min)}</span>
                      </div>
                      <div className="type-detail-item">
                        <span className="type-detail-label">Highest</span>
                        <span className="type-detail-value red">{formatPrice(max)}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Property search links */}
        <div className="search-links">
          <a
            href={`https://www.domain.com.au/sold-listings/?suburb=${displayName.toLowerCase().replace(/ /g, '-')}-nsw-${suburbPostcode}&ptype=residential`}
            target="_blank"
            rel="noopener noreferrer"
            className="domain-link"
          >
            <span>🔗</span>
            Search on Domain.com.au
            <span className="ext-icon">↗</span>
          </a>
          <a
            href={`https://www.realestate.com.au/sold/in-${displayName.toLowerCase().replace(/ /g, '-')},+nsw+${suburbPostcode}/list-1?activeSort=solddate`}
            target="_blank"
            rel="noopener noreferrer"
            className="domain-link realestate-link"
          >
            <span>🔗</span>
            Search on realestate.com.au
            <span className="ext-icon">↗</span>
          </a>
          <a
            href="https://www.valuergeneral.nsw.gov.au/services/sales-enquiry.htm?execution=e1s2"
            target="_blank"
            rel="noopener noreferrer"
            className="domain-link vg-link"
          >
            <span>🔗</span>
            Verify on NSW Valuer General
            <span className="ext-icon">↗</span>
          </a>
        </div>
      </div>

      {/* Tabs */}
      <div className="panel-tabs">
        {TABS.map(tab => (
          <button
            key={tab}
            className={`panel-tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
            {tab === 'Properties' && properties.length > 0 && (
              <span className="tab-badge">{properties.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="panel-content">
        {activeTab === 'Chart' && (
          <div className="chart-section">
            <div className="section-heading">
              Price History
              <span className="section-hint">Dashed lines = trend</span>
            </div>
            <PriceChart properties={properties} filters={filters} />
          </div>
        )}

        {activeTab === 'Properties' && (
          <PropertyList properties={properties} suburb={displayName} />
        )}
      </div>
    </div>
  )
}
