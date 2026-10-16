# ALMURADI SOFT ERP mode selector
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run_bat(name):
    subprocess.Popen(['cmd', '/c', 'start', '', str(ROOT / name)], cwd=str(ROOT), shell=False)

def main():
    print('=' * 58)
    print('       ALMURADI SOFT ERP | مشغّل النظام')
    print('=' * 58)
    print('1) تشغيل تطبيق سطح المكتب (نافذة مستقلة)')
    print('2) تشغيل موقع الويب محليًا في المتصفح')
    print('3) فتح إرشادات نشر الموقع برابط عام')
    print('0) خروج')
    choice = input('\nاختر رقم التشغيل: ').strip()
    if choice == '1': run_bat('RUN_DESKTOP.bat')
    elif choice == '2': run_bat('RUN_SYSTEM.bat')
    elif choice == '3':
        p = ROOT / 'DEPLOY_WEB_AR.txt'
        if sys.platform == 'win32': os.startfile(str(p))
        else: print(p.read_text(encoding='utf-8'))
    elif choice == '0': return
    else: print('اختيار غير صحيح.')

if __name__ == '__main__': main()
