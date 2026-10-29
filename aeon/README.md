# AEON - Agent-to-Agent Settlement Network for Shared Compute

AEON is a clearing house for AI agents to trade small units of compute with each other and settle money through PayPal sandbox under human-controlled limits.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB Atlas (or local MongoDB)
- PayPal Sandbox accounts (Business treasury + Personal agents)
- Cloudflare Workers AI account (or use replay mode)

### Environment Setup
1. Copy `.env.example` to `.env` and fill in values
2. Install dependencies
3. Run services

### Running Locally
```bash
# Using docker-compose
docker-compose up
```

## Architecture
See [DESIGN.md](./DESIGN.md) and [Project Blueprint](./AEON_Project_Blueprint.pdf) for full details.

## Honesty Notes
- **PayPal**: Sandbox only. No real money movement.
- **Energy prices & regions**: Simulated based on Open-Meteo weather data (labeled in UI).
- **LLM**: Real model outputs via Cloudflare Workers AI (cached/replayed for demo).
- **Jobs**: Real compute jobs (image resize, matrix multiply) with CPU metering.

## License
MIT License - see [LICENSE](./LICENSE)
