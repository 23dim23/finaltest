import subprocess
import time
import sys

scripts = ["bot.py", "parser.py"]

def run_script(script_name):
    print(f"🚀 Запуск {script_name}...")
    return subprocess.Popen([sys.executable, script_name])

processes = {script: run_script(script) for script in scripts}

try:
    while True:
        for script, process in processes.items():
            # Если процесс завершился, значит он упал
            if process.poll() is not None:
                print(f"⚠️ {script} упал (код {process.returncode}). Перезапуск...")
                time.sleep(5)
                processes[script] = run_script(script)
        time.sleep(10)
except KeyboardInterrupt:
    for p in processes.values():
        p.terminate()