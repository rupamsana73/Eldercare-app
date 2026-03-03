from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout, authenticate, login
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils.timezone import now, localtime
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from datetime import date, timedelta, time as dt_time, datetime, time
from collections import defaultdict
import calendar
import re
import os
import difflib
import mimetypes
from functools import wraps

from .models import EmergencyContact, Medicine, MedicineStatus, MedicineTime, UserProfile, Prescription, MedicineDoseLog
from .forms import MedicineForm, UserProfileForm, UserProfilePhotoForm, PrescriptionUploadForm
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# PRODUCTION-READY SECURITY & VALIDATION
# ============================================================================

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/jpg', 'image/webp'}
MAX_MEDICINE_NAME_LENGTH = 100
MAX_MEDICINES_PER_REQUEST = 50
MAX_PRESCRIPTION_PER_DAY = 10

def rate_limit_prescription_scan(view_func):
    """Rate limit prescription scanning to prevent abuse."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return view_func(request, *args, **kwargs)
        try:
            today = date.today()
            scan_count = Prescription.objects.filter(
                user=request.user,
                created_at__date=today
            ).count()
            if scan_count >= MAX_PRESCRIPTION_PER_DAY:
                return JsonResponse({
                    'success': False,
                    'error': f'Rate limit exceeded. Max {MAX_PRESCRIPTION_PER_DAY} scans per day.',
                    'retry_after': 3600
                }, status=429)
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
        return view_func(request, *args, **kwargs)
    return wrapper

def validate_image_file(image_file):
    """Validate image file for security and compatibility."""
    if not image_file:
        return False, "No file provided"
    if image_file.size > MAX_FILE_SIZE:
        return False, f"File exceeds {MAX_FILE_SIZE / 1024 / 1024:.0f}MB limit"
    mime_type, _ = mimetypes.guess_type(image_file.name)
    if mime_type not in ALLOWED_IMAGE_MIMES:
        return False, "Invalid image format. Use JPEG, PNG, or WebP"
    try:
        file_header = image_file.read(4)
        image_file.seek(0)
        is_jpeg = file_header.startswith(b'\xff\xd8')
        is_png = file_header.startswith(b'\x89PNG')
        if not (is_jpeg or is_png):
            return False, "Invalid image file (corrupted or wrong format)"
    except Exception as e:
        logger.error(f"File validation error: {e}")
        return False, "Unable to validate file"
    return True, None

def sanitize_medicine_name(name):
    """Sanitize medicine name input for safety and consistency."""
    if not isinstance(name, str):
        return None
    name = name.strip()
    name = ' '.join(name.split())
    if len(name) == 0 or len(name) > MAX_MEDICINE_NAME_LENGTH:
        return None
    name = re.sub(r'[^a-zA-Z0-9\s\-().+\']', '', name)
    if not name:
        return None
    return name

def validate_medicine_list(medicines):
    """Validate a list of medicine names for the request."""
    if not isinstance(medicines, list):
        return False, [], "Medicines must be a list"
    if len(medicines) == 0:
        return False, [], "No medicines provided"
    if len(medicines) > MAX_MEDICINES_PER_REQUEST:
        return False, [], f"Too many medicines. Max {MAX_MEDICINES_PER_REQUEST} at once"
    cleaned = []
    for med in medicines:
        sanitized = sanitize_medicine_name(med)
        if sanitized:
            cleaned.append(sanitized)
    if len(cleaned) == 0:
        return False, [], "No valid medicine names in request"
    return True, cleaned, None


# 🆕 DRUG CLASSIFICATION SYSTEM
DRUG_CLASSIFICATIONS = {
    'Antibiotic': [
        'amoxicillin', 'ampicillin', 'azithromycin', 'cefixime', 'cephalexin',
        'ciprofloxacin', 'doxycycline', 'erythromycin', 'levofloxacin', 'moxifloxacin',
        'ofloxacin', 'penicillin', 'sulfamethoxazole', 'tetracycline', 'trimethoprim'
    ],
    'Antidiabetic': [
        'metformin', 'glibenclamide', 'gliclazide', 'glipizide', 'insulin', 'sitagliptin',
        'pioglitazone', 'repaglinide', 'acarbose', 'miglitol'
    ],
    'Antifungal': [
        'fluconazole', 'itraconazole', 'ketoconazole', 'miconazole', 'terbinafine',
        'amphotericin', 'clotrimazole'
    ],
    'Anti-Inflammatory': [
        'aspirin', 'diclofenac', 'ibuprofen', 'indomethacin', 'naproxen', 'paracetamol',
        'acetaminophen', 'piroxicam', 'meloxicam'
    ],
    'Antiviral': [
        'acyclovir', 'valacyclovir', 'oseltamivir', 'zanamivir', 'tenofovir',
        'lamivudine', 'efavirenz', 'ritonavir', 'lopinavir'
    ],
    'Anti-Hypertensive': [
        'atenolol', 'amlodipine', 'enalapril', 'lisinopril', 'ramipril', 'valsartan',
        'losartan', 'hydrochlorothiazide', 'metoprolol', 'nifedipine'
    ],
    'Tuberculosis': [
        'isoniazid', 'rifampicin', 'pyrazinamide', 'ethambutol', 'streptomycin',
        'levofloxacin', 'moxifloxacin'
    ],
    'Narcotic': [
        'morphine', 'codeine', 'tramadol', 'hydrocodone', 'oxycodone', 'methadone'
    ],
    'Barbiturate': [
        'phenobarbital', 'barbituric', 'pentobarbital', 'secobarbital'
    ],
    'Analgesic': [
        'aspirin', 'paracetamol', 'ibuprofen', 'tramadol', 'acetaminophen',
        'naproxen', 'diclofenac'
    ],
    'Local Anesthetic': [
        'lidocaine', 'bupivacaine', 'procaine', 'prilocaine', 'xylocaine'
    ],
    'Anti-Arrhythmic': [
        'amiodarone', 'procainamide', 'quinidine', 'disopyramide', 'flecainide'
    ],
    'Anti-Asthmatic': [
        'salbutamol', 'albuterol', 'theophylline', 'montelukast', 'fluticasone',
        'budesonide', 'beclomethasone'
    ],
    'Anti-Epileptic': [
        'phenytoin', 'carbamazepine', 'valproic', 'lamotrigine', 'levetiracetam',
        'phenobarbital', 'gabapentin'
    ],
    'Anti-Malarial': [
        'chloroquine', 'amodiaquine', 'quinine', 'primaquine', 'artemisinin'
    ],
    'Anti-Psychotic': [
        'haloperidol', 'chlorpromazine', 'risperidone', 'quetiapine', 'olanzapine',
        'aripiprazole', 'lurasidone'
    ],
    'Diuretic': [
        'furosemide', 'hydrochlorothiazide', 'torsemide', 'bumetanide', 'amiloride',
        'spironolactone'
    ],
    'UTI Drug': [
        'nitrofurantoin', 'norfloxacin', 'ciprofloxacin', 'ofloxacin', 'cephalexin'
    ],
    'Proton Pump Inhibitor': [
        'omeprazole', 'esomeprazole', 'lansoprazole', 'pantoprazole', 'rabeprazole'
    ],
    'Anti-Emetic': [
        'metoclopramide', 'ondansetron', 'promethazine', 'granisetron', 'aprepitant'
    ],
}


def classify_medicine(medicine_name):
    """
    Classify a medicine based on its name.
    Returns the classification or 'Unclassified' if not found.
    """
    if not medicine_name:
        return 'Unclassified'
    
    med_lower = medicine_name.lower().strip()
    
    for classification, medicines in DRUG_CLASSIFICATIONS.items():
        for med in medicines:
            if med in med_lower or med_lower in med:
                return classification
    
    return 'Unclassified'


def get_drug_classification_stats(user):
    """
    Get statistics of drug classifications for user's medicines.
    Returns dict with counts of each classification.
    """
    try:
        if not user or not user.is_authenticated:
            return {}
        
        medicines = Medicine.objects.filter(user=user, status='active')
        stats = {}
        
        for med in medicines:
            classification = med.drug_classification
            if classification not in stats:
                stats[classification] = 0
            stats[classification] += 1
        
        # Sort by count descending
        sorted_stats = dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))
        return sorted_stats
    
    except Exception as e:
        logger.error(f"Error getting drug classification stats for user {user.id if user else 'None'}: {e}")
        return {}


logger = logging.getLogger(__name__)


def calculate_daily_adherence(user, days=7):
    """
    Calculate daily adherence percentage for last N days based on MedicineDoseLog.
    Returns dict with daily percentages and overall average.
    """
    try:
        from .models import MedicineDoseLog
        
        if not user or not user.is_authenticated:
            return {"daily": [], "average": 0, "total_doses": 0, "completed_doses": 0}
        
        today = date.today()
        start_date = today - timedelta(days=days-1)
        
        # Get all dose logs for the period from MedicineDoseLog
        dose_logs = MedicineDoseLog.objects.filter(
            user=user,
            date__range=[start_date, today]
        )
        
        daily_stats = {}
        total_doses = 0
        completed_doses = 0
        
        for dose_log in dose_logs:
            day = dose_log.date
            if day not in daily_stats:
                daily_stats[day] = {'total': 0, 'taken': 0}
            
            daily_stats[day]['total'] += 1
            if dose_log.status == 'Taken':
                daily_stats[day]['taken'] += 1
            
            total_doses += 1
            if dose_log.status == 'Taken':
                completed_doses += 1
        
        # Build daily adherence
        daily_adherence = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            if d in daily_stats:
                stats = daily_stats[d]
                percentage = round((stats['taken'] / stats['total'] * 100) if stats['total'] > 0 else 0)
            else:
                percentage = 0  # No medicines scheduled
            daily_adherence.append({
                "date": d.strftime("%Y-%m-%d"),
                "percentage": percentage,
                "weekday": calendar.day_abbr[d.weekday()]
            })
        
        overall_adherence = round((int(completed_doses) / int(total_doses) * 100) if int(total_doses) > 0 else 0)
        
        return {
            "daily": daily_adherence,
            "average": overall_adherence,
            "total_doses": total_doses,
            "completed_doses": completed_doses
        }
    except Exception as e:
        logger.error(f"Error calculating daily adherence for user {user.id if user else 'None'}: {e}")
        return {"daily": [], "average": 0, "total_doses": 0, "completed_doses": 0}


def calculate_streaks(user):
    """
    Calculate current and best streaks for user.
    A streak is consecutive days with 100% adherence.
    Returns dict with current_streak, best_streak, last_perfect_day.
    """
    try:
        if not user or not user.is_authenticated:
            return {"current_streak": 0, "best_streak": 0, "last_perfect_day": None}
        
        today = date.today()
        # Look back up to 365 days for streaks
        start_date = today - timedelta(days=365)
        
        # Get all statuses
        statuses = MedicineStatus.objects.filter(
            date__range=[start_date, today],
            medicine_time__medicine__user=user
        ).order_by('date')
        
        # Group by date and calculate daily completion
        daily_completion = {}
        for status in statuses:
            day = status.date
            if day not in daily_completion:
                daily_completion[day] = {'total': 0, 'taken': 0}
            daily_completion[day]['total'] += 1
            if status.is_taken:
                daily_completion[day]['taken'] += 1
        
        # Calculate streaks
        current_streak = 0
        best_streak = 0
        last_perfect_day = None
        
        # Check from today backwards
        for i in range(365):
            check_date = today - timedelta(days=i)
            
            if check_date not in daily_completion:
                # No data = break streak
                if current_streak > 0:
                    break  # Stop counting backwards when we hit a gap
                continue
            
            stats = daily_completion[check_date]
            if stats['total'] == 0:
                # No medicines scheduled = perfect day
                if current_streak == 0:
                    last_perfect_day = check_date
                current_streak += 1
            elif stats['taken'] == stats['total']:
                # 100% adherence
                if current_streak == 0:
                    last_perfect_day = check_date
                current_streak += 1
            else:
                # Streak broken
                if current_streak > best_streak:
                    best_streak = current_streak
                current_streak = 0
        
        # Final check for best streak
        if current_streak > best_streak:
            best_streak = current_streak
        
        # Update user profile with streak data
        try:
            profile = user.profile
            profile.current_streak = current_streak
            if best_streak > profile.best_streak:
                profile.best_streak = best_streak
            profile.save(update_fields=['current_streak', 'best_streak'])
        except UserProfile.DoesNotExist:
            logger.warning(f"UserProfile not found for user {user.id}")
        
        return {
            "current_streak": current_streak,
            "best_streak": best_streak,
            "last_perfect_day": last_perfect_day.strftime("%Y-%m-%d") if last_perfect_day else None
        }
    except Exception as e:
        logger.error(f"Error calculating streaks for user {user.id if user else 'None'}: {e}")
        return {"current_streak": 0, "best_streak": 0, "last_perfect_day": None}


def calculate_health_score(user):
    """
    Calculate smart health score based on adherence metrics.
    Score ranges from 0-100.
    Factors: 
    - Last 7 days adherence (40%)
    - Current streak (35%)
    - Last 30 days adherence (25%)
    """
    try:
        if not user or not user.is_authenticated:
            return {"score": 0, "level": "Poor", "breakdown": {}}
        
        # Get last 7 days adherence
        adherence_7d = calculate_daily_adherence(user, days=7)
        score_7d = float(adherence_7d.get("average", 0)) if isinstance(adherence_7d, dict) else 0.0
        
        # Get streaks
        streaks = calculate_streaks(user)
        current_streak = streaks.get("current_streak", 0)
        best_streak = streaks.get("best_streak", 0)
        
        current_streak_val = int(current_streak) if current_streak is not None else 0
        best_streak_val = int(best_streak) if best_streak is not None else 0
        
        # Normalize streak to 100 (assume 30 days is excellent)
        streak_score = min((current_streak_val / 30) * 100, 100) if best_streak_val > 0 else 0
        
        # Get last 30 days adherence
        adherence_30d = calculate_daily_adherence(user, days=30)
        score_30d = float(adherence_30d.get("average", 0)) if isinstance(adherence_30d, dict) else 0.0
        
        # Calculate weighted score
        health_score = round(
            (score_7d * 0.40) +
            (streak_score * 0.35) +
            (score_30d * 0.25)
        )
        
        # Determine health level
        if health_score >= 90:
            level = "Excellent"
            color = "#22c55e"  # Green
        elif health_score >= 75:
            level = "Good"
            color = "#3b82f6"  # Blue
        elif health_score >= 60:
            level = "Fair"
            color = "#f59e0b"  # Amber
        elif health_score >= 40:
            level = "Poor"
            color = "#ef4444"  # Red
        else:
            level = "Critical"
            color = "#7f1d1d"  # Dark red
        
        return {
            "score": health_score,
            "level": level,
            "color": color,
            "breakdown": {
                "adherence_7d": score_7d,
                "streak": streak_score,
                "adherence_30d": score_30d
            }
        }
    except Exception as e:
        logger.error(f"Error calculating health score for user {user.id if user else 'None'}: {e}")
        return {"score": 0, "level": "Unknown", "color": "#808080", "breakdown": {}}


def home(request):
    """
    Home page - redirect to dashboard if user is already logged in.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')



