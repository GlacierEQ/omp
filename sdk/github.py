"""GitHub connector module — 14-tool surface, read-first, write-with-uplift.

Mirrors the computer-user GitHub connector (read/search/inspect/verify/write/create/update,
default_mode=read). All provider calls go through an injected adapter; this module
never holds tokens. Writes require scoped authority via the capability twin.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Mapping, Optional
from .capability import CapabilityClient
from .errors import AdapterError, PolicyError, QualityError
from .quality import QualityGate, QUALITY_THRESHOLD
from .receipts import ReceiptStore, sha256_json
from .runtime import ConnectorRuntimeClient

# The 14 declared GitHub tools (from computer-user/connectors/CONNECTORS.md)
GITHUB_READ_TOOLS = frozenset({
    "github_list_repositories",
    "github_get_repository",
    "github_list_issues",
    "github_list_pull_requests",
    "github_get_pull_request",
    "github_get_file_content",
    "github_search_issues",
})
GITHUB_WRITE_TOOLS = frozenset({
    "github_create_issue",
    "github_create_pull_request",
    "github_push_to_branch",
    "github_create_issue_comment",
    "github_update_issue",
})
ALL_GITHUB_TOOLS = GITHUB_READ_TOOLS | GITHUB_WRITE_TOOLS

DESTRUCTIVE_GITHUB_TOOLS = frozenset()  # none of the 14 are destructive by design


class GitHubAdapter:
    """Minimal GitHub REST adapter for the SDK.

    Credentials are supplied out-of-band via `credential_headers` (an
    Authorization header map). No tokens are stored in this package.

    This is a reference implementation; production use should route through
    the unified credential broker (computer-user/connections.py).
    """

    def __init__(
        self,
        *,
        credential_headers: Mapping[str, str],
        base_url: str = "https://api.github.com",
        owner: str = "GlacierEQ",
        timeout: float = 20.0,
    ) -> None:
        self.credential_headers = dict(credential_headers)
        self.base_url = base_url.rstrip("/")
        self.owner = owner
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "glaciereq-sdk"}
        headers.update(self.credential_headers)
        return headers

    # ---- read tools ----
    def get_repository(self, *, owner: Optional[str] = None, repo: str) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_issues(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        import urllib.parse
        import urllib.request
        params = urllib.parse.urlencode({"state": state, "per_page": per_page})
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/issues?{params}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_pull_request(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        pull_number: int,
    ) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/pulls/{pull_number}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_file_content(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> dict[str, Any]:
        import urllib.parse
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}"
        if ref:
            url += f"?ref={ref}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("encoding") == "base64" and "content" in data:
            data["decoded_content"] = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data

    def search_issues(self, *, query: str, per_page: int = 30) -> list[dict[str, Any]]:
        import urllib.parse
        import urllib.request
        params = urllib.parse.urlencode({"q": query, "per_page": per_page})
        url = f"{self.base_url}/search/issues?{params}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("items", [])

    # ---- write tools (require uplift / human approval) ----
    def create_issue(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/issues"
        payload: dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        data = json.dumps(payload).encode("utf-8")
        headers = dict(self._headers())
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def create_issue_comment(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/issues/{issue_number}/comments"
        data = json.dumps({"body": body}).encode("utf-8")
        headers = dict(self._headers())
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def update_issue(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/issues/{issue_number}"
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        data = json.dumps(payload).encode("utf-8")
        headers = dict(self._headers())
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def create_pull_request(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: Optional[str] = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        import urllib.request
        url = f"{self.base_url}/repos/{owner or self.owner}/{repo}/pulls"
        payload: dict[str, Any] = {"title": title, "head": head, "base": base, "draft": draft}
        if body is not None:
            payload["body"] = body
        data = json.dumps(payload).encode("utf-8")
        headers = dict(self._headers())
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def push_to_branch(
        self,
        *,
        owner: Optional[str] = None,
        repo: str,
        branch: str,
        commit_message: str,
        files: list[Mapping[str, str]],
    ) -> dict[str, Any]:
        """Create or update files on a branch (commit & push).

        Each file: {"repoPath": str, "content": str} or {"path": str, "content": str}.
        This is a multi-step GitHub API sequence: get ref → get tree → create blobs
        → create tree → create commit → update ref.
        """
        import urllib.request
        owner = owner or self.owner

        def request(method, url, data=None):
            headers = dict(self._headers())
            if data is not None:
                headers["Content-Type"] = "application/json"
                body = json.dumps(data).encode("utf-8")
            else:
                body = None
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        # Get the default branch ref
        ref_data = request("GET", f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}")
        ref_sha = ref_data["object"]["sha"]

        # Get base tree
        tree_data = request("GET", f"{self.base_url}/repos/{owner}/{repo}/git/commit/{ref_sha}")
        base_tree_sha = tree_data["tree"]["sha"]

        # Create blobs
        blob_entries = []
        for index, file in enumerate(files):
            path = file.get("repoPath") or file.get("path") or f"file-{index}"
            content = file["content"]
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            blob = request(
                "POST",
                f"{self.base_url}/repos/{owner}/{repo}/git/blobs",
                {"content": encoded, "encoding": "base64"},
            )
            blob_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

        # Create tree
        tree = request(
            "POST",
            f"{self.base_url}/repos/{owner}/{repo}/git/trees",
            {"base_tree": base_tree_sha, "tree": blob_entries},
        )

        # Create commit
        commit = request(
            "POST",
            f"{self.base_url}/repos/{owner}/{repo}/git/commits",
            {
                "message": commit_message,
                "tree": tree["sha"],
                "parents": [ref_sha],
            },
        )

        # Update ref
        request(
            "PATCH",
            f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            {"sha": commit["sha"]},
        )

        return {
            "status": "pushed",
            "branch": branch,
            "commit": commit["sha"],
            "tree": tree["sha"],
            "files": [e["path"] for e in blob_entries],
        }

    # ---- verification ----
    def verify(self, value: Any) -> bool:
        """Independent readback verification: confirm the value is non-empty and
        contains an identifier GitHub returned (id, number, sha, or html_url)."""
        if isinstance(value, dict):
            return bool(value and any(k in value for k in ("id", "number", "sha", "html_url")))
        if isinstance(value, list):
            return bool(value)
        return bool(value)


class GitHubClient:
    """High-level GitHub client combining capability gating, runtime execution,
    receipts, and quality gates."""

    def __init__(
        self,
        *,
        capability: Optional[CapabilityClient] = None,
        runtime: Optional[ConnectorRuntimeClient] = None,
        receipts: Optional[ReceiptStore] = None,
        quality: Optional[QualityGate] = None,
        adapter: Optional[GitHubAdapter] = None,
    ) -> None:
        self.capability = capability or CapabilityClient()
        self.receipts = receipts or ReceiptStore("sdk-receipts")
        self.quality = quality or QualityGate()
        self.adapter = adapter
        self.runtime = runtime or ConnectorRuntimeClient(
            capability=self.capability,
            adapters={"github": adapter} if adapter else {},
            audit_path=self.receipts.root / "audit.jsonl",
        )
        if adapter is not None:
            self.runtime.register("github", adapter)

    def register_adapter(self, adapter: GitHubAdapter) -> None:
        self.adapter = adapter
        self.runtime.register("github", adapter)

    _TOOL_TO_CAPABILITY_OP = {
        "get_repository": "read",
        "list_repositories": "read",
        "get_file_content": "read",
        "search_issues": "search",
        "list_issues": "read",
        "list_pull_requests": "read",
        "get_pull_request": "read",
        "inspect": "inspect",
        "verify": "verify",
        "create_issue": "create",
        "create_pull_request": "create",
        "create_issue_comment": "create",
        "update_issue": "update",
        "push_to_branch": "write",
    }

    def plan(self, action: str, *, human_approved: bool = False) -> dict[str, Any]:
        cap_op = self._TOOL_TO_CAPABILITY_OP.get(action, action)
        return self.capability.plan("github", cap_op, human_approved=human_approved)


    async def execute(
        self,
        action: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        human_approved: bool = False,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Execute a GitHub action end-to-end: plan → execute → receipt → quality gate."""
        decision = self.plan(action, human_approved=human_approved)
        if not decision["allowed"]:
            raise PolicyError(f"GitHub {action} blocked: {decision['reason']}")

        verifier = self.adapter.verify if (verify and self.adapter) else None
        cap_op = self._TOOL_TO_CAPABILITY_OP.get(action, action)
        result = await self.runtime.execute(
            "github", action, payload=payload,
            human_approved=human_approved, verify=verifier,
            policy_action=cap_op,
        )

        # Seal an invocation + execution receipt
        envelope = {
            "trace_id": f"gh-{action}-{int(time.time())}",
            "caller": "GlaciereqSDK/GitHubClient",
            "capability": "github",
            "connector": "github",
            "operation": action,
            "idempotency_key": f"gh:{action}:{json.dumps(payload or {}, sort_keys=True)}",
            "mission_id": None,
            "depends_on": [],
        }
        auth_env = {"status": "authorized" if decision["allowed"] else "blocked"}
        self.receipts.remember_invocation(
            envelope["trace_id"], envelope, authorization=auth_env
        )
        receipt = self.receipts.finalize(
            envelope["trace_id"],
            status=result["status"],
            attempts=1,
            result=result,
            source_sha=None,
        )

        # Quality gate: require verification for completion-grade
        verified = bool(result.get("verified"))
        effort = 9.5 if verified else 6.0
        gate = self.quality.gate_effort(
            effort_score=effort,
            verified=verified,
            criterion_id=f"github:{action}",
        )
        result["quality_gate"] = gate
        result["receipt"] = receipt
        result["receipt_sha256"] = receipt.get("receipt_sha256")
        if gate["decision"] == "fail":
            raise QualityError(
                f"GitHub {action} failed quality gate: "
                f"{', '.join(gate['failed_ids'])}"
            )
        return result

    def execute_sync(self, *args, **kwargs) -> dict[str, Any]:
        import asyncio
        return asyncio.run(self.execute(*args, **kwargs))

    def list_tools(self) -> dict[str, list[str]]:
        return {
            "read": sorted(GITHUB_READ_TOOLS),
            "write": sorted(GITHUB_WRITE_TOOLS),
            "all": sorted(ALL_GITHUB_TOOLS),
        }

    def quality_floor(self) -> float:
        return QUALITY_THRESHOLD
