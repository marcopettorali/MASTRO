# MASTRO - Frontend

React (Vite) single-page application providing the graphical interface of MASTRO. Infrastructure operations are provided by the replaceable orchestrator adapter.

## Pages

| Page | Description |
|------|-------------|
| **Chat** | Conversation with the agents: natural-language intents, ReAct traces, persistent sessions |
| **Context** | Management of the operational context entries injected into the agents' prompts |
| **MCP Gateway** | Start and stop the MASTRO MCP Gateway, node selection, mock and dry-run modes, process logs |
| **Settings** | Agents and skills, MCP servers, autonomous mode, LLM endpoint, MongoDB, notification webhooks |

## Development

```bash
npm install
npm run dev       # Start the Vite dev server on http://localhost:5174
npm run build     # Production build
```

The frontend connects to the MASTRO backend at `http://localhost:9100`. The API calls are
defined in `src/api/mastro.js`.
