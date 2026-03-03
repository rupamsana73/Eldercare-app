#!/usr/bin/env python
"""
Django Smart Dashboard - Quick Operations Guide
Common commands for running and debugging the application.
"""

import subprocess
import sys
import os

class Colors:
    """ANSI color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{text}{Colors.END}\n")

def print_section(text):
    print(f"{Colors.BLUE}→ {text}{Colors.END}")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def run_command(cmd, description):
    """Run a shell command and handle output"""
    print(f"{Colors.CYAN}{description}...{Colors.END}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print_success(description)
            if result.stdout:
                print(f"  {result.stdout[:200]}")
        else:
            print_error(f"{description} failed")
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}")
        return result.returncode == 0
    except Exception as e:
        print_error(f"{description}: {str(e)}")
        return False

# Menu system
def show_menu():
    print_header("Django Smart Dashboard - Quick Operations")
    print(f"""
{Colors.BOLD}Development & Testing:{Colors.END}
  1. Run development server
  2. Run verification tests
  3. Check system health
  4. View error logs

{Colors.BOLD}Database Operations:{Colors.END}
  5. Create database backup
  6. Restore from backup
  7. Run migrations
  8. Create superuser

{Colors.BOLD}Code Quality:{Colors.END}
  9. Check Python syntax
  10. Run Django checks
  11. View database query plan

{Colors.BOLD}Monitoring:{Colors.END}
  12. Tail error logs
  13. Check log file size
  14. Clear old logs

{Colors.BOLD}Maintenance:{Colors.END}
  15. Clean up cache files
  16. Reset test data
  17. Update dependencies

{Colors.BOLD}Exit:{Colors.END}
  0. Exit

{Colors.BOLD}Enter your choice:{Colors.END}""")

def menu_run_server():
    print_section("Starting Django development server")
    print("Access at: http://localhost:8000")
    print("Admin at: http://localhost:8000/admin")
    os.system("python manage.py runserver")

def menu_verify_tests():
    print_section("Running verification tests")
    os.system("python verify_audit.py")

def menu_health_check():
    print_section("Running system checks")
    run_command("python manage.py check", "Django system check")
    run_command("python manage.py migrate --plan", "Migration plan check")
    run_command("python -c \"import django; django.setup(); from django.conf import settings; print(f'Database: {settings.DATABASES}')\"", "Database configuration")

def menu_view_logs():
    print_section("Recent errors in logs/django.log")
    if os.path.exists('logs/django.log'):
        os.system("tail -n 20 logs/django.log")
    else:
        print_warning("No logs directory yet")

def menu_backup_db():
    print_section("Creating database backup")
    run_command("copy db.sqlite3 db.sqlite3.backup.%date:~-4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%", "Database backup")

def menu_restore_db():
    print_section("Restoring from backup")
    backups = [f for f in os.listdir('.') if f.startswith('db.sqlite3.backup')]
    if not backups:
        print_error("No backup files found")
        return
    print("Available backups:")
    for i, backup in enumerate(backups, 1):
        print(f"  {i}. {backup}")
    try:
        choice = int(input("Select backup to restore (number): "))
        if 1 <= choice <= len(backups):
            backup_file = backups[choice-1]
            run_command(f"copy {backup_file} db.sqlite3", f"Restoring {backup_file}")
        else:
            print_error("Invalid choice")
    except ValueError:
        print_error("Invalid input")

def menu_run_migrations():
    print_section("Running database migrations")
    run_command("python manage.py migrate", "Apply migrations")

def menu_create_superuser():
    print_section("Creating superuser")
    print("Note: Choose a strong password")
    os.system("python manage.py createsuperuser")

def menu_check_syntax():
    print_section("Checking Python syntax")
    files = [
        'accounts/views.py',
        'accounts/models.py',
        'accounts/forms.py',
        'eldercare_project/settings.py'
    ]
    for file in files:
        if os.path.exists(file):
            run_command(f"python -m py_compile {file}", f"Syntax check: {file}")

def menu_django_checks():
    print_section("Running comprehensive Django checks")
    run_command("python manage.py check --deploy", "Deployment checks")

def menu_query_plan():
    print_section("Database query optimization plan")
    run_command("python manage.py sqlmigrate accounts 0001", "View initial schema")

def menu_tail_logs():
    print_section("Monitoring error logs (press Ctrl+C to stop)")
    if os.path.exists('logs/django.log'):
        os.system("powershell -Command \"Get-Content logs\\django.log -Wait -Tail 20\"")
    else:
        print_warning("No logs directory yet. Run the server first.")

def menu_log_size():
    print_section("Log file statistics")
    if os.path.exists('logs/django.log'):
        size = os.path.getsize('logs/django.log')
        print_success(f"Log file size: {size/1024:.2f} KB")
        if size > 10*1024*1024:  # 10MB
            print_warning("Consider rotating logs")
    else:
        print_warning("No logs directory yet")

def menu_clear_logs():
    print_section("Clearing old logs")
    if os.path.exists('logs/django.log'):
        os.remove('logs/django.log')
        print_success("Logs cleared")
    else:
        print_warning("No logs to clear")

def menu_cleanup_cache():
    print_section("Cleaning up cache files")
    run_command("dir /s __pycache__", "Find cache directories")
    print("To remove cache:")
    print("  powershell: Get-ChildItem -Path . -Directory -Name __pycache__ | Remove-Item -Recurse")

def menu_reset_data():
    print_section("Resetting test data")
    print(f"{Colors.RED}WARNING: This will delete all data!{Colors.END}")
    confirm = input("Type 'reset' to confirm: ")
    if confirm == 'reset':
        run_command("python manage.py flush --noinput", "Clear all data")
        run_command("python manage.py migrate", "Recreate schema")
        print_success("Database reset complete")
    else:
        print_warning("Reset cancelled")

def menu_update_deps():
    print_section("Updating dependencies")
    run_command("pip install --upgrade -r requirements.txt", "Update packages")
    run_command("pip freeze > requirements.txt", "Update requirements.txt")

# Main loop
if __name__ == '__main__':
    while True:
        try:
            show_menu()
            choice = input(f"\n{Colors.BOLD}Your choice: {Colors.END}")
            
            if choice == '1':
                menu_run_server()
            elif choice == '2':
                menu_verify_tests()
            elif choice == '3':
                menu_health_check()
            elif choice == '4':
                menu_view_logs()
            elif choice == '5':
                menu_backup_db()
            elif choice == '6':
                menu_restore_db()
            elif choice == '7':
                menu_run_migrations()
            elif choice == '8':
                menu_create_superuser()
            elif choice == '9':
                menu_check_syntax()
            elif choice == '10':
                menu_django_checks()
            elif choice == '11':
                menu_query_plan()
            elif choice == '12':
                menu_tail_logs()
            elif choice == '13':
                menu_log_size()
            elif choice == '14':
                menu_clear_logs()
            elif choice == '15':
                menu_cleanup_cache()
            elif choice == '16':
                menu_reset_data()
            elif choice == '17':
                menu_update_deps()
            elif choice == '0':
                print_success("Goodbye!")
                sys.exit(0)
            else:
                print_error("Invalid choice")
                
        except KeyboardInterrupt:
            print_success("\nOperation cancelled")
        except Exception as e:
            print_error(f"Error: {str(e)}")
