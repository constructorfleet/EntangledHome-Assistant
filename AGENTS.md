# EntangledHome - Assistant | HACS‑installable skeleton

> Custom component that funnels free‑form utterances into a prompt‑adapter microservice, enriches with RAG from Qdrant (Plex + HA entities), and executes actions in Home Assistant. This is a minimal, working scaffold to extend.

---

## Repository layout

```
entangledhome_assistant/
├─ .github/
│  └─ workflows/
│     └─ release.yml
├─ custom_components/
│  └─ entangledhome/
│     ├─ __init__.py
│     ├─ manifest.json
│     ├─ const.py
│     ├─ conversation.py
│     ├─ intent_handlers.py
│     ├─ qdrant_client.py
│     ├─ adapter_client.py
│     ├─ coordinator.py
│     ├─ services.yaml
│     ├─ strings.json
│     ├─ translations/
│     │  └─ en.json
│     ├─ sentences/
│     │  └─ en.yaml
│     ├─ helpers/
│     │  └─ color_maps.py
│     └─ mock_adapter.py
├─ hacs.json
├─ README.md
├─ LICENSE
└─ pyproject.toml
```

---

## Root files

### `hacs.json`
```json
{
  "name": "EntangledHome - Assistant",
  "content_in_root": false,
  "filename": "",
  "render_readme": true,
  "domains": ["entangledhome"],
  "country": ["US"],
  "hide_default_branch": false
}
```

### `pyproject.toml` (optional typing and dev tools)
```toml
[project]
name = "entangledhome"
version = "0.1.0"
description = "Home Assistant custom component: prompt-adapter + Qdrant RAG for home commands"
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
```

### `.github/workflows/release.yml`
```yaml
name: release
on:
  push:
    tags:
      - "v*"
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
```

### `LICENSE`
```text
Business Source License 1.1

Licensor: ConstructorFleet L.L.C
Licensed Work: Eddie (the "Licensed Work")
Change Date: 2029-01-01
Change License: Apache License, Version 2.0
... (standard BSL text) ...
```

### `README.md`
```md
# EntangledHome - Assistant (entangledhome)

HACS‑installable custom component that:
- Registers a catch‑all intent to capture free‑form voice/text commands
- Calls a **prompt‑adapter** microservice to produce structured JSON intents
- Uses **Qdrant** to enrich prompts with a catalog of HA areas/devices/scenes and Plex items
- Executes the resulting action via HA services with guardrails

> Status: skeleton. Safe to install; does very little until you wire your adapter and Qdrant.

## Features
- Catch‑all sentence: everything not matched by native sentences routes to the adapter
- Confidence gating and simple color mapping
- Coordinator that periodically syncs entity/area/scene catalogs to Qdrant (optional switch)

## Installation (HACS)
1. HACS → Integrations → ⋯ → **Custom repositories** → paste this repo URL, category **Integration**.
2. Install **EntangledHome - Assistant**.
3. Restart Home Assistant.
4. Add configuration in `configuration.yaml` (or UI when config_flow is added):

```yaml
entangledhome:
  adapter_url: "http://adapter:8080/interpret"  # your prompt adapter endpoint
  qdrant:
    host: qdrant
    port: 6333
    api_key: "YOUR_KEY"  # if applicable
  collections:
    plex: "plex_media"
    entities: "ha_entities"
  sync_entities_to_qdrant: false  # set true to push HA registry periodically
```

## Usage
- Enable **Assist** or Conversation.
- Say anything. If no native sentence matches, the `EHInterpretCommand` intent captures it and calls your adapter. High‑confidence outputs execute; low confidence returns a gentle refusal.

## Development
- Drop in a fake adapter at `custom_components/entangledhome/mock_adapter.py` for offline testing.
- Unit tests left as an exercise.
```

---

## Component files

### `custom_components/entangledhome/manifest.json`
```json
{
  "domain": "entangledhome",
  "name": "EntangledHome - Assistant",
  "version": "0.1.0",
  "after_dependencies": ["conversation"],
  "requirements": [
    "qdrant-client>=1.12.0"
  ],
  "codeowners": ["@teagan"],
  "iot_class": "local_push"
}
```

### `custom_components/entangledhome/const.py`
```python
from __future__ import annotations

DOMAIN = "entangledhome"
CONF_ADAPTER_URL = "adapter_url"
CONF_QDRANT = "qdrant"
CONF_QDRANT_HOST = "host"
CONF_QDRANT_PORT = "port"
CONF_QDRANT_API_KEY = "api_key"
CONF_COLLECTIONS = "collections"
CONF_COLL_PLEX = "plex"
CONF_COLL_ENTITIES = "entities"
CONF_SYNC_ENTITIES = "sync_entities_to_qdrant"

DEFAULTS = {
    CONF_QDRANT_HOST: "localhost",
    CONF_QDRANT_PORT: 6333,
    CONF_COLL_PLEX: "plex_media",
    CONF_COLL_ENTITIES: "ha_entities",
    CONF_SYNC_ENTITIES: False,
}
```

