Oracle Hyperion EPM Extractor
==============================

Extracts data from Oracle Hyperion Enterprise Performance Management (EPM) into Keboola Storage.
Supports two modules: **Essbase 21C** OLAP cubes via MDX queries, and **Hyperion Planning** data slice exports.

**Table of Contents:**

[TOC]

Prerequisites
=============

- Oracle Hyperion EPM server with Essbase 21C and/or Hyperion Planning deployed (on-premise or cloud VM)
- Network access from Keboola to the Essbase REST API port (default **9010**) and/or Planning REST API port (default **9000**)
- Valid Oracle Shared Services (CSS) credentials

Features
========

| **Feature**             | **Notes**                                                       |
|-------------------------|-----------------------------------------------------------------|
| Generic UI Form         | Dynamic UI form with async dropdowns for applications/databases |
| Row-Based Configuration | Each row defines one independent extraction query               |
| Essbase 21C MDX         | Execute any MDX SELECT against Essbase OLAP cubes               |
| Hyperion Planning       | Export data slices from Planning plan types                     |
| Sync Actions            | Load available applications and databases directly in UI        |

Supported Modules
=================

### Essbase 21C

Connects to the Essbase 21C REST API (Basic Auth, default port 9010). Each row executes one MDX query against a specified application and database (cube) and writes the result to a flat CSV table in Keboola Storage.

### Hyperion Planning

Connects to the Hyperion Planning REST API (CSS SSO token auth, default port 9000). Each row exports a data slice from a specified application and plan type.

Configuration
=============

### Connection Settings (component level)

These settings are shared across all extraction rows.

| **Parameter**        | **Title**                | **Required** | **Default**        | **Description**                                                                 |
|----------------------|--------------------------|--------------|--------------------|---------------------------------------------------------------------------------|
| `hyperion_url`       | Hyperion Server URL      | Yes          | —                  | Base URL of the Hyperion EPM server including port (e.g. `http://hyperiondev:9000`) |
| `username`           | Username                 | Yes          | —                  | Shared Services (CSS) username                                                  |
| `#password`          | Password                 | Yes          | —                  | CSS password (stored encrypted)                                                 |
| `essbase_host`       | Essbase Host             | No           | Host from URL      | Essbase hostname or IP; falls back to the host parsed from `hyperion_url`       |
| `essbase_port`       | Essbase REST API Port    | No           | `9010`             | Port for the Essbase 21C REST API                                               |
| `ssl_verify`         | Verify SSL Certificate   | No           | `true`             | Disable to allow self-signed certificates                                       |
| `debug`              | Debug Mode               | No           | `false`            | Enables verbose DEBUG logging                                                   |

### Extraction Row Settings (row level)

Each configuration row defines one extraction. Rows can be individually enabled or disabled.

| **Parameter**   | **Title**            | **Required**             | **Description**                                                                              |
|-----------------|----------------------|--------------------------|----------------------------------------------------------------------------------------------|
| `module`        | Module               | Yes                      | `essbase` or `planning`                                                                      |
| `application`   | Application          | Yes                      | Essbase or Planning application name. A dropdown is loaded via the `listApplications` action |
| `database`      | Database / Cube      | For Essbase              | Essbase database (cube) name. A dropdown is loaded via the `listDatabases` action            |
| `mdx_query`     | MDX Query            | For Essbase; optional for Planning | MDX `SELECT` statement for data extraction                                       |
| `plan_type`     | Plan Type            | For Planning             | Plan type name for data export                                                               |
| `output_table`  | Output Table Name    | Yes                      | Name of the output table in Keboola Storage (without `.csv` extension)                       |

Output
======

Each extraction row produces one table in Keboola Storage under the name specified in `output_table`.

**Essbase output:** Columns are derived from the MDX result grid — row dimension name(s) followed by column member names. Each data row maps one row member to its values across all column members.

**Planning output:** Columns correspond to the `headers` returned by the Planning `exportdataslice` endpoint.

All tables are written in full (non-incremental) mode.

Development
-----------

Clone this repository and run the component locally:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
git clone <repo-url> keboola.ex-oracle-hyperion
cd keboola.ex-oracle-hyperion
docker-compose build
docker-compose run --rm dev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the test suite:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose run --rm test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration
===========

For details about deployment and integration with Keboola, refer to the
[deployment section of the developer documentation](https://developers.keboola.com/extend/component/deployment/).
