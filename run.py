"""
SmartLDS 一键启动 — Flask 后端 + Vue3 前端
用法: 在项目根目录执行  python run.py
"""
import subprocess, sys, os, time, signal

ROOT = os.path.dirname(os.path.abspath(__file__))

def kill_port(port):
    """清理占用端口的进程 (Windows)"""
    if sys.platform != "win32": return
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port} "', shell=True, text=True
        )
        for line in out.strip().split("\n"):
            parts = line.strip().split()
            if parts and "LISTENING" in line:
                pid = parts[-1]
                subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def main():
    # 清理旧 Vite 进程
    kill_port(8080)

    venv_py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        print("错误: 找不到虚拟环境 .venv", file=sys.stderr)
        sys.exit(1)

    print(" SmartLDS 启动中...")
    print("   Flask  :5000  |  Vue3 :8080\n")

    # 启动后端
    env = os.environ.copy()
    env["FLASK_DEBUG"] = "0"
    backend = subprocess.Popen(
        [venv_py, "app.py"],
        cwd=os.path.join(ROOT, "backend"),
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # 给后端几秒加载 PaddleOCR 模型
    time.sleep(6)

    # 启动前端
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "--port", "8080"],
        cwd=os.path.join(ROOT, "frontend"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    time.sleep(3)
    print("  后端: http://localhost:5000/api/health")
    print("  前端: http://localhost:8080")
    print("  Ctrl+C 停止\n")

    # 保持运行
    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n正在停止...")
        for p in [backend, frontend]:
            try: p.terminate()
            except: pass
        print("已停止")

if __name__ == "__main__":
    main()