def login_view(request):
    """
    Custom login view - redirect to dashboard if user is already logged in.
    Handles both GET (display form) and POST (process login).
    This works in conjunction with django-allauth.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Redirect to allauth's login page
    return redirect('account_login')


def signup_view(request):
    """
    Custom signup view - redirect to dashboard if user is already logged in.
    This works in conjunction with django-allauth.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Redirect to allauth's signup page
    return redirect('account_signup')

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')

@login_required
def emergency(request):
    contacts = EmergencyContact.objects.filter(user=request.user)
    c1 = contacts.filter(priority=1).first()
    c2 = contacts.filter(priority=2).first()
    return render(request, 'emergency.html', {'c1': c1, 'c2': c2})


@login_required
def profile_view(request):
    """
    Display user profile information.
    Creates a UserProfile if it doesn't exist.
    """
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'profile.html', {'profile': profile})


@login_required
def profile_edit_view(request):
    """
    Edit user profile (phone, DOB, emergency note).
    """
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'profile_edit.html', {'form': form, 'profile': profile})


@login_required
def profile_photo_upload_view(request):
    """
    Handle profile photo upload via AJAX or form submission.
    """
    if request.method == 'POST':
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        form = UserProfilePhotoForm(request.POST, request.FILES, instance=profile)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile photo updated successfully!')
            
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'image_url': profile.get_profile_image_url()
                })
            return redirect('profile')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid image file'
                }, status=400)
    
    return redirect('profile')


