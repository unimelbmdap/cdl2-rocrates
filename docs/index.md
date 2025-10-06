# RO-Crate Analysis and Visualisation Tools

[![Tests](https://github.com/unimelbmdap/cdl2-rocrates/actions/workflows/test.yml/badge.svg)](https://github.com/unimelbmdap/cdl2-rocrates)
![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![GitHub](https://img.shields.io/badge/GitHub-unimelbmdap%2Fcdl2--rocrates-blue?logo=github)](https://github.com/unimelbmdap/cdl2-rocrates)

## ARDC Community Data Lab Phase 2: Work Package 2

Tools for analysing and visualising research data collections stored in RO-Crates.

## About

RO-Crates offer a powerful format for preserving HASS and GLAM collections with curated metadata and linkage information. While existing tools focus on creating RO-Crates as archival objects, this project unlocks them for active research use.

This project develops accessible tools for researchers to:

- Analyse network relationships and metadata within and across RO-Crates
- Visualise collections interactively, both online and offline
- Understand and work with RO-Crate workflows through documentation and training


## Background

This work builds on existing University of Melbourne projects and external collaborations that have developed specialised RO-Crate tools and workflows, including work derived from former Online Heritage Resource Manager projects.

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linting
uv run ruff check
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
