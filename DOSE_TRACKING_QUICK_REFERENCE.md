# Smart Dashboard Dose Tracking - Quick Reference

## 🎯 What Changed?

**Problem**: Clicking "Mark as Taken" showed "Medicine not found"

**Solution**: Rebuilt to track **individual doses** instead of medicines

## 📋 Key Models

### MedicineDoseLog (NEW)
Individual dose instance for a medicine

```python
Fields:
- user: The patient
- medicine: Which medicine
- scheduled_time: When it's scheduled (e.g., 9:00 AM)
- status: 'Pending', 'Taken', 'Missed'
- date: Which day (e.g., 2026-03-03)
- marked_at: When user marked as taken
```

**Example**:
```
Medicine: Aspirin (dose_per_day=2)
Date: 2026-03-03

MedicineDoseLog #1: Aspirin, 08:00 AM, Pending
MedicineDoseLog #2: Aspirin, 20:00 PM, Taken (marked at 20:15)
```

## 🔄 Main Workflows

### 1️⃣ Creating a Medicine
```
Medicine created → Signal triggers
  ↓
Check: Is it active? Is it scheduled for today?
  ↓
Get dose times (from MedicineTime or auto-distribute)
  ↓
Create MedicineDoseLog for each dose
```

### 2️⃣ Smart Dashboard Display
```
Load /smart-dashboard/
  ↓
Query today's MedicineDoseLog entries
  ↓
Check: Any Pending doses >24h old? → Mark as Missed
  ↓
Count: Pending, Taken, Missed
  ↓
Display each dose with its status
```

### 3️⃣ Mark as Taken (User Action)
```
Click "Mark as Taken" button
  ↓
JavaScript: fetch('/medicine/toggle-status/', dose_log_id)
  ↓
Backend: Find MedicineDoseLog by ID
  ↓
Update: status='Taken', marked_at=now()
  ↓
Return: Updated status + adherence metrics
  ↓
Frontend: Button turns green, gets disabled
```

### 4️⃣ Daily Background Task
```
Midnight: python manage.py generate_daily_doses
  ↓
For each active medicine
  ↓
If scheduled for tomorrow → Create dose logs
  ↓
Mark any overdue Pending doses from today as Missed
```

## 📊 Database

### MedicineDoseLog Table
```
┌──────┬─────────┬────────────┬─────────────┬──────────┬────────────┐
│ id   │ user_id │ medicine   │ date        │ time     │ status     │
├──────┼─────────┼────────────┼─────────────┼──────────┼────────────┤
│ 1    │ 5       │ Aspirin    │ 2026-03-03  │ 08:00 AM │ Taken      │
│ 2    │ 5       │ Aspirin    │ 2026-03-03  │ 20:00 PM │ Pending    │
│ 3    │ 5       │ Metformin  │ 2026-03-03  │ 09:00 AM │ Taken      │
│ 4    │ 5       │ Aspirin    │ 2026-03-04  │ 08:00 AM │ Pending    │
└──────┴─────────┴────────────┴─────────────┴──────────┴────────────┘
```

**Unique Constraint**: Each (user, medicine, time, date) only once!

## 🛠️ Common Tasks

### Check Dose for a User Today
```python
from accounts.models import MedicineDoseLog
from datetime import date

today_doses = MedicineDoseLog.objects.filter(
    user_id=5,
    date=date.today()
).select_related('medicine')

for dose in today_doses:
    print(f"{dose.medicine.name} @ {dose.scheduled_time}: {dose.status}")
```

### Mark a Dose as Taken
```python
dose_log = MedicineDoseLog.objects.get(id=123)
dose_log.mark_as_taken()
# Result: status='Taken', marked_at=now()
```

### Get Adherence for 7 Days
```python
from accounts.views import calculate_daily_adherence
adherence = calculate_daily_adherence(user, days=7)
# Returns: {'average': 85, 'completed_doses': 12, 'total_doses': 14}
```

### Generate Tomorrow's Doses
```bash
python manage.py generate_daily_doses --days-ahead 1
```

### Mark Overdue Doses as Missed
```bash
python manage.py generate_daily_doses --mark-missed
```

## 🔗 API Endpoints

### Mark as Taken (AJAX)
```
POST /medicine/toggle-status/
Content-Type: application/x-www-form-urlencoded

dose_log_id=123&csrfmiddlewaretoken=...

Response:
{
  "success": true,
  "dose_log_id": 123,
  "status": "Taken",
  "marked_at": "2026-03-03T09:15:30Z",
  "adherence": {"average": 85, ...},
  "health_score": {"score": 88, ...}
}
```

### Get Smart Dashboard
```
GET /smart-dashboard/

Template Context:
{
  "today_data": [
    {
      "dose_log": <MedicineDoseLog>,
      "medicine": <Medicine>,
      "scheduled_time": time object,
      "status": "Pending|Taken|Missed",
      "is_overdue": true|false,
      "can_mark_taken": true|false
    },
    ...
  ],
  "completed_count": 2,
  "missed_count": 1,
  "pending_count": 3
}
```