@login_required
def save_emergency_contact(request):
    if request.method == 'POST':
        EmergencyContact.objects.update_or_create(
            user=request.user,
            priority=request.POST['priority'],
            defaults={
                'name': request.POST['name'],
                'phone': request.POST['phone']
            }
        )
    return redirect('/emergency/')


def logout_view(request):
    """
    Logout view - logs out user and redirects to home page.
    LOGOUT_REDIRECT_URL is configured in settings to redirect to '/'.
    """
    logout(request)
    return redirect('home')  

@login_required
def add_medicine(request):
    if request.method == "POST":
        name = request.POST.get('name')
        frequency = request.POST.get('frequency_type')
        dose_per_day = int(request.POST.get('dose_per_day', 1))
        days_of_week = request.POST.get('days_of_week', '')
        duration_days = request.POST.get('duration_days') or None
        end_date = request.POST.get('end_date') or None
        food_timing = request.POST.get('food_timing')
        notes = request.POST.get('notes', '')
        times = request.POST.getlist('times[]')

        # ✅ Create Medicine (INDENT FIXED)
        medicine = Medicine.objects.create(
            user=request.user,
            name=name,
            frequency_type=frequency,
            dose_per_day=dose_per_day,
            days_of_week=days_of_week,
            duration_days=duration_days,
            end_date=end_date,
            food_timing=food_timing,
            notes=notes,
            status='active',
           
        )

        # ✅ Save times
        for t in times:
            if t:
                MedicineTime.objects.create(
                    medicine=medicine,
                    time=t
                )

        # 🔔 Success message
        messages.success(request, "Medicine added successfully")

        return redirect('manage_medicine')

    return render(request, 'add_medicine.html')



