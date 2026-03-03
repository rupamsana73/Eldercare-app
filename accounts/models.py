from django.db import models
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from PIL import Image
from io import BytesIO


class UserProfile(models.Model):
    """
    User profile with additional information.
    OneToOne relationship with Django's User model.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_image = models.ImageField(
        upload_to='profile_images/',
        null=True,
        blank=True,
        help_text="User's profile picture"
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="User's phone number"
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="User's date of birth"
    )
    emergency_note = models.TextField(
        blank=True,
        help_text="Important emergency information"
    )
    # 🆕 Streak tracking for health metrics
    current_streak = models.IntegerField(
        default=0,
        help_text="Current consecutive days of perfect adherence"
    )
    best_streak = models.IntegerField(
        default=0,
        help_text="Best consecutive days of perfect adherence achieved"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def get_profile_image_url(self):
        """Return profile image URL or None if not set."""
        if self.profile_image:
            return self.profile_image.url
        return None

    def has_profile_image(self):
        """Check if user has uploaded a profile image."""
        return bool(self.profile_image)


class EmergencyContact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    priority = models.IntegerField()

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Medicine(models.Model):

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('custom_week', 'Custom Days'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
    ]

    CLASSIFICATION_CHOICES = [
        ('Unclassified', 'Unclassified'),
        ('Antibiotic', 'Antibiotics'),
        ('Antidiabetic', 'Antidiabetics'),
        ('Antifungal', 'Antifungal'),
        ('Anti-Inflammatory', 'Anti-Inflammatory'),
        ('Antiviral', 'Antiviral'),
        ('Anti-Hypertensive', 'Anti-Hypertensive'),
        ('Tuberculosis', 'Tuberculosis'),
        ('Narcotic', 'Narcotic'),
        ('Barbiturate', 'Barbiturates'),
        ('Analgesic', 'Analgesic'),
        ('Local Anesthetic', 'Local Anesthetics'),
        ('Anti-Arrhythmic', 'Anti-Arrhythmics'),
        ('Anti-Asthmatic', 'Anti-Asthmatics'),
        ('Anti-Epileptic', 'Anti-Epileptics'),
        ('Anti-Malarial', 'Anti-Malarial'),
        ('Anti-Psychotic', 'Anti-Psychotic'),
        ('Diuretic', 'Diuretics'),
        ('UTI Drug', 'UTI Drugs'),
        ('Proton Pump Inhibitor', 'Proton Pump Inhibitors'),
        ('Anti-Emetic', 'Anti-Emetic'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    name = models.CharField(max_length=100)

    # 🆕 Drug classification system
    drug_classification = models.CharField(
        max_length=30,
        choices=CLASSIFICATION_CHOICES,
        default='Unclassified',
        help_text="Drug classification category"
    )

    

    frequency_type = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily'
    )

    # 🔥 NEW — Daily dose count
    dose_per_day = models.IntegerField(
        default=1,
        help_text="How many times per day"
    )

    # For weekly/custom
    days_of_week = models.CharField(
        max_length=50,
        blank=True,
        help_text="Mon,Wed,Fri"
    )

    start_date = models.DateField(auto_now_add=True)

    duration_days = models.IntegerField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    food_timing = models.CharField(
        max_length=20,
        choices=[
            ("Before Food", "Before Food"),
            ("After Food", "After Food"),
        ]
    )

    notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )

    # 🆕 Reminder toggle
    is_reminder_enabled = models.BooleanField(
        default=True,
        help_text="Enable or disable reminders for this medicine"
    )

    # 🔥 NEW — Next due time for dose tracking
    next_due_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Next scheduled time to take this medicine"
    )

    last_taken_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name



class MedicineTime(models.Model):
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name='times'
    )
    time = models.TimeField()

    def __str__(self):
        return f"{self.medicine.name} @ {self.time}"


class MedicineStatus(models.Model):
    medicine_time = models.ForeignKey(
        'MedicineTime',
        on_delete=models.CASCADE,
        related_name='statuses'
    )
    date = models.DateField()
    is_taken = models.BooleanField(default=False)
    is_missed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('medicine_time', 'date')


class MedicineDoseLog(models.Model):
    """
    Tracks individual dose instances for each medicine.
    Created automatically when medicine is added.
    One log entry per dose per day.
    
    Flow:
    1. When medicine created → auto-generate today's dose logs
    2. Smart Dashboard shows only today's logs
    3. Mark as Taken → update status and actual_taken_time
    4. If not marked in 24h → auto-marked as Missed
    5. Background task generates next day's logs at midnight
    """
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Taken', 'Taken'),
        ('Missed', 'Missed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dose_logs')
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='dose_logs')
    
    # Scheduled time for this dose (e.g., 8:00 AM)
    scheduled_time = models.TimeField(help_text="Scheduled time for this dose")
    
    # Status of this dose
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    
    # Date this dose is scheduled for
    date = models.DateField(help_text="Date this dose is scheduled")
    
    # When the user actually took the dose (NEW)
    actual_taken_time = models.DateTimeField(null=True, blank=True, help_text="Actual time when dose was taken")
    
    # Legacy field - kept for compatibility
    marked_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        # Prevent duplicate dose logs for same medicine, time, and date
        unique_together = ('user', 'medicine', 'scheduled_time', 'date')
        ordering = ['-date', 'scheduled_time']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['medicine', 'date']),
            models.Index(fields=['status', 'date']),
        ]
    
    def __str__(self):
        return f"{self.medicine.name} - {self.date} @ {self.scheduled_time} ({self.status})"
    
    def mark_as_taken(self):
        """Mark this dose as taken and record actual_taken_time."""
        from django.utils.timezone import now
        self.status = 'Taken'
        self.actual_taken_time = now()
        self.marked_at = self.actual_taken_time  # Keep for legacy compatibility
        self.save(update_fields=['status', 'actual_taken_time', 'marked_at'])
    
    def mark_as_missed(self):
        """Mark this dose as missed."""
        self.status = 'Missed'
        self.save(update_fields=['status'])
    
    def get_timing_info(self):
        """
        Returns timing information for display in dashboard.
        
        Returns:
        dict with keys:
        - is_on_time: bool
        - is_early: bool (taken before scheduled)
        - is_late: bool (taken after scheduled)
        - minutes_diff: int (minutes early/late, positive = late, negative = early)
        - status_badge: str ('On Time', 'Taken Early', 'Late by X minutes', etc.)
        """
        if self.status != 'Taken' or not self.actual_taken_time:
            return {
                'is_on_time': False,
                'is_early': False,
                'is_late': False,
                'minutes_diff': 0,
                'status_badge': None
            }
        
        from datetime import datetime, time as dt_time
        
        try:
            # Create datetime for scheduled time (combine date + scheduled_time)
            scheduled_dt = datetime.combine(self.date, self.scheduled_time)
            
            # Make timezone-aware if needed
            if self.actual_taken_time.tzinfo and not scheduled_dt.tzinfo:
                import pytz
                scheduled_dt = pytz.make_aware(scheduled_dt, self.actual_taken_time.tzinfo)
            elif not self.actual_taken_time.tzinfo and scheduled_dt.tzinfo:
                scheduled_dt = scheduled_dt.replace(tzinfo=None)
            
            # Calculate difference in minutes
            time_diff = (self.actual_taken_time - scheduled_dt).total_seconds() / 60
            minutes_diff = int(time_diff)
            
            # Determine timing (grace period: 15 minutes)
            grace_period_minutes = 15
            
            if abs(minutes_diff) <= grace_period_minutes:
                badge = 'On Time'
                is_on_time = True
                is_early = False
                is_late = False
            elif minutes_diff < 0:  # Early
                badge = f'Taken Early ({abs(minutes_diff)}m)'
                is_on_time = False
                is_early = True
                is_late = False
            else:  # Late
                badge = f'Late by {minutes_diff}m'
                is_on_time = False
                is_early = False
                is_late = True
            
            return {
                'is_on_time': is_on_time,
                'is_early': is_early,
                'is_late': is_late,
                'minutes_diff': minutes_diff,
                'status_badge': badge
            }
        except Exception as e:
            import logging
            logging.error(f"Error calculating timing info for dose log {self.id}: {e}")
            return {
                'is_on_time': False,
                'is_early': False,
                'is_late': False,
                'minutes_diff': 0,
                'status_badge': None
            }
    
    @property
    def is_overdue(self):
        """Check if dose is overdue (scheduled time passed but not marked)."""
        from django.utils.timezone import now
        from datetime import time as dt_time, datetime, timedelta
        
        if self.status != 'Pending':
            return False
        
        # Create datetime for scheduled time today
        current_time = now()
        scheduled_datetime = datetime.combine(self.date, self.scheduled_time)
        scheduled_datetime = scheduled_datetime.replace(tzinfo=current_time.tzinfo)
        
        # Check if more than 24 hours have passed
        hours_passed = (current_time - scheduled_datetime).total_seconds() / 3600
        return hours_passed > 24


class Prescription(models.Model):
    """
    Stores uploaded prescription images and OCR-extracted text.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prescriptions')
    image = models.ImageField(upload_to='prescriptions/')
    extracted_text = models.TextField(blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prescription by {self.user.username} at {self.uploaded_at:%Y-%m-%d %H:%M}"

    class Meta:
        ordering = ['-uploaded_at']
