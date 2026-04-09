from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.ai.agent import run_agent

router = APIRouter()


class AgentRequest(BaseModel):
    question: str


@router.post("/{ticker}")
def agent_analyse(ticker: str, body: AgentRequest, db: Session = Depends(get_db)):
    verdict = run_agent(ticker, body.question, db)
    return {
        "ticker":         verdict.ticker,
        "question":       verdict.question,
        "recommendation": verdict.recommendation,
        "confidence":     verdict.confidence,
        "reasoning":      verdict.reasoning,
        "stop_loss":      verdict.stop_loss,
        "target":         verdict.target,
        "steps": [
            {"name": s.name, "result": s.result, "score": s.score}
            for s in verdict.steps
        ],
    }
