import asyncio
import tkinter as tk
import json
from datetime import datetime
from pymodbus.client import AsyncModbusTcpClient

CONFIG_FILE = "config.json"

class ModbusUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Modbus 데이터 뷰어")

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.rows = len(self.config)
        self.labels = []

        header_font = ("Arial", 12, "bold")
        value_font = ("Arial", 12)

        # 테이블 헤더
        tk.Label(root, text="신호명", font=header_font).grid(row=0, column=0, padx=10, pady=5)
        tk.Label(root, text="값", font=header_font).grid(row=0, column=1, padx=10, pady=5)
        tk.Label(root, text="단위", font=header_font).grid(row=0, column=2, padx=10, pady=5)

        # 신호 행 생성
        for i, signal in enumerate(self.config, start=1):
            tk.Label(root, text=signal["name"], font=value_font).grid(row=i, column=0, padx=10, pady=5)
            val_label = tk.Label(root, text="...", font=value_font)
            val_label.grid(row=i, column=1, padx=10, pady=5)
            self.labels.append(val_label)
            tk.Label(root, text=signal["unit"], font=value_font).grid(row=i, column=2, padx=10, pady=5)

        # 최종 갱신 시간 라벨
        self.time_label = tk.Label(root, text="", font=("Arial", 10, "italic"))
        self.time_label.grid(row=self.rows + 1, column=0, columnspan=3, pady=(10, 0))

        self.client = AsyncModbusTcpClient("localhost", port=5020)

    async def update_label(self):
        await self.client.connect()
        while True:
            try:
                for i, signal in enumerate(self.config):
                    addr = signal["address"]
                    length = signal.get("length", 1)
                    result = await self.client.read_holding_registers(addr, length)
                    if result.isError():
                        self.labels[i].config(text="에러")
                    else:
                        value = result.registers
                        if length == 2:
                            value = (value[0] << 16) + value[1]
                        else:
                            value = value[0]

                        if signal["unit"] == "bin":
                            value = bin(value)

                        self.labels[i].config(text=str(value))

                # 갱신 시간 표시
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.time_label.config(text=f"최종 갱신 시간: {now}")

            except Exception as e:
                for label in self.labels:
                    label.config(text=f"오류: {e}")
            await asyncio.sleep(2)

def start_async_loop(ui: ModbusUI):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ui.update_label())

if __name__ == "__main__":
    root = tk.Tk()
    ui = ModbusUI(root)

    import threading
    threading.Thread(target=start_async_loop, args=(ui,), daemon=True).start()

    root.mainloop()
