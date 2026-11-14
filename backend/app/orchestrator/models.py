from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, func
from app.db.session import Base

class WorkflowModel(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    goal = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowTaskModel(Base):
    __tablename__ = "workflow_tasks"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, nullable=False, index=True)
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    dependencies_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
