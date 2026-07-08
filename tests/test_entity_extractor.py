"""Entity extraction tests: layer 1 (manifests), layer 2 (mocked LLM), resolution."""

import json
from unittest.mock import MagicMock

import pytest

from clawdiney.entity_extractor import (
    extract_from_manifests,
    extract_semantic,
    run_extraction,
)
from clawdiney.storage import BrainStorage

DIM = 4


class FakeProvider:
    def embed(self, text):
        seed = float(sum(ord(c) for c in text) % 97) + 1.0
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture()
def storage(tmp_path):
    store = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    yield store
    store.close()


@pytest.fixture()
def py_project(tmp_path):
    root = tmp_path / "proj-py"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "proj-py"\nversion = "1.0"\n'
        'dependencies = ["httpx>=0.25.0", "tenacity"]\n'
        '[project.scripts]\nproj-cli = "proj:main"\n',
        encoding="utf-8",
    )
    (root / ".env.example").write_text(
        "DATABASE_URL=postgres://user:pass@localhost:5432/app\n"
        "API_BASE=https://api.example.com/v1\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def node_project(tmp_path):
    root = tmp_path / "proj-node"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "proj-node",
                "dependencies": {"express": "^4.0.0"},
                "scripts": {"start": "node index.js"},
            }
        ),
        encoding="utf-8",
    )
    (root / ".env.example").write_text(
        "DB=postgres://localhost/app\n", encoding="utf-8"
    )
    return root


class TestLayer1:
    def test_pyproject_dependencies(self, py_project):
        result = extract_from_manifests(py_project)
        libs = {e.name for e in result.entities if e.kind == "library"}
        assert libs == {"httpx", "tenacity"}
        rels = {(r.target_name, r.rel_type) for r in result.relations}
        assert ("httpx", "DEPENDS_ON") in rels

    def test_package_json_dependencies(self, node_project):
        result = extract_from_manifests(node_project)
        assert {e.name for e in result.entities if e.kind == "library"} == {"express"}

    def test_env_datastore_and_http(self, py_project):
        result = extract_from_manifests(py_project)
        stores = [e for e in result.entities if e.kind == "datastore"]
        assert stores and stores[0].name == "postgresql"
        consumes = dict(result.interfaces.consumes)
        assert any("postgresql" in desc for desc in consumes)
        assert any(
            "api.example.com" in desc for desc in dict(result.interfaces.consumes)
        )

    def test_exposes_with_source_attribution(self, py_project):
        result = extract_from_manifests(py_project)
        exposes = result.interfaces.exposes
        assert any(
            "proj-cli" in desc and src == "pyproject.toml" for desc, src in exposes
        )

    def test_compose_services(self, tmp_path):
        pytest.importorskip("yaml")
        root = tmp_path / "proj-compose"
        root.mkdir()
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  db:\n    image: postgres:16\n    ports:\n      - '5432:5432'\n"
            "  api:\n    image: myorg/api:latest\n",
            encoding="utf-8",
        )
        result = extract_from_manifests(root)
        kinds = {(e.name, e.kind) for e in result.entities}
        assert ("db", "datastore") in kinds
        assert ("api", "service") in kinds

    def test_malformed_manifest_skipped(self, tmp_path):
        root = tmp_path / "broken"
        root.mkdir()
        (root / "pyproject.toml").write_text("not [ valid toml", encoding="utf-8")
        result = extract_from_manifests(root)  # must not raise
        assert result.entities == []


class TestLayer2Extraction:
    def _client(self, payload):
        client = MagicMock()
        client.generate.return_value = {"response": payload}
        return client

    def test_valid_extraction(self):
        payload = json.dumps(
            {
                "entities": [
                    {
                        "name": "repository pattern",
                        "kind": "pattern",
                        "description": "data access",
                    }
                ],
                "relations": [
                    {
                        "target": "repository pattern",
                        "rel_type": "USES_PATTERN",
                        "confidence": 0.9,
                        "quote": "Repository pattern with service layer",
                    }
                ],
            }
        )
        entities, relations = extract_semantic(
            "card", "proj", client=self._client(payload)
        )
        assert entities[0].kind == "pattern"
        assert relations[0].rel_type == "USES_PATTERN"
        assert relations[0].confidence == 0.9

    def test_malformed_json_discarded(self):
        entities, relations = extract_semantic(
            "card", "proj", client=self._client("not json {")
        )
        assert entities == [] and relations == []

    def test_enum_violation_discarded(self):
        payload = json.dumps(
            {
                "entities": [{"name": "x", "kind": "spaceship"}],
                "relations": [
                    {"target": "x", "rel_type": "DESTROYS", "confidence": 0.9}
                ],
            }
        )
        entities, relations = extract_semantic(
            "card", "proj", client=self._client(payload)
        )
        assert entities == [] and relations == []

    def test_confidence_clamped(self):
        payload = json.dumps(
            {
                "entities": [],
                "relations": [
                    {"target": "t", "rel_type": "MENTIONS", "confidence": 1.7}
                ],
            }
        )
        _, relations = extract_semantic("card", "proj", client=self._client(payload))
        assert relations[0].confidence == 0.99