## 📱 Frontend Changes

### Old Button
```html
<button data-med-id="123">Mark as Taken</button>
```

### New Button
```html
<button data-dose-id="456">Mark as Taken</button>
```

### Old JavaScript Handler
```javascript
const medId = this.dataset.medId;
fetch('/medicine/toggle-status/', {
  body: { medicine_id: medId }
});
```

### New JavaScript Handler
```javascript
const doseLogId = this.dataset.doseId;
fetch('/medicine/toggle-status/', {
  body: { dose_log_id: doseLogId }
});
```

### Old Response Check
```javascript
if (data.is_taken) { /* mark taken */ }
```

### New Response Check
```javascript
if (data.status === 'Taken') { /* mark taken */ }
```

## 🧪 Testing

### Run Django Checks
```bash
python manage.py check
```

### Create Test Data
```python
from django.contrib.auth.models import User
from accounts.models import Medicine, MedicineTime, MedicineDoseLog
from datetime import date, time

# Get user
user = User.objects.get(username='testuser')

# Create medicine
med = Medicine.objects.create(
    user=user,
    name='Test Medicine',
    frequency_type='daily',
    dose_per_day=2,
    status='active'
)

# Create times (or let signal handle auto-distribution)
MedicineTime.objects.create(medicine=med, time=time(9, 0))
MedicineTime.objects.create(medicine=med, time=time(21, 0))

# Check doses were auto-created
doses = MedicineDoseLog.objects.filter(
    medicine=med,
    date=date.today()
)
print(f"Created {doses.count()} doses")
```

### Test Mark as Taken
```python
dose = MedicineDoseLog.objects.first()
print(f"Before: {dose.status}")

dose.mark_as_taken()
print(f"After: {dose.status}")
print(f"Marked at: {dose.marked_at}")
```

## 🐛 Troubleshooting

### "Dose not found" Error
- Verify dose_log_id is correct
- Check user owns that dose log
- Confirm MedicineDoseLog exists for that date

### No Doses Showing
- Check medicine.status == 'active'
- Verify medicine frequency is set correctly
- Run: `python manage.py generate_daily_doses`
- Check date in database

### Adherence Showing 0%
- Confirm doses exist for user today
- Check MedicineDoseLog entries
- Look in admin: `/admin/accounts/medicinedoselog/`

### Overdue Doses Not Marked
- Run: `python manage.py generate_daily_doses --mark-missed`
- Or wait for automated daily task
- Check date_time on dose (scheduled_time in past?)

## 📚 Files to Know

| File | Purpose |
|------|---------|
| `accounts/models.py` | MedicineDoseLog model |
| `accounts/signals.py` | Auto-generation signal |
| `accounts/views.py` | toggle_medicine_status, smart_dashboard |
| `accounts/admin.py` | Admin interface |
| `accounts/management/commands/generate_daily_doses.py` | Daily task |
| `templates/smart_dashboard.html` | Frontend template |

## ⚡ Performance Tips

1. **Always use select_related('medicine')**
   ```python
   doses = MedicineDoseLog.objects.select_related('medicine')
   ```

2. **Filter by date for large queries**
   ```python
   MedicineDoseLog.objects.filter(user=user, date=date.today())
   ```

3. **Use indexes**: Already created on (user,date), (medicine,date), (status,date)

4. **Batch operations**: Use bulk_create for many doses

## 🚀 Deployment Checklist

- [ ] Run migrations: `migrate accounts`
- [ ] Generate first week's doses: `generate_daily_doses --days-ahead 7`
- [ ] Set up cron for daily task (midnight)
- [ ] Test in staging first
- [ ] Verify Smart Dashboard works
- [ ] Check admin interface loads

## 📞 Support Quick Links

| Question | Answer |
|----------|--------|
| How do I track a dose? | Click "Mark as Taken" button |
| Where are the doses stored? | MedicineDoseLog table |
| How are doses auto-generated? | Signal on Medicine creation + daily task |
| What's the dose per day for? | Controls how many doses created daily |
| How is adherence calculated? | (Taken doses / Total doses) × 100 |
| What marks a dose as missed? | Automatic if >24h old and still Pending |
| Can I bulk mark doses? | Not yet - planned enhancement |
| Where's the admin interface? | `/admin/accounts/medicinedoselog/` |

## 🎓 Learning Path

1. Read: `SMART_DASHBOARD_REBUILD_SUMMARY.md`
2. Read: `DOSE_TRACKING_ARCHITECTURE.md`
3. Review: `accounts/models.py` MedicineDoseLog
4. Review: `accounts/views.py` toggle_medicine_status
5. Review: `templates/smart_dashboard.html`
6. Try: Create test medicine + verify doses created
7. Try: Mark dose as taken via admin
8. Try: Check dashboard shows updated status

---

**Last Updated**: March 3, 2026  
**Status**: ✅ Production Ready  
**Version**: 1.0
