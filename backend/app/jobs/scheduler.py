import logging
import os
import tempfile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import SchedulerNotRunningError, STATE_STOPPED
from app.auth.models import DBManager
from app.db.models import User
from app.db.session import SessionLocal
from app.jobs.scraper import JobScraper
from app.jobs.matcher import JobMatcher
from app.services.email_service import EmailService
from app.vector_db.profile_store import ProfileStore
from starlette.concurrency import run_in_threadpool
import asyncio
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_scraping_lock = asyncio.Lock()
_is_scraping_active = False
_scheduler_lock_handle = None


def _acquire_process_lock() -> bool:
    """Acquire single-process lock using fcntl so only one worker starts APScheduler."""
    global _scheduler_lock_handle
    try:
        import fcntl
        lock_path = os.path.join(tempfile.gettempdir(), "ai_platform_apscheduler.lock")
        _scheduler_lock_handle = open(lock_path, "a+")
        fcntl.flock(_scheduler_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (ImportError, IOError, OSError):
        logger.info("Another process holds the scheduler lock. APScheduler will not run in this process.")
        return False


def _release_process_lock() -> None:
    """Release single-process lock on scheduler shutdown."""
    global _scheduler_lock_handle
    if _scheduler_lock_handle:
        try:
            import fcntl
            fcntl.flock(_scheduler_lock_handle, fcntl.LOCK_UN)
            _scheduler_lock_handle.close()
        except Exception:
            pass
        _scheduler_lock_handle = None


async def scheduled_scraping_job():
    """
    Finds active users, groups identical search criteria (M16),
    scrapes relevant jobs without blocking the event loop (H5),
    and saves them to ChromaDB. Guarded against concurrent runs.
    """
    global _is_scraping_active
    if _scraping_lock.locked() or _is_scraping_active:
        logger.info("Scheduled scraping task is already running. Skipping duplicate concurrent run (M16).")
        return

    async with _scraping_lock:
        _is_scraping_active = True
        try:
            logger.info("Starting scheduled job scraping task...")
            
            # 1. Fetch all users from DB off-loop (H5)
            try:
                users = await run_in_threadpool(DBManager.get_all_users)
            except Exception as db_err:
                logger.error("Error fetching users for scheduled scrape: %s", db_err)
                return
            
            if not users:
                logger.info("No registered users. Skipping scheduled scrape.")
                return
                
            # 2. Group identical criteria to prevent duplicate scraping runs (M16)
            criteria_groups = {}
            for user in users:
                user_id = user["id"]
                criteria = await run_in_threadpool(DBManager.get_criteria, user_id)
                profile = await run_in_threadpool(ProfileStore.get_profile, user_id) or {}
                suggested_roles = profile.get("suggested_roles") or []
                if isinstance(suggested_roles, str):
                    suggested_roles = [suggested_roles]

                search_titles = []
                if criteria and criteria.get("title"):
                    search_titles.append(criteria["title"].strip())
                for role in suggested_roles:
                    cleaned = str(role).strip()
                    if cleaned and cleaned not in search_titles:
                        search_titles.append(cleaned)

                if not search_titles:
                    continue

                location = criteria.get("location") if criteria else None
                if not location or location.strip().lower() in ["any", "", "all"]:
                    location = "Bengaluru, India"
                else:
                    location = location.strip()

                for search_title in search_titles:
                    group_key = (search_title.lower(), location.lower())
                    if group_key not in criteria_groups:
                        criteria_groups[group_key] = {
                            "search_title": search_title,
                            "location": location,
                            "users": []
                        }
                    criteria_groups[group_key]["users"].append(user)

            if not criteria_groups:
                logger.info("No active job search criteria across registered users. Skipping scrape.")
                return

            logger.info("Grouped criteria into %d unique search target(s) across %d user(s).", len(criteria_groups), len(users))

            # 3. Scrape once per unique criteria group
            for (title_key, loc_key), group_data in criteria_groups.items():
                search_title = group_data["search_title"]
                location = group_data["location"]
                target_users = group_data["users"]

                try:
                    logger.info("Scraping once for unique criterion '%s' in '%s' (%d users)...", search_title, location, len(target_users))
                    jobs = await run_in_threadpool(
                        JobScraper.scrape,
                        search_term=search_title,
                        location=location,
                        results_wanted=25,
                        hours_old=48
                    )
                    
                    if jobs:
                        await run_in_threadpool(JobMatcher.upsert_jobs, jobs)
                        logger.info("Successfully scraped and stored %d jobs for criteria '%s'.", len(jobs), search_title)
                        
                        # Match and notify each user in the group
                        for user in target_users:
                            user_id = user["id"]
                            user_email = user.get("email")
                            try:
                                matched_jobs = await run_in_threadpool(
                                    JobMatcher.match_jobs_for_user,
                                    user_id,
                                    limit=10
                                )
                                high_matches = [mj for mj in matched_jobs if mj.get("match_score", 0) >= 80.0]
                                
                                for j in high_matches:
                                    await run_in_threadpool(
                                        DBManager.add_notification,
                                        user_id=user_id,
                                        title="New Job Match Found!",
                                        message=f"'{j['title']}' at '{j['company']}' matches {j['match_score']}% of your profile skills.",
                                        type="job_alert"
                                    )
                                    
                                    if user_email and user.get("email_notifications", True):
                                        await run_in_threadpool(
                                            EmailService.send_job_match_alert,
                                            to_email=user_email,
                                            job_title=j['title'],
                                            company=j['company'],
                                            match_score=j['match_score']
                                        )
                            except Exception as match_err:
                                logger.error("Error checking matches/generating notifications for user %s: %s", user_id, match_err)
                    else:
                        logger.info("No jobs found for criterion '%s' in '%s'.", search_title, location)
                except Exception as e:
                    logger.error("Error in scheduler scraping for '%s': %s", search_title, e, exc_info=True)

                # Non-blocking pause between distinct criteria scrapes
                await asyncio.sleep(2)

        finally:
            _is_scraping_active = False


async def scheduled_cleanup_job():
    """Daily cleanup of stale job embeddings and expired background job metadata."""
    logger.info("Starting scheduled stale jobs cleanup task...")
    try:
        await run_in_threadpool(JobMatcher.cleanup_old_jobs, days=30)
    except Exception as e:
        logger.error("Error in scheduler Chroma cleanup job: %s", e)

    try:
        from app.utils.bg_jobs import cleanup_expired_jobs
        purged = await run_in_threadpool(cleanup_expired_jobs, max_retention_days=7)
        if purged > 0:
            logger.info("Scheduler purged %d expired background job records.", purged)
    except Exception as e:
        logger.error("Error in background job expiration cleanup: %s", e)


def _ensure_scheduler_loop():
    """Rebind the scheduler to a live event loop when reused across tests or restarts."""
    loop = getattr(scheduler, "_eventloop", None)
    if loop is not None and not getattr(loop, "is_closed", False):
        return loop

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    scheduler._eventloop = loop
    return loop


def start_scheduler():
    """Start APScheduler with single-process lock guard."""
    if scheduler.running:
        return

    # In multi-worker environments, ensure only one worker runs the scheduler
    if not _acquire_process_lock():
        return

    _ensure_scheduler_loop()

    try:
        scheduler.add_job(
            scheduled_scraping_job,
            'interval',
            hours=12,
            id='job_scraper_job',
            replace_existing=True
        )
        scheduler.add_job(
            scheduled_cleanup_job,
            'interval',
            days=1,
            id='db_cleanup_job',
            replace_existing=True
        )

        # Weekly job summary - Every Sunday at 9 AM
        scheduler.add_job(
            send_weekly_job_summary,
            'cron',
            day_of_week=6,  # Sunday
            hour=9,
            minute=0,
            id='weekly_job_summary',
            name='Weekly Job Application Summary',
            replace_existing=True
        )

        # Daily job alerts - Every day at 8 AM
        scheduler.add_job(
            send_daily_job_alerts,
            'cron',
            hour=8,
            minute=0,
            id='daily_job_alerts',
            name='Daily Job Alerts',
            replace_existing=True
        )

        scheduler.start()
        logger.info("APScheduler started successfully.")
    except RuntimeError as exc:
        if "Event loop is closed" in str(exc):
            scheduler._eventloop = asyncio.new_event_loop()
            asyncio.set_event_loop(scheduler._eventloop)
            scheduler.start()
            logger.info("APScheduler started successfully after resetting closed event loop.")
        else:
            raise


def get_scheduler_status() -> dict:
    """Return runtime status of the scheduler and scheduled jobs."""
    is_running = scheduler.running
    jobs_info = []
    if is_running:
        for job in scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
            })
    return {
        "running": is_running,
        "job_count": len(jobs_info),
        "jobs": jobs_info
    }


