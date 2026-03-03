# Dose Timing Feature - Quick Reference

## Summary of Changes

Added tracking of actual dose intake times with visual timing badges.

## What's Different?

| Feature | Before | After |
|---------|--------|-------|
| Track intake time | ✗ | ✓ Show actual_taken_time |
| Show timing badge | ✗ | ✓ On Time / Early / Late |
| AJAX response | marked_at only | marked_at + actual_taken_time + timing_info |
| Database | No timing field | actual_taken_time (nullable) |

## Database Change

```sql
ALTER TABLE accounts_medicinedoselog 
ADD COLUMN actual_taken_time DATETIME NULL;
```

**Migration:** `0010_medicinedoselog_actual_taken_time.py`

## Model Changes

### New Field
```python
actual_taken_time = models.DateTimeField(null=True, blank=True)
```

### Updated method: `mark_as_taken()`
```python
def mark_as_taken(self):
    self.status = 'Taken'
    self.actual_taken_time = now()  # NEW: Save actual time
    self.marked_at = self.actual_taken_time  # Keep for compatibility
    self.save(update_fields=['status', 'actual_taken_time', 'marked_at'])
```

### New method: `get_timing_info()`
```python
def get_timing_info(self):
    """Returns: {is_on_time, is_early, is_late, minutes_diff, status_badge}"""
    # Grace period: ±15 minutes = "On Time"
    # Returns badge text: "On Time", "Taken Early (5m)", "Late by 20m"
```

## View Changes

### smart_dashboard()
```python
# Add to each dose in template context:
timing_info = dose_log.get_timing_info()
today_data.append({
    "timing_info": timing_info,
    "actual_taken_time": dose_log.actual_taken_time,
    # ... other fields
})
```

### toggle_medicine_status()
```python
# After marking dose:
timing_info = dose_log.get_timing_info()

# In JSON response:
return JsonResponse({
    "success": True,
    "actual_taken_time": dose_log.actual_taken_time.isoformat(),
    "timing_info": timing_info,
    # ... other fields
})
```

## Template Changes

### Dose Card Display
```django
{% if item.status == 'Taken' %}
  <small>✓ Taken at {{ item.actual_taken_time|time:"H:i" }}</small>
  <!-- NEW: Show timing badge with color coding -->
  {% if item.timing_info.status_badge %}
    {% if item.timing_info.is_early %}
      <span style="color:#059669;">⚡ {{ item.timing_info.status_badge }}</span>
    {% elif item.timing_info.is_late %}
      <span style="color:#dc2626;">🕐 {{ item.timing_info.status_badge }}</span>
    {% else %}
      <span style="color:#0891b2;">✓ {{ item.timing_info.status_badge }}</span>
    {% endif %}
  {% endif %}
{% endif %}
```

### AJAX Handler
```javascript
// When AJAX response received:
if (data.timing_info && data.timing_info.status_badge) {
  // Create and append badge element
  const badgeElement = document.createElement('span');
  badgeElement.innerHTML = `⚡ ${data.timing_info.status_badge}`;
  medLeft.appendChild(badgeElement);
}
```

## Display Examples

### On Time ✓
- Taken between (scheduled - 15min) and (scheduled + 15min)
- Badge: "✓ On Time" (Cyan)

### Early ⚡
- Taken before (scheduled - 15min)
- Badge: "⚡ Taken Early (30m)" (Green)

### Late 🕐
- Taken after (scheduled + 15min)
- Badge: "🕐 Late by 25m" (Red)

## Testing Quick Checklist

```
☐ Dose marked on time (within 15min) → Shows "✓ On Time"
☐ Dose marked 30min early → Shows "⚡ Taken Early (30m)"
☐ Dose marked 45min late → Shows "🕐 Late by 45m"
☐ Dashboard refreshed → Timing persists
☐ Database has actual_taken_time → Value populated
☐ Old doses without actual_taken_time → Still display (fallback to marked_at)
☐ Graph calculations → Unaffected
☐ Adherence % → Unchanged
```

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| accounts/models.py | Added actual_taken_time + get_timing_info() | +50 |
| accounts/views.py | Updated smart_dashboard() and toggle_medicine_status() | +30 |
| templates/smart_dashboard.html | Updated dose display and AJAX handler | +40 |
| accounts/migrations/0010_*.py | Migration script (auto-generated) | New |

## Key Points

✅ **Backward Compatible:** Old records work with fallback to marked_at
✅ **Non-Breaking:** No changes to existing fields or structure
✅ **User Isolation:** Uses request.user verification
✅ **Timezone-Aware:** Handles timezone differences correctly
✅ **Error Handling:** Graceful fallback if calculation fails
✅ **Performance:** Minimal overhead, no new database indexes needed

## Rollback Plan

If needed, reverting is safe:
```bash
python manage.py migrate accounts 0009_medicine_next_due_time_medicinedoselog
# Removes actual_taken_time field (data lost but no errors)
```

Restore:
```bash
python manage.py migrate accounts 0010_medicinedoselog_actual_taken_time
# Recreates field, old doses show NULL
```

## API Reference

### GET dose timing info
```python
dose_log = MedicineDoseLog.objects.get(pk=1)
timing = dose_log.get_timing_info()

# Returns:
{
    'is_on_time': True,
    'is_early': False,
    'is_late': False,
    'minutes_diff': 5,
    'status_badge': 'On Time'
}
```

### AJAX Response (POST /medicine/toggle-status/)
```json
{
    "success": true,
    "status": "Taken",
    "actual_taken_time": "2026-03-03T08:15:32.123456+00:00",
    "timing_info": {
        "is_on_time": true,
        "is_early": false,
        "is_late": false,
        "minutes_diff": 15,
        "status_badge": "On Time"
    }
}
```

## Troubleshooting

**Q: Badge not showing on AJAX response?**
- Check browser console for errors
- Verify response includes timing_info object
- Check if .med-left element exists in DOM

**Q: Timing shows wrong info?**
- Check database: actual_taken_time should be populated
- Verify timezone settings in Django settings.py
- Check get_timing_info() returns valid dict

**Q: Old doses show no timing?**
- Expected: actual_taken_time is NULL for old records
- Fallback to marked_at time in template
- New doses will have actual_taken_time populated

## Status

✅ **Implementation:** Complete
✅ **Migration:** Applied (0010)
✅ **Testing:** Ready
✅ **Production:** Ready to deploy

**Last Updated:** 2026-03-03