@login_required
def manage_medicine(request):
    medicines = (
        Medicine.objects
        .filter(user=request.user)
        .prefetch_related('times')
        .order_by('-created_at')
    )
    return render(request, 'manage_medicine.html', {
        'medicines': medicines
    })

@login_required
def pause_medicine(request, med_id):
    med = get_object_or_404(Medicine, id=med_id, user=request.user)
    med.status = 'paused'
    med.save()
    return redirect('manage_medicine')

@login_required
def resume_medicine(request, med_id):
    med = get_object_or_404(Medicine, id=med_id, user=request.user)
    med.status = 'active'
    med.save()
    return redirect('manage_medicine')

@login_required
def delete_medicine(request, med_id):
    med = get_object_or_404(Medicine, id=med_id, user=request.user)
    med.delete()
    return redirect('manage_medicine')

@login_required
def edit_medicine(request, med_id):
    med = get_object_or_404(Medicine, id=med_id, user=request.user)

    if request.method == "POST":
        med.name = request.POST.get('name')
        med.frequency_type = request.POST.get('frequency_type')
        med.days_of_week = request.POST.get('days_of_week', '')
        med.food_timing = request.POST.get('food_timing')
        med.notes = request.POST.get('notes', '')
        med.save()

        # 🔁 replace times
        MedicineTime.objects.filter(medicine=med).delete()
        times = request.POST.getlist('times[]')
        for t in times:
            if t:
                MedicineTime.objects.create(medicine=med, time=t)

        return JsonResponse({"success": True})

    return render(request, 'partials/edit_medicine_form.html', {"med": med})

@login_required
def smart_dashboard(request):
    """
    Smart dashboard showing today's doses with clean architecture.
    Uses MedicineDoseLog for precise dose tracking.
    
    Features:
    - Shows only today's scheduled doses
    - Individual dose tracking (not medicine-based)
    - Adherence percentage, streaks, and health score
    - Activity heatmap and drug classification stats
    """
    try:
        from .models import MedicineDoseLog
        from django.utils.timezone import now, localtime
        
        today = date.today()
        current_time = localtime(now()).time()
        
        # Get all dose logs for today, ordered by scheduled time
        today_dose_logs = MedicineDoseLog.objects.filter(
            user=request.user,
            date=today
        ).select_related('medicine').order_by('scheduled_time')
        
        # Prepare data for template
        today_data = []
        completed_count = 0
        missed_count = 0
        pending_count = 0
        
        for dose_log in today_dose_logs:
            # Check if overdue (24h past scheduled time)
            if dose_log.status == 'Pending' and dose_log.is_overdue:
                dose_log.mark_as_missed()
                dose_log.refresh_from_db()
            
            # Count statuses
            if dose_log.status == 'Taken':
                completed_count += 1
            elif dose_log.status == 'Missed':
                missed_count += 1
            else:
                pending_count += 1
            
            # Get timing information for display
            timing_info = dose_log.get_timing_info()
            
            today_data.append({
                "dose_log": dose_log,
                "medicine": dose_log.medicine,
                "scheduled_time": dose_log.scheduled_time,
                "status": dose_log.status,
                "is_overdue": dose_log.is_overdue if dose_log.status == 'Pending' else False,
                "can_mark_taken": dose_log.status == 'Pending',
                "timing_info": timing_info,
                "actual_taken_time": dose_log.actual_taken_time,
            })
        
        # Get activity data
        activity_data = get_activity_data(request.user)
        
        # Calculate metrics
        adherence_data = calculate_daily_adherence(request.user, days=7)
        streak_data = calculate_streaks(request.user)
        health_score = calculate_health_score(request.user)
        adherence_30d = calculate_daily_adherence(request.user, days=30)
        drug_class_stats = get_drug_classification_stats(request.user)
        
        # Calculate today's adherence
        today_adherence = 0
        if completed_count + missed_count + pending_count > 0:
            today_adherence = round((completed_count / (completed_count + missed_count + pending_count) * 100))
        
        return render(request, "smart_dashboard.html", {
            "today_data": today_data,
            "completed_count": completed_count,
            "missed_count": missed_count,
            "pending_count": pending_count,
            "total_doses": len(today_dose_logs),
            "today_adherence": today_adherence,
            "activity_data": activity_data or [],
            "daily_adherence": adherence_data,
            "streaks": streak_data,
            "health_score": health_score,
            "adherence_30d": adherence_30d,
            "drug_classification_stats": drug_class_stats,
        })
    
    except Exception as e:
        logger.error(f"Critical error in smart_dashboard for user {request.user.id}: {str(e)}")
        return render(request, "smart_dashboard.html", {
            "today_data": [],
            "completed_count": 0,
            "missed_count": 0,
            "pending_count": 0,
            "total_doses": 0,
            "today_adherence": 0,
            "activity_data": [],
            "daily_adherence": {"daily": [], "average": 0, "total_doses": 0, "completed_doses": 0},
            "streaks": {"current_streak": 0, "best_streak": 0, "last_perfect_day": None},
            "health_score": {"score": 0, "level": "Unknown", "color": "#808080", "breakdown": {}},
            "adherence_30d": {"daily": [], "average": 0, "total_doses": 0, "completed_doses": 0},
            "error": "Unable to load dashboard data"
        })



