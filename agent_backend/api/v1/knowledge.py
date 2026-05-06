"""
知识库本地管理 API。

SQLite 是知识库条目的主存储；Markdown 文件由数据库记录重建，
用于兼容现有 RAG 同步流程。首次读取已有 Markdown 文件时，会自动
导入为 legacy 条目，避免历史样本丢失。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_backend.agent.registry import get_registry
from agent_backend.db.chat_history import get_session
from agent_backend.db.models import KnowledgeEntry
from agent_backend.rag_engine.chunking import chunk_markdown
from agent_backend.rag_engine.sql_samples import parse_sql_sample_sections

router = APIRouter(prefix="/{agent_type}/knowledge", tags=["knowledge"])

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_VALID_KB_TYPES = {"sql", "solution"}
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
_SQL_BLOCK_RE = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_LEGACY_USER = "legacy"
_SQL_ADMIN_USER = "admin"


class KnowledgeFileRequest(BaseModel):
    kb_type: str
    name: str
    editor_name: str = ""


class RenameKnowledgeFileRequest(BaseModel):
    kb_type: str
    new_name: str
    editor_name: str = ""


class KnowledgeEntryRequest(BaseModel):
    kb_type: str
    title: str
    scenario: str
    key_tables: str = ""
    sql_code: str = ""
    answer: str = ""
    editor_name: str = ""


class DeleteKnowledgeEntryRequest(BaseModel):
    kb_type: str
    editor_name: str = ""


def _validate_kb_type(kb_type: str) -> str:
    if kb_type not in _VALID_KB_TYPES:
        raise HTTPException(status_code=400, detail="知识库类型无效")
    return kb_type


def _normalize_editor_name(name: str) -> str:
    editor = " ".join(str(name or "").strip().split())
    if not editor:
        raise HTTPException(status_code=400, detail="请先输入用户名")
    return editor


def _assert_write_allowed(kb_type: str, editor_name: str) -> str:
    editor = _normalize_editor_name(editor_name)
    if kb_type == "sql" and editor != _SQL_ADMIN_USER:
        raise HTTPException(status_code=403, detail="该账号无权限")
    return editor


def _assert_delete_allowed(editor_name: str) -> str:
    editor = _normalize_editor_name(editor_name)
    if editor != _SQL_ADMIN_USER:
        raise HTTPException(status_code=403, detail="该账号无权限")
    return editor


def _resolve_config_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute() and path.exists():
        return path

    normalized = path_text.replace("\\", "/")
    if normalized.startswith("/data/"):
        return _PROJECT_ROOT / normalized.lstrip("/")

    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


def _get_library_dir(agent_type: str, kb_type: str) -> Path:
    registry = get_registry()
    if not registry.has_agent(agent_type):
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_type}")

    rag_config = registry.get_rag_config(agent_type)
    if kb_type == "sql":
        base_dir = _resolve_config_path(rag_config.sql_dir or f"data/{agent_type}/sql")
    else:
        docs_dir = _resolve_config_path(rag_config.docs_dir or f"data/{agent_type}/docs")
        base_dir = docs_dir / "solutions"

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _normalize_filename(name: str) -> str:
    filename = name.strip()
    if filename.lower().endswith(".md"):
        filename = filename[:-3].strip()
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if any(char in _INVALID_FILENAME_CHARS for char in filename):
        raise HTTPException(status_code=400, detail="文件名不能包含路径或特殊字符")
    return f"{filename}.md"


def _file_path(base_dir: Path, filename: str) -> Path:
    normalized = _normalize_filename(filename)
    target = (base_dir / normalized).resolve()
    base = base_dir.resolve()
    if target.parent != base:
        raise HTTPException(status_code=400, detail="文件路径无效")
    return target


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_initial_file(path: Path, kb_type: str) -> None:
    title = "SQL查询样本库" if kb_type == "sql" else "问题解答知识库"
    path.write_text(f"# {title}\n\n", encoding="utf-8")


def _extract_prefixed_line(text: str, prefix: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(f"{prefix}："):
            return line.split("：", 1)[1].strip()
        if line.startswith(f"{prefix}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_sql_code(text: str) -> str:
    match = _SQL_BLOCK_RE.search(text)
    return match.group(1).strip() if match else ""


def _parse_sql_entries(markdown: str, source_path: str) -> list[dict]:
    entries = []
    for section in parse_sql_sample_sections(markdown, source_path=source_path):
        entries.append(
            {
                "title": section.heading,
                "scenario": _extract_prefixed_line(section.full_text, "适用场景"),
                "key_tables": ", ".join(section.key_tables),
                "sql_code": _extract_sql_code(section.full_text),
                "answer": "",
            }
        )
    return entries


def _parse_solution_entries(markdown: str) -> list[dict]:
    entries = []
    for chunk in chunk_markdown(markdown, split_paragraphs=False):
        title = (chunk.heading or "").strip()
        body = chunk.text.strip()
        if not title or not body:
            continue

        scenario = _extract_prefixed_line(body, "适用场景")
        answer_lines = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith("适用场景：") or line.startswith("适用场景:"):
                continue
            if line in {"---", "***"}:
                continue
            answer_lines.append(raw_line)

        answer = "\n".join(answer_lines).strip()
        if scenario or answer:
            entries.append(
                {
                    "title": title,
                    "scenario": scenario,
                    "key_tables": "",
                    "sql_code": "",
                    "answer": answer,
                }
            )
    return entries


def _clean_single_line(value: str) -> str:
    return " ".join(value.strip().splitlines()).strip()


def _validate_entry_payload(req: KnowledgeEntryRequest) -> dict:
    title = _clean_single_line(req.title)
    scenario = _clean_single_line(req.scenario)
    if not title or not scenario:
        raise HTTPException(status_code=400, detail="标题和适用场景不能为空")

    if req.kb_type == "sql":
        key_tables = _clean_single_line(req.key_tables)
        sql_code = req.sql_code.strip()
        if not key_tables or not sql_code:
            raise HTTPException(status_code=400, detail="关键表和SQL代码不能为空")
        return {
            "title": title,
            "scenario": scenario,
            "key_tables": key_tables,
            "sql_code": sql_code,
            "answer": "",
        }

    answer = req.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="解答内容不能为空")
    return {
        "title": title,
        "scenario": scenario,
        "key_tables": "",
        "sql_code": "",
        "answer": answer,
    }


def _entry_to_payload(entry: KnowledgeEntry) -> dict:
    return {
        "id": entry.id,
        "title": entry.title,
        "scenario": entry.scenario,
        "key_tables": entry.key_tables,
        "sql_code": entry.sql_code,
        "answer": entry.answer,
        "created_by": entry.created_by,
        "created_at": entry.created_at,
        "updated_by": entry.updated_by,
        "updated_at": entry.updated_at,
    }


async def _count_entries(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
    filename: str,
    include_deleted: bool = False,
) -> int:
    stmt = select(func.count()).select_from(KnowledgeEntry).where(
        KnowledgeEntry.agent_type == agent_type,
        KnowledgeEntry.kb_type == kb_type,
        KnowledgeEntry.filename == filename,
    )
    if not include_deleted:
        stmt = stmt.where(KnowledgeEntry.is_deleted == 0)
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _get_entries(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
    filename: str,
) -> list[KnowledgeEntry]:
    result = await db.execute(
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.agent_type == agent_type,
            KnowledgeEntry.kb_type == kb_type,
            KnowledgeEntry.filename == filename,
            KnowledgeEntry.is_deleted == 0,
        )
        .order_by(KnowledgeEntry.id.asc())
    )
    return list(result.scalars().all())


async def _ensure_file_imported(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
    path: Path,
) -> None:
    if not path.exists():
        return
    existing_count = await _count_entries(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        include_deleted=True,
    )
    if existing_count > 0:
        return

    markdown = _read_text(path)
    raw_entries = (
        _parse_sql_entries(markdown, path.name)
        if kb_type == "sql"
        else _parse_solution_entries(markdown)
    )
    if not raw_entries:
        return

    legacy_time = path.stat().st_mtime
    for raw in raw_entries:
        db.add(
            KnowledgeEntry(
                agent_type=agent_type,
                kb_type=kb_type,
                filename=path.name,
                title=raw["title"],
                scenario=raw["scenario"],
                key_tables=raw["key_tables"],
                sql_code=raw["sql_code"],
                answer=raw["answer"],
                created_by=_LEGACY_USER,
                created_at=legacy_time,
                updated_by=_LEGACY_USER,
                updated_at=legacy_time,
            )
        )
    await db.commit()


async def _ensure_all_files_imported(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
    base_dir: Path,
) -> None:
    for path in sorted(base_dir.glob("*.md"), key=lambda p: p.name.lower()):
        await _ensure_file_imported(
            db,
            agent_type=agent_type,
            kb_type=kb_type,
            path=path,
        )


async def _render_markdown_file(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
    filename: str,
    base_dir: Path,
) -> None:
    path = _file_path(base_dir, filename)
    entries = await _get_entries(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
    )

    title = "SQL查询样本库" if kb_type == "sql" else "问题解答知识库"
    parts = [f"# {title}\n"]
    for entry in entries:
        if kb_type == "sql":
            parts.append(
                "\n".join(
                    [
                        f"#### {entry.title}",
                        "",
                        f"适用场景：{entry.scenario}",
                        "",
                        f"关键表：{entry.key_tables}",
                        "",
                        "```sql",
                        entry.sql_code,
                        "```",
                        "",
                        "---",
                        "",
                    ]
                )
            )
        else:
            parts.append(
                "\n".join(
                    [
                        f"#### {entry.title}",
                        "",
                        f"适用场景：{entry.scenario}",
                        "",
                        entry.answer,
                        "",
                        "---",
                        "",
                    ]
                )
            )
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


async def _list_db_file_stats(
    db: AsyncSession,
    *,
    agent_type: str,
    kb_type: str,
) -> dict[str, dict]:
    result = await db.execute(
        select(
            KnowledgeEntry.filename,
            func.count(KnowledgeEntry.id),
            func.max(KnowledgeEntry.updated_at),
        )
        .where(
            KnowledgeEntry.agent_type == agent_type,
            KnowledgeEntry.kb_type == kb_type,
            KnowledgeEntry.is_deleted == 0,
        )
        .group_by(KnowledgeEntry.filename)
    )
    return {
        row[0]: {"entry_count": int(row[1] or 0), "updated_at": float(row[2] or 0)}
        for row in result.all()
    }


@router.get("/files")
async def list_files(
    agent_type: str,
    kb_type: str = Query(default="sql"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(kb_type)
    base_dir = _get_library_dir(agent_type, kb_type)
    await _ensure_all_files_imported(db, agent_type=agent_type, kb_type=kb_type, base_dir=base_dir)

    db_stats = await _list_db_file_stats(db, agent_type=agent_type, kb_type=kb_type)
    filenames = set(db_stats.keys()) | {path.name for path in base_dir.glob("*.md")}

    files = []
    for filename in sorted(filenames, key=str.lower):
        path = _file_path(base_dir, filename)
        if not path.exists() and db_stats.get(filename, {}).get("entry_count", 0) > 0:
            await _render_markdown_file(
                db,
                agent_type=agent_type,
                kb_type=kb_type,
                filename=filename,
                base_dir=base_dir,
            )
        stat = path.stat() if path.exists() else None
        info = db_stats.get(filename, {})
        files.append(
            {
                "name": filename,
                "path": str(path),
                "size": stat.st_size if stat else 0,
                "updated_at": int(info.get("updated_at") or (stat.st_mtime if stat else 0)),
                "entry_count": int(info.get("entry_count") or 0),
            }
        )
    return {"kb_type": kb_type, "base_dir": str(base_dir), "files": files}


@router.post("/files")
async def create_file(
    agent_type: str,
    req: KnowledgeFileRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(req.kb_type)
    _assert_write_allowed(kb_type, req.editor_name)
    base_dir = _get_library_dir(agent_type, kb_type)
    path = _file_path(base_dir, req.name)
    if path.exists():
        raise HTTPException(status_code=409, detail="文件已存在")
    _write_initial_file(path, kb_type)
    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=path)
    return {"file": {"name": path.name, "path": str(path)}}


@router.put("/files/{filename}")
async def rename_file(
    agent_type: str,
    filename: str,
    req: RenameKnowledgeFileRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(req.kb_type)
    _assert_write_allowed(kb_type, req.editor_name)
    base_dir = _get_library_dir(agent_type, kb_type)
    source = _file_path(base_dir, filename)
    target = _file_path(base_dir, req.new_name)
    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=source)

    row_count = await _count_entries(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=source.name,
        include_deleted=True,
    )
    if not source.exists() and row_count == 0:
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.exists() and target != source:
        raise HTTPException(status_code=409, detail="目标文件已存在")

    if source.exists() and target != source:
        source.rename(target)

    await db.execute(
        update(KnowledgeEntry)
        .where(
            KnowledgeEntry.agent_type == agent_type,
            KnowledgeEntry.kb_type == kb_type,
            KnowledgeEntry.filename == source.name,
        )
        .values(filename=target.name)
    )
    await db.commit()
    await _render_markdown_file(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=target.name,
        base_dir=base_dir,
    )
    return {"file": {"name": target.name, "path": str(target)}}


@router.get("/files/{filename}/entries")
async def list_entries(
    agent_type: str,
    filename: str,
    kb_type: str = Query(default="sql"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(kb_type)
    base_dir = _get_library_dir(agent_type, kb_type)
    path = _file_path(base_dir, filename)
    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=path)

    row_count = await _count_entries(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        include_deleted=True,
    )
    if not path.exists() and row_count == 0:
        raise HTTPException(status_code=404, detail="文件不存在")

    entries = await _get_entries(db, agent_type=agent_type, kb_type=kb_type, filename=path.name)
    return {"file": path.name, "entries": [_entry_to_payload(entry) for entry in entries]}


@router.post("/files/{filename}/entries")
async def add_entry(
    agent_type: str,
    filename: str,
    req: KnowledgeEntryRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(req.kb_type)
    editor = _assert_write_allowed(kb_type, req.editor_name)
    base_dir = _get_library_dir(agent_type, kb_type)
    path = _file_path(base_dir, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=path)
    values = _validate_entry_payload(req)
    now = time.time()
    entry = KnowledgeEntry(
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        created_by=editor,
        created_at=now,
        updated_by=editor,
        updated_at=now,
        **values,
    )
    db.add(entry)
    await db.commit()
    await _render_markdown_file(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        base_dir=base_dir,
    )
    return {"file": path.name, "entry": _entry_to_payload(entry)}


@router.put("/files/{filename}/entries/{entry_id}")
async def update_entry(
    agent_type: str,
    filename: str,
    entry_id: int,
    req: KnowledgeEntryRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(req.kb_type)
    editor = _assert_write_allowed(kb_type, req.editor_name)
    base_dir = _get_library_dir(agent_type, kb_type)
    path = _file_path(base_dir, filename)
    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=path)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.agent_type == agent_type,
            KnowledgeEntry.kb_type == kb_type,
            KnowledgeEntry.filename == path.name,
            KnowledgeEntry.is_deleted == 0,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    values = _validate_entry_payload(req)
    for key, value in values.items():
        setattr(entry, key, value)
    entry.updated_by = editor
    entry.updated_at = time.time()
    await db.commit()
    await _render_markdown_file(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        base_dir=base_dir,
    )
    return {"file": path.name, "entry": _entry_to_payload(entry)}


@router.delete("/files/{filename}/entries/{entry_id}")
async def delete_entry(
    agent_type: str,
    filename: str,
    entry_id: int,
    req: DeleteKnowledgeEntryRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    kb_type = _validate_kb_type(req.kb_type)
    editor = _assert_delete_allowed(req.editor_name)
    base_dir = _get_library_dir(agent_type, kb_type)
    path = _file_path(base_dir, filename)
    await _ensure_file_imported(db, agent_type=agent_type, kb_type=kb_type, path=path)

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.agent_type == agent_type,
            KnowledgeEntry.kb_type == kb_type,
            KnowledgeEntry.filename == path.name,
            KnowledgeEntry.is_deleted == 0,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    entry.is_deleted = 1
    entry.updated_by = editor
    entry.updated_at = time.time()
    await db.commit()
    await _render_markdown_file(
        db,
        agent_type=agent_type,
        kb_type=kb_type,
        filename=path.name,
        base_dir=base_dir,
    )
    return {"file": path.name, "entry": _entry_to_payload(entry)}
