"""Guided demo scenarios with judge quotas."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.security.sessions import Session, consume_scenario_quota, require_judge_or_operator, require_viewer
from app.services import scenarios

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


class ScenarioRun(BaseModel):
    job: dict = Field(default_factory=lambda: dict(scenarios.DEFAULT_JOB))


@router.get("")
async def list_scenarios(session: Session = Depends(require_viewer)):
    return {"scenarios": [{"id": key, "description": value} for key, value in scenarios.SCENARIOS.items()]}


@router.post("/{name}/run", status_code=status.HTTP_201_CREATED)
async def run(name: str, body: ScenarioRun, request: Request,
              session: Session = Depends(require_judge_or_operator)):
    name = name.upper()
    if name not in scenarios.SCENARIOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown scenario")
    db = get_database()
    if session.role == "judge":
        allowed = await consume_scenario_quota(db, session)
        if not allowed:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Judge scenario quota exhausted - start a new judge session")

    async def handler() -> dict:
        return await scenarios.run_scenario(db, name, actor=session.role, job=body.job or None)

    return await mutate(request, {"scenario": name, **body.model_dump()}, handler)


@router.get("/runs")
async def runs(limit: int = 20, session: Session = Depends(require_viewer)):
    return {"runs": await scenarios.list_runs(get_database(), limit=min(limit, 100))}


@router.get("/runs/{run_id}")
async def run_detail(run_id: str, session: Session = Depends(require_viewer)):
    doc = await scenarios.get_run(get_database(), run_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return doc