@require_POST
@login_required
def toggle_medicine_status(request):
    """
    Mark a dose as taken. Uses MedicineDoseLog for proper dose tracking.
    
    Expects:
    - dose_log_id: Primary key of MedicineDoseLog (preferred)
    OR
    - medicine_id + scheduled_time: Medicine ID and scheduled time
    
    Returns updated adherence metrics and health score.
    """
    try:
        from .models import MedicineDoseLog
        from django.utils.timezone import now
        
        dose_log_id = request.POST.get('dose_log_id')
        medicine_id = request.POST.get('medicine_id')
        scheduled_time_str = request.POST.get('scheduled_time')  # Format: HH:MM
        
        dose_log = None
        
        # Try to get by dose_log_id first
        if dose_log_id:
            try:
                dose_log_id = int(dose_log_id)
                dose_log = MedicineDoseLog.objects.get(
                    id=dose_log_id,
                    user=request.user
                )
            except (ValueError, MedicineDoseLog.DoesNotExist):
                pass
        
        # If not found by ID, try by medicine_id and scheduled_time
        if not dose_log and medicine_id and scheduled_time_str:
            try:
                medicine_id = int(medicine_id)
                from datetime import time as dt_time
                # Parse scheduled_time (expected format: "HH:MM")
                time_parts = scheduled_time_str.split(':')
                scheduled_time = dt_time(int(time_parts[0]), int(time_parts[1]))
                
                today = date.today()
                dose_log = MedicineDoseLog.objects.get(
                    user=request.user,
                    medicine_id=medicine_id,
                    scheduled_time=scheduled_time,
                    date=today
                )
            except (ValueError, MedicineDoseLog.DoesNotExist, IndexError):
                pass
        
        # No dose log found
        if not dose_log:
            return JsonResponse(
                {"success": False, "error": "Dose not found"},
                status=404
            )
        
        # Mark as taken
        dose_log.mark_as_taken()
        
        # Get timing information
        timing_info = dose_log.get_timing_info()
        
        # Get updated adherence data
        adherence_data = calculate_daily_adherence(request.user, days=7)
        health_score = calculate_health_score(request.user)
        
        return JsonResponse({
            "success": True,
            "dose_log_id": dose_log.id,
            "status": dose_log.status,
            "actual_taken_time": dose_log.actual_taken_time.isoformat() if dose_log.actual_taken_time else None,
            "marked_at": dose_log.marked_at.isoformat() if dose_log.marked_at else None,
            "timing_info": timing_info,
            "message": "Dose marked as taken",
            "adherence": adherence_data,
            "health_score": health_score
        })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in toggle_medicine_status: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "Failed to update dose status"},
            status=500
        )


