import React, { useState } from 'react'
import { formatPrice, formatShortDate } from '../utils/formatters'
import './PropertyList.css'

const TYPE_COLORS = {
  House: '#4f6ef7',
  Unit: '#34d399',
  Townhouse: '#fbbf24',
  Land: '#a78bfa',
}

const TYPE_ICONS = {
  House: '🏠',
  Unit: '🏢',
  Townhouse: '🏡',
  Land: '🌱',
}

const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Newest first' },
  { value: 'date_asc', label: 'Oldest first' },
  { value: 'price_desc', label: 'Price: high–low' },
  { value: 'price_asc', label: 'Price: low–high' },
]

export default function PropertyList({ properties, suburb }) {
  const [sort, setSort] = useState('date_desc')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15

  const sorted = [...properties].sort((a, b) => {
    switch (sort) {
      case 'date_desc': return new Date(b.date) - new Date(a.date)
      case 'date_asc':  return new Date(a.date) - new Date(b.date)
      case 'price_desc': return b.price - a.price
      case 'price_asc':  return a.price - b.price
      default: return 0
    }
  })

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleSort = (val) => {
    setSort(val)
    setPage(1)
  }

  if (!properties.length) {
    return (
      <div className="prop-empty">
        <p>No properties found for this suburb and filters.</p>
      </div>
    )
  }

  return (
    <div className="property-list">
      <div className="prop-list-header">
        <span className="prop-count">{properties.length} properties</span>
        <select
          className="prop-sort-select"
          value={sort}
          onChange={e => handleSort(e.target.value)}
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="prop-items">
        {paged.map((p, i) => {
          const suburbSlug = suburb.toLowerCase().replace(/ /g, '-')
          const domainSoldUrl = `https://www.domain.com.au/sold-listings/?suburb=${suburbSlug}-nsw-${p.postcode || ''}&ptype=residential`
          const realestateUrl = `https://www.realestate.com.au/sold/in-${suburbSlug},+nsw+${p.postcode || ''}/list-1?activeSort=solddate`

          return (
            <div key={p.id || i} className="prop-card">
              <div className="prop-card-top">
                <div className="prop-type-badge" style={{ color: TYPE_COLORS[p.type], borderColor: TYPE_COLORS[p.type] + '44' }}>
                  <span>{TYPE_ICONS[p.type]}</span>
                  {p.type}
                </div>
                <span className="prop-date">{formatShortDate(p.date)}</span>
              </div>

              <div className="prop-address">{p.address}</div>

              <div className="prop-price">{formatPrice(p.price)}</div>

              {(p.bedrooms || p.area) && (
                <div className="prop-details">
                  {p.bedrooms && <span>🛏 {p.bedrooms} bed</span>}
                  {p.bathrooms && <span>🚿 {p.bathrooms} bath</span>}
                  {p.area && <span>📐 {p.area.toLocaleString()} m²</span>}
                </div>
              )}

              <div className="prop-links">
                <a
                  href={domainSoldUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="prop-domain-link"
                >
                  Domain.com.au ↗
                </a>
                <span className="prop-link-sep">·</span>
                <a
                  href={realestateUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="prop-domain-link prop-realestate-link"
                >
                  realestate.com.au ↗
                </a>
              </div>
            </div>
          )
        })}
      </div>

      {totalPages > 1 && (
        <div className="prop-pagination">
          <button
            className="page-btn"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            ‹
          </button>
          <span className="page-info">{page} / {totalPages}</span>
          <button
            className="page-btn"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            ›
          </button>
        </div>
      )}
    </div>
  )
}
