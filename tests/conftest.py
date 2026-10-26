"""Keep Qt alive while test windows and graphics scenes are disposed normally."""
import gc
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def _flush_deferred_deletes(app):
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(scope='session', autouse=True)
def _qt_test_runtime(request):
    if not any('qt_app' in item.fixturenames for item in request.session.items):
        yield None
        return
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    previous = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    yield app
    _flush_deferred_deletes(app)
    gc.collect()
    _flush_deferred_deletes(app)
    app.setQuitOnLastWindowClosed(previous)


@pytest.fixture(autouse=True)
def _dispose_qt_test_windows(request, _qt_test_runtime):
    yield
    app = _qt_test_runtime
    if app is None or 'qt_app' not in request.fixturenames:
        return
    from PySide6.QtWidgets import QDialog, QMainWindow
    import pyqtgraph as pg
    from shiboken6 import isValid
    windows = [widget for widget in app.topLevelWidgets()
               if isinstance(widget, (QMainWindow, QDialog)) and isValid(widget)]
    for window in windows:
        window.close()
        # PlotWidget.close() explicitly removes its option widgets before
        # clearing the scene. Parent-window close alone only hides the plots.
        for plot in window.findChildren(pg.PlotWidget):
            if isValid(plot):
                if plot.getPlotItem() is not None:
                    plot.close()
                plot.deleteLater()
        window.deleteLater()
    _flush_deferred_deletes(app)
    del windows
    gc.collect()
    _flush_deferred_deletes(app)