@login_required
def get_adherence_update(request):
    """
    AJAX endpoint for real-time graph updates.
    
    Returns:
    - Today's adherence percentage
    - 7-day average adherence
    - Daily breakdown for chart updates
    - Updated health score
    - Current streak data
    - Today's dose counts (taken/missed/pending)
    
    Used by: JavaScript fetch() every 60 seconds for auto-refresh
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from .models import MedicineDoseLog
        
        # Get metrics
        today_adherence = calculate_daily_adherence(request.user, days=1)
        week_adherence = calculate_daily_adherence(request.user, days=7)
        health_score = calculate_health_score(request.user)
        streaks = calculate_streaks(request.user)
        
        # Get today's dose counts
        today = date.today()
        today_doses = MedicineDoseLog.objects.filter(
            user=request.user,
            date=today
        ).values('status').annotate(count=Count('id'))
        
        dose_counts = {
            'taken': 0,
            'missed': 0,
            'pending': 0,
        }
        
        for item in today_doses:
            if item['status'] == 'Taken':
                dose_counts['taken'] = item['count']
            elif item['status'] == 'Missed':
                dose_counts['missed'] = item['count']
            else:  # Pending
                dose_counts['pending'] = item['count']
        
        return JsonResponse({
            'success': True,
            'today_adherence': today_adherence.get('average', 0),
            'week_adherence': week_adherence.get('average', 0),
            'daily_breakdown': week_adherence.get('daily', []),
            'health_score': health_score.get('score', 0),
            'health_level': health_score.get('level', 'Unknown'),
            'current_streak': streaks.get('current_streak', 0),
            'dose_counts': dose_counts,
        })
    
    except Exception as e:
        logger.error(f"Error in get_adherence_update for user {request.user.id}: {str(e)}")
        return JsonResponse({'error': 'Unable to fetch update'}, status=500)


def is_missed(med_time):
    """
    Missed rules:
    - 1 hour grace after scheduled time
    - Valid only until 9:00 PM (dinner cutoff)
    - After 9 PM → locked as missed
    - Next day auto reset (date-based)
    """
    try:
        now_dt = localtime(now())
        now_time = now_dt.time()

        dinner_cutoff = time(21, 0)  # 9:00 PM

        # Safe time operations with None check
        if med_time is None:
            return False

        scheduled_dt = datetime.combine(date.today(), med_time)
        grace_dt = scheduled_dt + timedelta(hours=1)

        # if current time is after grace & before dinner cutoff → missed
        if grace_dt.time() < now_time <= dinner_cutoff:
            return True

        return False
    
    except (TypeError, ValueError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error in is_missed function: {str(e)}")
        return False


def get_activity_data(user, days=28):
    """
    Get user's medicine activity for last N days based on MedicineDoseLog.
    Returns activity state (none, full, partial, missed) for each day.
    """
    try:
        from .models import MedicineDoseLog
        
        if user is None or not user.is_authenticated:
            return []

        today = date.today()
        start_date = today - timedelta(days=days-1)

        # Query MedicineDoseLog for the period
        dose_logs = MedicineDoseLog.objects.filter(
            user=user,
            date__range=[start_date, today]
        ).values('date').annotate(
            total=Count('id'),
            taken=Count('id', filter=Q(status='Taken')),
            missed=Count('id', filter=Q(status='Missed'))
        )

        # Build activity dictionary
        activity_dict = {}
        for log in dose_logs:
            activity_dict[log['date']] = {
                'total': log['total'],
                'taken': log['taken'],
                'missed': log['missed']
            }

        # Build result list for all days
        activity = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            
            if d in activity_dict:
                stats = activity_dict[d]
                total = stats['total']
                taken = stats['taken']
                
                if total == 0:
                    state = "none"
                elif taken == total:
                    state = "full"
                elif taken > 0:
                    state = "partial"
                else:
                    state = "missed"
            else:
                state = "none"
                taken = 0
                stats = {'total': 0, 'missed': 0}

            activity.append({
                "date": d,
                "state": state,
                "taken": taken,
                "missed": stats.get('missed', 0),
                "count": taken
            })

        return activity
    
    except Exception as e:
        logger.error(f"Error in get_activity_data for user {user.id if user else 'None'}: {str(e)}")
        return []

@login_required
def reminder_view(request):
    try:
        today = date.today()
        weekday = calendar.day_abbr[today.weekday()]
        now_dt = localtime(now())
        now_time = now_dt.time()
        
        medicines = Medicine.objects.filter(
            user=request.user,
            status='active'
        ).prefetch_related('times')
        
        upcoming_meds = []
        completed_meds = []
        missed_meds = []
        
        has_missed = False
        
        for med in medicines:
            freq = (med.frequency_type or "").lower().strip()
            valid_today = False
            if freq == "daily":
                valid_today = True
            elif freq == "weekly" and med.days_of_week:
                days = [d.strip() for d in (med.days_of_week or "").split(",")]
                valid_today = weekday in days
            
            if not valid_today:
                continue
                
            times = med.times.all().order_by('time')
            if not times.exists():
                continue
                
            for mt in times:
                try:
                    status, created = MedicineStatus.objects.get_or_create(
                        medicine_time=mt,
                        date=today,
                        defaults={'is_taken': False, 'is_missed': False}
                    )
                    
                    item_data = {
                        "medicine": med,
                        "times": times,
                        "next_time": mt.time if mt.time >= now_time else None,
                        "medicine_time_id": mt.id,
                        # 30 min alert logic
                        "is_alert": False
                    }
                    
                    if status.is_taken:
                        completed_meds.append(item_data)
                    elif is_missed(mt.time):
                        if not status.is_missed:
                            status.is_missed = True
                            status.save()
                        missed_meds.append(item_data)
                        has_missed = True
                    else:
                        # calculate 30 min difference
                        dt_scheduled = datetime.combine(today, mt.time)
                        now_dt_naive = datetime.combine(today, now_time)
                        time_diff = (dt_scheduled - now_dt_naive).total_seconds() / 60
                        if 0 <= time_diff <= 30:
                            item_data["is_alert"] = True
                        upcoming_meds.append(item_data)
                        
                except Exception as e:
                    logger.error(f"Error processing medicine status for reminder: {e}")
                    continue
                    
        # 9 PM missed logic
        show_9pm_warning = False
        if now_dt.time() >= dt_time(21, 0) and has_missed:
            show_9pm_warning = True
            
        return render(request, "reminder.html", {
            "upcoming_meds": upcoming_meds,
            "completed_meds": completed_meds,
            "missed_meds": missed_meds,
            "show_9pm_warning": show_9pm_warning
        })
    except Exception as e:
        logger.error(f"Error loading reminder view: {e}")
        return render(request, "reminder.html", {
            "upcoming_meds": [],
            "completed_meds": [],
            "missed_meds": [],
            "show_9pm_warning": False
        })

@require_POST
@login_required
def toggle_reminder_setting(request):
    try:
        med_id = request.POST.get('medicine_id')
        is_enabled = request.POST.get('is_enabled') == 'true'
        
        med = get_object_or_404(Medicine, id=med_id, user=request.user)
        med.is_reminder_enabled = is_enabled
        med.save()
        
        return JsonResponse({"success": True, "is_enabled": is_enabled})
    except Exception as e:
        logger.error(f"Error toggling reminder setting: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def quick_call_view(request):
    """
    One-Click Call page — displays emergency contacts with
    tel: call links and a copy-number fallback.
    Reuses the existing EmergencyContact model (no DB changes).
    """
    contacts = EmergencyContact.objects.filter(
        user=request.user
    ).order_by('priority')
    return render(request, 'quick_call.html', {'contacts': contacts})


@login_required
def prescription_reader_view(request):
    """Prescription Reader page — upload a prescription image for OCR processing."""
    try:
        form = PrescriptionUploadForm()
        recent = Prescription.objects.filter(user=request.user).order_by('-created_at')[:5]
        return render(request, 'prescription_reader.html', {
            'form': form,
            'recent_prescriptions': recent,
        })
    except Exception as e:
        logger.error(f"Error rendering prescription reader: {e}")
        return render(request, 'prescription_reader.html', {
            'form': PrescriptionUploadForm(),
            'recent_prescriptions': [],
            'error': 'Unable to load prescription reader',
        })

@login_required
@rate_limit_prescription_scan
@require_http_methods(["POST"])
def prescription_process(request):
    """
    AJAX endpoint — accepts prescription image, runs OCR, matches medicines.
    Production-ready with validation, error handling, and rate limiting.
    """
    try:
        # Validate form
        form = PrescriptionUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            errors = []
            for field, field_errors in form.errors.items():
                errors.extend(field_errors)
            return JsonResponse({
                'success': False,
                'error': 'Invalid form: ' + '; '.join(errors)
            }, status=400)
        
        image_file = form.cleaned_data.get('image')
        
        # Validate image file
        is_valid, error_msg = validate_image_file(image_file)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)
        
        # Create prescription record with transaction safety
        try:
            with transaction.atomic():
                prescription = Prescription.objects.create(
                    user=request.user,
                    image=image_file,
                    extracted_text='',
                )
        except IntegrityError as e:
            logger.error(f"Database integrity error: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to save prescription. Please try again.'
            }, status=500)
        except Exception as e:
            logger.error(f"Error creating prescription: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Unable to save prescription record'
            }, status=500)
        
        # Run OCR with robust error handling
        extracted_text = ''
        ocr_available = False
        ocr_error = None
        
        try:
            import pytesseract
            from PIL import Image
            
            # Auto-detect Tesseract path on Windows
            tesseract_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                os.path.join('C:\\\\Users', os.environ.get('USERNAME', ''), 'AppData', 'Local', 'Programs', 'Tesseract-OCR', 'tesseract.exe')
            ]
            
            tesseract_found = False
            for tp in tesseract_paths:
                if os.path.isfile(tp):
                    pytesseract.pytesseract.tesseract_cmd = tp
                    tesseract_found = True
                    break
            
            if not tesseract_found:
                logger.warning('Tesseract OCR not found on system')
                ocr_available = False
            else:
                try:
                    img = Image.open(prescription.image.path)
                    img.verify()
                    img = Image.open(prescription.image.path)
                    
                    extracted_text = pytesseract.image_to_string(img)
                    
                    if extracted_text and len(extracted_text.strip()) > 0:
                        extracted_text = extracted_text.strip()[:5000]
                        try:
                            prescription.extracted_text = extracted_text
                            prescription.save(update_fields=['extracted_text'])
                            ocr_available = True
                        except Exception as e:
                            logger.error(f"Failed to save OCR text: {e}")
                            ocr_available = False
                    else:
                        logger.info("OCR returned empty text")
                        ocr_available = False
                        
                except (IOError, ValueError) as e:
                    logger.error(f"Image processing error: {e}")
                    ocr_available = False
                    ocr_error = "Could not process image file"
                except Exception as e:
                    logger.error(f"OCR execution error: {e}")
                    ocr_available = False
                    ocr_error = "OCR processing failed"
                    
        except ImportError:
            logger.warning('pytesseract or PIL not installed')
            ocr_available = False
            ocr_error = "OCR module not available"
        except Exception as e:
            logger.error(f'Unexpected OCR error: {e}')
            ocr_available = False
            ocr_error = str(e)[:100]
        
        # Extract and filter medicine names
        try:
            detected_medicines = []
            if extracted_text:
                detected_medicines = _extract_medicine_names(extracted_text)
                detected_medicines = list(set([
                    m for m in detected_medicines if sanitize_medicine_name(m)
                ]))
        except Exception as e:
            logger.error(f"Error extracting medicine names: {e}")
            detected_medicines = []
        
        # Match against user's medicines
        try:
            user_medicines = list(
                Medicine.objects.filter(user=request.user)
                .values_list('name', flat=True)
                .distinct()
            )
            matches = _match_medicines(detected_medicines, user_medicines)
        except Exception as e:
            logger.error(f"Error matching medicines: {e}")
            matches = [{"detected": m, "matched": None, "confidence": 0} for m in detected_medicines]
        
        # Return success response
        response = {
            'success': True,
            'image_url': prescription.image.url if prescription.image else '',
            'prescription_id': prescription.id,
            'extracted_text': extracted_text,
            'ocr_available': ocr_available,
            'detected_medicines': detected_medicines,
            'matches': matches or [],
        }
        
        if ocr_error:
            response['ocr_warning'] = ocr_error
        
        return JsonResponse(response)
        
    except Exception as e:
        logger.error(f'Unexpected error in prescription_process: {e}')
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred. Please try again.'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def prescription_add_medicines(request):
    """
    AJAX endpoint — add medicines from prescription with full validation.
    Production-ready with transaction safety, duplicate prevention, and error handling.
    """
    try:
        import json
        
        # Parse JSON request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON format'
            }, status=400)
        
        # Validate medicines list
        medicines_to_add = data.get('medicines', [])
        is_valid, cleaned_meds, error_msg = validate_medicine_list(medicines_to_add)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)
        
        added_count = 0
        skipped_count = 0
        skipped_names = []
        errors = {}
        
        # Deduplicate input
        cleaned_meds = list(set(cleaned_meds))
        
        # Check for duplicates with existing user medicines
        existing_meds = set(
            Medicine.objects.filter(user=request.user)
            .values_list('name', flat=True)
            .distinct()
        )
        
        # Process each medicine with transaction safety
        for med_name in cleaned_meds:
            med_lower = med_name.lower()
            exists_case_insensitive = any(
                m.lower() == med_lower for m in existing_meds
            )
            
            if exists_case_insensitive:
                skipped_count += 1
                skipped_names.append(med_name)
                continue
            
            try:
                # Create medicine and related records in atomic transaction
                with transaction.atomic():
                    medicine = Medicine.objects.create(
                        user=request.user,
                        name=med_name,
                        frequency_type='daily',
                        dose_per_day=1,
                        food_timing='After Food',
                        status='active',
                        is_reminder_enabled=True,
                        notes='Added from prescription',
                        drug_classification=classify_medicine(med_name)
                    )
                    
                    med_time = MedicineTime.objects.create(
                        medicine=medicine,
                        time=dt_time(8, 0)
                    )
                    
                    today = date.today()
                    MedicineStatus.objects.get_or_create(
                        medicine_time=med_time,
                        date=today,
                        defaults={'is_taken': False, 'is_missed': False}
                    )
                    
                    added_count += 1
                    existing_meds.add(med_name)
                    
            except IntegrityError as e:
                logger.warning(f"Duplicate medicine during insertion: {med_name} - {e}")
                skipped_count += 1
                skipped_names.append(med_name)
                errors[med_name] = "Already exists (race condition)"
                
            except ValidationError as e:
                logger.error(f"Validation error for {med_name}: {e}")
                skipped_count += 1
                skipped_names.append(med_name)
                errors[med_name] = "Invalid medicine data"
                
            except Exception as e:
                logger.error(f"Error creating medicine '{med_name}': {e}")
                skipped_count += 1
                skipped_names.append(med_name)
                errors[med_name] = str(e)[:100]
        
        # Build response
        response = {
            'success': True,
            'added_count': added_count,
            'skipped_count': skipped_count,
            'skipped_names': skipped_names,
            'message': f'Added {added_count} medicine(s). {skipped_count} skipped.'
        }
        
        if errors:
            response['errors'] = errors
        
        return JsonResponse(response)
        
    except Exception as e:
        logger.error(f'Unexpected error in prescription_add_medicines: {e}')
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred'
        }, status=500)


def _extract_medicine_names(text):
    """Extract candidate medicine names from OCR text with validation."""
    if not text or not isinstance(text, str):
        return []
    
    text = text[:50000]  # Limit processing
    
    rx_keywords = {
        'tab', 'tablet', 'cap', 'capsule', 'syrup', 'inj',
        'injection', 'ointment', 'drops', 'cream', 'gel',
        'suspension', 'mg', 'ml', 'mcg', 'units', 'gm',
        'strength', 'dose'
    }
    
    noise_words = {
        'the', 'and', 'for', 'with', 'take', 'after', 'before',
        'food', 'daily', 'once', 'twice', 'morning', 'evening',
        'night', 'days', 'weeks', 'patient', 'name', 'date',
        'doctor', 'hospital', 'prescription', 'pharmacy', 'address',
        'phone', 'age', 'sex', 'male', 'female', 'diagnosis',
        'time', 'hour', 'day', 'week', 'month', 'year', 'dr',
        'rx', 'sig', 'prn', 'bid', 'tid', 'qid', 'hs', 'od'
    }
    
    try:
        words = re.findall(r'[A-Za-z][A-Za-z0-9]{2,}', text)
        if not words:
            return []
        
        candidates = set()
        
        for i, word in enumerate(words):
            word_lower = word.lower()
            if word_lower in noise_words:
                continue
            if i > 0 and words[i - 1].lower() in rx_keywords:
                candidates.add(word)
                continue
            if word[0].isupper() and len(word) >= 4:
                candidates.add(word)
                continue
            if i + 1 < len(words) and re.match(r'^\\d+', words[i + 1]):
                candidates.add(word)
                continue
        
        return sorted(list(set(candidates)))[:100]
        
    except Exception as e:
        logger.error(f"Error in _extract_medicine_names: {e}")
        return []


def _match_medicines(detected, user_medicines):
    """Fuzzy-match detected names against user's medicine database."""
    if not detected or not user_medicines:
        return [{"detected": d, "matched": None, "confidence": 0} for d in detected]
    
    results = []
    
    try:
        for name in detected:
            if not name or not isinstance(name, str):
                continue
            
            best_match = None
            best_ratio = 0.0
            name_lower = name.lower().strip()
            
            # Quick pass: Check for exact substring matches
            for db_name in user_medicines:
                db_lower = db_name.lower().strip()
                
                if name_lower == db_lower:
                    best_match = db_name
                    best_ratio = 1.0
                    break
                
                if (name_lower in db_lower or db_lower in name_lower):
                    ratio = len(min(name_lower, db_lower)) / len(max(name_lower, db_lower))
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = db_name
            
            # If no substring match, try fuzzy matching
            if best_ratio < 0.9:
                for db_name in user_medicines:
                    try:
                        ratio = difflib.SequenceMatcher(
                            None, name_lower, db_name.lower()
                        ).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_match = db_name
                    except Exception as e:
                        logger.warning(f"Error comparing '{name}' with '{db_name}': {e}")
                        continue
            
            confidence = int(best_ratio * 100) if best_ratio >= 0.7 else 0
            
            results.append({
                "detected": name,
                "matched": best_match if confidence > 0 else None,
                "confidence": confidence
            })
    
    except Exception as e:
        logger.error(f"Error in _match_medicines: {e}")
        return [{"detected": d, "matched": None, "confidence": 0} for d in detected]
    
    return results


@login_required
def nearby_pharmacy_view(request):
    """
    Nearby Pharmacy page — uses browser geolocation and OpenStreetMap (Overpass API)
    to find pharmacies near the user's current location.
    """
    return render(request, 'nearby_pharmacy.html')
