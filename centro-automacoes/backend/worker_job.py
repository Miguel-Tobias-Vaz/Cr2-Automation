"""Proxy de Job usado dentro do subprocesso worker."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


class WorkerJob:
    """Implementa a interface mínima de Job para os runners no subprocesso."""

    def __init__(
        self,
        job_id: str,
        service_id: str,
        config: dict[str, Any],
        work_dir: Path,
    ) -> None:
        self.id = job_id
        self.service_id = service_id
        self.config = config
        self.dir = work_dir
        self.status = "running"
        self._cancel_requested = False
        self.error: str | None = None
        self.result: dict[str, Any] = {}
        self.progress_done = 0
        self.progress_total = 0
        self.progress_label = ""
        self._cancel_flag = work_dir / "cancel.flag"

    @property
    def cancel_requested(self) -> bool:
        self._sync_cancel()
        return self._cancel_requested

    @cancel_requested.setter
    def cancel_requested(self, value: bool) -> None:
        self._cancel_requested = bool(value)

    @property
    def progress_percent(self) -> int | None:
        if self.progress_total > 0:
            pct = int(round(100.0 * self.progress_done / self.progress_total))
            pct = max(0, min(100, pct))
            if self.status == "running" and pct >= 100:
                return 99
            return pct
        return None

    def _sync_cancel(self) -> None:
        if self._cancel_flag.is_file():
            self._cancel_requested = True

    def set_progress(
        self,
        done: int | None = None,
        total: int | None = None,
        label: str | None = None,
    ) -> None:
        self._sync_cancel()
        if total is not None and total >= 0:
            self.progress_total = int(total)
        if done is not None and done >= 0:
            self.progress_done = int(done)
        if label is not None:
            self.progress_label = str(label).strip()[:80]
        self._emit_op(
            {
                "op": "progress",
                "done": self.progress_done,
                "total": self.progress_total,
                "percent": self.progress_percent,
                "label": self.progress_label,
            }
        )

    def emit(self, level: str, msg: str) -> None:
        self._sync_cancel()
        self._emit_op({"op": "log", "level": level, "msg": str(msg)})

    def _emit_op(self, payload: dict[str, Any]) -> None:
        # Usar __stdout__: run_main_with_logs troca sys.stdout por um Tee que
        # chama job.emit — print() normal reentraria e aninharia NDJSON até estourar.
        stream = sys.__stdout__ or sys.stdout
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()

    def write_result(self) -> None:
        path = self.dir / "result.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "result": self.result,
                    "error": self.error,
                    "cancel_requested": self.cancel_requested,
                    "finished_at": time.time(),
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