async def send_weekly_job_summary():
    """Send weekly application summary every Sunday at 9 AM"""
    try:
        logger.info("📧 Sending weekly job application summaries...")
        users = await run_in_threadpool(DBManager.get_all_users)
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            weekly_apps = await run_in_threadpool(DBManager.get_weekly_applications, user["id"], days=7)
            
            if weekly_apps:
                await run_in_threadpool(
                    EmailService.send_weekly_summary_email,
                    email=user["email"],
                    full_name=user.get("full_name", "User"),
                    total_applications=len(weekly_apps),
                    applications=weekly_apps
                )
                logger.info("Weekly summary sent to %s", user['email'])
    except Exception as e:
        logger.error("Error in weekly job summary: %s", e)


async def send_daily_job_alerts():
    """Send daily job alerts every day at 8 AM"""
    try:
        logger.info("📧 Sending daily job alerts...")
        users = await run_in_threadpool(DBManager.get_all_users)
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            try:
                matching_jobs = await run_in_threadpool(JobMatcher.match_jobs_for_user, user["id"], limit=10)
                
                if matching_jobs:
                    await run_in_threadpool(
                        EmailService.send_job_alert_email,
                        email=user["email"],
                        full_name=user.get("full_name", "User"),
                        jobs=matching_jobs
                    )
                    logger.info("Daily alert sent to %s", user['email'])
            except Exception as match_err:
                logger.error("Error matching jobs for user %s: %s", user['id'], match_err)
    except Exception as e:
        logger.error("Error in daily job alerts: %s", e)


def shutdown_scheduler(wait: bool = False):
    """Shutdown the scheduler safely and idempotently, releasing the process lock."""
    if not scheduler:
        _release_process_lock()
        return

    try:
        if scheduler.running:
            shutdown_impl = getattr(AsyncIOScheduler.shutdown, "__wrapped__", None)
            if shutdown_impl is not None:
                shutdown_impl(scheduler, wait=wait)
            else:
                scheduler.shutdown(wait=wait)
            scheduler.state = STATE_STOPPED
            logger.info("APScheduler shut down successfully.")
        else:
            scheduler.state = STATE_STOPPED
            logger.info("APScheduler already not running; skipping shutdown.")
    except SchedulerNotRunningError:
        scheduler.state = STATE_STOPPED
        logger.info("APScheduler already not running; skipping shutdown.")
    except RuntimeError:
        scheduler.state = STATE_STOPPED
        logger.info("APScheduler already not running; skipping shutdown.")
    except Exception as e:
        scheduler.state = STATE_STOPPED
        logger.warning(f"Warning during scheduler shutdown: {e}")
    finally:
        _release_process_lock()
