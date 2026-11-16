"""指标联合窗口业务规则。

三项采集指标（成功率、延迟、错误率）按「指标编号 + 时间窗」组成联合窗口，
联合计算后每个窗口只保留一个可解释结论，并带上判定版本与发布时依据快照。

数据口径：
  「样本引用」是当前结论依据的三项样本，每个指标类型一条；
  「全部样本」收存该窗口收到的每一条样本，迟到样本只追加、不覆盖生效引用，
  终态裁决选择「采纳更正」时才用迟到样本替换对应指标的生效引用。

状态流转只允许在本模块内发生：
  采集中 --三项样本到齐/手动发布--> 已发布 --迟到样本冲突、裁决--> 终态裁决
迟到样本不会直接改写已发布结论，而是进入指标待办队列等待裁决。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

WINDOW_TABLE = "metric_window"
SAMPLE_TABLE = "metric_sample"
TODO_TABLE = "metric_todo"

METRIC_TYPES = ("成功率", "延迟", "错误率")

WINDOW_COLLECTING = "采集中"
WINDOW_PUBLISHED = "已发布"
WINDOW_FINALIZED = "终态裁决"

CONCLUSION_INCOMPLETE = "样本不全"
CONCLUSION_NORMAL = "正常"
CONCLUSION_ABNORMAL = "异常"

JUDGE_NORMAL = "正常"
JUDGE_RECOVERED = "恢复"
JUDGE_EXCEEDED = "超限"

TODO_ABNORMAL = "异常窗口"
TODO_LATE = "迟到裁决"
PRIORITY_HIGH = "高"
PRIORITY_MEDIUM = "中"
PRIORITY_LOW = "低"
PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}

TODO_OPEN = "待处理"
TODO_DONE = "已处理"

KEEP_ORIGINAL = "维持原结论"
USE_CORRECTED = "采纳更正"
ARBITRATION_CHOICES = (KEEP_ORIGINAL, USE_CORRECTED)

REQUIRED_SAMPLE_FIELDS = ["指标编号", "关联端点", "时间窗", "指标类型", "样本值", "阈值", "到达批次"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(table: str) -> int:
    return max((int(row.get("id", 0)) for row in store.rows(table)), default=0) + 1


def _bump_version(version: str) -> str:
    try:
        return f"v{int(str(version).lstrip('v')) + 1}"
    except ValueError:
        return "v1"


class MetricWindowService:
    """联合窗口、样本与待办的全部业务规则集中在这一个服务里。"""

    # ---------- 单指标判定与联合结论 ----------

    def _judge_metric(self, metric_type: str, value: float, threshold: float, recovered: bool) -> str:
        """按指标类型选择比较方向：成功率不低于阈值，延迟/错误率不高于阈值。"""
        if metric_type == "成功率":
            ok = value >= threshold
        else:
            ok = value <= threshold
        if ok:
            return JUDGE_RECOVERED if recovered else JUDGE_NORMAL
        return JUDGE_EXCEEDED

    def _was_error_rate_exceeded(self, metric_id: str, time_window: str) -> bool:
        """错误率本窗正常、但同指标更早的窗口曾超限，才算「恢复」。"""
        history = [
            row for row in store.rows(SAMPLE_TABLE)
            if row.get("指标编号") == metric_id
            and row.get("指标类型") == "错误率"
            and str(row.get("时间窗", "")) < str(time_window)
            and row.get("判定") == JUDGE_EXCEEDED
        ]
        return bool(history)

    def _find_sample_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(SAMPLE_TABLE):
            if row.get("样本编号") == code:
                return row
        return None

    def _samples_from_refs(self, refs: dict[str, str]) -> list[dict[str, Any]]:
        """按引用取回三项样本；引用缺失则该指标缺位。"""
        samples: list[dict[str, Any]] = []
        for metric_type in METRIC_TYPES:
            code = refs.get(metric_type)
            sample = self._find_sample_by_code(code) if code else None
            if sample is not None:
                samples.append(sample)
        return samples

    def _current_samples(self, window: dict[str, Any]) -> list[dict[str, Any]]:
        """当前结论依据的三项生效样本。"""
        return self._samples_from_refs(window.get("样本引用", {}))

    def _all_samples(self, window: dict[str, Any]) -> list[dict[str, Any]]:
        """窗口收到的全部样本，含迟到样本，按进入顺序排列。"""
        samples = []
        for code in window.get("全部样本", []):
            sample = self._find_sample_by_code(code)
            if sample is not None:
                samples.append(sample)
        return samples

    def _build_conclusion(
        self, samples: list[dict[str, Any]]
    ) -> tuple[str, list[str], str, dict[str, str]] | None:
        """三项样本联合计算；缺项返回 None，窗口继续留在「采集中」。"""
        refs: dict[str, str] = {}
        abnormal_items: list[str] = []
        parts: list[str] = []
        for metric_type in METRIC_TYPES:
            sample = next((row for row in samples if row.get("指标类型") == metric_type), None)
            if sample is None:
                return None
            refs[metric_type] = str(sample["样本编号"])
            if sample["判定"] == JUDGE_EXCEEDED:
                abnormal_items.append(metric_type)
            parts.append(
                f"{metric_type}{sample['判定']}"
                f"（实测 {sample['样本值']}，阈值 {sample['阈值']}，样本 {sample['样本编号']}）"
            )
        conclusion = CONCLUSION_ABNORMAL if abnormal_items else CONCLUSION_NORMAL
        explain = "联合判定：" + "；".join(parts)
        if abnormal_items:
            explain += f"。异常项：{'、'.join(abnormal_items)}"
        else:
            explain += "。三项指标均在阈值内。"
        return conclusion, abnormal_items, explain, refs

    def _candidate_refs(
        self, current_refs: dict[str, str], replacements: dict[str, str]
    ) -> dict[str, str]:
        """把迟到样本替换进对应指标，得到若采纳更正后的候选引用。"""
        refs = dict(current_refs)
        refs.update(replacements)
        return refs

    def _snapshot(
        self, window: dict[str, Any], source: str, version: str, refs: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """已发布窗口保存当时依据：结论、引用与三条样本原样留档。"""
        effective_refs = refs if refs is not None else window.get("样本引用", {})
        samples = self._samples_from_refs(effective_refs)
        built = self._build_conclusion(samples)
        if built is None:
            conclusion, abnormal, explain, out_refs = CONCLUSION_INCOMPLETE, [], "三项样本未到齐", {}
        else:
            conclusion, abnormal, explain, out_refs = built
        return {
            "来源": source,
            "判定版本": version,
            "联合结论": conclusion,
            "异常项": list(abnormal),
            "结论说明": explain,
            "样本引用": dict(out_refs),
            "样本快照": [dict(sample) for sample in samples],
            "依据时间": _now(),
        }

    # ---------- 窗口查找与登记 ----------

    def find_window(self, window_id: int) -> dict[str, Any] | None:
        return store.find(WINDOW_TABLE, window_id)

    def _find_window_by_identity(self, metric_id: str, time_window: str) -> dict[str, Any] | None:
        for row in store.rows(WINDOW_TABLE):
            if row.get("指标编号") == metric_id and row.get("时间窗") == time_window:
                return row
        return None

    def _get_or_create_window(self, metric_id: str, endpoint: str, time_window: str) -> dict[str, Any]:
        window = self._find_window_by_identity(metric_id, time_window)
        if window is not None:
            return window
        window = {
            "id": _next_id(WINDOW_TABLE),
            "窗口编号": f"MW-{metric_id}-{time_window.replace(' ', '').replace(':', '').replace('-', '')}",
            "指标编号": metric_id,
            "关联端点": endpoint,
            "时间窗": time_window,
            "状态": WINDOW_COLLECTING,
            "判定版本": "v0",
            "联合结论": CONCLUSION_INCOMPLETE,
            "异常项": [],
            "结论说明": "三项样本尚未到齐，等待联合计算。",
            "样本引用": {},
            "全部样本": [],
            "发布快照": None,
            "版本记录": [],
            "冲突说明": None,
            "pending": True,
            "abnormal": False,
            "创建时间": _now(),
            "更新时间": _now(),
        }
        store.rows(WINDOW_TABLE).append(window)
        return window

    # ---------- 样本进入（含迟到冲突） ----------

    def ingest_sample(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], dict[str, Any] | None]:
        """登记一条指标样本并驱动联合窗口流转。

        返回 (样本, 缺失字段, 冲突信息)；样本在结论发布后到达即视为迟到，
        迟到样本只追加到「全部样本」并挂冲突，不改写生效引用与现有结论。
        """
        missing = [field for field in REQUIRED_SAMPLE_FIELDS if str(values.get(field) or "").strip() == ""]
        if missing:
            return None, missing, None
        metric_type = str(values["指标类型"]).strip()
        if metric_type not in METRIC_TYPES:
            return None, [f"指标类型仅支持 {'、'.join(METRIC_TYPES)}"], None
        try:
            value = float(values["样本值"])
            threshold = float(values["阈值"])
        except (TypeError, ValueError):
            return None, ["样本值", "阈值"], None

        metric_id = str(values["指标编号"]).strip()
        endpoint = str(values["关联端点"]).strip()
        time_window = str(values["时间窗"]).strip()
        recovered = metric_type == "错误率" and self._was_error_rate_exceeded(metric_id, time_window)
        judge = self._judge_metric(metric_type, value, threshold, recovered)

        sample_id = _next_id(SAMPLE_TABLE)
        sample = {
            "id": sample_id,
            "样本编号": f"SMP-{sample_id:04d}",
            "指标编号": metric_id,
            "关联端点": endpoint,
            "时间窗": time_window,
            "指标类型": metric_type,
            "样本值": value,
            "阈值": threshold,
            "判定": judge,
            "到达批次": str(values["到达批次"]).strip(),
            "是否迟到": False,
            "采集时间": str(values.get("采集时间") or _now()),
            "异常标记": judge == JUDGE_EXCEEDED,
        }
        store.rows(SAMPLE_TABLE).append(sample)

        window = self._get_or_create_window(metric_id, endpoint, time_window)
        late = window["状态"] in (WINDOW_PUBLISHED, WINDOW_FINALIZED)
        if late:
            sample["是否迟到"] = True
        window.setdefault("全部样本", []).append(sample["样本编号"])
        window["更新时间"] = _now()

        conflict: dict[str, Any] | None = None
        if window["状态"] == WINDOW_COLLECTING:
            # 采集中：样本直接成为该指标的生效引用，三项到齐即联合发布。
            window.setdefault("样本引用", {})[metric_type] = sample["样本编号"]
            built = self._build_conclusion(self._current_samples(window))
            if built is not None:
                candidate, abnormal, explain, _ = built
                self._apply_conclusion(window, candidate, abnormal, explain, source="发布")
                window["状态"] = WINDOW_PUBLISHED
                if candidate == CONCLUSION_ABNORMAL:
                    self._open_abnormal_todo(window, explain)
        elif late:
            conflict = self._register_late_conflict(window, sample)
        return sample, [], conflict

    def _apply_conclusion(
        self, window: dict[str, Any], conclusion: str, abnormal: list[str], explain: str, *, source: str
    ) -> None:
        """写入一个新版本的结论；窗口顶层始终只暴露这一个联合结论。"""
        version = "v1" if window["判定版本"] == "v0" else _bump_version(window["判定版本"])
        window["判定版本"] = version
        window["联合结论"] = conclusion
        window["异常项"] = list(abnormal)
        window["结论说明"] = explain
        record = self._snapshot(window, source, version)
        window["版本记录"].append(record)
        if window["发布快照"] is None:
            # 首次发布的依据永久保留，后续复测/裁决只追加版本记录。
            window["发布快照"] = dict(record)
        window["abnormal"] = conclusion == CONCLUSION_ABNORMAL
        window["更新时间"] = _now()

    def _register_late_conflict(
        self, window: dict[str, Any], sample: dict[str, Any]
    ) -> dict[str, Any]:
        """迟到样本挂冲突：原结论与生效引用不动，待办队列收一条高优先级裁决任务。"""
        todo = self._find_open_late_todo(window["id"])
        replacements = dict(todo["冲突替换"]) if todo else {}
        replacements[str(sample["指标类型"])] = str(sample["样本编号"])
        candidate_refs = self._candidate_refs(window["样本引用"], replacements)
        candidate_samples = self._samples_from_refs(candidate_refs)
        built = self._build_conclusion(candidate_samples)
        assert built is not None
        candidate, abnormal, explain, _ = built

        conflict = {
            "迟到样本": sample["样本编号"],
            "指标类型": sample["指标类型"],
            "原结论": window["联合结论"],
            "候选更正结论": candidate,
            "候选异常项": list(abnormal),
            "候选说明": explain,
            "发现时间": _now(),
        }
        window["冲突说明"] = (
            f"迟到样本 {sample['样本编号']}（{sample['指标类型']}）于结论发布后到达："
            f"原结论「{window['联合结论']}」，若采纳更正将变为「{candidate}」，需裁决。"
        )
        if todo is None:
            todo = self._create_todo(
                window,
                TODO_LATE,
                PRIORITY_HIGH,
                summary=window["冲突说明"],
                conflicts=[conflict],
                replacements=replacements,
            )
        else:
            todo.setdefault("冲突列表", []).append(conflict)
            todo["冲突替换"] = replacements
            todo["指标结果摘要"] = window["冲突说明"]
            todo["判定版本"] = window["判定版本"]
        return conflict

    # ---------- 手动发布与复测 ----------

    def publish_window(self, window_id: int) -> tuple[dict[str, Any] | None, str]:
        window = self.find_window(window_id)
        if window is None:
            return None, f"联合窗口 {window_id} 不存在或已归档"
        if window["状态"] != WINDOW_COLLECTING:
            return None, f"窗口处于「{window['状态']}」，无需重复发布"
        built = self._build_conclusion(self._current_samples(window))
        if built is None:
            return None, "三项指标样本未到齐，不能发布联合结论"
        conclusion, abnormal, explain, _ = built
        self._apply_conclusion(window, conclusion, abnormal, explain, source="发布")
        window["状态"] = WINDOW_PUBLISHED
        if conclusion == CONCLUSION_ABNORMAL:
            self._open_abnormal_todo(window, explain)
        return window, "联合窗口已发布，发布依据已快照留档"

    def retest_window(self, window_id: int) -> tuple[dict[str, Any] | None, str]:
        """按当前三项生效样本复测一窗指标，生成新判定版本并分别引用三项样本。"""
        window = self.find_window(window_id)
        if window is None:
            return None, f"联合窗口 {window_id} 不存在或已归档"
        if window["状态"] == WINDOW_COLLECTING:
            return None, "窗口尚未发布，不能复测"
        built = self._build_conclusion(self._current_samples(window))
        if built is None:
            return None, "三项指标样本缺失，无法复测"
        conclusion, abnormal, explain, _ = built
        self._apply_conclusion(window, conclusion, abnormal, explain, source="复测")
        message = f"复测完成，判定版本升至 {window['判定版本']}，联合结论引用三项样本"
        if conclusion == CONCLUSION_ABNORMAL:
            self._open_abnormal_todo(window, explain, retest=True)
        return window, message

    # ---------- 迟到裁决 ----------

    def arbitrate(self, window_id: int, choice: str) -> tuple[dict[str, Any] | None, str]:
        """终态取舍：维持原结论或采纳更正，裁决后窗口只有一个可解释结论。"""
        window = self.find_window(window_id)
        if window is None:
            return None, f"联合窗口 {window_id} 不存在或已归档"
        if choice not in ARBITRATION_CHOICES:
            return None, f"裁决方式仅支持 {'、'.join(ARBITRATION_CHOICES)}"
        todo = self._find_open_late_todo(window_id)
        if todo is None:
            return None, "该窗口没有待裁决的迟到样本冲突"
        if choice == USE_CORRECTED:
            # 用迟到样本替换对应指标的生效引用，再基于新的三项样本重算结论。
            window["样本引用"] = self._candidate_refs(window["样本引用"], todo["冲突替换"])
            built = self._build_conclusion(self._current_samples(window))
            if built is None:
                return None, "三项指标样本缺失，无法采纳更正结论"
            conclusion, abnormal, explain, _ = built
            self._apply_conclusion(window, conclusion, abnormal, explain, source="裁决-采纳更正")
        else:
            # 维持原结论：生效引用不变，只追加一个留痕版本。
            self._apply_conclusion(
                window, window["联合结论"], list(window["异常项"]), window["结论说明"],
                source="裁决-维持原结论",
            )
        window["状态"] = WINDOW_FINALIZED
        window["冲突说明"] = None
        todo["状态"] = TODO_DONE
        todo["处理方式"] = choice
        todo["处理时间"] = _now()
        todo["pending"] = False
        return window, f"裁决完成（{choice}），窗口进入终态，当前判定版本 {window['判定版本']}"

    # ---------- 待办队列 ----------

    def _create_todo(
        self,
        window: dict[str, Any],
        todo_type: str,
        priority: str,
        *,
        summary: str,
        conflicts: list[dict[str, Any]] | None = None,
        replacements: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        todo_id = _next_id(TODO_TABLE)
        todo = {
            "id": todo_id,
            "待办编号": f"TODO-{todo_id:04d}",
            "窗口编号": window["窗口编号"],
            "窗口ID": window["id"],
            "指标编号": window["指标编号"],
            "关联端点": window["关联端点"],
            "时间窗": window["时间窗"],
            "待办类型": todo_type,
            "优先级": priority,
            "状态": TODO_OPEN,
            "判定版本": window["判定版本"],
            "指标结果摘要": summary,
            "冲突列表": conflicts or [],
            "冲突替换": replacements or {},
            "处理方式": None,
            "处理时间": None,
            "pending": True,
            "abnormal": True,
        }
        store.rows(TODO_TABLE).append(todo)
        return todo

    def _open_abnormal_todo(self, window: dict[str, Any], explain: str, *, retest: bool = False) -> dict[str, Any] | None:
        """异常窗口进入待办；同一窗口同类型不重复建单，复测仍异常则升级优先级。"""
        for todo in store.rows(TODO_TABLE):
            if todo["窗口ID"] == window["id"] and todo["待办类型"] == TODO_ABNORMAL and todo["状态"] == TODO_OPEN:
                todo["判定版本"] = window["判定版本"]
                todo["指标结果摘要"] = explain
                if retest:
                    todo["优先级"] = PRIORITY_HIGH
                return todo
        priority = PRIORITY_HIGH if retest or len(window.get("异常项", [])) > 1 else PRIORITY_MEDIUM
        return self._create_todo(window, TODO_ABNORMAL, priority, summary=explain)

    def _find_open_late_todo(self, window_id: int) -> dict[str, Any] | None:
        for todo in store.rows(TODO_TABLE):
            if (
                todo["窗口ID"] == window_id
                and todo["待办类型"] == TODO_LATE
                and todo["状态"] == TODO_OPEN
            ):
                return todo
        return None

    def list_todos(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(TODO_TABLE))
        if status:
            rows = [row for row in rows if row.get("状态") == status]
        if priority:
            rows = [row for row in rows if row.get("优先级") == priority]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("指标编号", "")) or keyword in str(row.get("关联端点", ""))
            ]
        # 待处理优先、高优先级先行，再按入队顺序稳定排列。
        rows.sort(key=lambda row: (
            0 if row.get("状态") == TODO_OPEN else 1,
            PRIORITY_ORDER.get(str(row.get("优先级")), 9),
            int(row.get("id", 0)),
        ))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    # ---------- 查询：窗口 / 样本 ----------

    def list_windows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        endpoint: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(WINDOW_TABLE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("指标编号", ""))]
        if status:
            rows = [row for row in rows if row.get("状态") == status]
        if endpoint:
            rows = [row for row in rows if endpoint in str(row.get("关联端点", ""))]
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_window_detail(self, window_id: int) -> dict[str, Any] | None:
        window = self.find_window(window_id)
        if window is None:
            return None
        current_codes = set(window.get("样本引用", {}).values())
        all_samples = self._all_samples(window)
        for sample in all_samples:
            # 标注每条样本当前是否仍是结论依据，迟到样本与被替换样本一目了然。
            sample["生效中"] = sample["样本编号"] in current_codes
        todos = [row for row in store.rows(TODO_TABLE) if row.get("窗口ID") == window_id]
        return {
            "window": window,
            "samples": all_samples,
            "todos": todos,
            "版本记录": window.get("版本记录", []),
        }

    def list_samples(
        self,
        *,
        keyword: str | None = None,
        endpoint: str | None = None,
        abnormal_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(SAMPLE_TABLE))
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("指标编号", "")) or keyword in str(row.get("样本编号", ""))
            ]
        if endpoint:
            rows = [row for row in rows if endpoint in str(row.get("关联端点", ""))]
        if abnormal_only:
            rows = [row for row in rows if row.get("异常标记")]
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(self) -> dict[str, int]:
        windows = store.rows(WINDOW_TABLE)
        todos = store.rows(TODO_TABLE)
        samples = store.rows(SAMPLE_TABLE)
        return {
            "联合窗口总数": len(windows),
            "异常窗口数": sum(1 for row in windows if row.get("abnormal")),
            "待处理待办数": sum(1 for row in todos if row.get("状态") == TODO_OPEN),
            "高优先级待办": sum(
                1 for row in todos if row.get("状态") == TODO_OPEN and row.get("优先级") == PRIORITY_HIGH
            ),
            "迟到冲突数": sum(
                1 for row in todos if row.get("待办类型") == TODO_LATE and row.get("状态") == TODO_OPEN
            ),
            "指标样本总数": len(samples),
        }


service = MetricWindowService()
