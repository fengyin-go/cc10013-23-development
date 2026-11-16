"""指标联合窗口接口。

围绕「按指标编号建立联合窗口」组织：窗口列表/详情、样本进入（含迟到冲突）、
发布、复测、迟到裁决，以及监控待处理队列；列表统一分页，业务判断全部下沉到服务层。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.metric_window import (
    ARBITRATION_CHOICES,
    REQUIRED_SAMPLE_FIELDS,
    WINDOW_COLLECTING,
    WINDOW_FINALIZED,
    WINDOW_PUBLISHED,
    service,
)

router = APIRouter(prefix="/api/metric-window", tags=["指标联合窗口"])

WINDOW_STATUSES = [WINDOW_COLLECTING, WINDOW_PUBLISHED, WINDOW_FINALIZED]
PRIORITIES = ["高", "中", "低"]


@router.get("/stats")
def stats() -> dict[str, int]:
    """联合窗口看板卡片：窗口、异常、待办与迟到冲突计数。"""
    return service.stats()


@router.get("/windows", response_model=PageResult[dict])
def list_windows(
    keyword: str | None = Query(default=None, description="按指标编号检索"),
    status: str | None = Query(default=None, description="采集中、已发布、终态裁决"),
    endpoint: str | None = Query(default=None, description="按关联端点筛选"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """监控列表：按指标编号搜索、端点与状态筛选、分页，定位异常端点后可回到同一窗口。"""
    if status and status not in WINDOW_STATUSES:
        raise HTTPException(status_code=400, detail=f"窗口状态仅支持 {'、'.join(WINDOW_STATUSES)}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_windows(
        keyword=keyword, status=status, endpoint=endpoint, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/windows/{window_id}")
def get_window(window_id: int) -> dict:
    """窗口结果详情：指标编号、时间窗与判定版本可回溯三条原始样本，不只展示汇总数。"""
    detail = service.get_window_detail(window_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"联合窗口 {window_id} 不存在或已归档")
    return detail


@router.post("/windows/{window_id}/publish", response_model=ActionResult)
def publish_window(window_id: int) -> ActionResult:
    """三项样本到齐后手动发布联合结论，并保存当时依据快照。"""
    window, message = service.publish_window(window_id)
    if window is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=window)


@router.post("/windows/{window_id}/retest", response_model=ActionResult)
def retest_window(window_id: int) -> ActionResult:
    """复测一窗指标：联合结论分别引用三项样本，并生成新判定版本。"""
    window, message = service.retest_window(window_id)
    if window is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=window)


@router.post("/windows/{window_id}/arbitrate", response_model=ActionResult)
def arbitrate(window_id: int, payload: EntryPayload) -> ActionResult:
    """迟到样本终态取舍：维持原结论或采纳更正，裁决后窗口只有一个可解释结论。"""
    choice = str(payload.values.get("choice") or "").strip()
    if not choice:
        return ActionResult(ok=False, message="缺少裁决方式 choice", entry=None)
    window, message = service.arbitrate(window_id, choice)
    if window is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=window)


@router.get("/samples", response_model=PageResult[dict])
def list_samples(
    keyword: str | None = Query(default=None, description="按指标编号或样本编号检索"),
    endpoint: str | None = Query(default=None, description="按关联端点筛选"),
    abnormal_only: bool = Query(default=False, description="只看异常样本，联动标出异常端点"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """样本列表：异常样本带异常标记，可按端点定位同一窗口的异常来源。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_samples(
        keyword=keyword, endpoint=endpoint, abnormal_only=abnormal_only, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/samples", response_model=ActionResult)
def ingest_sample(payload: EntryPayload) -> ActionResult:
    """采集指标样本进入：三项指标、窗口身份与判定版本一起写入；迟到样本形成冲突待裁决。"""
    values = payload.values
    missing = [field for field in REQUIRED_SAMPLE_FIELDS if not str(values.get(field) or "").strip()]
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    sample, errors, conflict = service.ingest_sample(values)
    if sample is None:
        return ActionResult(ok=False, message="；".join(errors))
    message = "指标样本已进入联合窗口"
    if conflict is not None:
        message = "样本迟到并与已发布结论冲突，已进入高优先级待裁决队列，原结论暂不变更"
    return ActionResult(ok=True, message=message, entry={"sample": sample, "conflict": conflict})


@router.get("/todos", response_model=PageResult[dict])
def list_todos(
    status: str | None = Query(default=None, description="待处理、已处理"),
    priority: str | None = Query(default=None, description="高、中、低"),
    keyword: str | None = Query(default=None, description="按指标编号或关联端点检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """监控待处理队列：收存指标结果，高优先级先行，按指标编号可搜索、分页。"""
    if priority and priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"优先级仅支持 {'、'.join(PRIORITIES)}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_todos(
        status=status, priority=priority, keyword=keyword, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)
