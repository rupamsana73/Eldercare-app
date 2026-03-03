from django.contrib import admin
from .models import EmergencyContact, Medicine, UserProfile, MedicineDoseLog


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'date_of_birth', 'updated_at')
    search_fields = ('user__username', 'user__email', 'phone_number')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Profile Details', {
            'fields': ('profile_image', 'phone_number', 'date_of_birth', 'emergency_note')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class MedicineDoseLogAdmin(admin.ModelAdmin):
    """Admin interface for MedicineDoseLog model."""
    list_display = ('medicine', 'user', 'date', 'scheduled_time', 'status', 'marked_at')
    list_filter = ('status', 'date', 'medicine__user')
    search_fields = ('medicine__name', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Dose Information', {
            'fields': ('user', 'medicine', 'date', 'scheduled_time', 'status')
        }),
        ('Marking', {
            'fields': ('marked_at',),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'date'


admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(EmergencyContact)
admin.site.register(Medicine)
admin.site.register(MedicineDoseLog, MedicineDoseLogAdmin)


