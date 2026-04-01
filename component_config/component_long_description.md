# Oracle Hyperion EPM Extractor

Extracts data from Oracle Hyperion Enterprise Performance Management (EPM) into Keboola Storage.

## Supported Modules

### Essbase 21C (Primary)
- Executes MDX queries against Essbase OLAP cubes via the Essbase 21C REST API (port 9010, Basic Auth)
- Supports any application/database/cube combination
- Returns flat tabular output from MDX grid results

### Hyperion Planning
- Exports data slices from Planning applications via the Planning REST API (port 9000)
- Authenticates using CSS SSO token flow

## Prerequisites

- Oracle Hyperion EPM server with Essbase 21C deployed (on-premise or cloud VM)
- Network access from Keboola to the Essbase REST API port (default 9010) and/or Planning port (9000)
- Valid Shared Services (CSS) credentials

## Configuration

Authentication is configured at the component level (shared across all rows). Each configuration row defines one extraction — module type, application, query, and output table name.
