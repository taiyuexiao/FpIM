"""OKF Repository(V1.2 §10.3):Git 受控文件仓库。

负责:版本历史、Diff、Review(经 git)、Publish、Rollback、Source Trace。
不承担:在线向量检索、Agent 会话状态、用户实时负责领域、动态 RawTag、人员推荐排名。

Published / Draft 边界:只有 Publisher 校验通过的文档才写入并 commit;
任意正式版本可定位和回滚;RAG Indexer(模块 23)只消费这里的 Published OKF。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import get_settings
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.okf import OkfDocument, OkfStatus
from app.okf.document import from_markdown, to_markdown


class OkfRepository:
    """Git 文件仓库。"""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or get_settings().okf_repo_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        for t in ("responsibilities", "people", "departments", "processes",
                  "policies", "faqs", "contents", "relationships"):
            (self._root / t).mkdir(exist_ok=True)

    # ---------------- 基础路径 ----------------

    @property
    def root(self) -> Path:
        return self._root

    def _path_of(self, doc: OkfDocument) -> Path:
        return self._root / doc.metadata.type.value / f"{doc.metadata.id}.md"

    # ---------------- 写(Publish)----------------

    async def write(self, doc: OkfDocument) -> Path:
        """写入文档并 git commit(每次发布一个版本,§10.3 版本历史)。"""
        path = self._path_of(doc)
        path.write_text(to_markdown(doc), encoding="utf-8")
        await self._git("add", str(path.relative_to(self._root)))
        await self._git(
            "-c", "user.name=okf-publisher", "-c", "user.email=okf@local",
            "commit", "--allow-empty-message", "-m",
            f"publish {doc.metadata.id} v{doc.metadata.version}",
        )
        return path

    # ---------------- 读(Source Trace)----------------

    async def get_latest(self, document_id: str) -> OkfDocument | None:
        """按 ID 读最新发布版本。"""
        for t in ("responsibilities", "people", "departments", "processes",
                  "policies", "faqs", "contents", "relationships"):
            path = self._root / t / f"{document_id}.md"
            if path.exists():
                return from_markdown(path.read_text(encoding="utf-8"))
        return None

    async def list_published_ids(self) -> set[str]:
        """全部已发布文档 ID(链接完整性校验/索引输入)。"""
        ids: set[str] = set()
        for t in ("responsibilities", "people", "departments", "processes",
                  "policies", "faqs", "contents", "relationships"):
            for path in (self._root / t).glob("*.md"):
                ids.add(path.stem)
        return ids

    async def list_published(self) -> list[OkfDocument]:
        """全部 Published 文档(RAG Indexer 的唯一输入,§10.6)。"""
        docs: list[OkfDocument] = []
        for t in ("responsibilities", "people", "departments", "processes",
                  "policies", "faqs", "contents", "relationships"):
            for path in sorted((self._root / t).glob("*.md")):
                doc = from_markdown(path.read_text(encoding="utf-8"))
                if doc.metadata.status == OkfStatus.PUBLISHED:
                    docs.append(doc)
        return docs

    # ---------------- 版本管理(§10.3)----------------

    async def history(self, document_id: str) -> list[dict]:
        """版本历史:git log 该文件。"""
        rel = await self._rel_path(document_id)
        out = await self._git(
            "log", "--format=%H|%cs|%s", "--", rel, allow_fail=True,
        )
        history = []
        for line in out.splitlines():
            if "|" in line:
                commit, date, subject = line.split("|", 2)
                history.append({"commit": commit, "date": date, "subject": subject})
        return history

    async def diff(self, document_id: str, commit_a: str, commit_b: str) -> str:
        """两个提交间的 Diff(§10.3)。"""
        rel = await self._rel_path(document_id)
        return await self._git("diff", commit_a, commit_b, "--", rel, allow_fail=True)

    async def rollback(self, document_id: str, commit: str) -> None:
        """回滚到指定提交(§10.3:任意正式版本可定位和回滚)。"""
        rel = await self._rel_path(document_id)
        await self._git("checkout", commit, "--", rel)
        await self._git("add", rel)
        await self._git(
            "-c", "user.name=okf-publisher", "-c", "user.email=okf@local",
            "commit", "-m", f"rollback {document_id} to {commit[:8]}",
        )

    async def _rel_path(self, document_id: str) -> str:
        doc = await self.get_latest(document_id)
        if doc is None:
            raise AgentError(ErrorCode.INPUT_ERROR, f"OKF 文档不存在: {document_id}")
        return str(self._path_of(doc).relative_to(self._root))

    # ---------------- git 封装 ----------------

    async def _git(self, *args: str, allow_fail: bool = False) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0 and not allow_fail:
            raise AgentError(
                ErrorCode.INTERNAL_ERROR,
                f"git {' '.join(args)} 失败: {err.decode('utf-8', 'ignore')[:300]}",
            )
        return out.decode("utf-8", "ignore")

    async def ensure_git_initialized(self) -> None:
        """确保仓库目录是 git 仓库(首次使用时调用)。"""
        if not (self._root / ".git").exists():
            await self._git("init")
            await self._git(
                "-c", "user.name=okf-publisher", "-c", "user.email=okf@local",
                "commit", "--allow-empty", "-m", "init okf repository",
            )
