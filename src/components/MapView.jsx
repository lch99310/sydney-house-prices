import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { formatPrice, formatShortDate } from '../utils/formatters'
import 'leaflet/dist/leaflet.css'
import './MapView.css'

// Fix Leaflet default icon issue with Vite
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const TYPE_COLORS = {
  House: '#4f6ef7',
  Unit: '#34d399',
  Townhouse: '#fbbf24',
  Land: '#a78bfa',
  Commercial: '#f87171',
}

// Color scale: green (low) → yellow → red (high)
function priceToColor(price, min, max) {
  if (!price || min === max) return '#4f6ef7'
  const ratio = Math.min(1, Math.max(0, (price - min) / (max - min)))
  if (ratio < 0.5) {
    const r = Math.round(52 + (251 - 52) * ratio * 2)
    const g = Math.round(211 + (191 - 211) * ratio * 2)
    const b = Math.round(153 + (36 - 153) * ratio * 2)
    return `rgb(${r},${g},${b})`
  } else {
    const t = (ratio - 0.5) * 2
    const r = Math.round(251 + (248 - 251) * t)
    const g = Math.round(191 + (113 - 191) * t)
    const b = Math.round(36 + (113 - 36) * t)
    return `rgb(${r},${g},${b})`
  }
}

// Component to recenter map, track zoom level, and create custom panes
function MapController({ selectedSuburb, suburbCentroids, onZoomChange, onSearchLocation }) {
  const map = useMap()

  // Create custom panes for z-index control
  useEffect(() => {
    if (!map.getPane('suburbPane')) {
      const suburbPane = map.createPane('suburbPane')
      suburbPane.style.zIndex = 300
    }
    if (!map.getPane('markerPane')) {
      const markerPane = map.createPane('markerPane')
      markerPane.style.zIndex = 500
    }
  }, [map])

  useMapEvents({
    zoomend() {
      onZoomChange(map.getZoom())
    },
  })

  useEffect(() => {
    if (selectedSuburb && suburbCentroids[selectedSuburb]) {
      const [lat, lng] = suburbCentroids[selectedSuburb]
      map.setView([lat, lng], Math.max(map.getZoom(), 14), { animate: true })
    }
  }, [selectedSuburb, suburbCentroids, map])

  useEffect(() => {
    if (onSearchLocation) {
      map.__flyToSearchLocation = (lat, lng, zoom) => {
        map.setView([lat, lng], zoom || 16, { animate: true })
      }
    }
  }, [map, onSearchLocation])

  return null
}

