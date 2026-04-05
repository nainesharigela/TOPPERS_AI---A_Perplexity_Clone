"""
Scheduler module for TOPPERS AI Business Intelligence.
Uses APScheduler to run recurring competitor crawls.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import time
from datetime import datetime

scheduler = BackgroundScheduler(daemon=True)
_initialized = False


def run_scheduled_crawl():
    """Check for due schedules and run them."""
    try:
        import db
        import scraper

        due_schedules = db.get_due_schedules()
        if not due_schedules:
            return

        for sched in due_schedules:
            comp_id = sched['competitor_id']
            comp_name = sched.get('competitor_name', 'Unknown')
            comp_url = sched.get('competitor_url', '')
            frequency = sched.get('frequency', 'daily')

            print(f"⏰ Running scheduled crawl for: {comp_name} ({comp_url})")

            try:
                # Use BS4 only for scheduled crawls to save API tokens (per user preference)
                result = scraper.scrape_competitor(comp_url, use_gemini=False)

                if result['error']:
                    # Save failed crawl
                    db.save_crawl(comp_id, [], result['duration_ms'], 'error', result['error'])
                    print(f"❌ Scheduled crawl failed for {comp_name}: {result['error']}")
                else:
                    # Save successful crawl
                    crawl_id = db.save_crawl(comp_id, result['products'], result['duration_ms'])

                    # Compare with previous crawl
                    prev = db.get_previous_crawl(comp_id)
                    if prev:
                        changes = scraper.compare_crawls(prev['products'], result['products'])
                        if changes['total_changes'] > 0:
                            summary = scraper.generate_change_summary(comp_name, changes)
                            db.save_report(comp_id, comp_name, summary, changes)
                            print(f"📊 Change report saved: {summary}")
                        else:
                            print(f"✅ No changes detected for {comp_name}")
                    else:
                        print(f"✅ First crawl for {comp_name}, no comparison available")

            except Exception as e:
                print(f"❌ Scheduled crawl error for {comp_name}: {e}")

            # Update the schedule
            db.update_schedule_run(sched['id'], frequency)

    except Exception as e:
        print(f"Scheduler run error: {e}")


def init_scheduler():
    """Initialize and start the background scheduler."""
    global _initialized
    if _initialized:
        return

    # Check for due crawls every 5 minutes
    scheduler.add_job(
        func=run_scheduled_crawl,
        trigger=IntervalTrigger(minutes=5),
        id='check_scheduled_crawls',
        name='Check and run scheduled competitor crawls',
        replace_existing=True
    )

    scheduler.start()
    _initialized = True
    print("⏰ Background scheduler started (checking every 5 minutes)")

    # Shutdown scheduler gracefully when the app exits
    atexit.register(lambda: scheduler.shutdown(wait=False))


def force_run_now():
    """Manually trigger all due scheduled crawls immediately."""
    run_scheduled_crawl()
