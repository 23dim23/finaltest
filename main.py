import subprocess
import time

# Список скриптов для запуска
scripts = ["bot.py", "parser.py"]

processes = []

for script in scripts:
    print(f"🚀 Запуск {script}...")
    # Запускаем каждый скрипт как отдельный процесс
    p = subprocess.Popen(["python", script])
    processes.append(p)

print("✅ Все системы запущены!")

try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    for p in processes:
        p.terminate()