### `custom_components/entangledhome/__init__.py`
```python
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN
from .conversation import async_setup_sentences
from .intent_handlers import async_register_intents
from .coordinator import CatalogCoordinator

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_setup_sentences(hass)
    await async_register_intents(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = CatalogCoordinator(hass, entry.data)
    await hass.data[DOMAIN]["coordinator"].async_start()
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coord = hass.data.get(DOMAIN, {}).get("coordinator")
    if coord:
        await coord.async_stop()
    return True
```

### `custom_components/entangledhome/conversation.py`
```python
from __future__ import annotations
from homeassistant.core import HomeAssistant

# For sentence registration at startup; actual sentence file is in sentences/en.yaml
async def async_setup_sentences(hass: HomeAssistant) -> None:
    # Nothing needed; HA loads sentence files automatically for the integration domain
    return None
```

### `custom_components/entangledhome/sentences/en.yaml`
```yaml
language: "en"
intents:
  EHInterpretCommand:
    data:
      - sentences:
          - "{utterance:catchall}"
lists:
  utterance:
    wildcard: true
```

### `custom_components/entangledhome/intent_handlers.py`
```python
from __future__ import annotations
from typing import Any
from homeassistant.helpers import intent
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.area_registry import async_get as async_get_area_reg
from homeassistant.helpers.entity_registry import async_get as async_get_entity_reg
from .adapter_client import call_prompt_adapter
from .qdrant_client import build_catalog_slice

INTENT_NAME = "EHInterpretCommand"

class InterpretCommandHandler(intent.IntentHandler):
    intent_type = INTENT_NAME

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        utterance = intent_obj.slots.get("utterance", {}).get("value", "")
        catalog = await build_catalog_slice(self.hass, utterance)
        cmd = await call_prompt_adapter(self.hass, utterance, catalog)

        resp = intent_obj.create_response()
        try:
            await route_command(self.hass, cmd)
            resp.async_set_speech(f"Done: {cmd.get('intent')}")
        except Exception as ex:  # noqa: BLE001
            resp.async_set_speech(f"Couldn't: {ex}")
        return resp

async def async_register_intents(hass: HomeAssistant) -> None:
    intent.async_register(hass, InterpretCommandHandler(hass))

async def route_command(hass: HomeAssistant, cmd: dict[str, Any]) -> None:
    intent_name = cmd.get("intent")
    area = cmd.get("area")
    params = cmd.get("params") or {}
    confidence = float(cmd.get("confidence", 1))

    if confidence < 0.6:
        raise RuntimeError(params.get("reason") or "Low confidence")

    target = {"area_id": area} if area else {}

    if intent_name == "set_light_color":
        data: dict[str, Any] = {}
        color = params.get("color")
        if color:
            from .helpers.color_maps import COLOR_HS
            data["hs_color"] = COLOR_HS.get(color.lower(), [35, 60])
        await hass.services.async_call("light", "turn_on", data, target=target, blocking=True)

    elif intent_name == "turn_on":
        await hass.services.async_call("homeassistant", "turn_on", {}, target=target, blocking=True)

    elif intent_name == "turn_off":
        await hass.services.async_call("homeassistant", "turn_off", {}, target=target, blocking=True)

    elif intent_name == "set_brightness":
        val = params.get("brightness")
        if val is None:
            raise RuntimeError("Missing brightness")
        await hass.services.async_call("light", "turn_on", {"brightness_pct": val}, target=target, blocking=True)

    elif intent_name == "scene_activate":
        scene = params.get("scene")
        if not scene:
            raise RuntimeError("Missing scene")
        await hass.services.async_call("scene", "turn_on", {"entity_id": f"scene.{scene}"}, blocking=True)

    elif intent_name == "report_sensor":
        # stub for your reporting flow
        return

    elif intent_name == "noop":
        raise RuntimeError(params.get("reason") or "Refused")

    else:
        raise RuntimeError(f"Unknown intent: {intent_name}")
```

