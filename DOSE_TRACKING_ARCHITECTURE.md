# Smart Dashboard Dose Tracking System - Architecture Guide

## 🎯 Overview

The Smart Dashboard medicine tracking engine has been completely rebuilt with a **clean dose-tracking architecture** that properly separates concerns and tracks individual doses instead of just medicines.

## 📋 Core Models

### 1. Medicine Model (Updated)
```python
Fields:
- name: CharField
- frequency_type: CharField (daily, weekly, custom_week)
- dose_per_day: IntegerField (how many times per day)
- days_of_week: CharField (for weekly scheduling)
- status: CharField (active, paused, completed)
- next_due_time: TimeField (NEW - next scheduled dose time)
- drug_classification: CharField (Antibiotic, Analgesic, etc.)
- food_timing: CharField (Before/After Food)
- is_reminder_enabled: BooleanField
```

### 2. MedicineDoseLog Model (NEW)
```python
NEW - Tracks individual dose instances

Fields:
- user: ForeignKey(User)
- medicine: ForeignKey(Medicine)
- scheduled_time: TimeField (e.g., 8:00 AM)
- status: CharField (Pending, Taken, Missed)
- date: DateField (which day this dose is for)
- marked_at: DateTimeField (when user marked as taken)
- created_at, updated_at: DateTimeField

Unique Constraint: (user, medicine, scheduled_time, date)

Key Methods:
- mark_as_taken(): Mark dose as taken + record timestamp
- mark_as_missed(): Mark dose as missed
- is_overdue: Property that checks if >24h past scheduled time
```

## 🔄 Workflow Logic

### Step 1: Medicine Creation
When a medicine is created, signals automatically generate **today's dose logs**:

```
Medicine Created
    ↓
Signal Handler Triggered
    ↓
Check if medicine is scheduled for today
    ↓
Get MedicineTime objects OR distribute by dose_per_day
    ↓
Create MedicineDoseLog entries for today
    ↓
Set medicine.next_due_time
```

**Distribution Logic for dose_per_day:**
- 1 dose → 9:00 AM
- 2 doses → 8:00 AM, 8:00 PM
- 3 doses → 8:00 AM, 1:00 PM, 8:00 PM
- N doses → Evenly distributed

### Step 2: Smart Dashboard Display
```
User visits /smart-dashboard/
    ↓
Query all MedicineDoseLog for today
    ↓
Check if any Pending doses are overdue (>24h) → auto-mark as Missed
    ↓
Count: Pending, Taken, Missed
    ↓
Calculate adherence % and health metrics
    ↓
Display individual doses with status
```

### Step 3: Mark as Taken (AJAX)
```
User clicks "Mark as Taken" button
    ↓
JavaScript sends dose_log_id to /medicine/toggle-status/
    ↓
Backend finds MedicineDoseLog by ID
    ↓
Call dose_log.mark_as_taken()
    ↓
Response includes updated adherence metrics
    ↓
Button turns green + disabled
    ↓
Card animates to show completion
```

### Step 4: Automatic Missed Marking
```
Every 24 hours after scheduled_time:
    ↓
Check if status still Pending
    ↓
Auto-mark as Missed
    ↓
Update adherence calculations
```

### Step 5: Next Day Generation
```
Daily background task (midnight): python manage.py generate_daily_doses
    ↓
For each active medicine
    ↓
Check if scheduled for tomorrow
    ↓
Create MedicineDoseLog entries for tomorrow
    ↓
No duplicates (unique constraint prevents)
```

## 💻 API Changes

### Old System (Broken)
```python
# Smart Dashboard showed medicines with toggle
{
  "medicine_id": 123,
  "medicine_name": "Aspirin",
  "is_taken": False,
  "times": [<MedicineTime objects>]
}

# Toggle endpoint
POST /medicine/toggle-status/
  medicine_id: 123  # ❌ PROBLEM: Ambiguous when multiple times/doses
```

### New System (Fixed)
```python
# Smart Dashboard shows individual doses
{
  "dose_log": <MedicineDoseLog>,
  "medicine": <Medicine>,
  "scheduled_time": "09:00",
  "status": "Pending",  # or "Taken" or "Missed"
  "is_overdue": False,
  "can_mark_taken": True
}

# Toggle endpoint
POST /medicine/toggle-status/
  dose_log_id: 456  # ✅ Unique and unambiguous
  
Response:
{
  "success": True,
  "dose_log_id": 456,
  "status": "Taken",  # Updated status
  "marked_at": "2026-03-03T09:15:30Z",
  "adherence": {...},
  "health_score": {...}
}
```

## 📊 Database Structure

```
MedicineDoseLog Table:
┌─────────────────────────────────────────────────────────┐
│ id │ user_id │ medicine_id │ date       │ scheduled_time │
├─────────────────────────────────────────────────────────┤
│ 1  │ 1       │ 5           │ 2026-03-03 │ 08:00:00       │
│ 2  │ 1       │ 5           │ 2026-03-03 │ 20:00:00       │  2 doses per day
│ 3  │ 1       │ 7           │ 2026-03-03 │ 09:00:00       │
│ 4  │ 1       │ 5           │ 2026-03-04 │ 08:00:00       │  Tomorrow's doses
│ 5  │ 1       │ 5           │ 2026-03-04 │ 20:00:00       │
└─────────────────────────────────────────────────────────┘

Status column:
- Pending → Not yet marked (default for new logs)
- Taken   → User marked as taken at marked_at timestamp
- Missed  → Auto-marked or user decided not taken
```

