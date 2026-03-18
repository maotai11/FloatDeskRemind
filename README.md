# FloatDesk Remind

Windows 桌面離線常駐提醒工具。浮動小視窗永遠顯示今日/明日/後日待辦，搭配主控台管理介面。

---

## 快速啟動（已打包 EXE）

1. 下載 `FloatDeskRemind.exe`
2. 雙擊執行
3. 系統匣出現圖示，浮動視窗自動顯示於螢幕右上角

> **不需要安裝 Python 或任何依賴。**
> 資料儲存於 `%APPDATA%\FloatDeskRemind\`（自動建立）。

### 系統需求
- Windows 10 / 11（x64）
- 無需網路連線

---

## 開發模式執行

### 安裝依賴

```bat
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 啟動

```bat
scripts\run_dev.bat
```
或直接：
```bat
python src/main.py
```

### 執行測試

```bat
scripts\run_tests.bat
```
或：
```bat
python -m pytest tests/ -v
```

---

## 打包 EXE

需先安裝 [PyInstaller](https://pyinstaller.org/)：

```bat
pip install pyinstaller
scripts\build.bat
```

輸出：`dist\FloatDeskRemind.exe`（自包含，約 60–130MB）

---

## 資料位置

| 類型 | 路徑 |
|------|------|
| 資料庫 | `%APPDATA%\FloatDeskRemind\floatdesk.db` |
| 記錄檔 | `%APPDATA%\FloatDeskRemind\logs\floatdesk.log` |

---

## 功能（v0.1）

- 任務 CRUD（新增、編輯、刪除、完成）
- 父子任務（最多一層）+ 完成連動（場景 A-E）
- 浮動視窗（always-on-top，可拖曳，透明度可調，位置記憶）
- 主控台三欄介面（視圖切換 / 清單 / 編輯面板）
- 系統匣圖示 + 右鍵選單
- 開機自動啟動（設定內切換）
- 鍵盤快捷鍵：`Ctrl+N` 新增、`Ctrl+F` 搜尋、`Delete` 刪除、`Space` 切換完成

---

## 授權

MIT License
