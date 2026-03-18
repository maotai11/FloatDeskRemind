"""
FloatDesk Remind — Entry Point
Single-instance lock → QApplication → AppController
"""
import sys
import os

# Add project root to path so "src.*" imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from src.core.single_instance import acquire_lock, release_lock
from src.core.logger import logger


def main() -> int:
    if not acquire_lock():
        # Already running — show a quick tray notification or just exit
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.information(
            None, 'FloatDesk Remind',
            'FloatDesk Remind 已在執行中。\n請查看系統匣圖示。'
        )
        return 0

    try:
        app = QApplication(sys.argv)
        app.setApplicationName('FloatDesk Remind')
        app.setOrganizationName('FloatDesk')
        app.setQuitOnLastWindowClosed(False)  # Keep running with tray

        # Load QSS
        _apply_stylesheet(app)

        from src.app import AppController
        controller = AppController()
        controller.start()

        ret = app.exec()
        return ret
    except Exception as e:
        logger.exception(f'Fatal error: {e}')
        try:
            _app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                'FloatDesk Remind — 啟動失敗',
                f'程式發生錯誤，無法啟動：\n\n{e}\n\n'
                f'請查閱記錄檔以取得詳細資訊。'
            )
        except Exception:
            pass
        return 1
    finally:
        release_lock()


def _apply_stylesheet(app: QApplication) -> None:
    import sys
    from pathlib import Path
    from src.core.paths import QSS_PATH

    candidates = [
        QSS_PATH,  # resolved via _MEIPASS in frozen, or project root in dev
    ]
    # Extra dev fallback: running directly as 'python src/main.py' from project root
    candidates.append(Path(__file__).parent.parent / 'src' / 'ui' / 'styles' / 'main.qss')

    for path in candidates:
        if path.exists():
            try:
                app.setStyleSheet(path.read_text(encoding='utf-8'))
                logger.info(f'QSS loaded from {path}')
                return
            except Exception as e:
                logger.warning(f'Failed to load QSS: {e}')
    logger.warning('QSS file not found, using default style')


if __name__ == '__main__':
    sys.exit(main())
