from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import load_only
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.db.session import SessionLocal
from app.db.models import ApplicationHistory, Notification
from sqlalchemy import func
from collections import defaultdict, Counter

router = APIRouter(prefix="/analytics", tags=["analytics"])

def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _build_analytics_dashboard(user_id: int) -> Dict:
    db = SessionLocal()
    try:
        # Get applications (L3: load only needed columns, avoiding massive cover_letter/notes blobs)
        all_apps = db.query(ApplicationHistory).options(
            load_only(
                ApplicationHistory.id,
                ApplicationHistory.job_title,
                ApplicationHistory.company,
                ApplicationHistory.applied_at,
                ApplicationHistory.status,
            )
        ).filter(ApplicationHistory.user_id == user_id).all()
        
        # 1. Applications over time (last 30 days)
        now_utc = datetime.now(timezone.utc)
        thirty_days_ago = now_utc - timedelta(days=30)
        apps_by_date: Dict[str, int] = defaultdict(int)
        
        for app in all_apps:
            applied_at_utc = _ensure_utc(app.applied_at)
            if applied_at_utc >= thirty_days_ago:
                date_key = applied_at_utc.strftime('%Y-%m-%d')
                apps_by_date[date_key] += 1
        
        timeline_data = [
            {
                "date": date,
                "applications": count,
                "cumulative": sum(apps_by_date[d] for d in sorted(apps_by_date.keys()) if d <= date)
            }
            for date, count in sorted(apps_by_date.items())
        ]
        
        # 2. Status breakdown
        status_counts: Counter[str] = Counter()
        for app in all_apps:
            status_counts[app.status or 'applied'] += 1
        
        status_data = [
            {"name": status, "value": count, "color": _get_status_color(status)}
            for status, count in status_counts.items()
        ]
        
        # 3. Summary stats
        total_applications = len(all_apps)
        success_count = sum(1 for app in all_apps if app.status in ['offered', 'interview_scheduled'])
        success_rate = (success_count / total_applications * 100) if total_applications > 0 else 0
        
        # 4. Recent applications
        recent_apps = sorted(all_apps, key=lambda x: _ensure_utc(x.applied_at), reverse=True)[:5]
        recent_data = [
            {
                "company": app.company,
                "job_title": app.job_title,
                "status": app.status,
                "applied_date": _ensure_utc(app.applied_at).strftime('%Y-%m-%d'),
                "days_ago": (now_utc - _ensure_utc(app.applied_at)).days
            }
            for app in recent_apps
        ]
        
        # 5. Company frequency (most applied to)
        company_counts = Counter(app.company for app in all_apps)
        top_companies = company_counts.most_common(10)
        
        companies_data = [
            {"company": company, "applications": count}
            for company, count in top_companies
        ]
        
        # 6. Job title frequency
        job_title_counts = Counter(app.job_title for app in all_apps)
        top_titles = job_title_counts.most_common(8)
        
        titles_data = [
            {"title": title, "count": count}
            for title, count in top_titles
        ]
        
        # 7. Monthly trend
        monthly_data: Dict[str, int] = defaultdict(int)
        for app in all_apps:
            month_key = _ensure_utc(app.applied_at).strftime('%B %Y')
            monthly_data[month_key] += 1
        
        monthly_trend = [
            {"month": month, "count": count}
            for month, count in sorted(monthly_data.items())[-6:]  # Last 6 months
        ]
        
        return {
            "summary": {
                "total_applications": total_applications,
                "success_count": success_count,
                "success_rate": f"{success_rate:.1f}%",
                "avg_per_week": f"{total_applications / 4:.1f}" if total_applications > 0 else "0",
                "status_breakdown": {
                    "applied": status_counts.get('applied', 0),
                    "interview_scheduled": status_counts.get('interview_scheduled', 0),
                    "offered": status_counts.get('offered', 0),
                    "rejected": status_counts.get('rejected', 0),
                }
            },
            "timeline": timeline_data,
            "status_distribution": status_data,
            "recent_applications": recent_data,
            "top_companies": companies_data,
            "top_job_titles": titles_data,
            "monthly_trend": monthly_trend,
            "recommendations": _generate_recommendations(status_counts, total_applications)
        }
    finally:
        db.close()

