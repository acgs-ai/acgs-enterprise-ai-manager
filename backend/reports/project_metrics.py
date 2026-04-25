"""
Project Metrics Calculator
Calculates project-related metrics for reporting dashboard
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

from backend.models.project import Project

logger = logging.getLogger(__name__)


class ProjectMetrics:
    """Calculate project-related metrics for reporting."""

    @staticmethod
    async def get_health_overview(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get overall project health overview.

        Args:
            db: Database session

        Returns:
            Dict with project health metrics
        """
        # Get projects by status
        status_query = select(
            Project.status,
            func.count(Project.id).label('count')
        ).group_by(Project.status)

        result = await db.execute(status_query)
        rows = result.all()

        by_status = {row.status: row.count for row in rows}

        # Get projects by health
        health_query = select(
            Project.health_status,
            func.count(Project.id).label('count')
        ).group_by(Project.health_status)

        result = await db.execute(health_query)
        rows = result.all()

        by_health = {row.health_status: row.count for row in rows}

        total_projects = sum(by_status.values())
        healthy_projects = by_health.get('healthy', 0) + by_health.get('on_track', 0)
        health_rate = (healthy_projects / total_projects * 100) if total_projects > 0 else 0

        return {
            'total_projects': total_projects,
            'by_status': by_status,
            'by_health': by_health,
            'health_rate': round(health_rate, 2)
        }

    @staticmethod
    async def get_completion_metrics(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get project completion metrics.

        Args:
            db: Database session

        Returns:
            Dict with completion metrics
        """
        # Average completion percentage
        avg_completion_query = select(
            func.avg(Project.completion_percentage).label('avg_completion')
        ).where(Project.status != 'completed')

        result = await db.execute(avg_completion_query)
        avg_completion = result.scalar() or 0

        # Projects by completion range
        completion_range_query = select(
            case(
                (Project.completion_percentage < 25, '0-25%'),
                (Project.completion_percentage < 50, '25-50%'),
                (Project.completion_percentage < 75, '50-75%'),
                (Project.completion_percentage < 100, '75-100%'),
                else_='100%'
            ).label('range'),
            func.count(Project.id).label('count')
        ).group_by('range')

        result = await db.execute(completion_range_query)
        rows = result.all()

        by_range = {row.range: row.count for row in rows}

        return {
            'average_completion': round(avg_completion, 2),
            'by_range': by_range
        }

    @staticmethod
    async def get_timeline_metrics(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get project timeline metrics.

        Args:
            db: Database session

        Returns:
            Dict with timeline metrics
        """
        now = datetime.utcnow()

        # On-time projects
        on_time_query = select(func.count(Project.id)).where(
            and_(
                Project.end_date >= now,
                Project.status != 'completed'
            )
        )

        result = await db.execute(on_time_query)
        on_time = result.scalar() or 0

        # Overdue projects
        overdue_query = select(func.count(Project.id)).where(
            and_(
                Project.end_date < now,
                Project.status != 'completed'
            )
        )

        result = await db.execute(overdue_query)
        overdue = result.scalar() or 0

        # Completed projects
        completed_query = select(func.count(Project.id)).where(
            Project.status == 'completed'
        )

        result = await db.execute(completed_query)
        completed = result.scalar() or 0

        total = on_time + overdue + completed
        on_time_rate = (on_time / total * 100) if total > 0 else 0

        return {
            'on_time': on_time,
            'overdue': overdue,
            'completed': completed,
            'on_time_rate': round(on_time_rate, 2)
        }

    @staticmethod
    async def get_budget_metrics(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get project budget metrics.

        Args:
            db: Database session

        Returns:
            Dict with budget metrics
        """
        # Total budget
        total_budget_query = select(
            func.sum(Project.budget).label('total_budget')
        ).where(Project.status != 'completed')

        result = await db.execute(total_budget_query)
        total_budget = result.scalar() or 0

        # Total spent
        total_spent_query = select(
            func.sum(Project.spent).label('total_spent')
        ).where(Project.status != 'completed')

        result = await db.execute(total_spent_query)
        total_spent = result.scalar() or 0

        # Budget utilization
        budget_utilization = (total_spent / total_budget * 100) if total_budget > 0 else 0

        # Projects over budget
        over_budget_query = select(func.count(Project.id)).where(
            and_(
                Project.spent > Project.budget,
                Project.status != 'completed'
            )
        )

        result = await db.execute(over_budget_query)
        over_budget = result.scalar() or 0

        return {
            'total_budget': float(total_budget),
            'total_spent': float(total_spent),
            'remaining': float(total_budget - total_spent),
            'budget_utilization': round(budget_utilization, 2),
            'over_budget_count': over_budget
        }

    @staticmethod
    async def get_risk_metrics(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get project risk metrics.

        Args:
            db: Database session

        Returns:
            Dict with risk metrics
        """
        # Projects by risk level
        risk_query = select(
            Project.risk_level,
            func.count(Project.id).label('count')
        ).where(Project.status != 'completed').group_by(Project.risk_level)

        result = await db.execute(risk_query)
        rows = result.all()

        by_risk = {row.risk_level: row.count for row in rows}

        # High-risk projects
        high_risk = by_risk.get('high', 0) + by_risk.get('critical', 0)
        total = sum(by_risk.values())
        high_risk_percentage = (high_risk / total * 100) if total > 0 else 0

        return {
            'by_risk_level': by_risk,
            'high_risk_count': high_risk,
            'high_risk_percentage': round(high_risk_percentage, 2)
        }
