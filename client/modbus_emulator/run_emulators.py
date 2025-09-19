# run_emulators.py
import time
import multiprocessing
from modbus_emulator_instance import run_emulator

def _print_status(tag: str, procs):
    alive = [(p.pid, p.is_alive(), p.exitcode) for p in procs]
    print(f"[상태] {tag}: " + " | ".join([f"pid={pid}, alive={alv}, exit={code}" for pid, alv, code in alive]))

if __name__ == "__main__":
    # 두 포트를 각각 별도 프로세스로 기동
    p1 = multiprocessing.Process(target=run_emulator, args=(5021, "온도센서_1호기"))  # 온도/압력/상태/누적
    p2 = multiprocessing.Process(target=run_emulator, args=(5022, "전력센서_2호기"))  # 전류/전압

    p1.start()
    p2.start()
    print("[메인] TCP 에뮬레이터(5021/5022) 실행 요청 완료.")
    time.sleep(0.8)  # 포트 바인딩 대기
    _print_status("기동 직후", [p1, p2])

    try:
        p1.join()
        p2.join()
    finally:
        _print_status("종료 시점", [p1, p2])