@router.get("/dashboard")
async def get_analytics_dashboard(current_user: dict = Depends(get_current_user)):
    """
    Get comprehensive analytics dashboard data
    """
    return await run_in_threadpool(_build_analytics_dashboard, current_user["id"])

def score_distribution(jobs):
    import math
    from statistics import mean, median
    scores = [float(job['match_score']) for job in jobs
              if isinstance(job.get('match_score'), (int, float))
              and math.isfinite(job['match_score']) and 0 <= job['match_score'] <= 100]
    bins = [{'range': f'{start}-{start+20}%', 'count': 0} for start in range(0, 100, 20)]
    for score in scores:
        bins[min(int(score // 20), 4)]['count'] += 1
    return {'bins': bins, 'average_match': round(mean(scores), 1) if scores else None,
            'median_match': median(scores) if scores else None, 'sample_size': len(scores)}


@router.get("/match-score-distribution")
async def get_match_score_distribution(current_user: dict = Depends(get_current_user)):
    from app.jobs.matcher import JobMatcher
    from app.jobs.filter import JobFilter
    jobs = await run_in_threadpool(JobMatcher.match_jobs_for_user, current_user['id'], limit=100, hours_old=168)
    return score_distribution(JobFilter.live_jobs(jobs, 168))


@router.get("/missing-skills")
async def get_missing_skills(current_user: dict = Depends(get_current_user)):
    from app.vector_db.profile_store import ProfileStore
    from app.jobs.repository import list_live_jobs
    from app.market.router import skills_in_description
    from app.services.esco_service import ESCOSkillService
    profile = await run_in_threadpool(ProfileStore.get_profile, current_user['id'])
    skills = (profile or {}).get('skills', [])
    jobs = await run_in_threadpool(list_live_jobs, 168)
    counts = Counter()
    for job in jobs:
        for required in skills_in_description(job.get('description', '')):
            if not any(ESCOSkillService.evaluate_skill_relation(required, candidate)[0] == 'exact' for candidate in skills):
                counts[required] += 1
    return {
        'missing_skills': [{'skill': skill, 'occurrences': count, 'trend': None} for skill, count in counts.most_common(10)],
        'recommendation': 'Review recurring requirements against your target role.' if counts else 'No missing-skill evidence in the current listing sample.',
        'sample_size': len(jobs),
    }


@router.get("/conversion-funnel")
async def get_conversion_funnel(current_user: dict = Depends(get_current_user)):
    """Get conversion funnel: Applied -> Interview -> Offer"""
    db = SessionLocal()
    try:
        user_id = current_user["id"]
        all_apps = db.query(ApplicationHistory).filter(
            ApplicationHistory.user_id == user_id
        ).all()
        
        applied = len(all_apps)
        interviews = sum(1 for app in all_apps if app.status == 'interview_scheduled')
        offers = sum(1 for app in all_apps if app.status == 'offered')
        
        return {
            "funnel": [
                {"stage": "Applied", "count": applied, "percentage": 100 if applied else 0},
                {"stage": "Interview", "count": interviews, "percentage": (interviews/applied*100) if applied > 0 else 0},
                {"stage": "Offer", "count": offers, "percentage": (offers/applied*100) if applied > 0 else 0},
            ],
            "conversion_rates": {
                "applied_to_interview": f"{(interviews/applied*100):.1f}%" if applied > 0 else "0%",
                "interview_to_offer": f"{(offers/interviews*100):.1f}%" if interviews > 0 else "0%",
                "overall": f"{(offers/applied*100):.1f}%" if applied > 0 else "0%"
            }
        }
    finally:
        db.close()

def _get_status_color(status: str) -> str:
    """Get color for status badge"""
    colors = {
        'applied': '#3b82f6',
        'interview_scheduled': '#f59e0b',
        'offered': '#10b981',
        'rejected': '#ef4444',
    }
    return colors.get(status, '#6b7280')

def _generate_recommendations(status_counts: Counter[str], total: int) -> List[str]:
    """Generate actionable recommendations based on analytics"""
    recommendations: List[str] = []
    
    if total == 0:
        recommendations.append("Start applying to jobs to generate analytics")
    elif status_counts.get('offered', 0) / total < 0.1:
        recommendations.append("Increase application volume or improve resume tailoring")
    
    if status_counts.get('interview_scheduled', 0) / total < 0.2:
        recommendations.append("Consider practicing interviews or refining your profile")
    
    return recommendations