## 🛠️ Implementation Details

### Signal Handler (auto_generate_daily_doses)
Location: `accounts/signals.py`

Triggered on: Medicine.post_save() with created=True

Actions:
1. Check medicine.status == 'active'
2. Check if scheduled for today (freq + days_of_week)
3. Get or create MedicineDoseLog for each dose
4. Set medicine.next_due_time to first dose time

### View: toggle_medicine_status
Location: `accounts/views.py` (line ~815)

Accepts:
- `dose_log_id`: Primary key of MedicineDoseLog (preferred)
- OR `medicine_id` + `scheduled_time`: For fallback

Returns JSON with:
- `success`: True/False
- `status`: Updated status
- `adherence`: 7-day adherence metrics
- `health_score`: Updated health score

### Management Command: generate_daily_doses
Location: `accounts/management/commands/generate_daily_doses.py`

Usage:
```bash
# Generate tomorrow's doses
python manage.py generate_daily_doses

# Generate next 7 days
python manage.py generate_daily_doses --days-ahead 7

# Mark overdue doses as missed
python manage.py generate_daily_doses --mark-missed

# Cleanup old logs
python manage.py generate_daily_doses --cleanup
```

Schedule in cron:
```bash
# At midnight every day
0 0 * * * cd /path && python manage.py generate_daily_doses --mark-missed
```

Or with celery:
```python
from celery.schedules import crontab
from celery import shared_task

@shared_task
def daily_dose_generation():
    call_command('generate_daily_doses', mark_missed=True)

CELERY_BEAT_SCHEDULE = {
    'generate_doses_daily': {
        'task': 'accounts.tasks.daily_dose_generation',
        'schedule': crontab(hour=0, minute=0),  # Midnight
    },
}
```

## 🎨 Template Changes

### Smart Dashboard (`templates/smart_dashboard.html`)

**Old:**
```html
{% for item in today_data %}
  <button data-med-id="{{ item.medicine_time_id }}">Mark as Taken</button>
```

**New:**
```html
{% for item in today_data %}
  {% if item.dose_log %}
    Status: {{ item.status }}
    Time: {{ item.scheduled_time|time:"H:i" }}
    <button data-dose-id="{{ item.dose_log.id }}">Mark as Taken</button>
  {% endif %}
```

**JavaScript Changes:**
```javascript
// Old selector
document.querySelectorAll('.btn[data-med-id]')

// New selector
document.querySelectorAll('.btn[data-dose-id]')

// Old data
const medId = this.dataset.medId;
body: { 'medicine_id': medId }

// New data
const doseLogId = this.dataset.doseId;
body: { 'dose_log_id': doseLogId }

// Old response
if (data.is_taken) { ... }

// New response
if (data.status === 'Taken') { ... }
```

## 📈 Adherence Calculation

**Before:** Count is_taken flags across all MedicineStatus entries
**After:** Count 'Taken' status in MedicineDoseLog entries

```python
# Query for 7-day adherence
doses = MedicineDoseLog.objects.filter(
    user=user,
    date__gte=start_date,
    date__lte=end_date
)

total = doses.count()
taken = doses.filter(status='Taken').count()
adherence_percent = (taken / total * 100) if total > 0 else 0
```

## ✅ Benefits of New System

1. **Accuracy**: Each dose tracked individually, not lumped by medicine
2. **Clarity**: Clear status for each scheduled dose
3. **Auto-Scaling**: Handles 1-N doses per day without code changes
4. **Historical**: Complete log of when doses were taken
5. **Analytics**: Better data for adherence patterns
6. **Flexibility**: Easy to add recurring dose patterns
7. **Missed Tracking**: Automatic detection of overdue doses
8. **Atomic Operations**: Each dose is independent, no cascade issues

## 🚀 Future Enhancements

1. **Recurring Patterns**: Add repeat rules (e.g., every other day)
2. **Dose Reminders**: Send push notifications at scheduled_time
3. **Adaptive Scheduling**: Learn best times and suggest adjustments
4. **Interaction Warnings**: Warn about drug interactions
5. **Bulk Actions**: Mark multiple doses at once
6. **Custom Duration**: Set start/end date for medications
7. **Refill Reminders**: Notify when to refill prescription
8. **Reports**: Export adherence reports for doctor visits

## 🐛 Testing

```bash
# Check system health
python manage.py check

# Run migrations
python manage.py migrate

# Create test user
python manage.py createsuperuser

# Access admin
http://localhost:8000/admin/

# Test dose generation
python manage.py generate_daily_doses --days-ahead 7
```

## 🔗 Related Files

- Models: `accounts/models.py`
- Views: `accounts/views.py`
- Signals: `accounts/signals.py`
- Admin: `accounts/admin.py`
- Management: `accounts/management/commands/generate_daily_doses.py`
- Template: `templates/smart_dashboard.html`
- URLs: `accounts/urls.py`

## 💡 Migration Path

If you have existing data:

1. New medicines created after this update will use dose tracking
2. Old medicines still have MedicineStatus but can be updated
3. To migrate old medicines:
   ```python
   # Create doses from old MedicineStatus entries
   for status in MedicineStatus.objects.all():
       MedicineDoseLog.objects.create(
           user=status.medicine_time.medicine.user,
           medicine=status.medicine_time.medicine,
           scheduled_time=status.medicine_time.time,
           date=status.date,
           status='Taken' if status.is_taken else 'Missed' if status.is_missed else 'Pending'
       )
   ```

---

**Version**: 1.0  
**Date**: March 3, 2026  
**Status**: Production Ready