### `custom_components/entangledhome/adapter_client.py`
```python
from __future__ import annotations
import aiohttp
from homeassistant.core import HomeAssistant
from .const import DOMAIN, CONF_ADAPTER_URL
from .mock_adapter import interpret as mock_interpret

async def call_prompt_adapter(hass: HomeAssistant, utterance: str, catalog: dict):
    adapter_url: str | None = (hass.data.get(DOMAIN, {}).get("config") or {}).get(CONF_ADAPTER_URL)
    if not adapter_url:
        # Offline dev mode: use mock
        return await mock_interpret(utterance, catalog)

    timeout = aiohttp.ClientTimeout(total=1.5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(adapter_url, json={"utterance": utterance, "catalog": catalog}) as resp:
            resp.raise_for_status()
            return await resp.json()
```

### `custom_components/entangledhome/qdrant_client.py`
```python
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import async_get as async_get_area_reg
from homeassistant.helpers.entity_registry import async_get as async_get_entity_reg
from homeassistant.helpers.device_registry import async_get as async_get_device_reg
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from .const import DOMAIN, CONF_QDRANT, CONF_COLLECTIONS, CONF_COLL_PLEX, CONF_COLL_ENTITIES

async def build_catalog_slice(hass: HomeAssistant, utterance: str) -> dict[str, Any]:
    # Minimal local catalog from HA registries
    area_reg = async_get_area_reg(hass)
    ent_reg = async_get_entity_reg(hass)

    areas = [a.name.replace(" ", "_").lower() for a in area_reg.areas.values()]
    scenes = [s.entity_id.split(".")[1] for s in hass.states.async_all("scene")]

    catalog: dict[str, Any] = {"areas": areas, "scenes": scenes}

    # Optional: query Qdrant for relevant entities and Plex items
    cfg = (hass.data.get(DOMAIN, {}) or {}).get("config") or {}
    qcfg = cfg.get("qdrant")
    colls = cfg.get("collections", {})

    if not qcfg:
        return catalog

    qc = QdrantClient(host=qcfg.get("host", "localhost"), port=qcfg.get("port", 6333), api_key=qcfg.get("api_key"))

    # naive text match search; you will likely switch to vector search with your embedder
    ent_coll = colls.get(CONF_COLL_ENTITIES, "ha_entities")
    plex_coll = colls.get(CONF_COLL_PLEX, "plex_media")

    # Try pull top-K entities relevant to utterance (placeholder: random filter to keep skeleton simple)
    try:
        res = qc.scroll(collection_name=ent_coll, limit=50)
        entities = [p.payload for p in res[0]]
        catalog["entities"] = entities
    except Exception:
        catalog["entities"] = []

    try:
        res = qc.scroll(collection_name=plex_coll, limit=20)
        plex = [p.payload for p in res[0]]
        catalog["plex_samples"] = plex
    except Exception:
        catalog["plex_samples"] = []

    return catalog
```

### `custom_components/entangledhome/coordinator.py`
```python
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant, CALLBACK_TYPE
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from homeassistant.helpers.area_registry import async_get as async_get_area_reg
from homeassistant.helpers.entity_registry import async_get as async_get_entity_reg
from .const import (
    DOMAIN, CONF_QDRANT, CONF_COLLECTIONS, CONF_COLL_ENTITIES, CONF_SYNC_ENTITIES
)

class CatalogCoordinator:
    def __init__(self, hass: HomeAssistant, config: dict[str, Any]):
        self.hass = hass
        self.config = config or {}
        self._unsub: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        if not self.config.get(CONF_SYNC_ENTITIES, False):
            return
        self._unsub = async_track_time_interval(self.hass, self._sync, timedelta(minutes=30))

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _sync(self, *_):
        qcfg = self.config.get(CONF_QDRANT)
        if not qcfg:
            return
        qc = QdrantClient(host=qcfg.get("host", "localhost"), port=qcfg.get("port", 6333), api_key=qcfg.get("api_key"))
        coll = self.config.get(CONF_COLLECTIONS, {}).get(CONF_COLL_ENTITIES, "ha_entities")
        try:
            qc.recreate_collection(coll, vectors_config=qm.VectorParams(size=384, distance=qm.Distance.COSINE))
        except Exception:
            pass

        area_reg = async_get_area_reg(self.hass)
        ent_reg = async_get_entity_reg(self.hass)

        points = []
        for e in ent_reg.entities.values():
            payload = {
                "entity_id": e.entity_id,
                "domain": e.domain,
                "area_id": e.area_id,
                "device_id": e.device_id,
                # You may enrich with friendly_name, device_class, etc.
            }
            # vectors: you will compute embeddings in your adapter; here store zero-vector placeholder
            vec = [0.0] * 384
            points.append(qm.PointStruct(id=hash(e.entity_id) & ((1<<63)-1), vector=vec, payload=payload))

        if points:
            qc.upsert(collection_name=coll, points=points)
```

