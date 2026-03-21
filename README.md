# Sydney House Prices

Interactive map of property sale prices across Greater Sydney, powered by official NSW Government open data.

**Live:** [https://lch99310.github.io/sydney-house-prices/](https://lch99310.github.io/sydney-house-prices/)

---

## What It Does

- **Colour-coded suburb map** - See median sale prices at a glance across 100+ Sydney suburbs (green = affordable, red = premium)
- **Click any suburb** - Opens a detail panel with median, average, lowest, and highest prices broken down by property type
- **Price trend chart** - Scatter plot with trend lines showing how prices move over time for each property type
- **Transaction list** - Browse every recorded sale with address, price, date, land area, and zoning
- **Filters** - Narrow by property type (House / Unit / Townhouse / Land / Commercial), price range, and time period (3-24 months)
- **Search** - Find any Sydney address or suburb via the search bar
- **Auto-updated weekly** - GitHub Actions fetches new data from NSW Valuer General every Tuesday morning

---

## Data Source

All property sales data comes from the **NSW Valuer General - Property Sales Information (PSI)** portal.

> You can access free bulk NSW Property Sales Information (PSI) from 1990 onwards. Current (2001 to current date) PSI files are generated on a weekly basis for each Local Government Area. These files contain sales data created in the week prior to file creation.
>
> PSI data files are delivered in .DAT file format. They can be imported into most spreadsheet and database programs.
>
> Bulk PSI is available under open access licensing as part of the NSW Government Open Data Policy and is subject to the **Creative Commons BY-NC-ND 4.0 Licence**.
>
> We do not guarantee the completeness or accuracy of the data as bulk PSI is obtained from a variety of sources.
>
> -- *NSW Valuer General, [valuergeneral.nsw.gov.au](https://www.valuergeneral.nsw.gov.au/)*

### Important Notes

- Property positions on the map are **approximate** (suburb centroid with small offset) -- not exact street addresses
- Bedroom and bathroom counts are **not available** from the VG data
- The data pipeline filters for Greater Sydney postcodes and arm's-length residential/commercial sales only
- To verify any individual sale, use the official [NSW VG Sales Enquiry](https://valuation.property.nsw.gov.au/embed/propertySalesInformation)

---

## Built with AI

This entire project -- from concept to deployment -- was developed using **Claude Code** (Anthropic's AI coding agent). The process involved:

1. **Data pipeline design** - Claude analysed the NSW VG PSI .DAT file format (semicolon-delimited, multi-record type with A/B/C/D records) and built a Python pipeline to download, parse, filter, and transform the data
2. **Frontend development** - React app with Leaflet maps, Recharts visualisation, responsive dark theme UI -- all generated through iterative conversation
3. **CI/CD setup** - GitHub Actions workflows for automatic weekly data updates and GitHub Pages deployment
4. **Debugging with real data** - Used actual .DAT file samples to verify column mapping, fix parsing bugs (record type prefix, yearly vs weekly file availability), and validate the full data pipeline

The entire codebase was written, debugged, and refined through natural language prompts to Claude.

---

## Licence

Data is provided by the NSW Valuer General under the [Creative Commons BY-NC-ND 4.0 Licence](https://creativecommons.org/licenses/by-nc-nd/4.0/) as part of the NSW Government Open Data Policy. Code is MIT licensed.