class TestRunExtraction:
    def test_layer1_populates_graph(self, py_project, storage):
        summary = run_extraction(
            "proj-py", py_project, storage, provider=FakeProvider()
        )
        assert summary["layer1"] >= 2
        paths = storage.find_paths("default", "proj-py", "httpx", max_depth=1)
        assert paths and paths[0][0]["rel_type"] == "DEPENDS_ON"

    def test_dependency_removed_disappears(self, py_project, storage):
        run_extraction("proj-py", py_project, storage, provider=FakeProvider())
        (py_project / "pyproject.toml").write_text(
            '[project]\nname = "proj-py"\ndependencies = ["httpx"]\n',
            encoding="utf-8",
        )
        run_extraction("proj-py", py_project, storage, provider=FakeProvider())
        assert storage.find_paths("default", "proj-py", "tenacity", max_depth=1) == []
        assert storage.find_paths("default", "proj-py", "httpx", max_depth=1)

    def test_other_projects_untouched(self, py_project, node_project, storage):
        run_extraction("proj-py", py_project, storage, provider=FakeProvider())
        run_extraction("proj-node", node_project, storage, provider=FakeProvider())
        run_extraction("proj-py", py_project, storage, provider=FakeProvider())
        assert storage.find_paths("default", "proj-node", "express", max_depth=1)

    def test_shared_datastore_single_entity(self, py_project, node_project, storage):
        run_extraction("proj-py", py_project, storage, provider=FakeProvider())
        run_extraction("proj-node", node_project, storage, provider=FakeProvider())
        n = storage.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE kind='datastore'"
        ).fetchone()[0]
        assert n == 1
        paths = storage.find_paths("default", "proj-py", "proj-node", max_depth=2)
        assert paths  # connected through postgresql

    def _llm(self, payload):
        client = MagicMock()
        client.generate.return_value = {"response": json.dumps(payload)}
        return client

    def test_layer2_with_hash_gate(self, py_project, storage):
        payload = {
            "entities": [
                {"name": "jwt auth", "kind": "pattern", "description": "auth"}
            ],
            "relations": [
                {
                    "target": "jwt auth",
                    "rel_type": "USES_PATTERN",
                    "confidence": 0.8,
                    "quote": "x",
                }
            ],
        }
        client = self._llm(payload)
        summary = run_extraction(
            "proj-py",
            py_project,
            storage,
            provider=FakeProvider(),
            card_content="card v1",
            llm_client=client,
        )
        assert summary["layer2"] == 1
        assert client.generate.call_count == 1

        # unchanged card → skipped, no second LLM call
        summary2 = run_extraction(
            "proj-py",
            py_project,
            storage,
            provider=FakeProvider(),
            card_content="card v1",
            llm_client=client,
        )
        assert summary2["layer2"] == "skipped"
        assert client.generate.call_count == 1

    def test_entity_resolution_merges_duplicates(self, py_project, storage):
        provider = FakeProvider()
        # Pre-existing pattern entity with a vector
        emb = provider.embed("jwt auth: auth")
        storage.upsert_typed_entity(
            "default", "JWT Authentication", "pattern", "auth", embedding=emb
        )
        payload = {
            "entities": [
                {"name": "jwt auth", "kind": "pattern", "description": "auth"}
            ],
            "relations": [
                {
                    "target": "jwt auth",
                    "rel_type": "USES_PATTERN",
                    "confidence": 0.8,
                    "quote": "",
                }
            ],
        }
        run_extraction(
            "proj-py",
            py_project,
            storage,
            provider=provider,
            card_content="card",
            llm_client=self._llm(payload),
        )
        n = storage.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE kind='pattern'"
        ).fetchone()[0]
        assert n == 1  # merged, no duplicate