// Search bar component
function SearchBar({ onSearch, mapRef }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const searchTimeout = useRef(null)

  const handleInputChange = useCallback((e) => {
    const value = e.target.value
    setQuery(value)

    if (searchTimeout.current) clearTimeout(searchTimeout.current)

    if (value.length < 3) {
      setResults([])
      setShowResults(false)
      return
    }

    setIsSearching(true)
    searchTimeout.current = setTimeout(async () => {
      try {
        // Use Nominatim (OpenStreetMap) for geocoding - free, no API key needed
        const response = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(value + ', Sydney, NSW, Australia')}&limit=5&addressdetails=1`
        )
        const data = await response.json()
        setResults(data.map(r => ({
          displayName: r.display_name,
          lat: parseFloat(r.lat),
          lng: parseFloat(r.lon),
          type: r.type,
          suburb: r.address?.suburb || r.address?.city_district || r.address?.town || '',
        })))
        setShowResults(true)
      } catch {
        setResults([])
      } finally {
        setIsSearching(false)
      }
    }, 400)
  }, [])

  const handleSelect = useCallback((result) => {
    setQuery(result.displayName.split(',').slice(0, 2).join(','))
    setShowResults(false)
    onSearch(result)
  }, [onSearch])

  const handleClear = useCallback(() => {
    setQuery('')
    setResults([])
    setShowResults(false)
  }, [])

  return (
    <div className="map-search-bar">
      <div className="search-input-wrapper">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          className="search-input"
          placeholder="Search address or suburb..."
          value={query}
          onChange={handleInputChange}
          onFocus={() => results.length > 0 && setShowResults(true)}
          onBlur={() => setTimeout(() => setShowResults(false), 200)}
        />
        {query && (
          <button className="search-clear-btn" onClick={handleClear}>✕</button>
        )}
        {isSearching && <span className="search-spinner" />}
      </div>

      {showResults && results.length > 0 && (
        <div className="search-results">
          {results.map((r, i) => (
            <button
              key={i}
              className="search-result-item"
              onMouseDown={() => handleSelect(r)}
            >
              <span className="result-name">
                {r.displayName.split(',').slice(0, 3).join(',')}
              </span>
              {r.suburb && <span className="result-suburb">{r.suburb}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MapView({ properties, suburbs, filters, selectedSuburb, onSuburbSelect }) {
  const geoJsonRef = useRef(null)
  const mapContainerRef = useRef(null)
  const [zoomLevel, setZoomLevel] = useState(11)

  // Filter properties based on current filters
  const filteredProperties = useMemo(() => {
    const cutoff = new Date()
    cutoff.setMonth(cutoff.getMonth() - filters.months)

    return properties.filter(p => {
      if (!filters.types.includes(p.type)) return false
      if (new Date(p.date) < cutoff) return false
      if (p.price < filters.minPrice || p.price > filters.maxPrice) return false
      return true
    })
  }, [properties, filters])

  // Compute median price per suburb from filtered properties
  const suburbStats = useMemo(() => {
    const stats = {}

    filteredProperties.forEach(p => {
      const sub = p.suburb.toUpperCase()
      if (!stats[sub]) stats[sub] = { prices: [], count: 0 }
      stats[sub].prices.push(p.price)
      stats[sub].count++
    })

    Object.keys(stats).forEach(sub => {
      const sorted = [...stats[sub].prices].sort((a, b) => a - b)
      const mid = Math.floor(sorted.length / 2)
      stats[sub].median = sorted.length % 2 === 0
        ? (sorted[mid - 1] + sorted[mid]) / 2
        : sorted[mid]
    })

    return stats
  }, [filteredProperties])

  // Extract suburb centroids from GeoJSON for map controller
  const suburbCentroids = useMemo(() => {
    const centroids = {}
    if (!suburbs?.features) return centroids
    suburbs.features.forEach(f => {
      const name = (f.properties?.LOC_NAME || f.properties?.suburb || '').toUpperCase()
      if (!name) return
      try {
        const coords = f.geometry?.coordinates
        if (!coords) return
        const allCoords = []
        const flatten = (arr) => {
          if (typeof arr[0] === 'number') allCoords.push(arr)
          else arr.forEach(flatten)
        }
        flatten(coords)
        if (!allCoords.length) return
        const lngs = allCoords.map(c => c[0])
        const lats = allCoords.map(c => c[1])
        centroids[name] = [
          (Math.min(...lats) + Math.max(...lats)) / 2,
          (Math.min(...lngs) + Math.max(...lngs)) / 2,
        ]
      } catch {
        // skip bad geometry
      }
    })
    return centroids
  }, [suburbs])

  // Compute per-suburb data from property data
  const suburbClusters = useMemo(() => {
    const clusters = {}
    filteredProperties.forEach(p => {
      const sub = p.suburb.toUpperCase()
      if (!clusters[sub]) clusters[sub] = { lats: [], lngs: [], prices: [], count: 0 }
      if (p.lat && p.lng) {
        clusters[sub].lats.push(p.lat)
        clusters[sub].lngs.push(p.lng)
      }
      clusters[sub].prices.push(p.price)
      clusters[sub].count++
    })

    return Object.entries(clusters)
      .filter(([, data]) => data.lats.length > 0)
      .map(([name, data]) => {
        const sorted = [...data.prices].sort((a, b) => a - b)
        const mid = Math.floor(sorted.length / 2)
        const med = sorted.length % 2 === 0
          ? (sorted[mid - 1] + sorted[mid]) / 2
          : sorted[mid]
        return {
          name,
          lat: data.lats.reduce((a, b) => a + b, 0) / data.lats.length,
          lng: data.lngs.reduce((a, b) => a + b, 0) / data.lngs.length,
          count: data.count,
          median: med,
          prices: data.prices,
        }
      })
  }, [filteredProperties])

  // Dynamic clustering: merge nearby suburbs at low zoom to avoid overlapping circles
  const displayClusters = useMemo(() => {
    if (zoomLevel >= 13) return suburbClusters

    // Grid-based spatial clustering: merge suburbs in the same grid cell
    const gridSize = zoomLevel <= 10 ? 0.04 : zoomLevel <= 11 ? 0.02 : 0.012
    const grid = {}

    suburbClusters.forEach(cluster => {
      const key = `${Math.floor(cluster.lat / gridSize)}_${Math.floor(cluster.lng / gridSize)}`
      if (!grid[key]) {
        grid[key] = { lats: [], lngs: [], prices: [], count: 0, names: [] }
      }
      grid[key].lats.push(cluster.lat * cluster.count)
      grid[key].lngs.push(cluster.lng * cluster.count)
      grid[key].prices.push(...cluster.prices)
      grid[key].count += cluster.count
      grid[key].names.push(cluster.name)
    })

    return Object.values(grid).map(g => {
      const sorted = [...g.prices].sort((a, b) => a - b)
      const mid = Math.floor(sorted.length / 2)
      const med = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
      const label = g.names.length === 1
        ? g.names[0]
        : g.names.length <= 3
          ? g.names.join(', ')
          : `${g.names[0]} +${g.names.length - 1}`
      return {
        name: label,
        lat: g.lats.reduce((a, b) => a + b) / g.count,
        lng: g.lngs.reduce((a, b) => a + b) / g.count,
        count: g.count,
        median: med,
        suburbNames: g.names,
      }
    })
  }, [suburbClusters, zoomLevel])

  // Price range for color scale
  const { minPrice, maxPrice } = useMemo(() => {
    const medians = Object.values(suburbStats).map(s => s.median).filter(Boolean)
    if (!medians.length) return { minPrice: 500000, maxPrice: 5000000 }
    return { minPrice: Math.min(...medians), maxPrice: Math.max(...medians) }
  }, [suburbStats])

  // Style each suburb polygon
  const suburbStyle = (feature) => {
    const name = (feature.properties?.LOC_NAME || feature.properties?.suburb || '').toUpperCase()
    const stats = suburbStats[name]
    const isSelected = name === selectedSuburb?.toUpperCase()

    return {
      fillColor: stats ? priceToColor(stats.median, minPrice, maxPrice) : '#2e3350',
      fillOpacity: isSelected ? 0.7 : stats ? 0.5 : 0.15,
      color: isSelected ? '#fff' : stats ? 'rgba(255,255,255,0.3)' : '#2e3350',
      weight: isSelected ? 2.5 : 1,
      pane: 'suburbPane',
    }
  }

  // Attach event handlers to each suburb feature
  function onEachSuburb(feature, layer) {
    const name = (feature.properties?.LOC_NAME || feature.properties?.suburb || '').toUpperCase()
    const stats = suburbStats[name]

    const tooltipContent = stats
      ? `<div class="map-tooltip">
          <strong>${name}</strong>
          <div>Median: ${formatPrice(stats.median)}</div>
          <div>${stats.count} sale${stats.count !== 1 ? 's' : ''}</div>
         </div>`
      : `<div class="map-tooltip"><strong>${name}</strong><div>No data</div></div>`

    layer.bindTooltip(tooltipContent, {
      sticky: true,
      className: 'custom-tooltip',
      offset: [10, 0],
    })

    layer.on({
      mouseover(e) {
        const l = e.target
        if (name !== selectedSuburb?.toUpperCase()) {
          l.setStyle({ fillOpacity: 0.8, weight: 1.5, color: 'rgba(255,255,255,0.6)' })
        }
        l.bringToFront()
      },
      mouseout(e) {
        geoJsonRef.current?.resetStyle(e.target)
      },
      click() {
        if (stats) {
          onSuburbSelect(name)
        }
      },
    })
  }

  // Show property markers when zoomed in enough (zoom >= 14)
  const showPropertyMarkers = zoomLevel >= 14

  // Handle search result selection
  const handleSearchResult = useCallback((result) => {
    // Use global fly-to function set by SearchFlyTo component
    if (window.__sydneyMapFlyTo) {
      window.__sydneyMapFlyTo(result.lat, result.lng, 16)
    }

    // Also try to select suburb if we can match it
    if (result.suburb) {
      const suburbKey = result.suburb.toUpperCase()
      if (suburbStats[suburbKey]) {
        onSuburbSelect(suburbKey)
      }
    }
  }, [suburbStats, onSuburbSelect])

  // Legend labels
  const legendItems = [
    { color: priceToColor(minPrice, minPrice, maxPrice), label: formatPrice(minPrice) },
    { color: priceToColor((minPrice + maxPrice) / 2, minPrice, maxPrice), label: formatPrice((minPrice + maxPrice) / 2) },
    { color: priceToColor(maxPrice, minPrice, maxPrice), label: formatPrice(maxPrice) },
  ]

  return (
    <div className="map-container" ref={mapContainerRef}>
      {/* Search bar */}
      <SearchBar onSearch={handleSearchResult} />

      <MapContainer
        center={[-33.865, 151.209]}
        zoom={11}
        style={{ height: '100%', width: '100%' }}
        zoomControl={true}
        maxZoom={19}
        minZoom={10}
      >
        {/* Dark tile layer */}
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          maxZoom={19}
        />

        {/* Suburb boundaries */}
        {suburbs?.features?.length > 0 && (
          <GeoJSON
            key={`${selectedSuburb}-${JSON.stringify(filters)}`}
            ref={geoJsonRef}
            data={suburbs}
            style={suburbStyle}
            onEachFeature={onEachSuburb}
          />
        )}

        {/* Suburb cluster dots — only show when not zoomed into individual markers */}
        {zoomLevel < 15 && displayClusters.map(cluster => {
          const countRadius = Math.max(5, Math.min(16, 3 + Math.sqrt(cluster.count) * 1.2))
          const zoomScale = zoomLevel <= 12 ? 1 : Math.max(0.4, 1 - (zoomLevel - 12) * 0.15)
          const radius = Math.round(countRadius * zoomScale)
          const isMerged = cluster.suburbNames && cluster.suburbNames.length > 1
          const isSelected = isMerged
            ? cluster.suburbNames?.includes(selectedSuburb?.toUpperCase())
            : cluster.name === selectedSuburb?.toUpperCase()
          return (
            <CircleMarker
              key={`cluster-${cluster.name}-${zoomLevel}`}
              center={[cluster.lat, cluster.lng]}
              radius={isSelected ? radius + 2 : radius}
              fillColor={priceToColor(cluster.median, minPrice, maxPrice)}
              fillOpacity={isSelected ? 0.7 : 0.5}
              color={isSelected ? '#fff' : 'rgba(255,255,255,0.4)'}
              weight={isSelected ? 2 : 1}
              eventHandlers={{
                click: () => {
                  if (isMerged) {
                    onSuburbSelect(cluster.suburbNames[0])
                  } else {
                    onSuburbSelect(cluster.name)
                  }
                },
              }}
            >
              <Tooltip
                className="custom-tooltip"
                offset={[10, 0]}
              >
                <div className="map-tooltip">
                  <strong>{cluster.name}</strong>
                  <div>Median: {formatPrice(cluster.median)}</div>
                  <div>{cluster.count} sale{cluster.count !== 1 ? 's' : ''}</div>
                </div>
              </Tooltip>
            </CircleMarker>
          )
        })}

        {/* Property markers - shown when zoomed in */}
        {showPropertyMarkers && filteredProperties.map(p => {
          if (!p.lat || !p.lng) return null

          return (
            <CircleMarker
              key={p.id}
              center={[p.lat, p.lng]}
              radius={6}
              fillColor={TYPE_COLORS[p.type] || '#4f6ef7'}
              fillOpacity={0.8}
              stroke={true}
              color={TYPE_COLORS[p.type] || '#4f6ef7'}
              weight={1.5}
              opacity={0.5}
              pane="markerPane"
            >
              <Popup className="property-popup" maxWidth={280}>
                <div className="popup-content">
                  <div className="popup-type" style={{ color: TYPE_COLORS[p.type] }}>
                    {p.type}
                  </div>
                  <div className="popup-address">{p.address}</div>
                  <div className="popup-suburb">{p.suburb}</div>
                  <div className="popup-price">{formatPrice(p.price)}</div>
                  <div className="popup-date">{formatShortDate(p.date)}</div>
                  {(p.area || p.zoning) && (
                    <div className="popup-details">
                      {p.area && <span>{p.area.toLocaleString()} m²</span>}
                      {p.zoning && <span>Zone: {p.zoning}</span>}
                    </div>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        <MapController
          selectedSuburb={selectedSuburb}
          suburbCentroids={suburbCentroids}
          onZoomChange={setZoomLevel}
          onSearchLocation={handleSearchResult}
        />

        {/* Map fly-to helper for search */}
        <SearchFlyTo />
      </MapContainer>

      {/* Zoom hint when not zoomed in enough */}
      {!showPropertyMarkers && (
        <div className="zoom-hint">
          Zoom in to see individual properties
        </div>
      )}

      {/* Color legend */}
      <div className="map-legend">
        <div className="legend-title">Median Price</div>
        <div className="legend-gradient">
          <div
            className="legend-bar"
            style={{
              background: `linear-gradient(to right, ${legendItems.map(i => i.color).join(', ')})`,
            }}
          />
          <div className="legend-labels">
            {legendItems.map((item, i) => (
              <span key={i} style={{ color: item.color }}>{item.label}</span>
            ))}
          </div>
        </div>
        <div className="legend-hint">Click a suburb to view details</div>
      </div>

      {/* Transaction count badge */}
      <div className="map-stats-badge">
        <span className="badge-number">{Object.values(suburbStats).reduce((s, v) => s + v.count, 0).toLocaleString()}</span>
        <span className="badge-label">transactions</span>
        <span className="badge-sep">·</span>
        <span className="badge-number">{Object.keys(suburbStats).length}</span>
        <span className="badge-label">suburbs</span>
      </div>
    </div>
  )
}

// Helper component that provides search fly-to via a global function
function SearchFlyTo() {
  const map = useMap()

  useEffect(() => {
    // Store map reference on the container element for search to access
    if (map._container) {
      map._container._leaflet_map = map
    }
  }, [map])

  // Also expose a global function for the search bar
  useEffect(() => {
    window.__sydneyMapFlyTo = (lat, lng, zoom) => {
      map.setView([lat, lng], zoom || 16, { animate: true })
    }
    return () => {
      delete window.__sydneyMapFlyTo
    }
  }, [map])

  return null
}
