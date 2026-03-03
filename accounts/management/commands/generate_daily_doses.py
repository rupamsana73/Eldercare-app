"""
Management command to generate daily doses and manage dose log cleanup.

This should be run once per day (preferably at midnight via cron/celery):
python manage.py generate_daily_doses

Functions:
1. Generate tomorrow's dose logs based on active medicines
2. Mark overdue doses (>24h) as missed
3. Clean up old dose logs (optional)
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import Medicine, MedicineDoseLog
from datetime import date, timedelta, time as dt_time
import calendar
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate daily dose logs and manage dose log lifecycle"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=1,
            help='Number of days ahead to generate doses (default: 1 for tomorrow)'
        )
        parser.add_argument(
            '--mark-missed',
            action='store_true',
            help='Mark overdue pending doses as missed'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove dose logs older than 90 days'
        )

    def handle(self, *args, **options):
        days_ahead = options.get('days_ahead', 1)
        mark_missed = options.get('mark_missed', True)
        cleanup = options.get('cleanup', False)

        self.stdout.write("Starting daily dose generation...")

        try:
            # 1. Generate doses for future days
            self.generate_future_doses(days_ahead)

            # 2. Mark missed doses
            if mark_missed:
                self.mark_missed_doses()

            # 3. Cleanup old logs
            if cleanup:
                self.cleanup_old_doses()

            self.stdout.write(
                self.style.SUCCESS('✓ Daily dose generation completed successfully')
            )

        except Exception as e:
            logger.error(f"Error in generate_daily_doses: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'✗ Error: {str(e)}')
            )

    def generate_future_doses(self, days_ahead=1):
        """Generate dose logs for specified days ahead."""
        target_date = date.today() + timedelta(days=days_ahead)
        weekday = calendar.day_abbr[target_date.weekday()]

        active_medicines = Medicine.objects.filter(status='active')
        created_count = 0

        for medicine in active_medicines:
            try:
                # Check if medicine should be taken on target_date
                freq = (medicine.frequency_type or "").lower().strip()
                should_schedule = False

                if freq == "daily":
                    should_schedule = True
                elif freq == "weekly" and medicine.days_of_week:
                    days = [d.strip() for d in (medicine.days_of_week or "").split(",")]
                    should_schedule = weekday in days

                if not should_schedule:
                    continue

                # Get scheduled times
                medicine_times = medicine.times.all().order_by('time')

                if medicine_times.exists():
                    # Use existing MedicineTime objects
                    for med_time in medicine_times:
                        log, created = MedicineDoseLog.objects.get_or_create(
                            user=medicine.user,
                            medicine=medicine,
                            scheduled_time=med_time.time,
                            date=target_date,
                            defaults={'status': 'Pending'}
                        )
                        if created:
                            created_count += 1
                else:
                    # No MedicineTime objects - generate based on dose_per_day
                    dose_per_day = medicine.dose_per_day or 1
                    times = self.get_distributed_times(dose_per_day)

                    for scheduled_time in times:
                        log, created = MedicineDoseLog.objects.get_or_create(
                            user=medicine.user,
                            medicine=medicine,
                            scheduled_time=scheduled_time,
                            date=target_date,
                            defaults={'status': 'Pending'}
                        )
                        if created:
                            created_count += 1

            except Exception as e:
                logger.error(
                    f"Error generating doses for medicine {medicine.id}: {str(e)}"
                )
                continue

        self.stdout.write(
            f"  Generated {created_count} dose logs for {target_date}"
        )

    def mark_missed_doses(self):
        """Mark overdue pending doses as missed."""
        from django.utils.timezone import now

        overdue_logs = MedicineDoseLog.objects.filter(
            status='Pending',
            date__lt=date.today()
        )

        marked_count = 0
        for dose_log in overdue_logs:
            try:
                dose_log.mark_as_missed()
                marked_count += 1
            except Exception as e:
                logger.error(f"Error marking dose as missed: {str(e)}")
                continue

        self.stdout.write(f"  Marked {marked_count} overdue doses as missed")

    def cleanup_old_doses(self, days_old=90):
        """Remove dose logs older than specified days."""
        cutoff_date = date.today() - timedelta(days=days_old)

        deleted_count, _ = MedicineDoseLog.objects.filter(
            date__lt=cutoff_date
        ).delete()

        self.stdout.write(f"  Cleaned up {deleted_count} old dose logs")

    @staticmethod
    def get_distributed_times(dose_per_day):
        """Distribute doses evenly throughout the day."""
        if dose_per_day == 1:
            return [dt_time(9, 0)]
        elif dose_per_day == 2:
            return [dt_time(8, 0), dt_time(20, 0)]
        elif dose_per_day == 3:
            return [dt_time(8, 0), dt_time(13, 0), dt_time(20, 0)]
        else:
            # Generic distribution
            times = []
            hours_interval = 24 // dose_per_day
            for i in range(dose_per_day):
                hour = (8 + i * hours_interval) % 24
                times.append(dt_time(hour, 0))
            return times
