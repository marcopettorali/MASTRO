# MOSAIC integration and use case

This package implements the [MASTRO adapter contract](../docs/adapter-contract.md) for
[MOSAIC](https://github.com/marcopettorali/MOSAIC), a distributed pipeline orchestrator across
edge, fog and cloud nodes. All MOSAIC-specific clients, tools, discovery, skills, CLI command
mappings, examples and experiment baselines live here.

## Setup

Install and start MOSAIC **v1.1 or later** following its README. Deploy its runtimes on the nodes
of your testbed, configure the topology and verify that its orchestrator can reach the runtimes.
Then configure the MASTRO integration:

```bash
ORCHESTRATOR_URL=http://127.0.0.1:9000 ./scripts/start.sh
```

The GUI's MCP Gateway panel discovers available nodes from MOSAIC and starts the gateway with
the selected runtimes. **Mock Mode** runs without a live MOSAIC installation. The package also
accepts `MOSAIC_URL` as a legacy alias of `ORCHESTRATOR_URL`.

## Environment variables

| Variable | Meaning |
|----------|---------|
| `ORCHESTRATOR_URL` | Full orchestrator URL; takes precedence over legacy host/port settings |
| `MOSAIC_URL` | Legacy alias, used when `ORCHESTRATOR_URL` is absent |
| `MOSAIC_HOST`, `MOSAIC_GUI_PORT` | Legacy gateway-only host and port, default `localhost:9000` |
| `MOSAIC_RUNTIME_NODES` | Runtime endpoints as `node_id:host:port,...`; supplied by backend discovery in managed mode |
| `MOSAIC_TIMEOUT`, `MOSAIC_RETRIES` | HTTP timeout and retry count |
| `MOSAIC_WRITE_INTERVAL` | Minimum interval between writes, default 5 seconds |
| `MASTRO_MCP_TOOLS` | Optional subset of `monitoring,placement,ops,deploy`; platform management tools remain available |
| `MOSAIC_MCP_TOOLS` | Legacy alias for tool selection |
| `MOCK_MODE`, `DRY_RUN` | Simulated responses; writes logged without execution |
| `MASTRO_URL` | Platform backend for the generic `mastro_mcp_*` management tools |

See [.env.example](.env.example). The example is a reference for exported environment variables;
the gateway does not load `.env` files automatically.

MOSAIC infrastructure tools retain their `mosaic_*` names; platform gateway lifecycle tools use
`mastro_mcp_*`. Skills under `skills/` reference the infrastructure tool names. See [CLI.md](CLI.md)
for the use-case command reference; `--mosaic-url` and `config set-mosaic-url` remain supported
by this adapter as aliases of the generic orchestrator URL settings.

## Experimental applications

Copy the contents of `examples/services/` and `examples/traffic_generators/` into the corresponding
folders of your MOSAIC installation and deploy them through MOSAIC.

| Application | Services | Traffic generator |
|-------------|----------|-------------------|
| Voice | `audio_noise_removal` → `audio_transcription` (Vosk) → `audio_intent` | `tg_audio` |
| Video | `image_preprocessing` → `object_detection_yolo` → `detection_postprocessing` | `tg_video` |

The video detection client uses `object_detection_yolo_server`, a persistent container with the
YOLOv8s model loaded, on the node hosting detection. Set the request rate through MOSAIC's
dashboard or `mastro tg start`.

The image dataset is included in `examples/traffic_generators/tg_video/images/`; its `DATASET.md`
lists the sources. Audio clips and the Vosk model are downloaded separately, following the
`DATASET.md` files in `examples/traffic_generators/tg_audio/wav/` and
`examples/services/audio_transcription/local/model/`.

`baselines/intentcontinuum/` contains the IntentContinuum-style monitor and one-shot LLM
reconfiguration baseline used in the experiments.

[COORDINATOR.md](COORDINATOR.md) contains the use-case procedures for an external coordinator.
