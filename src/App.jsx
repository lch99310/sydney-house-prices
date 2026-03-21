import React, { useState, useCallback } from 'react'
import MapView from './components/MapView'
import FilterBar from './components/FilterBar'
import SuburbPanel from './components/SuburbPanel'
import { usePropertyData } from './hooks/usePropertyData'
import './App.css'

export default function App() {
  const [selectedSuburb, setSelectedSuburb] = useState(null)
  const [filters, setFilters] = useState({
    types: ['House', 'Unit', 'Townhouse', 'Land'],
    minPrice: 0,
    maxPrice: Infinity,
    months: 12,
  })

  const { properties, suburbs, lastUpdated, dataNote, loading, error } = usePropertyData()

  const handleSuburbSelect = useCallback((suburb) => {
    setSelectedSuburb(suburb)
  }, [])

  const handleFilterChange = useCallback((newFilters) => {
    setFilters(f => ({ ...f, ...newFilters }))
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedSuburb(null)
  }, [])

  // Filter properties for selected suburb
  const suburbProperties = React.useMemo(() => {
    if (!selectedSuburb || !properties.length) return []
    const cutoff = new Date()
    cutoff.setMonth(cutoff.getMonth() - filters.months)

    return properties.filter(p => {
      const matchSuburb = p.suburb.toUpperCase() === selectedSuburb.toUpperCase()
      const matchType = filters.types.includes(p.type)
      const matchPrice = p.price >= filters.minPrice && p.price <= filters.maxPrice
      const matchDate = new Date(p.date) >= cutoff
      return matchSuburb && matchType && matchPrice && matchDate
    })
  }, [selectedSuburb, properties, filters])

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <span className="header-logo">🏠</span>
          <h1 className="header-title">Sydney House Prices</h1>
          <span className="header-subtitle">NSW Property Sales Data</span>
        </div>
        <div className="header-right">
          {lastUpdated && (
            <span className="last-updated">
              Updated: {lastUpdated}
            </span>
          )}
          <a
            href="https://www.valuergeneral.nsw.gov.au/land_values/land_value_summaries/property-sales-information"
            target="_blank"
            rel="noopener noreferrer"
            className="data-source-link"
          >
            Source: NSW Valuer General
          </a>
        </div>
      </header>

      {/* Data disclaimer */}
      <div className="data-disclaimer">
        <span className="disclaimer-icon">&#9432;</span>
        <span>
          Data sourced from <a href="https://www.valuergeneral.nsw.gov.au/services/sales-enquiry.htm?execution=e1s2" target="_blank" rel="noopener noreferrer">NSW Valuer General</a>.
          Prices, bedroom/bathroom counts, and property details are approximate and may not reflect exact records.
          Verify via <a href="https://www.valuergeneral.nsw.gov.au/services/sales-enquiry.htm?execution=e1s2" target="_blank" rel="noopener noreferrer">official NSW VG sales enquiry</a> for accuracy.
        </span>
      </div>

      {/* Filter Bar */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} />

      {/* Main content */}
      <div className="app-body">
        {loading && (
          <div className="loading-overlay">
            <div className="loading-spinner" />
            <p>Loading property data…</p>
          </div>
        )}
        {error && (
          <div className="error-banner">
            ⚠️ {error}
          </div>
        )}

        {/* Map */}
        <div className={`map-wrapper ${selectedSuburb ? 'with-panel' : ''}`}>
          <MapView
            properties={properties}
            suburbs={suburbs}
            filters={filters}
            selectedSuburb={selectedSuburb}
            onSuburbSelect={handleSuburbSelect}
          />
        </div>

        {/* Sidebar Panel */}
        {selectedSuburb && (
          <SuburbPanel
            suburb={selectedSuburb}
            properties={suburbProperties}
            filters={filters}
            onClose={handleClosePanel}
            onFilterChange={handleFilterChange}
          />
        )}
      </div>
    </div>
  )
}
