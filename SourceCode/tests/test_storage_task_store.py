"""Tests for TaskStore persistence layer.

Relates-to: FR-1
"""

import json
from pathlib import Path

import pytest
import yaml

from taskguard.models.errors import StorageError, TaskNotFoundError, TaskRegistrationError
from taskguard.models.task import LogSource, Task
from taskguard.storage.task_store import TaskStore


class TestTaskStoreLoadSave:
    @pytest.mark.asyncio
    async def test_cold_start(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        tasks = await store.load()
        assert tasks == []

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t1 = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        t2 = Task(alias="b", log_source=LogSource(type="file", path="C:\\x.log"))
        await store.save_all([t1, t2])

        loaded = await store.load()
        assert len(loaded) == 2
        assert loaded[0].alias == "a"
        assert loaded[1].alias == "b"

    @pytest.mark.asyncio
    async def test_atomic_write(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        await store.save_all([t])
        assert (tmp_path / "tasks_state.json").exists()

    @pytest.mark.asyncio
    async def test_corrupt_json_backup(self, tmp_path: Path) -> None:
        state_file = tmp_path / "tasks_state.json"
        state_file.write_text("not json at all", encoding="utf-8")
        store = TaskStore(tmp_path)
        loaded = await store.load()
        assert loaded == []
        # Original file should be backed up
        backups = list(tmp_path.glob("tasks_state.json.corrupt-*"))
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_version_mismatch(self, tmp_path: Path) -> None:
        state_file = tmp_path / "tasks_state.json"
        state_file.write_text(json.dumps({"version": 999, "tasks": []}), encoding="utf-8")
        store = TaskStore(tmp_path)
        with pytest.raises(StorageError):
            await store.load()


class TestTaskStoreAddRemove:
    @pytest.mark.asyncio
    async def test_add(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        await store.add(t)
        assert (await store.get("a")).alias == "a"

    @pytest.mark.asyncio
    async def test_add_duplicate(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        await store.add(t)
        with pytest.raises(TaskRegistrationError):
            await store.add(t)

    @pytest.mark.asyncio
    async def test_remove(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t = Task(alias="a", log_source=LogSource(type="file", path="C:\\test.log"))
        await store.add(t)
        await store.remove("a")
        with pytest.raises(TaskNotFoundError):
            await store.get("a")

    @pytest.mark.asyncio
    async def test_remove_not_found(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        with pytest.raises(TaskNotFoundError):
            await store.remove("nonexistent")


class TestYamlMerge:
    @pytest.mark.asyncio
    async def test_yaml_overrides_json(self, tmp_path: Path) -> None:
        """JSON has 下载A(cli); YAML has 下载A(yaml) -> keep yaml."""
        store = TaskStore(tmp_path)
        cli_task = Task(
            alias="下载A", log_source=LogSource(type="file", path="C:\\test.log"), source="cli"
        )
        await store.save_all([cli_task])

        yaml_path = tmp_path / "tasks.yaml"
        yaml_task = {
            "tasks": [
                {
                    "alias": "下载A",
                    "log_source": {"type": "file", "path": "C:\\y.log"},
                    "source": "yaml",
                }
            ]
        }
        yaml_path.write_text(yaml.dump(yaml_task), encoding="utf-8")

        await store.load_yaml_and_merge(yaml_path)
        loaded = await store.load()
        assert len(loaded) == 1
        assert loaded[0].source == "yaml"
        assert loaded[0].log_source.type == "file"

    @pytest.mark.asyncio
    async def test_yaml_adds_new_task(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        yaml_path = tmp_path / "tasks.yaml"
        data = {
            "tasks": [
                {"alias": "下载C", "log_source": {"type": "file", "path": "C:\\test.log"}}
            ]
        }
        yaml_path.write_text(yaml.dump(data), encoding="utf-8")

        await store.load_yaml_and_merge(yaml_path)
        loaded = await store.load()
        assert len(loaded) == 1
        assert loaded[0].alias == "下载C"

    @pytest.mark.asyncio
    async def test_json_retained_when_no_yaml_conflict(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t = Task(alias="服务B", log_source=LogSource(type="file", path="C:\\test.log"), source="cli")
        await store.save_all([t])

        yaml_path = tmp_path / "tasks.yaml"
        yaml_path.write_text(yaml.dump({"tasks": []}), encoding="utf-8")

        await store.load_yaml_and_merge(yaml_path)
        loaded = await store.load()
        assert len(loaded) == 1
        assert loaded[0].alias == "服务B"

    @pytest.mark.asyncio
    async def test_yaml_corrupt(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        yaml_path = tmp_path / "tasks.yaml"
        yaml_path.write_text("bad yaml: [: unclosed", encoding="utf-8")
        with pytest.raises(StorageError):
            await store.load_yaml_and_merge(yaml_path)
