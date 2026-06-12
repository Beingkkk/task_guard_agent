"""aiohttp API server main entry point.

Relates-to: FR-4
"""

import asyncio
import logging
from pathlib import Path

from aiohttp import web

from taskguard.agent import AgentHarness
from taskguard.api.events import EventPublisher
from taskguard.api.routes import setup_routes
from taskguard.api.websocket import WebSocketManager, setup_websocket_routes
from taskguard.collectors.file_collector import FileCollector
from taskguard.config_loader import ConfigLoader
from taskguard.crash.dumper import CrashDumper
from taskguard.llm.base import BaseProvider
from taskguard.llm.factory import LLMConfig, create_provider
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools import register_builtin_tools

logger = logging.getLogger(__name__)


class APIServer:
    """aiohttp server with AgentHarness background task."""

    def __init__(
        self,
        store: TaskStore,
        metrics_store: MetricsStore,
        harness: AgentHarness | None = None,
        provider: BaseProvider | None = None,
        host: str = "127.0.0.1",
        port: int = 18990,
    ) -> None:
        self._store = store
        self._metrics_store = metrics_store
        self._host = host
        self._port = port
        self._harness = harness
        self._provider = provider
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    def _create_app(self) -> web.Application:
        """Create and configure the aiohttp application."""
        app = web.Application()

        # Event publisher for WebSocket broadcasting
        publisher = EventPublisher()
        ws_manager = WebSocketManager(publisher)

        # Store references in app
        app["store"] = self._store
        app["metrics_store"] = self._metrics_store
        app["event_publisher"] = publisher
        app["ws_manager"] = ws_manager
        app["provider"] = self._provider

        # Setup routes
        setup_routes(app, self._provider)
        setup_websocket_routes(app)

        # Wire event publisher into harness if available
        if self._harness is not None:
            self._harness.event_publisher = publisher

        return app

    async def start(self) -> None:
        """Start the HTTP server."""
        self._app = self._create_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("API server started on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        logger.info("API server stopped")


async def _setup_harness(
    config_path: Path, data_dir: Path
) -> tuple[AgentHarness, TaskStore, MetricsStore, BaseProvider | None]:
    """Set up the AgentHarness with all collectors and analyzers."""
    store = TaskStore(data_dir)
    metrics = MetricsStore(data_dir / "metrics.db")

    # Load config
    cfg = ConfigLoader.load(config_path)
    collect_interval = getattr(cfg, "collect_interval", 30)
    collect_concurrency = getattr(cfg, "collect_concurrency", 12)

    harness = AgentHarness(
        store,
        metrics,
        collect_interval=collect_interval,
        collect_concurrency=collect_concurrency,
    )
    harness.register_collector("file", FileCollector())

    # Wire FR-6 crash handler
    harness.crash_handler = CrashDumper(
        data_dir=data_dir / "crash_dumps",
        max_dumps=cfg.crash.max_dumps,
        log_lines=cfg.crash.log_lines,
        metrics_minutes=cfg.crash.metrics_minutes,
    )

    # Wire FR-3 analyzer if LLM config is available
    provider: BaseProvider | None = None
    try:
        provider = create_provider(
            LLMConfig(
                model=cfg.llm.model,
                api_key=cfg.llm.api_key,
                base_url=cfg.llm.base_url,
            )
        )
        from taskguard.analyzers.pipeline import AnalyzerPipeline
        from taskguard.analyzers.regex_extractor import RegexExtractor
        from taskguard.analyzers.state_analyzer import StateAnalyzer

        state_analyzer: StateAnalyzer | None = None
        if cfg.llm.state_analysis_enabled:
            state_analyzer = StateAnalyzer(
                provider=provider,
                state_analysis_interval=cfg.llm.state_analysis_interval,
                max_log_lines=cfg.llm.max_log_lines,
            )

        harness.analyzer = AnalyzerPipeline(
            provider=provider,
            regex_extractor=RegexExtractor.from_builtin_templates(),
            llm_min_interval=cfg.llm.min_interval,
            max_log_lines=cfg.llm.max_log_lines,
            regex_threshold=cfg.llm.regex_threshold,
            state_analyzer=state_analyzer,
        )
    except Exception:
        logger.warning("LLM analyzer not available; running without progress extraction")

    return harness, store, metrics, provider


async def main() -> None:
    """Main entry point for the API server."""
    import os
    import sys

    data_dir = Path(os.environ.get("TASKGUARD_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Support PyInstaller bundled executable: config files are extracted to _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    config_path = Path(meipass) / "config" if meipass else Path("config")

    harness, store, metrics, provider = await _setup_harness(config_path, data_dir)

    # Load tasks
    await store.load()
    await metrics.open()

    # Register tools
    register_builtin_tools(store, metrics)

    # Start server
    server = APIServer(store, metrics, harness=harness, provider=provider)
    await server.start()

    # Start harness in background
    harness_task = asyncio.create_task(harness.run())

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        harness.shutdown()
        await harness_task
        await server.stop()
        await metrics.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