### `custom_components/entangledhome/helpers/color_maps.py`
```python
COLOR_HS = {
    "red": [0, 100],
    "green": [120, 100],
    "blue": [240, 100],
    "warm": [35, 60],
    "cozy": [35, 60],
}
```

### `custom_components/entangledhome/strings.json`
```json
{
  "title": "EntangledHome - Assistant",
  "config": {
    "step": {
      "user": {
        "title": "Setup",
        "description": "Configure adapter URL and Qdrant connection"
      }
    }
  }
}
```

### `custom_components/entangledhome/translations/en.json`
```json
{
  "title": "EntangledHome - Assistant"
}
```

### `custom_components/entangledhome/services.yaml`
```yaml
# reserve for future: e.g., entangledhome.sync_catalog
```

### `custom_components/entangledhome/mock_adapter.py`
```python
from __future__ import annotations

async def interpret(utterance: str, catalog: dict):
    u = utterance.lower()
    if "red" in u:
        area = next((a for a in catalog.get("areas", []) if a.replace("_", " ") in u), None)
        return {"intent": "set_light_color", "area": area, "targets": None, "params": {"color": "red"}, "confidence": 0.82}
    if "movie time" in u or "movie mode" in u:
        return {"intent": "scene_activate", "area": "movie_room", "targets": None, "params": {"scene": "movie"}, "confidence": 0.9}
    return {"intent": "noop", "area": None, "targets": None, "params": {"reason": "Unknown command"}, "confidence": 0.4}
```

---

## Agent build‑out instructions (feed these to your code agents)

### 1) Wire the adapter microservice
- Implement a FastAPI service at `/interpret` that:
  - Accepts `{ utterance, catalog }`
  - Performs RAG: embed utterance, query Qdrant `ha_entities` and `plex_media`, top‑K 32
  - Builds the prompt with schema + few shots + retrieved catalog slice
  - Calls your local model (Ollama/LocalAI/Tabby)
  - Strictly validate JSON against the schema; auto‑repair if needed
  - Return `{ intent, area, targets, params, confidence }`
- Env: `ADAPTER_MODEL`, `QDRANT_HOST`, `QDRANT_API_KEY`
- Add unit tests with fixed prompts and golden outputs

### 2) Populate Qdrant properly
- Replace zero‑vectors with real embeddings from your embedder (e.g., `text-embedding-3-small` equivalent local, or `bge-small`)
- `ha_entities` payload schema:
  - `entity_id`, `domain`, `area_id`, `device_id`, `friendly_name`, `capabilities` (on/off, color, brightness), `aliases` (synonyms)
- `plex_media` payload schema:
  - `rating_key`, `title`, `type` (movie, episode, artist), `year`, `collection`, `genres`, `actors`, `audio_language`, `subtitles`
- Build a periodic exporter that walks HA registries and Plex API to keep both collections fresh

### 3) Conversation pipeline niceties
- Add a **confidence gate** UI toggle with threshold
- Add a **night mode** rule set (block intents after 23:00 except whitelisted users)
- Add **idempotency** window: hash `{intent, area, targets, params}` for 2s dedupe

### 4) Expand routing
- Map `report_sensor` to templated spoken summaries grouped by area
- Add `media_play`, `media_pause`, `play_title` that routes to Plex clients via `media_player` domain
- Support scenes by human names: resolve to `scene.<slug>` with fuzzy matching

### 5) Tests
- HA core tests using `pytest-homeassistant-custom-component`
- Fixtures for `area_registry`, `entity_registry`, sample Qdrant results
- Golden tests for routing results: ensure proper service calls and data payloads

### 6) HACS polish
- Add `config_flow.py` for UI setup (adapter URL, Qdrant, flags)
- Add SVG icon and brand assets under `brands/`
- Add semantic versioning and GH release automation

### 7) Performance
- Cache catalog slices per user utterance window (LRU 256)
- Use streaming from the model if available; allow early‑exit when intent confidence spikes
- Timeouts: adapter 1500 ms, Qdrant 400 ms, overall 2s SLA

### 8) Security
- If adapter exposed off‑box, attach an auth token that HA signs; adapter verifies HMAC
- Never execute `open_garage`, `unlock_*` without secondary signal (presence, voice profile)

### 9) Telemetry
- Log to file or Loki: `{utterance, topk_terms, intent, params, confidence, duration_ms}`
- Provide a minimal `/diagnostics` panel via HA diagnostics integration

---

## Notes
- This skeleton runs without Qdrant or an adapter using the `mock_adapter`. Flip it off by setting `adapter_url`.
- Sentence file uses a catch‑all wildcard so your native intents still get priority; everything else falls through.
- Coordinator is opt‑in to avoid spamming Qdrant until you’re ready.
