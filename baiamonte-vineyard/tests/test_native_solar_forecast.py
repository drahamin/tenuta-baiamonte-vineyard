import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def test_energy_uses_hourly_estimates_for_current_and_next_estate_dates():
    path = Path(__file__).resolve().parents[1] / "custom_components/baiamonte_solar_forecast/energy.py"
    spec = importlib.util.spec_from_file_location("native_solar_energy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.hourly_wh({
        "target_day": "2026-11-22",
        "points": [
            {"observed_at": "2026-11-22T13:00:00+01:00", "power_w": 1234},
            {"observed_at": "2026-11-22T15:00:00+01:00", "power_w": "unavailable"},
            {"observed_at": "2026-11-21T16:00:00+01:00", "power_w": 999},
        ],
        "tomorrow": {
            "target_day": "2026-11-23",
            "points": [{"observed_at": "2026-11-23T13:00:00+01:00", "power_w": 1330}],
        },
    }, now=datetime(2026, 11, 21, 23, 30, tzinfo=timezone.utc))
    assert result == {
        "2026-11-22T13:00:00+01:00": 1234,
        "2026-11-23T13:00:00+01:00": 1330,
    }


def test_yaml_import_does_not_wait_for_its_own_component_setup():
    import ast
    import asyncio
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "custom_components/baiamonte_solar_forecast/__init__.py"
    domain = "baiamonte_solar_forecast"
    tree = ast.parse(path.read_text())
    setup = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup")
    namespace = {"DOMAIN": domain}
    exec(compile(ast.Module(body=[setup], type_ignores=[]), str(path), "exec"), namespace)

    async def verify():
        component_ready = asyncio.Event()
        imported = []
        tasks = []

        async def create_entry(handler, *, context, data):
            await component_ready.wait()
            imported.append((handler, context, data))

        def schedule(coro, name):
            tasks.append(asyncio.create_task(coro, name=name))

        hass = SimpleNamespace(
            async_create_task=schedule,
            config_entries=SimpleNamespace(flow=SimpleNamespace(async_init=create_entry)),
        )
        try:
            result = await asyncio.wait_for(namespace["async_setup"](hass, {domain: {"use_for_energy": True}}), 0.5)
            assert result is True
            assert imported == []
        finally:
            component_ready.set()
            await asyncio.gather(*tasks)
        assert imported == [(domain, {"source": "import"}, {"use_for_energy": True})]

    asyncio.run(verify())
