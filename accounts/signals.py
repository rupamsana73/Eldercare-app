from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, Medicine, MedicineDoseLog
from datetime import date, time as dt_time, time, timedelta
import calendar


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a UserProfile when a new User is created.
    This ensures every user has a profile.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Automatically save the UserProfile when the User is saved.
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_save, sender=Medicine)
def generate_dose_logs_for_medicine(sender, instance, created, **kwargs):
    """
    Automatically generate today's dose logs when a medicine is created or updated.
    
    Logic:
    1. Check if medicine is active and scheduled for today
    2. Get scheduled times from MedicineTime objects (or create from dose_per_day)
    3. Create MedicineDoseLog entries for today
    """
    if not created:
        return  # Only process on creation, not on updates
    
    try:
        medicine = instance
        user = medicine.user
        today = date.today()
        
        # Check if medicine is active
        if medicine.status != 'active':
            return
        
        # Check if medicine should be taken today based on frequency
        freq = (medicine.frequency_type or "").lower().strip()
        weekday = calendar.day_abbr[today.weekday()]
        should_schedule_today = False
        
        if freq == "daily":
            should_schedule_today = True
        elif freq == "weekly" and medicine.days_of_week:
            days = [d.strip() for d in (medicine.days_of_week or "").split(",")]
            should_schedule_today = weekday in days
        
        if not should_schedule_today:
            return
        
        # Get scheduled times from MedicineTime objects
        medicine_times = medicine.times.all().order_by('time')
        
        if medicine_times.exists():
            # Use existing MedicineTime objects
            for med_time in medicine_times:
                MedicineDoseLog.objects.get_or_create(
                    user=user,
                    medicine=medicine,
                    scheduled_time=med_time.time,
                    date=today,
                    defaults={'status': 'Pending'}
                )
        else:
            # No MedicineTime objects - create logs based on dose_per_day
            # Distribute doses evenly throughout the day
            dose_per_day = medicine.dose_per_day or 1
            
            if dose_per_day == 1:
                # Single dose at 9:00 AM
                scheduled_time = dt_time(9, 0)
                MedicineDoseLog.objects.get_or_create(
                    user=user,
                    medicine=medicine,
                    scheduled_time=scheduled_time,
                    date=today,
                    defaults={'status': 'Pending'}
                )
            elif dose_per_day == 2:
                # Two doses: 8:00 AM and 8:00 PM
                for hour in [8, 20]:
                    scheduled_time = dt_time(hour, 0)
                    MedicineDoseLog.objects.get_or_create(
                        user=user,
                        medicine=medicine,
                        scheduled_time=scheduled_time,
                        date=today,
                        defaults={'status': 'Pending'}
                    )
            elif dose_per_day == 3:
                # Three doses: 8:00 AM, 1:00 PM, 8:00 PM
                for hour in [8, 13, 20]:
                    scheduled_time = dt_time(hour, 0)
                    MedicineDoseLog.objects.get_or_create(
                        user=user,
                        medicine=medicine,
                        scheduled_time=scheduled_time,
                        date=today,
                        defaults={'status': 'Pending'}
                    )
            else:
                # Generic distribution for dose_per_day > 3
                hours_interval = 24 // dose_per_day
                for i in range(dose_per_day):
                    hour = (8 + i * hours_interval) % 24  # Start from 8 AM
                    scheduled_time = dt_time(hour, 0)
                    MedicineDoseLog.objects.get_or_create(
                        user=user,
                        medicine=medicine,
                        scheduled_time=scheduled_time,
                        date=today,
                        defaults={'status': 'Pending'}
                    )
        
        # Set next_due_time to the first scheduled dose time today
        if medicine.times.exists():
            first_time = medicine.times.all().order_by('time').first().time
            medicine.next_due_time = first_time
            medicine.save(update_fields=['next_due_time'])
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating dose logs for medicine {instance.id}: {str(e)}")

